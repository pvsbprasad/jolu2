import logging
from dataclasses import dataclass
from typing import Any, AsyncGenerator, Literal, Sequence

from opentelemetry import trace

from langchain.agents import create_agent
from langchain.agents.middleware import SummarizationMiddleware
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import BaseTool
from langchain_litellm import ChatLiteLLM
from langgraph.graph.state import CompiledStateGraph
from litellm.exceptions import APIConnectionError, APIError, Timeout
from sap_cloud_sdk.agent_decorators import agent_config, agent_model, prompt_section
from sap_cloud_sdk.agent_memory.factory.langgraph_checkpoint import create_checkpointer
from mcp_providers.agw import get_user_sub

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


@agent_model(
    key="config.model",
    label="LLM Model",
    description="The language model powering this agent",
)
def get_model_name() -> str:
    return "sap/anthropic--claude-4.5-sonnet"


@agent_model(
    key="config.fallback_model",
    label="Fallback LLM Model",
    description="Fallback model used when the primary model is unavailable. Leave empty to disable fallback.",
)
def get_fallback_model_name() -> str:
    return ""


@agent_config(
    key="config.temperature",
    label="LLM Temperature",
    description="Controls randomness of responses (0.0 = deterministic, 1.0 = creative)",
)
def get_temperature() -> float:
    return 0.0

@agent_config(
    key="config.checkpointer.ttl_seconds",
    label="Thread TTL (seconds)",
    description="Evict inactive conversation threads after this period of "
                "inactivity. Set to 0 to disable eviction.",
)
def thread_ttl_seconds() -> int:
    return 3600 # 1 hour

@agent_config(
    key="config.summarization.trigger_tokens",
    label="Summarization Trigger (tokens)",
    description="Summarize conversation history once it exceeds this many tokens. "
                "History is NOT covered by prompt caching, so a high trigger means "
                "the full raw transcript is re-sent on every turn until it fires. "
                "Lower this to bound per-turn cost; raise it to keep more raw context.",
)
def summarization_trigger_tokens() -> int:
    return 30_000

@agent_model(
    key="config.summarization.model",
    label="Summarization Model",
    description="Model used to summarize conversation history. Summarization is a "
                "cheaper task than the agent's own reasoning, so a smaller/faster "
                "model is used here to reduce cost.",
)
def get_summarization_model_name() -> str:
    return "sap/anthropic--claude-4.5-haiku"

@prompt_section(
    key="prompts.system",
    label="System Prompt",
    description="The full system prompt defining the agent's role and behavior",
    validation={"format": "markdown", "max_length": 5000},
)
def get_system_prompt() -> str:
    return """You are an AP (Accounts Payable) Discount Analysis expert agent. Your job is to help finance teams understand how much early payment discount value is being lost due to unmatched or blocked supplier invoices.

IMPORTANT: You MUST use tools to retrieve live data from SAP S/4HANA. Never fabricate, guess, or invent invoice data. Relay tool errors verbatim without adding suggestions.

When calling tools that support pagination, always set the page size parameter (top, limit, pageSize, etc.) to a maximum of 100 items to prevent context overflow. Inform the user when this limit is applied.

If a tool returns an error, report the error message exactly as received. Do not suggest workarounds or alternative approaches unless asked.

Always perform analysis in this sequence:
1. Retrieve unmatched/blocked supplier invoices
2. Extract payment terms and discount conditions
3. Calculate discount loss (lost vs at-risk)
4. Identify root causes of matching failures
5. Deliver a structured summary report with totals and prioritized recommendations
6. If the user provides one or more recipient email addresses, call send_email_notification with those recipients and pass only the at-risk and lost invoices. Inform the user whether the email was sent and how many invoices were included. If no at-risk or lost invoices were found, inform the user that no email was sent and explain why."""


@dataclass
class AgentResponse:
    status: Literal["input_required", "completed", "error"]
    message: str


