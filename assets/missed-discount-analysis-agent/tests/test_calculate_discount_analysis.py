"""Tests for calculate_discount_analysis tool."""
from datetime import date, timedelta
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

from discount_tools import calculate_discount_analysis


def _make_invoice(invoice_id, gross, disc1_pct, disc1_days, base_date_str, blocking="R"):
    return {
        "SupplierInvoice": invoice_id,
        "FiscalYear": "2026",
        "InvoicingParty": "VENDOR001",
        "CompanyCode": "1000",
        "InvoiceGrossAmount": str(gross),
        "DocumentCurrency": "USD",
        "PaymentTerms": "ZB30",
        "DueCalculationBaseDate": base_date_str,
        "CashDiscount1Percent": str(disc1_pct),
        "CashDiscount1Days": str(disc1_days),
        "CashDiscount2Percent": "0",
        "CashDiscount2Days": "0",
        "NetPaymentDays": "30",
        "PaymentBlockingReason": blocking,
    }


def test_lost_invoice():
    """Invoice with expired discount deadline is classified as 'lost'."""
    past_date = (date.today() - timedelta(days=20)).isoformat()
    invoices = [_make_invoice("INV001", 10000, 2.0, 5, past_date)]
    result = calculate_discount_analysis(invoices)
    assert result[0]["discount_status"] == "lost"
    assert result[0]["discount1_amount"] == 200.0


def test_at_risk_invoice():
    """Invoice with deadline within 3 days is classified as 'at_risk'."""
    soon_date = (date.today() - timedelta(days=1)).isoformat()
    invoices = [_make_invoice("INV002", 5000, 3.0, 3, soon_date)]
    result = calculate_discount_analysis(invoices)
    assert result[0]["discount_status"] == "at_risk"
    assert result[0]["discount1_amount"] == 150.0


def test_safe_invoice():
    """Invoice with discount deadline far in future is classified as 'safe'."""
    future_date = (date.today() - timedelta(days=1)).isoformat()
    invoices = [_make_invoice("INV003", 8000, 1.5, 30, future_date)]
    result = calculate_discount_analysis(invoices)
    assert result[0]["discount_status"] == "safe"


def test_no_discount_invoice():
    """Invoice with 0% discount is classified as 'no_discount'."""
    invoices = [_make_invoice("INV004", 12000, 0, 0, date.today().isoformat())]
    result = calculate_discount_analysis(invoices)
    assert result[0]["discount_status"] == "no_discount"
    assert result[0]["discount1_amount"] == 0.0


def test_sort_order_lost_before_at_risk():
    """Lost invoices should appear before at-risk invoices in results."""
    past = (date.today() - timedelta(days=10)).isoformat()
    soon = (date.today() - timedelta(days=1)).isoformat()
    invoices = [
        _make_invoice("SAFE", 1000, 2, 30, (date.today() - timedelta(days=1)).isoformat()),
        _make_invoice("AT_RISK", 2000, 2, 3, soon),
        _make_invoice("LOST", 3000, 2, 5, past),
    ]
    result = calculate_discount_analysis(invoices)
    statuses = [r["discount_status"] for r in result]
    assert statuses.index("lost") < statuses.index("at_risk")


def test_empty_invoice_list():
    """Empty list returns empty list."""
    result = calculate_discount_analysis([])
    assert result == []


def test_sap_date_format():
    """OData /Date(timestamp)/ format is parsed correctly."""
    # 2026-09-01 = 1756684800000 ms
    invoices = [_make_invoice("INV005", 1000, 2.0, 5, "/Date(1756684800000)/")]
    result = calculate_discount_analysis(invoices)
    assert result[0]["discount1_amount"] == 20.0
