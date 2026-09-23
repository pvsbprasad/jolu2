# Product Requirements Document (PRD) - TEST CHANGE

**Title:** Missed Discount Analysis Agent
**Date:** 2026-09-10
**Owner:** Finance / Accounts Payable Team
**Solution Category:** AI Agent

## Product Purpose & Value Proposition

**Elevator Pitch:**
Every day, supplier invoices that cannot be matched to purchase orders sit in a queue while their early payment discount windows expire — silently costing the business money. This AI agent surfaces exactly how much discount value is being lost, which invoices are at risk right now, and why matching is failing.

**Business Need:**
AP teams currently lack visibility into the discount dollars lost due to unmatched invoices. Without a proactive, intelligent analysis tool, discount opportunities expire before anyone acts.

**Expected Value:**
Reduce missed early payment discounts by identifying at-risk invoices before their discount deadlines expire and delivering root-cause insights that enable AP teams to resolve matching failures faster.

**Product Objectives (Prioritized):**
1. Quantify total discount value being lost due to unmatched/blocked invoices in SAP S/4HANA
2. Identify root causes of invoice matching failures (price, quantity, PO reference discrepancies)
3. Prioritize at-risk invoices by discount expiry proximity and discount amount

## Business Metrics

| Metric | Baseline | Target | Timeline | Process / Capability | Source |
|--------|----------|--------|----------|----------------------|--------|
| Missed early payment discounts | — | Reduce missed early payment discounts | — | Invoice to Pay (AP discount capture) | user |

## Requirements

### Must-Have Requirements

**REQ-01**: Retrieve Unmatched Invoices

- **Problem to Solve**: AP team has no single view of all currently blocked/unmatched invoices and their discount conditions.
- **User Story**: As an AP analyst, I need the agent to retrieve all unmatched supplier invoices with their payment terms so that I can see what is at risk.
- **Acceptance Criteria**:
  - Given the agent is invoked, when it queries SAP S/4HANA, then it returns all open supplier invoices with blocking reasons and payment term data
- **Maps to Objective**: 1
- **Priority Rank**: 1

**REQ-02**: Calculate Lost & At-Risk Discount Amounts

- **Problem to Solve**: No automated calculation exists for how much discount is already lost vs. still recoverable.
- **User Story**: As an AP manager, I need the agent to compute the discount amount per invoice and classify it as lost or at-risk so that I can prioritize my team's effort.
- **Acceptance Criteria**:
  - Given invoice data with payment terms, when the agent processes it, then each invoice is tagged with: discount %, discount amount, deadline, and status (lost / at-risk / safe)
- **Maps to Objective**: 1, 3
- **Priority Rank**: 2

**REQ-03**: Root Cause Analysis of Matching Failures

- **Problem to Solve**: AP clerks cannot quickly determine why an invoice is blocked without manually investigating each one.
- **User Story**: As an AP analyst, I need the agent to identify the likely reason an invoice is unmatched so that I can resolve it efficiently.
- **Acceptance Criteria**:
  - Given a set of unmatched invoices, when the agent analyzes them, then it categorizes each by failure type (e.g., price discrepancy, quantity mismatch, missing PO reference)
- **Maps to Objective**: 2
- **Priority Rank**: 3

**REQ-04**: Summary Report with Recommendations

- **Problem to Solve**: AP managers need an actionable summary, not raw data, to drive daily prioritization.
- **User Story**: As an AP manager, I need a concise report with total discount exposure and top recommended actions so that I can direct my team's work for the day.
- **Acceptance Criteria**:
  - Given the analysis is complete, when the agent responds, then it delivers: total discount at risk, total already lost, top 5 invoices by urgency, and recommended next steps per invoice
- **Maps to Objective**: 1, 2, 3
- **Priority Rank**: 4

**REQ-05**: Email Notification for Top-N At-Risk Invoices

- **Problem to Solve**: AP teams are not proactively alerted when high-value invoices are approaching their discount deadlines, leading to missed discount opportunities.
- **User Story**: As an AP manager, I need the agent to send an email with a summary table of the top-N invoices ranked by discount value at risk — including discount amounts and deadlines — to the recipients I specify when invoking the agent, so that my team can act before deadlines expire.
- **Acceptance Criteria**:
  - Given the agent completes its analysis and at-risk invoices are identified, when invoked with one or more recipient email addresses, then the agent sends an email containing a summary table of the top-N invoices ranked by discount value at risk, each row showing: supplier, invoice number, discount amount, and discount deadline
  - The email recipients are provided as an invocation parameter — no hardcoded addresses
  - If no at-risk invoices are found, no email is sent and the agent informs the user accordingly
- **Maps to Objective**: 3
- **Priority Rank**: 5

## Solution Architecture