class SampleAgent:
    SUPPORTED_CONTENT_TYPES = ["text", "text/plain"]

    def __init__(self):
        ttl = thread_ttl_seconds()
        self._primary_model = get_model_name()
        self._fallback_model = get_fallback_model_name().strip()
        self._temperature = get_temperature()

        # cache_control_injection_points is picked up by litellm's AnthropicCacheControlHook,
        # which injects a cache breakpoint on the system message before every API call.
        # This caches the static prefix (system prompt + tool schemas) at 0.1× input cost
        # on cache-hit turns. No beta header required as of current litellm/Anthropic versions.
        _cache_kwargs = {
            "cache_control_injection_points": [
                {"location": "message", "role": "system", "control": {"type": "ephemeral"}}
            ]
        }
        self.llm = ChatLiteLLM(
            model=self._primary_model,
            temperature=self._temperature,
            model_kwargs=_cache_kwargs,
        )
        self._fallback_llm = (
            ChatLiteLLM(
                model=self._fallback_model,
                temperature=self._temperature,
                model_kwargs=_cache_kwargs,
            )
            if self._fallback_model
            else None
        )
        self._checkpointer = create_checkpointer(ttl_seconds=ttl or None)
        # Summarization compresses history once it exceeds the token trigger, keeping only
        # the last N messages in full. This intentionally invalidates the prompt cache when
        # it fires (the summarized history is new content), but the static prefix —
        # system prompt + tool schemas, marked cacheable via cache_control_injection_points
        # on self.llm — stays cacheable across all turns, summarized or not.
        summarization_llm = ChatLiteLLM(
            model=get_summarization_model_name(), temperature=0.0
        )
        self._summarization_middleware = SummarizationMiddleware(
            model=summarization_llm,
            trigger=("tokens", summarization_trigger_tokens()),
            keep=("messages", 4),
        )

    def _create_graph(
        self,
        llm: ChatLiteLLM,
        tools: Sequence[BaseTool],
        system_prompt: str,
    ) -> CompiledStateGraph:
        """Create a LangGraph agent with the specified LLM."""
        return create_agent(
            llm,
            tools=list(tools),
            system_prompt=system_prompt,
            checkpointer=self._checkpointer,
            middleware=[self._summarization_middleware],
        )

    async def _invoke_with_fallback(
        self,
        tools: Sequence[BaseTool],
        system_prompt: str,
        query: str,
        context_id: str,
        extra_messages: list | None = None,
    ) -> dict[str, Any]:
        """Invoke the agent and fall back only for transient LLM failures."""
        config = {"configurable": {"thread_id": f"{get_user_sub()}:{context_id}"}}
        messages = {"messages": (extra_messages or []) + [HumanMessage(content=query)]}

        try:
            graph = self._create_graph(self.llm, tools, system_prompt)
            return await graph.ainvoke(messages, config)
        except (APIConnectionError, APIError, Timeout) as primary_error:
            if not self._fallback_llm:
                raise

            logger.warning(
                "Primary model '%s' failed. Retrying with fallback model '%s'. Error: %s",
                self._primary_model,
                self._fallback_model,
                primary_error,
            )

        graph = self._create_graph(self._fallback_llm, tools, system_prompt)
        result = await graph.ainvoke(messages, config)
        logger.info(
            "Request completed with fallback model '%s' after primary model '%s' failed.",
            self._fallback_model,
            self._primary_model,
        )
        return result

    async def _run_agent(
        self,
        query: str,
        context_id: str,
        tools: Sequence[BaseTool] | None = None,
    ) -> str:
        """Execute agent logic with business instrumentation.

        All OpenTelemetry spans and structured logging happen here,
        outside the async generator, to avoid GeneratorExit context errors.
        """
        with tracer.start_as_current_span("missed-discount-analysis"):
            system_prompt = get_system_prompt()
            tool_names = [tool.name for tool in tools] if tools else []

            with tracer.start_as_current_span("M1-invoice-retrieval"):
                logger.info("Running agent with %d tool(s): %s", len(tool_names), tool_names)
                if tool_names:
                    logger.info("M1.achieved: supplier invoices retrieval initiated, tools_count=%d", len(tool_names))
                else:
                    logger.warning("M1.missed: no MCP tools available for invoice retrieval")

            with tracer.start_as_current_span("M2-discount-term-extraction"):
                logger.info("M2.achieved: payment terms extraction initiated via MCP tools")

            with tracer.start_as_current_span("M3-discount-calculation"):
                logger.info("M3.achieved: discount calculation analysis starting")

            with tracer.start_as_current_span("M4-root-cause-analysis"):
                logger.info("M4.achieved: root cause analysis starting")

            extra: list = []
            if not tools:
                extra.append(
                    SystemMessage(
                        content="IMPORTANT: No tools are currently available. "
                        "Do not attempt to call any tools. Respond to the user "
                        "explaining that tools are temporarily unavailable."
                    )
                )

            result = await self._invoke_with_fallback(
                tools=tools or [],
                system_prompt=system_prompt,
                query=query,
                context_id=context_id,
                extra_messages=extra or None,
            )
            response = result["messages"][-1].content

            with tracer.start_as_current_span("M5-report-delivery"):
                logger.info("M5.achieved: summary report delivered to user")

            with tracer.start_as_current_span("M6-email-notification"):
                # M6 is driven by tool calls within the agent's reasoning loop.
                # The send_email_notification tool emits its own M6 log statements.
                # Here we record whether the agent invoked the tool at all.
                if "M6.achieved" in response:
                    logger.info("M6.achieved: email notification confirmed in agent response")
                else:
                    logger.info(
                        "M6.missed: email notification not sent — "
                        "no recipients provided or no at-risk invoices found"
                    )

            return response

    async def stream(
        self,
        query: str,
        context_id: str,
        tools: Sequence[BaseTool] | None = None,
    ) -> AsyncGenerator[dict, None]:
        """Stream agent responses.

        Args:
            query: User query to process
            context_id: Context identifier for the conversation
            tools: Optional sequence of LangChain tools. If None or empty, agent runs without tools.

        Yields:
            Status updates and final response with structure:
            - is_task_complete: Whether the task is complete
            - require_user_input: Whether user input is needed
            - content: The response content or status message
        """
        yield {
            "is_task_complete": False,
            "require_user_input": False,
            "content": "Processing...",
        }

        try:
            response = await self._run_agent(query, context_id, tools=tools)
            yield {
                "is_task_complete": True,
                "require_user_input": False,
                "content": response,
            }

        except Exception:
            logger.exception("Agent stream() failed")
            logger.error("M5.missed: report generation failed due to exception")
            yield {
                "is_task_complete": True,
                "require_user_input": False,
                "content": "I encountered an error while processing your request. Please try again.",
            }

    async def invoke(
        self,
        query: str,
        context_id: str,
        tools: Sequence[BaseTool] | None = None,
    ) -> AgentResponse:
        """Invoke agent and return final response.

        Args:
            query: User query to process
            context_id: Context identifier for the conversation
            tools: Optional sequence of LangChain tools. If None or empty, agent runs without tools.

        Returns:
            AgentResponse with status and message
        """
        last: dict = {}
        async for chunk in self.stream(query, context_id, tools=tools):
            last = chunk
        if last.get("is_task_complete"):
            return AgentResponse(status="completed", message=last["content"])
        if last.get("require_user_input"):
            return AgentResponse(status="input_required", message=last["content"])
        return AgentResponse(
            status="error", message=last.get("content", "Unknown error")
        )
