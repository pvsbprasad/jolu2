"""
Email notification tool for the Missed Discount Analysis Agent.

Sends a summary table of the top-N at-risk/lost invoices ranked by discount value
to a list of recipient email addresses.

Delivery backends (tried in order):
  1. SAP BTP Alert Notification Service (ANS) — env vars: ANS_URL, ANS_CLIENT_ID, ANS_CLIENT_SECRET
  2. SMTP — env vars: SMTP_HOST, SMTP_PORT (default 587), SMTP_USER, SMTP_PASSWORD, SMTP_FROM

If neither backend is configured, a ConfigurationError is raised.
"""
import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

import requests

logger = logging.getLogger(__name__)


class ConfigurationError(Exception):
    """Raised when no email backend is configured."""


def _build_email_body(invoices: list[dict]) -> tuple[str, str]:
    """
    Build both plain-text and HTML versions of the notification email body.

    Returns:
        Tuple of (plain_text, html)
    """
    lines_plain = [
        "AP Discount Alert — At-Risk Invoices Summary",
        "=" * 50,
        "",
        f"{'Supplier':<20} {'Invoice':<15} {'Discount Amt':>14} {'Currency':<10} {'Deadline':<12} {'Status':<10}",
        "-" * 85,
    ]
    rows_html = []

    for inv in invoices:
        supplier = str(inv.get("InvoicingParty") or inv.get("supplier") or "N/A")
        invoice_no = str(inv.get("SupplierInvoice") or inv.get("invoice") or "N/A")
        amount = inv.get("discount1_amount") or inv.get("discount_amount") or 0.0
        currency = str(inv.get("DocumentCurrency") or inv.get("currency") or "")
        deadline = str(inv.get("discount1_deadline") or inv.get("discount_deadline") or "N/A")
        status = str(inv.get("discount_status") or inv.get("status") or "N/A")

        lines_plain.append(
            f"{supplier:<20} {invoice_no:<15} {amount:>14.2f} {currency:<10} {deadline:<12} {status:<10}"
        )
        rows_html.append(
            f"<tr><td>{supplier}</td><td>{invoice_no}</td>"
            f"<td style='text-align:right'>{amount:.2f}</td>"
            f"<td>{currency}</td><td>{deadline}</td>"
            f"<td><b>{status}</b></td></tr>"
        )

    plain = "\n".join(lines_plain)
    html = f"""
<html><body>
<h2>AP Discount Alert — At-Risk Invoices Summary</h2>
<table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse;font-family:Arial,sans-serif;font-size:13px">
  <thead style="background:#f0f0f0">
    <tr>
      <th>Supplier</th><th>Invoice</th><th>Discount Amount</th>
      <th>Currency</th><th>Deadline</th><th>Status</th>
    </tr>
  </thead>
  <tbody>
    {"".join(rows_html)}
  </tbody>
</table>
<p style="color:#888;font-size:11px">Sent by Missed Discount Analysis Agent</p>
</body></html>
"""
    return plain, html


def _send_via_ans(recipients: list[str], subject: str, plain: str) -> None:
    """Send notification via SAP BTP Alert Notification Service."""
    ans_url = os.environ["ANS_URL"].rstrip("/")
    client_id = os.environ["ANS_CLIENT_ID"]
    client_secret = os.environ["ANS_CLIENT_SECRET"]

    # Obtain OAuth2 token (client credentials)
    token_url = os.environ.get("ANS_TOKEN_URL", f"{ans_url}/oauth/token")
    token_resp = requests.post(
        token_url,
        data={"grant_type": "client_credentials"},
        auth=(client_id, client_secret),
        timeout=15,
    )
    token_resp.raise_for_status()
    access_token = token_resp.json()["access_token"]

    # Post event to ANS
    payload = {
        "eventType": "APDiscountAlert",
        "eventTimestamp": None,
        "severity": "WARNING",
        "category": "ALERT",
        "subject": subject,
        "body": plain,
        "priority": 2,
        "tags": {"ap_team_notification": "true"},
        "recipients": [{"type": "EMAIL", "address": r} for r in recipients],
    }
    post_url = f"{ans_url}/cf/producer/v1/resource-events"
    resp = requests.post(
        post_url,
        json=payload,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=15,
    )
    resp.raise_for_status()
    logger.info("ANS notification sent. Status: %s", resp.status_code)


def _send_via_smtp(recipients: list[str], subject: str, plain: str, html: str) -> None:
    """Send notification via SMTP."""
    host = os.environ["SMTP_HOST"]
    port = int(os.environ.get("SMTP_PORT", "587"))
    user = os.environ["SMTP_USER"]
    password = os.environ["SMTP_PASSWORD"]
    sender = os.environ.get("SMTP_FROM", user)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)
    msg.attach(MIMEText(plain, "plain"))
    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP(host, port) as server:
        server.ehlo()
        server.starttls()
        server.login(user, password)
        server.sendmail(sender, recipients, msg.as_string())

    logger.info("SMTP notification sent to %d recipient(s).", len(recipients))


def send_email_notification(
    recipients: list[str],
    invoices: list[dict[str, Any]],
    top_n: int = 10,
) -> dict[str, Any]:
    """
    Send an email notification with the top-N at-risk/lost invoices ranked by discount value.

    Args:
        recipients: List of recipient email addresses (provided by the user at invocation time).
        invoices:   Enriched invoice list (output of calculate_discount_analysis).
                    Only 'at_risk' and 'lost' invoices are included in the email.
        top_n:      Maximum number of invoices to include in the summary table (default 10).

    Returns:
        Dict with keys:
          - sent (bool): True if email was dispatched, False if skipped.
          - recipients (list[str]): Addresses the email was sent to (empty if not sent).
          - invoice_count (int): Number of invoices included in the email.
          - reason (str): Explanation when sent=False.

    Raises:
        ConfigurationError: If neither ANS nor SMTP is configured.
    """
    # Filter to at-risk and lost invoices only
    actionable = [
        inv for inv in invoices
        if inv.get("discount_status") in ("at_risk", "lost")
    ]

    if not actionable:
        logger.info("M6.missed: email notification not sent — no at-risk invoices found")
        return {
            "sent": False,
            "recipients": [],
            "invoice_count": 0,
            "reason": "no at-risk invoices found",
        }

    # Rank by discount amount descending, pick top-N
    ranked = sorted(actionable, key=lambda x: -(x.get("discount1_amount") or 0))
    top_invoices = ranked[:top_n]

    plain, html = _build_email_body(top_invoices)
    subject = f"AP Discount Alert: {len(top_invoices)} invoice(s) at risk of missing discount deadline"

    # Try ANS first, then SMTP
    ans_configured = all(
        os.environ.get(k) for k in ("ANS_URL", "ANS_CLIENT_ID", "ANS_CLIENT_SECRET")
    )
    smtp_configured = all(
        os.environ.get(k) for k in ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD")
    )

    if not ans_configured and not smtp_configured:
        raise ConfigurationError(
            "No email backend configured. Set ANS_URL/ANS_CLIENT_ID/ANS_CLIENT_SECRET "
            "for SAP BTP Alert Notification Service, or SMTP_HOST/SMTP_USER/SMTP_PASSWORD "
            "for SMTP delivery."
        )

    if ans_configured:
        _send_via_ans(recipients, subject, plain)
    else:
        _send_via_smtp(recipients, subject, plain, html)

    logger.info(
        "M6.achieved: email notification sent to %d recipient(s), top_n_invoices=%d",
        len(recipients),
        len(top_invoices),
    )

    return {
        "sent": True,
        "recipients": recipients,
        "invoice_count": len(top_invoices),
    }
