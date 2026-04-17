"""Testy mailera SMTP — bez realnego polaczenia."""

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def mailer_module():
    from jdg_ksiegowy.invoice import mailer

    return mailer


@pytest.fixture
def smtp_configured(monkeypatch):
    from jdg_ksiegowy.config import SMTPConfig, settings

    monkeypatch.setattr(
        settings,
        "smtp",
        SMTPConfig.model_construct(
            host="smtp.example.com",
            port=587,
            username="user@example.com",
            password="secret",
            from_addr="noreply@example.com",
            use_ssl=False,
            timeout=30.0,
        ),
    )


def test_returns_error_when_smtp_not_configured(mailer_module, tmp_path, monkeypatch):
    from jdg_ksiegowy.config import SMTPConfig, settings

    monkeypatch.setattr(settings, "smtp", SMTPConfig.model_construct())
    pdf = tmp_path / "f.pdf"
    pdf.write_bytes(b"%PDF-1.4")

    result = mailer_module.send_invoice_email(
        to="x@y.pl",
        pdf_path=pdf,
        invoice_number="A1/04/2026",
        gross_amount="100.00",
        payment_due="2026-05-01",
    )
    assert result.success is False
    assert "SMTP" in result.error


def test_returns_error_when_pdf_missing(smtp_configured, mailer_module, tmp_path):
    result = mailer_module.send_invoice_email(
        to="x@y.pl",
        pdf_path=tmp_path / "missing.pdf",
        invoice_number="A1/04/2026",
        gross_amount="100.00",
        payment_due="2026-05-01",
    )
    assert result.success is False
    assert "PDF nie istnieje" in result.error


def test_sends_via_starttls(smtp_configured, mailer_module, tmp_path):
    pdf = tmp_path / "f.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")

    with patch.object(mailer_module.smtplib, "SMTP") as smtp_class:
        ctx = MagicMock()
        smtp_class.return_value.__enter__.return_value = ctx

        result = mailer_module.send_invoice_email(
            to="kontrahent@firma.pl",
            pdf_path=pdf,
            invoice_number="A1/04/2026",
            gross_amount="123.45",
            payment_due="2026-05-01",
        )

    assert result.success is True
    assert result.to == "kontrahent@firma.pl"
    assert "A1/04/2026" in result.subject
    ctx.starttls.assert_called_once()
    ctx.login.assert_called_once_with("user@example.com", "secret")
    ctx.send_message.assert_called_once()
    sent_msg = ctx.send_message.call_args.args[0]
    assert sent_msg["From"] == "noreply@example.com"
    assert sent_msg["To"] == "kontrahent@firma.pl"


def test_sends_via_ssl_when_configured(smtp_configured, mailer_module, tmp_path, monkeypatch):
    from jdg_ksiegowy.config import settings

    monkeypatch.setattr(settings.smtp, "use_ssl", True)
    monkeypatch.setattr(settings.smtp, "port", 465)

    pdf = tmp_path / "f.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")

    with patch.object(mailer_module.smtplib, "SMTP_SSL") as ssl_class:
        ctx = MagicMock()
        ssl_class.return_value.__enter__.return_value = ctx

        result = mailer_module.send_invoice_email(
            to="x@y.pl",
            pdf_path=pdf,
            invoice_number="A2/04/2026",
            gross_amount="100.00",
            payment_due="2026-05-01",
        )

    assert result.success is True
    ssl_class.assert_called_once_with("smtp.example.com", 465, timeout=30.0)
    ctx.login.assert_called_once()


def test_handles_smtp_exception(smtp_configured, mailer_module, tmp_path):
    import smtplib

    pdf = tmp_path / "f.pdf"
    pdf.write_bytes(b"%PDF-1.4")

    with patch.object(mailer_module.smtplib, "SMTP") as smtp_class:
        ctx = MagicMock()
        smtp_class.return_value.__enter__.return_value = ctx
        ctx.send_message.side_effect = smtplib.SMTPRecipientsRefused(
            {"x@y.pl": (550, b"User unknown")}
        )

        result = mailer_module.send_invoice_email(
            to="x@y.pl",
            pdf_path=pdf,
            invoice_number="A3/04/2026",
            gross_amount="100.00",
            payment_due="2026-05-01",
        )

    assert result.success is False
    assert "User unknown" in result.error or "550" in result.error
