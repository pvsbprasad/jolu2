---
name: discount-analysis
description: Step-by-step instructions for performing a missed discount analysis on unmatched supplier invoices from SAP S/4HANA
---

# Missed Discount Analysis Skill

Follow these steps in order to perform a complete missed discount analysis.

## Step 1: Retrieve Unmatched Invoices

Use the `list_a_supplierinvoice_for_api_supplierinvoice_process_srv` MCP tool to fetch supplier invoices.
- Apply filter: `PaymentBlockingReason ne ''` to get only blocked invoices
- Request fields: SupplierInvoice, FiscalYear, InvoicingParty, CompanyCode, InvoiceGrossAmount, DocumentCurrency, PaymentTerms, DueCalculationBaseDate, CashDiscount1Percent, CashDiscount1Days, CashDiscount2Percent, CashDiscount2Days, NetPaymentDays, PaymentBlockingReason, InvoiceReceiptDate
- Always set top=100 to limit response size

## Step 2: Extract Discount Conditions

For each invoice:
- Read CashDiscount1Percent and CashDiscount1Days (primary discount)
- Read CashDiscount2Percent and CashDiscount2Days (secondary discount)
- Read DueCalculationBaseDate as the baseline for deadline calculation
- Discount1 deadline = DueCalculationBaseDate + CashDiscount1Days
- Discount1 amount = InvoiceGrossAmount × (CashDiscount1Percent / 100)

## Step 3: Classify Each Invoice

Compare today's date with the discount deadline:
- **Lost**: today > discount1_deadline → discount opportunity has passed
- **At-risk**: today + 3 days >= discount1_deadline → urgent, resolve within 3 days
- **Safe**: plenty of time remaining

## Step 4: Identify Root Causes

Map PaymentBlockingReason codes to business-friendly names:
- 'R' → Price discrepancy between invoice and purchase order
- 'Q' → Quantity mismatch between invoice and goods receipt
- 'A' → Missing or incorrect account assignment
- 'B' → Invoice amount exceeds tolerance
- '' (empty) but no PO → Missing purchase order reference
- Other → Other blocking reason (show code)

Recommended action per root cause:
- Price discrepancy → AP clerk to compare invoice price with PO and request credit memo or price adjustment
- Quantity mismatch → Check goods receipt confirmation with warehouse
- Missing account assignment → AP team to assign correct cost center or GL account
- Missing PO reference → AP clerk to link invoice to correct purchase order

## Step 5: Deliver Report

Present a structured summary:
1. **Total discount at risk** (sum of at-risk invoices)
2. **Total discount already lost** (sum of lost invoices)
3. **Top 5 invoices** by discount amount, sorted by urgency (lost first, then at-risk)
4. For each top invoice: invoice number, supplier, gross amount, discount amount, deadline, blocking reason, root cause, recommended action
5. **Overall recommendation**: if total loss is significant, recommend an AP process review
