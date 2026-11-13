"""Wspolne fixtures + izolacja od srodowiska uzytkownika.

JDG_HOME wskazuje na pusty katalog tymczasowy, wiec testy nigdy nie czytaja
prawdziwego `.env` (z KSEF_ENV=prod) ani produkcyjnej bazy w `data/`. Zmienne
ustawiamy przez `=`, nie `setdefault` — musza wygrac ze srodowiskiem powloki.
"""

import os
import tempfile

# Musi byc PRZED importem jdg_ksiegowy.config — pydantic-settings czyta env przy instancjacji.
os.environ["JDG_HOME"] = tempfile.mkdtemp(prefix="jdg-test-home-")
os.environ["SELLER_NAME"] = "Test Sp. z o.o."
os.environ["SELLER_NIP"] = "1234567890"
os.environ["SELLER_ADDRESS"] = "ul. Testowa 1, 00-001 Warszawa"
os.environ["SELLER_BANK_ACCOUNT"] = "42 1140 0000 0000 0000 0000 0000"
os.environ["SELLER_BANK_NAME"] = "mBank"
os.environ["SELLER_FIRST_NAME"] = "Jan"
os.environ["SELLER_LAST_NAME"] = "Kowalski"
os.environ["SELLER_BIRTH_DATE"] = "1990-01-01"
os.environ["SELLER_TAX_OFFICE_CODE"] = "1471"
os.environ["SELLER_EMAIL"] = "test@example.com"
os.environ["KSEF_ENV"] = "test"
os.environ["KSEF_NIP"] = ""
os.environ["KSEF_TOKEN"] = ""
os.environ["MF_ENV"] = "test"
os.environ["MF_PESEL"] = ""
os.environ["MF_PRIOR_INCOME"] = "0"
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["GCAL_ENABLED"] = "false"
# ZUS — deterministycznie, niezaleznie od srodowiska uzytkownika
os.environ["SELLER_BUSINESS_START_DATE"] = ""
os.environ["SELLER_ZUS_SOCIAL_MODE"] = "auto"
os.environ["SELLER_EMPLOYMENT_GROSS_ABOVE_MIN"] = "false"
os.environ["SELLER_ZUS_VOLUNTARY_SICKNESS"] = "false"

import pytest


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    """Osobna baza SQLite per test — nadpisuje settings.db_url i resetuje silnik."""
    import jdg_ksiegowy.registry.db as db_module
    from jdg_ksiegowy.config import settings

    db_path = tmp_path / "jdg.db"
    monkeypatch.setattr(settings, "db_url", f"sqlite:///{db_path}")
    monkeypatch.setattr(db_module, "_engine", None)
    monkeypatch.setattr(db_module, "_SessionFactory", None)
    settings.mf.pesel = ""
    yield db_path


@pytest.fixture(autouse=True)
def _no_whitelist_network(monkeypatch):
    """Biala lista MF to siec — w testach domyslnie niedostepna (test moze nadpisac)."""
    from jdg_ksiegowy.invoice import whitelist

    def offline(nip, on, **kw):
        raise whitelist.WhiteListError("Biala lista niedostepna w testach")

    monkeypatch.setattr("jdg_ksiegowy.app.invoices.lookup", offline)
