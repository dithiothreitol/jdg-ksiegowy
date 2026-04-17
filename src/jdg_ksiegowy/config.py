"""Konfiguracja aplikacji — Pydantic Settings z .env."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"


class SellerConfig(BaseSettings):
    """Dane sprzedawcy — konfigurowalne z .env."""

    model_config = SettingsConfigDict(
        env_prefix="SELLER_",
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Wszystkie pola maja domyslne puste wartosci — import settings bez .env
    # nie crashuje. Walidacja obecnosci zachodzi w jdg_ksiegowy.doctor oraz
    # w poszczegolnych modulach (np. JPK wymaga tax_office_code/birth_date).
    name: str = ""
    nip: str = ""
    address: str = ""
    bank_account: str = ""
    bank_name: str = ""
    email: str = ""  # email kontaktowy (wymagany dla JPK)
    tax_form: str = "ryczalt"  # ryczalt | zasady_ogolne | liniowy
    ryczalt_rate: Decimal = Decimal("12")  # stawka ryczaltu (%)
    vat_rate: Decimal = Decimal("23")  # stawka VAT (%)
    vat_exempt: bool = False  # zwolnienie podmiotowe z VAT (do 200k PLN)

    # Dane osobowe (wymagane dla JPK_V7M — skill jpk-generator)
    first_name: str = ""
    last_name: str = ""
    birth_date: str = ""  # YYYY-MM-DD
    tax_office_code: str = ""  # np. 1471 = US Warszawa-Ursynow

    @property
    def bank_account_raw(self) -> str:
        """Numer konta bez spacji (do XML KSeF / JPK)."""
        return self.bank_account.replace(" ", "")


class SMTPConfig(BaseSettings):
    """Konfiguracja SMTP do wysylki faktur emailem."""

    model_config = SettingsConfigDict(
        env_prefix="SMTP_",
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    host: str = ""
    port: int = 587  # 465 dla SSL, 587 dla STARTTLS
    username: str = ""
    password: str = ""
    from_addr: str = Field(default="", alias="SMTP_FROM")  # jesli pusty, uzywa username
    use_ssl: bool = False  # True dla portu 465, False dla 587 (STARTTLS)
    timeout: float = 30.0

    def is_configured(self) -> bool:
        return bool(self.host and self.username and self.password)


class OCRConfig(BaseSettings):
    """Konfiguracja OCR faktur zakupu (Pixtral lokalny + Claude API fallback)."""

    model_config = SettingsConfigDict(
        env_prefix="OCR_",
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    provider: str = "auto"  # auto | ollama | claude
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "pixtral:12b"
    ollama_timeout: float = 120.0  # CPU inference moze byc wolna
    claude_model: str = "claude-haiku-4-5-20251001"
    claude_max_tokens: int = 1024


class MFGatewayConfig(BaseSettings):
    """Konfiguracja bramki MF dla JPK_V7M / JPK_EWP (autoryzacja danymi)."""

    model_config = SettingsConfigDict(
        env_prefix="MF_",
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: str = "test"  # test | prod
    pesel: str = ""
    prior_income: Decimal = Decimal("0")  # kwota przychodu z PIT za rok N-2
    cert_path: str | None = None  # lokalny PEM (override automatycznego pobierania)
    cert_url: str | None = None  # override URL-a skad pobierac klucz publiczny MF
    cert_ttl_days: int = 30  # jak czesto sprawdzac rotacje klucza MF

    @property
    def base_url(self) -> str:
        return {
            "prod": "https://e-dokumenty.mf.gov.pl",
            "test": "https://test-e-dokumenty.mf.gov.pl",
        }[self.env]

    def is_configured(self) -> bool:
        return bool(self.pesel) and self.prior_income >= Decimal("0")


class KSeFConfig(BaseSettings):
    """Konfiguracja KSeF API."""

    model_config = SettingsConfigDict(
        env_prefix="KSEF_",
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: str = "test"  # test | demo | prod
    nip: str = ""
    token: str = ""
    cert_path: str | None = None

    @property
    def base_url(self) -> str:
        urls = {
            "prod": "https://ksef.mf.gov.pl/api",
            "test": "https://ksef-test.mf.gov.pl/api",
            "demo": "https://ksef-demo.mf.gov.pl/api",
        }
        return urls[self.env]


class Settings(BaseSettings):
    """Glowna konfiguracja aplikacji."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    seller: SellerConfig = SellerConfig()
    ksef: KSeFConfig = KSeFConfig()
    mf: MFGatewayConfig = MFGatewayConfig()
    ocr: OCRConfig = OCRConfig()
    smtp: SMTPConfig = SMTPConfig()
    anthropic_api_key: str = ""

    db_url: str = f"sqlite:///{DATA_DIR / 'jdg_ksiegowy.db'}"


settings = Settings()
