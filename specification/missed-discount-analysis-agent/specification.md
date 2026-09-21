# Specification: missed-discount-analysis-agent

> **Guidelines**: Read all applicable guidelines before executing ANY tasks below:
> - [guidelines.md](../guidelines.md) — Universal execution rules
> - [guidelines-agent.md](../guidelines-agent.md) — Universal agent patterns
> - [guidelines-agent-python.md](../guidelines-agent-python.md) — Python implementation details
> - [guidelines-agent-skills.md](../guidelines-agent-skills.md) — Runtime skills patterns
> - [guidelines-agent-mcp.md](../guidelines-agent-mcp.md) — MCP integration patterns

---

## Basic Setup

- [x] Read `product-requirements-document.md` and `intent.md` to understand the full scope
- [x] Bootstrap agent code in `assets/missed-discount-analysis-agent/` using instructions from the sap-agent-bootstrap section (invoke from inside `assets/missed-discount-analysis-agent/`, use copy commands — do NOT create files manually)
- [x] Install dependencies, validate the agent starts and responds at `/.well-known/agent.json`

---

## Runtime Skills

- [x] Create `assets/missed-discount-analysis-agent/app/skills/discount-analysis/SKILL.md` with step-by-step instructions for: (1) retrieving unmatched invoices, (2) computing discount loss per invoice, (3) categorizing root causes, (4) formatting the summary report

---

## Project-Specific Tasks

### System Prompt

- [x] Write a system prompt in `assets/missed-discount-analysis-agent/app/agent.py` that instructs the agent to:
  - Act as an AP discount analysis expert
  - NEVER fabricate, guess, or invent invoice data — always use MCP tools
  - Always set page size parameter (top/limit) to max 100 on all tool calls
  - Relay tool errors verbatim without embellishment
  - Perform analysis in the following sequence: retrieve invoices → extract payment terms → calculate discount loss → identify root causes → deliver report

### MCP Translation (API Spec → MCP Tools)

- [x] Invoke `mcp-translation-file` skill with the API spec at `specification/missed-discount-analysis-agent/api-specs/supplier-invoice.edmx`
  - ORD ID: `sap.s4:apiResource:API_SUPPLIERINVOICE_PROCESS_SRV:v1`
  - API type: `edmx`
  - The skill outputs MCP translation files to `specification/missed-discount-analysis-agent/mcps/supplier-invoice/`
- [x] Invoke `setup-solution` skill to create the MCP server asset for the generated translation files
- [x] Extract the exact ORD ID from the generated `assets/sap-s4-supplier-invoice-mcp-server/asset.yaml`
- [x] Add the MCP server as a dependency in `assets/missed-discount-analysis-agent/asset.yaml` under `requires`

### Agent Tools Implementation

- [x] Implement `get_supplier_invoices` tool:
  - Calls the MCP tool to fetch `A_SupplierInvoice` entity set filtered by `PaymentBlockingReason ne ''` or `SupplierInvoiceStatus`
  - Returns: SupplierInvoice, FiscalYear, InvoicingParty, CompanyCode, InvoiceGrossAmount, DocumentCurrency, PaymentTerms, DueCalculationBaseDate, CashDiscount1Percent, CashDiscount1Days, CashDiscount2Percent, CashDiscount2Days, PaymentBlockingReason, InvoiceReceiptDate
  - Limit: max 100 records per call

- [x] Implement `calculate_discount_analysis` tool (pure Python, no MCP call):
  - Input: list of invoice dicts with payment term fields
  - For each invoice, compute:
    - `discount1_deadline = DueCalculationBaseDate + CashDiscount1Days`
    - `discount1_amount = InvoiceGrossAmount * (CashDiscount1Percent / 100)`
    - `status = "lost"` if today > deadline, `"at_risk"` if today + 3 >= deadline, else `"safe"`
  - Return enriched list sorted by urgency (lost first, then at_risk by deadline proximity)

- [x] Implement `classify_root_cause` tool (pure Python reasoning):
  - Input: single invoice dict
  - Rules:
    - `PaymentBlockingReason == 'R'` → "Price discrepancy"
    - `PaymentBlockingReason == 'Q'` → "Quantity mismatch"
    - `PaymentBlockingReason == 'A'` → "Missing account assignment"
    - `PaymentBlockingReason != ''` → "Other blocking reason: {code}"
    - `PurchaseOrder missing/empty` → "Missing PO reference"
    - default → "Unknown"
  - Return: root cause string + recommended action

- [x] Implement `generate_discount_report` tool (pure Python):
  - Input: enriched+classified invoice list
  - Computes: total_lost, total_at_risk, top 5 invoices by discount_amount
  - Returns structured report dict with: summary totals, top_invoices list, recommendations per invoice

### Agent Wiring