**Architecture Overview:**
A Python AI agent (A2A protocol) deployed on SAP BTP. The agent connects to SAP S/4HANA via the Supplier Invoice OData API to retrieve invoice and payment term data, performs analysis in its reasoning loop, and returns a structured summary to the user.

**Key Components:**
- Python AI Agent (A2A) — reasoning, analysis, and report generation
- SAP S/4HANA Supplier Invoice OData API (`API_SUPPLIERINVOICE_PROCESS_SRV`) — invoice and payment term data source
- SAP Generative AI Hub (GPT-4o) — LLM reasoning engine
- SAP BTP Alert Notification Service / SMTP — email delivery for at-risk invoice notifications

**Integration Points:**
- SAP S/4HANA: read supplier invoices, payment terms, blocking reasons (read-only, on-demand)
- Email service (SAP BTP Alert Notification Service or SMTP): send at-risk invoice summary to AP team recipients supplied at invocation time

### Agent Extensibility & Instrumentation

**Agent Extensibility:**
- The agent exposes extension points to add new matching failure categories without modifying core logic
- Future capabilities (e.g., automated escalation, supplier notification) can be added as additional tools

**Business Step Instrumentation:**
All milestones emit structured logs following the pattern `[MILESTONE_ID].[achieved|missed]: [description]`

### Automation & Agent Behaviour

**Automation Level:** Autonomous agent with read-only data access

**Actions the system performs without human approval:**
- Querying SAP S/4HANA for invoice and payment term data
- Calculating discount amounts and classifying invoice risk
- Generating root cause categories and summary report

**Actions that require human review or approval:**
- Any payment action or invoice clearance (explicitly out of scope for this agent)

**Model or engine used:** GPT-4o via SAP Generative AI Hub

**Knowledge & data sources accessed:**
- SAP S/4HANA: Supplier Invoice OData API — open invoice data, payment terms, blocking status (read-only)

**Tools or connectors invoked:**
- `get_supplier_invoices`: fetches open/blocked invoices from S/4HANA (read-only)
- `get_payment_terms`: retrieves discount conditions per invoice (read-only)
- `send_email_notification`: sends at-risk invoice summary email to specified recipients (write — sends external email)

**Guardrails & fail-safes:**
- Agent never modifies, posts, or clears any financial document
- If the S/4HANA API is unavailable, agent returns a clear error and does not hallucinate invoice data
- Agent communicates uncertainty explicitly when invoice data is incomplete

## Milestones

### M1: Invoice Retrieval

- **Description**: Agent fetches all unmatched/blocked supplier invoices from SAP S/4HANA AP
- **Achieved when**: Invoice list is returned with blocking reason codes
- **Log on achievement**: `M1.achieved: supplier invoices retrieved successfully, count={n}`
- **Log on miss**: `M1.missed: failed to retrieve supplier invoices from S/4HANA`

### M2: Discount Term Extraction

- **Description**: Agent reads payment terms and discount conditions for each invoice
- **Achieved when**: Discount percentage, discount deadline, and net due date extracted per invoice
- **Log on achievement**: `M2.achieved: payment terms extracted for {n} invoices`
- **Log on miss**: `M2.missed: payment term extraction incomplete or unavailable`

### M3: Missed Discount Calculation

- **Description**: Agent computes discount amount lost or at risk per invoice
- **Achieved when**: Each invoice is classified as lost, at-risk, or safe with a discount value
- **Log on achievement**: `M3.achieved: discount analysis complete, total_at_risk={amount}, total_lost={amount}`
- **Log on miss**: `M3.missed: discount calculation could not be completed`

### M4: Root Cause Analysis

- **Description**: Agent identifies patterns and categories of matching failures
- **Achieved when**: Each unmatched invoice has an assigned root cause category
- **Log on achievement**: `M4.achieved: root cause analysis complete for {n} invoices`
- **Log on miss**: `M4.missed: root cause analysis skipped or failed`

### M5: Summary Report Delivery

- **Description**: Agent presents total discount loss, top offending invoices, and actionable recommendations
- **Achieved when**: Structured report delivered to user with totals and top-5 prioritized invoices
- **Log on achievement**: `M5.achieved: summary report delivered to user`
- **Log on miss**: `M5.missed: report generation failed`

### M6: AP Team Email Notification

- **Description**: Agent sends a summary email containing the top-N at-risk invoices (ranked by discount value) with amounts and deadlines to the recipient(s) provided as an invocation parameter
- **Achieved when**: Email successfully dispatched to all specified recipients; at least one at-risk invoice was present
- **Log on achievement**: `M6.achieved: email notification sent to {n} recipient(s), top_n_invoices={n}`
- **Log on miss**: `M6.missed: email notification not sent — no at-risk invoices found or email delivery failed`
