"""Test skilla KSeF — order-of-checks, sensowne errory bez tokena/pliku."""

import asyncio
import importlib.util
from datetime import date
from decimal import Decimal
from pathlib import Path

from jdg_ksiegowy.ksef.client import KSeFResult

REPO_ROOT = Path(__file__).resolve().parent.parent
KSEF_SUBMIT = REPO_ROOT / "skills" / "ksef" / "scripts" / "submit.py"

_spec = importlib.util.spec_from_file_location("ksef_submit", KSEF_SUBMIT)
ksef_submit = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ksef_submit)

FA3_NS = "http://crd.gov.pl/wzor/2025/06/25/13775/"


def _xml_with_number(number: str) -> str:
    return f'<Faktura xmlns="{FA3_NS}"><Fa><P_2>{number}</P_2></Fa></Faktura>'


def _seed_invoice(number: str, *, ksef_reference: str | None = None):
    from jdg_ksiegowy.registry.db import InvoiceRecord, init_db, save_invoice

    init_db()
    save_invoice(
        InvoiceRecord(
            id=f"id-{number}",
            number=number,
            issue_date=date(2026, 6, 1),
            sale_date=date(2026, 5, 31),
            payment_due=date(2026, 6, 10),
            buyer_name="Klient",
            buyer_nip="5260250274",
            total_net=Decimal("100"),
            total_vat=Decimal("23"),
            total_gross=Decimal("123"),
            vat_rate=Decimal("23"),
            status="sent_ksef" if ksef_reference else "generated",
            ksef_reference=ksef_reference,
        )
    )


def _configure_ksef(monkeypatch):
    from jdg_ksiegowy.config import settings

    monkeypatch.setattr(settings.ksef, "nip", "1234567890")
    monkeypatch.setattr(settings.ksef, "env", "test")


def test_submit_returns_error_for_missing_xml(monkeypatch):
    monkeypatch.delenv("KSEF_TOKEN", raising=False)
    monkeypatch.delenv("KSEF_NIP", raising=False)

    result = asyncio.run(ksef_submit.submit("nieistniejacy.xml"))

    assert result["success"] is False
    assert "nie istnieje" in result["error"].lower()


def test_submit_returns_error_when_not_configured(tmp_path, monkeypatch):
    from jdg_ksiegowy.config import settings

    monkeypatch.setattr(settings.ksef, "nip", "")
    monkeypatch.setattr(settings.ksef, "token", "")
    monkeypatch.setattr(settings.ksef, "env", "prod")
    xml_file = tmp_path / "fake.xml"
    xml_file.write_text("<Faktura/>", encoding="utf-8")

    result = asyncio.run(ksef_submit.submit(str(xml_file)))

    assert result["success"] is False
    assert "KSEF_TOKEN" in result["error"]


def test_submit_persists_reference_on_success(tmp_path, monkeypatch, isolated_db):
    """Po udanej wysyłce numer referencyjny i status trafiają do rejestru."""
    from jdg_ksiegowy.registry.db import get_invoice_by_number

    _configure_ksef(monkeypatch)
    _seed_invoice("A9/06/2026")

    async def fake_send(self, xml_content):
        return KSeFResult(success=True, reference_number="REF-123", details={"env": "test"})

    monkeypatch.setattr(ksef_submit.KSeFClient, "send_invoice", fake_send)

    xml_file = tmp_path / "faktura.xml"
    xml_file.write_text(_xml_with_number("A9/06/2026"), encoding="utf-8")

    result = asyncio.run(ksef_submit.submit(str(xml_file)))

    assert result["success"] is True
    assert result["registered"] is True
    assert result["reference_number"] == "REF-123"

    inv = get_invoice_by_number("A9/06/2026")
    assert inv.status == "sent_ksef"
    assert inv.ksef_reference == "REF-123"
    assert inv.ksef_sent_at is not None


def test_submit_refuses_already_sent_invoice(tmp_path, monkeypatch, isolated_db):
    """Guard przed dublem: faktura z numerem KSeF nie jest wysyłana ponownie."""
    _configure_ksef(monkeypatch)
    _seed_invoice("A8/06/2026", ksef_reference="REF-EXISTING")

    called = False

    async def fake_send(self, xml_content):
        nonlocal called
        called = True
        return KSeFResult(success=True, reference_number="REF-NEW")

    monkeypatch.setattr(ksef_submit.KSeFClient, "send_invoice", fake_send)

    xml_file = tmp_path / "faktura.xml"
    xml_file.write_text(_xml_with_number("A8/06/2026"), encoding="utf-8")

    result = asyncio.run(ksef_submit.submit(str(xml_file)))

    assert result["success"] is False
    assert result["reference_number"] == "REF-EXISTING"
    assert "już wysłana" in result["error"]
    assert called is False, "Nie wolno wysyłać faktury z istniejącym numerem KSeF"


def test_submit_refuses_invoice_not_in_registry(tmp_path, monkeypatch, isolated_db):
    """XML spoza rejestru NIE jest wysyłany — inaczej faktura wypadłaby z JPK/VAT."""
    from jdg_ksiegowy.registry.db import init_db

    _configure_ksef(monkeypatch)
    init_db()

    called = False

    async def fake_send(self, xml_content):
        nonlocal called
        called = True
        return KSeFResult(success=True, reference_number="REF-XYZ", details={"env": "test"})

    monkeypatch.setattr(ksef_submit.KSeFClient, "send_invoice", fake_send)

    xml_file = tmp_path / "faktura.xml"
    xml_file.write_text(_xml_with_number("OBCY/01/2026"), encoding="utf-8")

    result = asyncio.run(ksef_submit.submit(str(xml_file)))

    assert result["success"] is False
    assert "rejestrze" in result["error"].lower()
    assert called is False, "Nie wolno wysyłać faktury spoza rejestru"