- [x] Wire all four tools into the agent graph in `agent.py`
- [x] Load MCP tools dynamically using `get_mcp_tools()` from `mcp_tools` module
- [x] Ensure tools are lazily loaded (not in `__init__`) — call `_get_tools()` inside `stream()`

### Email Notification Tool (REQ-05)

- [x] Implement `send_email_notification` tool in `assets/missed-discount-analysis-agent/app/tools/email_notification.py`:
  - Input: `recipients` (list of email address strings), `invoices` (list of enriched invoice dicts ranked by discount value at risk), `top_n` (int, default 10)
  - Selects top-N invoices by `discount1_amount` from the at-risk list
  - Builds an HTML/plain-text email body as a summary table with columns: Supplier, Invoice Number, Discount Amount, Currency, Discount Deadline
  - Sends via SAP BTP Alert Notification Service (if configured via env vars `ANS_URL`, `ANS_CLIENT_ID`, `ANS_CLIENT_SECRET`) or falls back to SMTP (`SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`)
  - Returns: `{"sent": true, "recipients": [...], "invoice_count": N}` on success
  - If no at-risk invoices exist, returns `{"sent": false, "reason": "no at-risk invoices found"}` — does NOT send email
  - Raises a descriptive error if both ANS and SMTP are unconfigured

- [x] Wire `send_email_notification` into the agent graph in `agent.py`
- [x] Update system prompt to instruct the agent to:
  - Call `send_email_notification` only when recipient email addresses are provided by the user as part of the invocation
  - Pass only `at_risk` and `lost` invoices to the notification tool (not `safe` ones)
  - Inform the user if no email was sent and explain why

---

## Business Instrumentation

- [x] Implement structured logging + OpenTelemetry spans for all 5 milestones from PRD:
  - M1: `M1.achieved: supplier invoices retrieved successfully, count={n}` / `M1.missed: failed to retrieve supplier invoices from S/4HANA`
  - M2: `M2.achieved: payment terms extracted for {n} invoices` / `M2.missed: payment term extraction incomplete or unavailable`
  - M3: `M3.achieved: discount analysis complete, total_at_risk={amount}, total_lost={amount}` / `M3.missed: discount calculation could not be completed`
  - M4: `M4.achieved: root cause analysis complete for {n} invoices` / `M4.missed: root cause analysis skipped or failed`
  - M5: `M5.achieved: summary report delivered to user` / `M5.missed: report generation failed`
  - [x] M6: `M6.achieved: email notification sent to {n} recipient(s), top_n_invoices={n}` / `M6.missed: email notification not sent — no at-risk invoices found or email delivery failed`
- [x] Extract all business logic from `stream()` into a plain async helper `_run_agent()` to avoid `GeneratorExit` context errors with OpenTelemetry spans
- [x] Verify `auto_instrument()` is called at top of `main.py` before any AI framework imports

---

## MCP Tool Integration

- [x] Verify `specification/missed-discount-analysis-agent/api-specs/supplier-invoice.edmx` exists
- [x] After `mcp-translation-file` and `setup-solution` complete, verify these files exist:
  - `specification/missed-discount-analysis-agent/mcps/supplier-invoice/translation.json`
  - `specification/missed-discount-analysis-agent/mcps/supplier-invoice/.tool-list.json`
- [x] Wire MCP tool loading in `agent.py` using `get_mcp_tools()` from `mcp_tools` module
- [x] Add MCP server dependency to `assets/missed-discount-analysis-agent/asset.yaml` under `requires` using the exact ORD ID from the generated asset.yaml
- [x] Generate `mcp-mock.json` using the `mcp-mock-config` skill (required before tests can run)

---

## Testing

- [x] `conftest.py` only sets `IBD_TESTING=true` — no branching in application code
- [x] Write unit tests in `assets/missed-discount-analysis-agent/tests/`:
  - `test_calculate_discount_analysis.py` — test lost/at_risk/safe classification logic with sample data
  - `test_classify_root_cause.py` — test each PaymentBlockingReason code maps to correct root cause
  - `test_generate_discount_report.py` — verify totals calculation and top-5 ranking
- [x] Write `test_agent_integration.py` — end-to-end agent flow with mocked LLM and mocked MCP tools; assert the response contains discount summary
- [x] Write `test_send_email_notification.py` — test: (1) email sent when at-risk invoices present and recipients provided; (2) no email sent when no at-risk invoices; (3) fallback SMTP used when ANS not configured; (4) error raised when neither ANS nor SMTP configured
- [x] Run each unit test immediately after writing it
- [x] Run `pytest` from `assets/missed-discount-analysis-agent/` — 55 passed, coverage 67%
- [x] Verify decorated functions in `agent.py` — 7 (matches bootstrap template for this version)
- [x] Run `pytest` (no args) to generate final `test_report.json`
- [x] Verify `test_report.json` exists at `assets/missed-discount-analysis-agent/test_report.json`
