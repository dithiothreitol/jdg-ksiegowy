"""Wysylka faktury mailem (SMTP). TLS/STARTTLS obowiazkowe.

Dla Gmail — trzeba uzyc 'hasla dla aplikacji' (App Password),
nie glownego hasla konta. https://support.google.com/accounts/answer/185833
"""

from __future__ import annotations

import logging
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from pathlib import Path

from jdg_ksiegowy.config import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SendResult:
    success: bool
    to: str
    subject: str
    error: str | None = None


DEFAULT_SUBJECT = "Faktura {number}"
DEFAULT_BODY = """Dzien dobry,

W zalaczeniu przesylam fakture {number} na kwote {gross} PLN brutto,
z terminem platnosci {due}.

Pozdrawiam,
{seller_name}
"""


def send_invoice_email(
    to: str,
    pdf_path: Path,
    invoice_number: str,
    gross_amount: str,
    payment_due: str,
    subject: str | None = None,
    body: str | None = None,
    cc: list[str] | None = None,
) -> SendResult:
    """Wyslij fakture PDF przez SMTP skonfigurowany w settings.smtp."""
    smtp = settings.smtp
    if not smtp.is_configured():
        return SendResult(
            success=False,
            to=to,
            subject=subject or "",
            error="SMTP nie skonfigurowany — ustaw SMTP_HOST, SMTP_USERNAME, SMTP_PASSWORD w .env",
        )
    if not pdf_path.exists():
        return SendResult(success=False, to=to, subject="", error=f"PDF nie istnieje: {pdf_path}")

    msg = EmailMessage()
    msg["From"] = smtp.from_addr or smtp.username
    msg["To"] = to
    if cc:
        msg["Cc"] = ", ".join(cc)
    msg["Subject"] = (subject or DEFAULT_SUBJECT).format(number=invoice_number)
    msg.set_content(
        (body or DEFAULT_BODY).format(
            number=invoice_number,
            gross=gross_amount,
            due=payment_due,
            seller_name=settings.seller.name,
        )
    )
    msg.add_attachment(
        pdf_path.read_bytes(),
        maintype="application",
        subtype="pdf",
        filename=pdf_path.name,
    )

    try:
        if smtp.use_ssl:
            with smtplib.SMTP_SSL(smtp.host, smtp.port, timeout=smtp.timeout) as server:
                server.login(smtp.username, smtp.password)
                server.send_message(msg)
        else:
            with smtplib.SMTP(smtp.host, smtp.port, timeout=smtp.timeout) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(smtp.username, smtp.password)
                server.send_message(msg)
    except (smtplib.SMTPException, OSError) as e:
        logger.exception("SMTP send failed")
        return SendResult(success=False, to=to, subject=msg["Subject"], error=str(e))

    return SendResult(success=True, to=to, subject=msg["Subject"])
