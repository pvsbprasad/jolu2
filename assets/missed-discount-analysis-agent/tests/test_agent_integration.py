"""Integration test for the Missed Discount Analysis Agent."""
import asyncio
import json
import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


def _make_mock_tool(name):
    """Create a mock LangChain tool."""
    tool = MagicMock()
    tool.name = name
    tool.description = f"Mock tool: {name}"
    return tool


def test_agent_invoke_no_tools():
    """Agent returns a response even when no MCP tools are available."""
    with patch("agent.ChatLiteLLM") as mock_llm_cls, \
         patch("agent.create_agent") as mock_create_agent, \
         patch("agent.create_checkpointer") as mock_checkpointer, \
         patch("agent.get_user_sub", return_value="test-user"):

        # Mock checkpointer
        mock_checkpointer.return_value = MagicMock()

        # Mock LLM
        mock_llm = MagicMock()
        mock_llm_cls.return_value = mock_llm

        # Mock LangGraph agent
        mock_message = MagicMock()
        mock_message.content = "Tools are unavailable. Please try again later."
        mock_graph = AsyncMock()
        mock_graph.ainvoke = AsyncMock(return_value={"messages": [mock_message]})
        mock_create_agent.return_value = mock_graph

        from agent import SampleAgent

        agent = SampleAgent()
        result = asyncio.get_event_loop().run_until_complete(
            agent.invoke("Show me discount analysis", "test-ctx-001", tools=[])
        )

        assert result.status == "completed"
        assert len(result.message) > 0


def test_agent_invoke_with_mock_tools():
    """Agent processes query and returns discount analysis report with mocked tools."""
    with patch("agent.ChatLiteLLM") as mock_llm_cls, \
         patch("agent.create_agent") as mock_create_agent, \
         patch("agent.create_checkpointer") as mock_checkpointer, \
         patch("agent.get_user_sub", return_value="test-user"):

        mock_checkpointer.return_value = MagicMock()
        mock_llm = MagicMock()
        mock_llm_cls.return_value = mock_llm

        mock_message = MagicMock()
        mock_message.content = (
            "## Discount Analysis Summary\n"
            "Total lost: $300.00\n"
            "Total at-risk: $150.00\n"
            "Top invoice: INV001 (Vendor: VENDOR001, Discount: $200.00, Deadline: 2026-09-10)"
        )
        mock_graph = AsyncMock()
        mock_graph.ainvoke = AsyncMock(return_value={"messages": [mock_message]})
        mock_create_agent.return_value = mock_graph

        from agent import SampleAgent

        tools = [_make_mock_tool("list_a_supplierinvoice_for_api_supplierinvoice_process_srv")]
        agent = SampleAgent()
        result = asyncio.get_event_loop().run_until_complete(
            agent.invoke("How much discount am I losing?", "test-ctx-002", tools=tools)
        )

        assert result.status == "completed"
        assert "discount" in result.message.lower() or "analysis" in result.message.lower()


def test_agent_stream_yields_progress_then_complete():
    """stream() yields a working update followed by a completed result."""
    with patch("agent.ChatLiteLLM") as mock_llm_cls, \
         patch("agent.create_agent") as mock_create_agent, \
         patch("agent.create_checkpointer") as mock_checkpointer, \
         patch("agent.get_user_sub", return_value="test-user"):

        mock_checkpointer.return_value = MagicMock()
        mock_llm_cls.return_value = MagicMock()

        mock_message = MagicMock()
        mock_message.content = "Discount analysis complete."
        mock_graph = AsyncMock()
        mock_graph.ainvoke = AsyncMock(return_value={"messages": [mock_message]})
        mock_create_agent.return_value = mock_graph

        from agent import SampleAgent

        agent = SampleAgent()

        async def collect_stream():
            chunks = []
            async for chunk in agent.stream("analyze discounts", "test-ctx-003"):
                chunks.append(chunk)
            return chunks

        chunks = asyncio.get_event_loop().run_until_complete(collect_stream())

        assert len(chunks) >= 2
        # First chunk should be a working/processing status
        assert chunks[0]["is_task_complete"] == False
        # Last chunk should be completed
        assert chunks[-1]["is_task_complete"] == True
        assert "discount" in chunks[-1]["content"].lower() or "complete" in chunks[-1]["content"].lower()
