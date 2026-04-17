"""Doctor — preflight check konfiguracji przed wysyłką do sandboxów.

Sprawdza:
- dane sprzedawcy (wymagane dla faktury + JPK)
- konfigurację KSeF (NIP, token, env)
- konfigurację bramki MF (PESEL, prior_income, cert)
- SMTP, OCR (opcjonalne)
- dostępność plików certyfikatów / kluczy

Nie dotyka sieci — to czysta walidacja lokalnej konfiguracji.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from jdg_ksiegowy.config import settings
from jdg_ksiegowy.validators import validate_nip, validate_pesel


@dataclass
class Finding:
    level: str          # "ok" | "warn" | "error"
    area: str           # "seller" | "ksef" | "mf" | "smtp" | "ocr"
    message: str


@dataclass
class DoctorReport:
    findings: list[Finding] = field(default_factory=list)

    @property
    def errors(self) -> list[Finding]:
        return [f for f in self.findings if f.level == "error"]

    @property
    def warnings(self) -> list[Finding]:
        return [f for f in self.findings if f.level == "warn"]

    @property
    def ok_count(self) -> int:
        return sum(1 for f in self.findings if f.level == "ok")

    def is_ready_for(self, area: str) -> bool:
        """True gdy brak błędów w danym obszarze."""
        return not any(f.level == "error" and f.area == area for f in self.findings)


def _check_seller(report: DoctorReport) -> None:
    s = settings.seller
    area = "seller"
    if not s.name:
        report.findings.append(Finding("error", area, "SELLER_NAME pusty"))
    if not s.nip:
        report.findings.append(Finding("error", area, "SELLER_NIP pusty"))
    elif not validate_nip(s.nip):
        report.findings.append(Finding("error", area, f"SELLER_NIP nieprawidłowy (suma kontrolna): {s.nip}"))
    else:
        report.findings.append(Finding("ok", area, f"NIP poprawny: {s.nip}"))
    if not s.address:
        report.findings.append(Finding("error", area, "SELLER_ADDRESS pusty"))
    if not s.bank_account:
        report.findings.append(Finding("error", area, "SELLER_BANK_ACCOUNT pusty"))
    if not s.email:
        report.findings.append(Finding("warn", area, "SELLER_EMAIL pusty — wymagany dla JPK"))
    if not (s.first_name and s.last_name):
        report.findings.append(Finding("warn", area, "SELLER_FIRST_NAME/LAST_NAME puste — wymagane dla JPK_V7M"))
    if not s.birth_date:
        report.findings.append(Finding("warn", area, "SELLER_BIRTH_DATE pusta — wymagana dla JPK_V7M"))
    else:
        try:
            date.fromisoformat(s.birth_date)
        except ValueError:
            report.findings.append(Finding("error", area, f"SELLER_BIRTH_DATE zły format (YYYY-MM-DD): {s.birth_date}"))
    if not s.tax_office_code:
        report.findings.append(Finding("warn", area, "SELLER_TAX_OFFICE_CODE pusty — wymagany dla JPK"))


def _check_ksef(report: DoctorReport) -> None:
    k = settings.ksef
    area = "ksef"
    if k.env not in {"test", "demo", "prod"}:
        report.findings.append(Finding("error", area, f"KSEF_ENV musi być test/demo/prod, jest: {k.env}"))
        return
    report.findings.append(Finding("ok", area, f"KSEF_ENV={k.env} (URL: {k.base_url})"))
    effective_nip = k.nip or settings.seller.nip
    if not effective_nip:
        report.findings.append(Finding("error", area, "KSEF_NIP pusty i SELLER_NIP też"))
    elif not k.token:
        report.findings.append(Finding("warn", area, "KSEF_TOKEN pusty — wysyłka do KSeF nie zadziała"))
    else:
        report.findings.append(Finding("ok", area, "KSEF NIP + token obecne"))


def _check_mf(report: DoctorReport) -> None:
    m = settings.mf
    area = "mf"
    if m.env not in {"test", "prod"}:
        report.findings.append(Finding("error", area, f"MF_ENV musi być test/prod, jest: {m.env}"))
        return
    report.findings.append(Finding("ok", area, f"MF_ENV={m.env} (URL: {m.base_url})"))
    if not m.pesel:
        report.findings.append(Finding("warn", area, "MF_PESEL pusty — wysyłka JPK nie zadziała"))
    elif not validate_pesel(m.pesel):
        report.findings.append(Finding("error", area, f"MF_PESEL nieprawidłowy (suma kontrolna)"))
    if m.cert_path:
        p = Path(m.cert_path)
        if not p.exists():
            report.findings.append(Finding("error", area, f"MF_CERT_PATH plik nie istnieje: {p}"))
        else:
            report.findings.append(Finding("ok", area, f"MF_CERT_PATH obecny: {p}"))
    elif m.cert_url:
        report.findings.append(Finding("ok", area, f"MF_CERT_URL ustawiony: {m.cert_url}"))
    else:
        report.findings.append(Finding("warn", area, "MF_CERT_PATH/URL puste — wysyłka JPK nie zadziała"))


def _check_smtp(report: DoctorReport) -> None:
    s = settings.smtp
    area = "smtp"
    if not s.host:
        report.findings.append(Finding("warn", area, "SMTP nie skonfigurowany (wysyłka email nieaktywna)"))
        return
    if not (s.username and s.password):
        report.findings.append(Finding("warn", area, "SMTP host jest, brak username/password"))
    else:
        report.findings.append(Finding("ok", area, f"SMTP skonfigurowany: {s.host}:{s.port}"))


def _check_ocr(report: DoctorReport) -> None:
    o = settings.ocr
    area = "ocr"
    if o.provider not in {"auto", "ollama", "claude"}:
        report.findings.append(Finding("error", area, f"OCR_PROVIDER musi być auto/ollama/claude, jest: {o.provider}"))
        return
    has_claude_key = bool(settings.anthropic_api_key)
    if o.provider == "claude" and not has_claude_key:
        report.findings.append(Finding("error", area, "OCR_PROVIDER=claude wymaga ANTHROPIC_API_KEY"))
    else:
        details = f"provider={o.provider}"
        if o.provider in {"ollama", "auto"}:
            details += f", ollama={o.ollama_url} ({o.ollama_model})"
        if has_claude_key:
            details += ", claude_api_key=set"
        report.findings.append(Finding("ok", area, details))


def run_doctor() -> DoctorReport:
    """Uruchom komplet preflight-check'ów. Nie dotyka sieci."""
    report = DoctorReport()
    _check_seller(report)
    _check_ksef(report)
    _check_mf(report)
    _check_smtp(report)
    _check_ocr(report)
    return report


def format_report(report: DoctorReport) -> str:
    """Sformatuj raport doktora jako czytelny tekst."""
    lines = ["=== Doctor JDG — preflight check ===", ""]
    areas_order = ["seller", "ksef", "mf", "smtp", "ocr"]
    for area in areas_order:
        area_findings = [f for f in report.findings if f.area == area]
        if not area_findings:
            continue
        lines.append(f"[{area.upper()}]")
        for f in area_findings:
            marker = {"ok": " OK  ", "warn": "WARN ", "error": "ERROR"}[f.level]
            lines.append(f"  {marker} {f.message}")
        lines.append("")
    lines.append("-" * 40)
    lines.append(
        f"Podsumowanie: {report.ok_count} OK, "
        f"{len(report.warnings)} ostrzeżeń, {len(report.errors)} błędów"
    )
    if report.errors:
        lines.append("Gotowość: BRAK (napraw błędy przed wysyłką)")
    elif report.warnings:
        lines.append("Gotowość: CZĘŚCIOWA (ostrzeżenia pokazują brakujące obszary)")
    else:
        lines.append("Gotowość: PEŁNA")
    return "\n".join(lines)
