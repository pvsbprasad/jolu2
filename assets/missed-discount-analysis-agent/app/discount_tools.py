"""
Discount analysis tools for the Missed Discount Analysis Agent.
Pure Python tools that perform calculations without making API calls.
API calls go through MCP tools loaded dynamically.
"""
from datetime import date, datetime, timedelta
from typing import Any


def _parse_date(val: Any) -> date | None:
    """Parse a date value from various formats returned by OData."""
    if val is None:
        return None
    if isinstance(val, date):
        return val
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, str):
        # OData datetime format: /Date(1234567890000)/
        if val.startswith("/Date("):
            ts = int(val[6:val.index(")")])
            return datetime.utcfromtimestamp(ts / 1000).date()
        # ISO format
        try:
            return datetime.fromisoformat(val[:10]).date()
        except ValueError:
            pass
    return None


def calculate_discount_analysis(invoices: list[dict]) -> list[dict]:
    """
    Compute discount loss classification for each invoice.

    For each invoice, computes:
    - discount1_deadline: DueCalculationBaseDate + CashDiscount1Days
    - discount1_amount: InvoiceGrossAmount * CashDiscount1Percent / 100
    - status: "lost", "at_risk", or "safe"

    Returns enriched list sorted by urgency (lost first, then at_risk by deadline).
    """
    today = date.today()
    enriched = []

    for inv in invoices:
        gross = float(inv.get("InvoiceGrossAmount") or 0)
        disc1_pct = float(inv.get("CashDiscount1Percent") or 0)
        disc1_days = int(inv.get("CashDiscount1Days") or 0)
        base_date = _parse_date(inv.get("DueCalculationBaseDate"))

        discount1_amount = round(gross * disc1_pct / 100, 2) if disc1_pct > 0 else 0.0

        if base_date and disc1_days > 0 and disc1_pct > 0:
            deadline = base_date + timedelta(days=disc1_days)
            days_remaining = (deadline - today).days

            if today > deadline:
                status = "lost"
            elif days_remaining <= 3:
                status = "at_risk"
            else:
                status = "safe"
        else:
            deadline = None
            days_remaining = None
            status = "no_discount" if disc1_pct == 0 else "unknown"

        enriched.append({
            **inv,
            "discount1_amount": discount1_amount,
            "discount1_deadline": str(deadline) if deadline else None,
            "days_remaining": days_remaining,
            "discount_status": status,
        })

    # Sort: lost first, then at_risk by urgency, then safe, then no_discount
    order = {"lost": 0, "at_risk": 1, "safe": 2, "unknown": 3, "no_discount": 4}
    enriched.sort(key=lambda x: (
        order.get(x["discount_status"], 5),
        x["days_remaining"] if x["days_remaining"] is not None else 9999,
        -x["discount1_amount"],
    ))

    return enriched


def classify_root_cause(invoice: dict) -> dict:
    """
    Classify the root cause of a matching failure based on PaymentBlockingReason.
    Returns a dict with root_cause and recommended_action.
    """
    reason = str(invoice.get("PaymentBlockingReason") or "").strip()
    po = str(invoice.get("PurchaseOrder") or "").strip()

    root_cause_map = {
        "R": ("Price discrepancy", "Compare invoice price with PO and request credit memo or price adjustment"),
        "Q": ("Quantity mismatch", "Verify goods receipt with warehouse and align quantity"),
        "A": ("Missing account assignment", "Assign correct cost center or GL account"),
        "B": ("Invoice amount exceeds tolerance", "Review tolerance settings or request invoice correction"),
        "I": ("Incorrect payment terms", "Verify payment terms with supplier"),
        "V": ("Payment method issue", "Review and correct payment method configuration"),
    }

    if reason in root_cause_map:
        root_cause, recommended_action = root_cause_map[reason]
    elif reason == "" and not po:
        root_cause = "Missing purchase order reference"
        recommended_action = "Link invoice to the correct purchase order"
    elif reason == "":
        root_cause = "No blocking reason recorded"
        recommended_action = "Investigate invoice manually in SAP"
    else:
        root_cause = f"Other blocking reason: {reason}"
        recommended_action = f"Investigate blocking reason code '{reason}' in SAP AP"

    return {
        "root_cause": root_cause,
        "recommended_action": recommended_action,
    }


def generate_discount_report(invoices: list[dict]) -> dict:
    """
    Generate a structured discount loss summary report.

    Computes total lost/at-risk amounts, top 5 invoices by discount amount,
    and an overall recommendation.
    """
    lost_invoices = [i for i in invoices if i.get("discount_status") == "lost"]
    at_risk_invoices = [i for i in invoices if i.get("discount_status") == "at_risk"]
    safe_invoices = [i for i in invoices if i.get("discount_status") == "safe"]

    total_lost = round(sum(i.get("discount1_amount", 0) for i in lost_invoices), 2)
    total_at_risk = round(sum(i.get("discount1_amount", 0) for i in at_risk_invoices), 2)
    total_safe = round(sum(i.get("discount1_amount", 0) for i in safe_invoices), 2)

    # Top 5 by discount amount across all non-safe/non-no_discount invoices
    priority_invoices = [i for i in invoices if i.get("discount_status") in ("lost", "at_risk")]
    priority_invoices.sort(key=lambda x: -x.get("discount1_amount", 0))
    top_5 = priority_invoices[:5]

    # Classify root causes for top 5
    top_5_enriched = []
    for inv in top_5:
        rc = classify_root_cause(inv)
        top_5_enriched.append({
            "invoice": inv.get("SupplierInvoice"),
            "fiscal_year": inv.get("FiscalYear"),
            "supplier": inv.get("InvoicingParty"),
            "company_code": inv.get("CompanyCode"),
            "gross_amount": inv.get("InvoiceGrossAmount"),
            "currency": inv.get("DocumentCurrency"),
            "discount_amount": inv.get("discount1_amount"),
            "discount_deadline": inv.get("discount1_deadline"),
            "days_remaining": inv.get("days_remaining"),
            "status": inv.get("discount_status"),
            "blocking_reason": inv.get("PaymentBlockingReason"),
            "root_cause": rc["root_cause"],
            "recommended_action": rc["recommended_action"],
        })

    grand_total_exposure = round(total_lost + total_at_risk, 2)

    if grand_total_exposure > 10000:
        overall_recommendation = (
            "Significant discount exposure detected. Recommend immediate AP process review: "
            "prioritize resolution of at-risk invoices within 3 days, and investigate root causes "
            "of repeated price and quantity discrepancies."
        )
    elif grand_total_exposure > 0:
        overall_recommendation = (
            "Moderate discount exposure. Focus on resolving at-risk invoices first to recover "
            "remaining discount opportunities."
        )
    else:
        overall_recommendation = (
            "No significant discount exposure at this time. Continue monitoring for new unmatched invoices."
        )

    return {
        "summary": {
            "total_invoices_analyzed": len(invoices),
            "lost_count": len(lost_invoices),
            "at_risk_count": len(at_risk_invoices),
            "safe_count": len(safe_invoices),
            "total_lost_amount": total_lost,
            "total_at_risk_amount": total_at_risk,
            "total_safe_amount": total_safe,
            "grand_total_exposure": grand_total_exposure,
        },
        "top_invoices": top_5_enriched,
        "overall_recommendation": overall_recommendation,
    }
