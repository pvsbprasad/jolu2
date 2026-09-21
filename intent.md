# Missed Discount Analysis Agent

AI agent for analyzing unmatched invoices to quantify lost early payment discounts in accounts payable.

## Business challenge

Finance teams lose early payment discounts because supplier invoices cannot be matched in time. Unmatched invoices block timely payment, causing discount deadlines to expire. There is no visibility into how much discount value is being lost, which invoices are at risk, and what the root cause of matching failures is.

## Business Goals & Success Criteria

| Metric | Baseline | Target | Timeline | Process / Capability | Source |
|--------|----------|--------|----------|----------------------|--------|
| Missed early payment discounts | — | Reduce missed early payment discounts | — | Invoice to Pay (AP discount capture) | user |

## Key Milestones

1. **Invoice Retrieval** — Agent fetches unmatched/blocked supplier invoices from SAP S/4HANA AP
2. **Discount Term Extraction** — Agent reads payment terms and discount conditions per invoice
3. **Missed Discount Calculation** — Agent computes discount amounts lost or at risk per invoice
4. **Root Cause Analysis** — Agent identifies patterns causing matching failures (price/quantity/PO discrepancies)
5. **Summary Report Delivery** — Agent presents total discount loss, top offending invoices, and actionable recommendations
6. **AP Team Email Notification** — Agent sends a summary email (top-N invoices by discount value at risk, with deadlines) to recipient(s) provided as an invocation parameter

## Business Architecture (RBA)

### End-to-End Process

Source to Pay (E2E)

### Process Hierarchy

```
Source to Pay
└── Invoice to Pay (generic)
    └── Process accounts payables and release payment (BPS-334)
        └── Process accounts payable (AP)
        └── Manage payables financing
```

### Summary

The challenge maps to the Invoice to Pay sub-process within Source to Pay, specifically AP invoice matching, early payment discount capture, and payables financing management (BPS-334).

## Fit Gap Analysis

| Requirement (business) | Standard asset(s) found | API ORD ID | MCP Server ORD ID | MCP Server Version | Gap? | Notes / assumptions |
|------------------------|------------------------|------------|-------------------|--------------------|------|---------------------|
| Read unmatched/blocked supplier invoices | SAP S/4HANA Cloud — Open Item Management (FI-AP) | `sap.s4:apiResource:API_SUPPLIERINVOICE_PROCESS_SRV:v1` | — | — | No | OData API available; no MCP server found — custom MCP tool or direct API call needed |
| Extract payment terms & discount conditions | SAP S/4HANA Cloud — Payment Processing | `sap.s4:apiResource:API_SUPPLIERINVOICE_PROCESS_SRV:v1` | — | — | No | Discount fields available in supplier invoice OData service |
| Calculate lost discount amounts | SAP Analytics Cloud / Financial Analytics | — | — | — | Maybe | Standard reporting exists but not agent-accessible; agent must compute from raw invoice data |
| Identify root causes of matching failures | No standard SAP capability for AI-driven root cause | — | — | — | Yes | Custom agent logic required to analyze discrepancies |
| Generate actionable recommendations | No standard SAP capability | — | — | — | Yes | Custom agent reasoning required |
| Notify AP team by email with top-N at-risk invoices (discount amount + deadline) | SAP BTP Alert Notification Service / SMTP | — | — | — | Maybe | No MCP server found; agent sends email via SAP BTP Alert Notification Service or SMTP; recipient email(s) passed as invocation parameter; email body contains a summary table of top-N invoices ranked by discount value at risk |

### Key findings
- SAP S/4HANA Supplier Invoice OData API (`API_SUPPLIERINVOICE_PROCESS_SRV`) is the primary data source for unmatched invoices and payment terms
- No MCP server exists for this API; the agent will call the S/4HANA OData API directly or via a custom MCP translation
- Standard SAP Financial Analytics covers reporting but not AI-driven discount loss analysis or root cause reasoning
- The core gap — missed discount quantification and root cause analysis — requires a custom AI agent
- SAP S/4HANA (Public or Private Cloud Edition) is the assumed ERP backbone
- Email notification for at-risk invoices can be delivered via SAP BTP Alert Notification Service or SMTP; no dedicated MCP server exists — custom integration required

## Recommendations

### Missed Discount Analysis AI Agent

#### Executive Summary

Custom Python AI agent querying S/4HANA AP to surface lost discount value.

#### Recommended Solution

A Python-based AI agent (A2A protocol) that connects to SAP S/4HANA via the Supplier Invoice OData API to retrieve unmatched and blocked invoices. The agent extracts payment terms and discount conditions, calculates the total discount amount being lost per invoice and in aggregate, identifies root causes of matching failures (e.g. price discrepancies, missing PO references, quantity mismatches), and delivers a structured summary report with prioritized recommendations for AP teams.

#### Recommended solution category

AI Agent

#### Intent fit
85%
