"""
Tests for the send_email_notification tool.

Covers:
  1. Email sent when at-risk invoices are present and recipients are provided
  2. No email sent when no at-risk/lost invoices exist
  3. SMTP fallback used when ANS is not configured
  4. ConfigurationError raised when neither ANS nor SMTP is configured
"""
import smtplib
from unittest.mock import MagicMock, patch

import pytest

from app.tools.email_notification import ConfigurationError, send_email_notification

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

AT_RISK_INVOICE = {
    "SupplierInvoice": "INV-001",
    "FiscalYear": "2026",
    "InvoicingParty": "Supplier A",
    "CompanyCode": "1000",
    "InvoiceGrossAmount": 10000.0,
    "DocumentCurrency": "USD",
    "CashDiscount1Percent": 2.0,
    "CashDiscount1Days": 10,
    "DueCalculationBaseDate": "2026-08-01",
    "PaymentBlockingReason": "R",
    "discount1_amount": 200.0,
    "discount1_deadline": "2026-08-11",
    "days_remaining": 1,
    "discount_status": "at_risk",
}

LOST_INVOICE = {
    **AT_RISK_INVOICE,
    "SupplierInvoice": "INV-002",
    "discount_status": "lost",
    "days_remaining": -5,
    "discount1_amount": 150.0,
}

SAFE_INVOICE = {
    **AT_RISK_INVOICE,
    "SupplierInvoice": "INV-003",
    "discount_status": "safe",
    "days_remaining": 20,
    "discount1_amount": 100.0,
}

RECIPIENTS = ["ap-team@example.com"]


# ---------------------------------------------------------------------------
# Test 1: Email sent via ANS when at-risk invoices are present
# ---------------------------------------------------------------------------

def test_email_sent_via_ans_when_at_risk_invoices_present(monkeypatch):
    """Email is dispatched via ANS when at-risk invoices exist and recipients are provided."""
    monkeypatch.setenv("ANS_URL", "https://ans.example.com")
    monkeypatch.setenv("ANS_CLIENT_ID", "client-id")
    monkeypatch.setenv("ANS_CLIENT_SECRET", "secret")
    monkeypatch.setenv("ANS_TOKEN_URL", "https://ans.example.com/oauth/token")

    mock_token_resp = MagicMock()
    mock_token_resp.json.return_value = {"access_token": "test-token"}
    mock_token_resp.raise_for_status = MagicMock()

    mock_post_resp = MagicMock()
    mock_post_resp.status_code = 202
    mock_post_resp.raise_for_status = MagicMock()

    with patch("app.tools.email_notification.requests.post") as mock_post:
        mock_post.side_effect = [mock_token_resp, mock_post_resp]

        result = send_email_notification(
            recipients=RECIPIENTS,
            invoices=[AT_RISK_INVOICE, SAFE_INVOICE],
            top_n=10,
        )

    assert result["sent"] is True
    assert result["recipients"] == RECIPIENTS
    assert result["invoice_count"] == 1  # only AT_RISK, not SAFE
    assert mock_post.call_count == 2  # token + event


# ---------------------------------------------------------------------------
# Test 2: No email sent when no at-risk/lost invoices
# ---------------------------------------------------------------------------

def test_no_email_sent_when_no_at_risk_invoices(monkeypatch):
    """Email is NOT sent when no at-risk or lost invoices are in the list."""
    monkeypatch.setenv("ANS_URL", "https://ans.example.com")
    monkeypatch.setenv("ANS_CLIENT_ID", "client-id")
    monkeypatch.setenv("ANS_CLIENT_SECRET", "secret")

    result = send_email_notification(
        recipients=RECIPIENTS,
        invoices=[SAFE_INVOICE],
        top_n=10,
    )

    assert result["sent"] is False
    assert result["recipients"] == []
    assert result["invoice_count"] == 0
    assert "no at-risk invoices" in result["reason"]


# ---------------------------------------------------------------------------
# Test 3: SMTP fallback when ANS is not configured
# ---------------------------------------------------------------------------

def test_smtp_fallback_when_ans_not_configured(monkeypatch):
    """SMTP is used as a fallback when ANS environment variables are absent."""
    # Remove any ANS vars that might be set
    for key in ("ANS_URL", "ANS_CLIENT_ID", "ANS_CLIENT_SECRET"):
        monkeypatch.delenv(key, raising=False)

    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USER", "sender@example.com")
    monkeypatch.setenv("SMTP_PASSWORD", "smtp-secret")

    mock_smtp_instance = MagicMock()
    mock_smtp_cls = MagicMock(return_value=mock_smtp_instance)
    mock_smtp_instance.__enter__ = MagicMock(return_value=mock_smtp_instance)
    mock_smtp_instance.__exit__ = MagicMock(return_value=False)

    with patch("app.tools.email_notification.smtplib.SMTP", mock_smtp_cls):
        result = send_email_notification(
            recipients=RECIPIENTS,
            invoices=[AT_RISK_INVOICE, LOST_INVOICE],
            top_n=10,
        )

    assert result["sent"] is True
    assert result["recipients"] == RECIPIENTS
    assert result["invoice_count"] == 2
    mock_smtp_instance.sendmail.assert_called_once()


# ---------------------------------------------------------------------------
# Test 4: ConfigurationError when neither ANS nor SMTP is configured
# ---------------------------------------------------------------------------

def test_raises_configuration_error_when_no_backend_configured(monkeypatch):
    """ConfigurationError is raised when neither ANS nor SMTP env vars are set."""
    for key in ("ANS_URL", "ANS_CLIENT_ID", "ANS_CLIENT_SECRET",
                "SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD"):
        monkeypatch.delenv(key, raising=False)

    with pytest.raises(ConfigurationError, match="No email backend configured"):
        send_email_notification(
            recipients=RECIPIENTS,
            invoices=[AT_RISK_INVOICE],
            top_n=10,
        )


# ---------------------------------------------------------------------------
# Test 5: top_n correctly limits the number of invoices in the email
# ---------------------------------------------------------------------------

def test_top_n_limits_invoices_in_email(monkeypatch):
    """Only top_n invoices (ranked by discount amount) are included in the email."""
    monkeypatch.setenv("ANS_URL", "https://ans.example.com")
    monkeypatch.setenv("ANS_CLIENT_ID", "client-id")
    monkeypatch.setenv("ANS_CLIENT_SECRET", "secret")
    monkeypatch.setenv("ANS_TOKEN_URL", "https://ans.example.com/oauth/token")

    # Create 5 at-risk invoices with varying discount amounts
    invoices = [
        {**AT_RISK_INVOICE, "SupplierInvoice": f"INV-{i}", "discount1_amount": float(i * 50)}
        for i in range(1, 6)
    ]

    mock_token_resp = MagicMock()
    mock_token_resp.json.return_value = {"access_token": "test-token"}
    mock_token_resp.raise_for_status = MagicMock()

    mock_post_resp = MagicMock()
    mock_post_resp.status_code = 202
    mock_post_resp.raise_for_status = MagicMock()

    with patch("app.tools.email_notification.requests.post") as mock_post:
        mock_post.side_effect = [mock_token_resp, mock_post_resp]

        result = send_email_notification(
            recipients=RECIPIENTS,
            invoices=invoices,
            top_n=3,
        )

    assert result["sent"] is True
    assert result["invoice_count"] == 3  # limited by top_n=3
