"""Testy doctor — preflight check konfiguracji."""

import pytest

from jdg_ksiegowy.doctor import DoctorReport, format_report, run_doctor


@pytest.fixture
def fresh_settings():
    """Przygotuj czyste settings — każdy test ustawia swoje env."""
    from jdg_ksiegowy.config import settings

    # Domyślne wartości z conftest są ustawione — nie resetujemy pól wymaganych
    original_pesel = settings.mf.pesel
    original_cert = settings.mf.cert_path
    original_cert_url = settings.mf.cert_url
    original_ksef_token = settings.ksef.token
    original_smtp_host = settings.smtp.host
    yield settings
    settings.mf.pesel = original_pesel
    settings.mf.cert_path = original_cert
    settings.mf.cert_url = original_cert_url
    settings.ksef.token = original_ksef_token
    settings.smtp.host = original_smtp_host


class TestRunDoctor:
    def test_returns_report_with_findings(self, fresh_settings):
        report = run_doctor()
        assert isinstance(report, DoctorReport)
        assert len(report.findings) > 0

    def test_valid_seller_nip_is_ok(self, fresh_settings):
        fresh_settings.seller.nip = "5260250274"
        report = run_doctor()
        seller_oks = [f for f in report.findings if f.area == "seller" and f.level == "ok"]
        assert any("NIP poprawny" in f.message for f in seller_oks)

    def test_invalid_seller_nip_is_error(self, fresh_settings):
        # 10 cyfr, ale zła suma kontrolna
        fresh_settings.seller.nip = "5260250270"
        report = run_doctor()
        assert any(f.level == "error" and "NIP nieprawidłowy" in f.message for f in report.findings)

    def test_valid_mf_pesel_no_error(self, fresh_settings):
        fresh_settings.mf.pesel = "44051401458"
        report = run_doctor()
        pesel_errors = [
            f
            for f in report.findings
            if f.area == "mf" and "PESEL" in f.message and f.level == "error"
        ]
        assert len(pesel_errors) == 0

    def test_invalid_mf_pesel_is_error(self, fresh_settings):
        fresh_settings.mf.pesel = "44051401457"  # zła suma kontrolna
        report = run_doctor()
        assert any(
            f.level == "error" and "PESEL nieprawidłowy" in f.message for f in report.findings
        )

    def test_missing_mf_cert_is_warn(self, fresh_settings):
        fresh_settings.mf.cert_path = None
        fresh_settings.mf.cert_url = None
        report = run_doctor()
        assert any(f.level == "warn" and "CERT" in f.message for f in report.findings)

    def test_mf_cert_url_set_is_ok(self, fresh_settings):
        fresh_settings.mf.cert_path = None
        fresh_settings.mf.cert_url = "https://example.com/cert.pem"
        report = run_doctor()
        mf_findings = [f for f in report.findings if f.area == "mf"]
        assert any(f.level == "ok" and "CERT_URL" in f.message for f in mf_findings)

    def test_mf_cert_path_not_existing_is_error(self, fresh_settings):
        fresh_settings.mf.cert_path = "/nonexistent/cert.pem"
        report = run_doctor()
        assert any(f.level == "error" and "CERT_PATH" in f.message for f in report.findings)

    def test_smtp_not_configured_is_warn_only(self, fresh_settings):
        fresh_settings.smtp.host = ""
        report = run_doctor()
        smtp_errors = [f for f in report.findings if f.area == "smtp" and f.level == "error"]
        assert smtp_errors == []
        smtp_warns = [f for f in report.findings if f.area == "smtp" and f.level == "warn"]
        assert len(smtp_warns) >= 1

    def test_is_ready_for_returns_true_without_errors(self, fresh_settings):
        fresh_settings.seller.nip = "5260250274"
        fresh_settings.mf.pesel = "44051401458"
        fresh_settings.mf.cert_url = "https://example.com/cert.pem"
        fresh_settings.mf.cert_path = None
        report = run_doctor()
        assert report.is_ready_for("mf") is True

    def test_is_ready_for_returns_false_with_errors(self, fresh_settings):
        fresh_settings.mf.pesel = "44051401457"  # zły PESEL
        report = run_doctor()
        assert report.is_ready_for("mf") is False


class TestFormatReport:
    def test_contains_all_sections(self, fresh_settings):
        report = run_doctor()
        text = format_report(report)
        assert "[SELLER]" in text
        assert "[KSEF]" in text
        assert "[MF]" in text

    def test_contains_summary(self, fresh_settings):
        report = run_doctor()
        text = format_report(report)
        assert "Podsumowanie" in text
        assert "Gotowość" in text
