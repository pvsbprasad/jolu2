"""Tests for classify_root_cause tool."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

from discount_tools import classify_root_cause


def _make_invoice(blocking_reason, purchase_order="4500000123"):
    return {
        "SupplierInvoice": "5100000001",
        "PaymentBlockingReason": blocking_reason,
        "PurchaseOrder": purchase_order,
    }


def test_price_discrepancy():
    result = classify_root_cause(_make_invoice("R"))
    assert "Price discrepancy" in result["root_cause"]
    assert "credit memo" in result["recommended_action"].lower()


def test_quantity_mismatch():
    result = classify_root_cause(_make_invoice("Q"))
    assert "Quantity mismatch" in result["root_cause"]
    assert "warehouse" in result["recommended_action"].lower()


def test_missing_account_assignment():
    result = classify_root_cause(_make_invoice("A"))
    assert "account assignment" in result["root_cause"].lower()


def test_invoice_exceeds_tolerance():
    result = classify_root_cause(_make_invoice("B"))
    assert "tolerance" in result["root_cause"].lower()


def test_missing_po_reference():
    result = classify_root_cause(_make_invoice("", purchase_order=""))
    assert "purchase order" in result["root_cause"].lower()


def test_unknown_blocking_reason():
    result = classify_root_cause(_make_invoice("Z"))
    assert "Z" in result["root_cause"]


def test_no_blocking_reason_with_po():
    result = classify_root_cause(_make_invoice("", purchase_order="4500000001"))
    assert "No blocking" in result["root_cause"] or "recorded" in result["root_cause"]
