"""Tests for generate_discount_report tool."""
from datetime import date, timedelta
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

from discount_tools import calculate_discount_analysis, generate_discount_report


def _make_enriched(invoice_id, amount, status, days_remaining=None):
    return {
        "SupplierInvoice": invoice_id,
        "FiscalYear": "2026",
        "InvoicingParty": f"VENDOR_{invoice_id}",
        "CompanyCode": "1000",
        "InvoiceGrossAmount": str(amount),
        "DocumentCurrency": "USD",
        "discount1_amount": amount * 0.02,
        "discount1_deadline": (date.today() - timedelta(days=1)).isoformat() if status == "lost" else (date.today() + timedelta(days=5)).isoformat(),
        "days_remaining": days_remaining,
        "discount_status": status,
        "PaymentBlockingReason": "R",
    }


def test_report_totals():
    invoices = [
        _make_enriched("INV001", 10000, "lost"),
        _make_enriched("INV002", 5000, "at_risk", 2),
        _make_enriched("INV003", 8000, "safe"),
    ]
    report = generate_discount_report(invoices)
    assert report["summary"]["lost_count"] == 1
    assert report["summary"]["at_risk_count"] == 1
    assert report["summary"]["safe_count"] == 1
    assert report["summary"]["total_lost_amount"] == 200.0
    assert report["summary"]["total_at_risk_amount"] == 100.0
    assert report["summary"]["grand_total_exposure"] == 300.0


def test_top_5_limit():
    invoices = [_make_enriched(f"INV{i:03d}", 1000 * i, "lost") for i in range(1, 9)]
    report = generate_discount_report(invoices)
    assert len(report["top_invoices"]) <= 5


def test_top_invoices_sorted_by_discount_amount():
    invoices = [
        _make_enriched("INV001", 1000, "lost"),
        _make_enriched("INV002", 5000, "lost"),
        _make_enriched("INV003", 2000, "at_risk", 1),
    ]
    report = generate_discount_report(invoices)
    amounts = [i["discount_amount"] for i in report["top_invoices"]]
    assert amounts == sorted(amounts, reverse=True)


def test_overall_recommendation_present():
    invoices = [_make_enriched("INV001", 10000, "lost")]
    report = generate_discount_report(invoices)
    assert len(report["overall_recommendation"]) > 0


def test_empty_invoice_list():
    report = generate_discount_report([])
    assert report["summary"]["total_invoices_analyzed"] == 0
    assert report["summary"]["grand_total_exposure"] == 0.0
    assert report["top_invoices"] == []


def test_root_cause_in_top_invoices():
    invoices = [_make_enriched("INV001", 10000, "lost")]
    report = generate_discount_report(invoices)
    top = report["top_invoices"][0]
    assert "root_cause" in top
    assert "recommended_action" in top


def test_integration_calculate_then_report():
    """End-to-end: calculate_discount_analysis feeds into generate_discount_report."""
    from datetime import date, timedelta
    raw = [
        {
            "SupplierInvoice": "INV001",
            "FiscalYear": "2026",
            "InvoicingParty": "V001",
            "CompanyCode": "1000",
            "InvoiceGrossAmount": "20000",
            "DocumentCurrency": "USD",
            "PaymentTerms": "ZB30",
            "DueCalculationBaseDate": (date.today() - timedelta(days=15)).isoformat(),
            "CashDiscount1Percent": "2.0",
            "CashDiscount1Days": "10",
            "CashDiscount2Percent": "0",
            "CashDiscount2Days": "0",
            "NetPaymentDays": "30",
            "PaymentBlockingReason": "R",
        }
    ]
    enriched = calculate_discount_analysis(raw)
    report = generate_discount_report(enriched)
    assert report["summary"]["lost_count"] == 1
    assert report["summary"]["total_lost_amount"] == 400.0
