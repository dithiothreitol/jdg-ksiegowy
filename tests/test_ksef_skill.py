"""Skrypt wysylki KSeF: kolejnosc sprawdzen, zapis numeru KSeF i UPO, guardy."""

import importlib.util
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from jdg_ksiegowy.ksef.client import KSeFResult
from jdg_ksiegowy.registry.repository import InvoiceRepository
from tests.helpers import InvoiceRow, save_invoice

REPO_ROOT = Path(__file__).resolve().parent.parent
KSEF_SUBMIT = REPO_ROOT / "skills" / "ksef" / "scripts" / "submit.py"

_spec = importlib.util.spec_from_file_location("ksef_submit", KSEF_SUBMIT)
ksef_submit = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ksef_submit)

FA3_NS = "http://crd.gov.pl/wzor/2025/06/25/13775/"
KSEF_NUMBER = "5260250274-20260601-0A1B2C-3D4E5F-6A"


def _xml_with_number(number: str) -> str:
    return f'<Faktura xmlns="{FA3_NS}"><Fa><P_2>{number}</P_2></Fa></Faktura>'


def _seed_invoice(number: str, *, ksef_number: str | None = None):
    save_invoice(
        InvoiceRow(
            id=f"id-{number}",
            number=number,
            issue_date=date(2026, 6, 1),
            sale_date=date(2026, 5, 31),
            payment_due=date(2026, 6, 10),
            total_net=Decimal("100"),
            status="sent_ksef" if ksef_number else "generated",
            ksef_number=ksef_number,
        )
    )


def _configure_ksef(monkeypatch):
    from jdg_ksiegowy.config import settings

    monkeypatch.setattr(settings.ksef, "nip", "1234567890")
    monkeypatch.setattr(settings.ksef, "env", "test")


def _fake_send(result: KSeFResult, calls: list):
    def send(self, xml_content):
        calls.append(xml_content)
        return result

    return send


def test_submit_returns_error_for_missing_xml():
    result = ksef_submit.submit("nieistniejacy.xml")
    assert result["success"] is False
    assert "nie istnieje" in result["error"].lower()


def test_submit_returns_error_when_not_configured(tmp_path, monkeypatch):
    from jdg_ksiegowy.config import settings

    monkeypatch.setattr(settings.ksef, "token", "")
    monkeypatch.setattr(settings.ksef, "env", "prod")
    xml_file = tmp_path / "fake.xml"
    xml_file.write_text("<Faktura/>", encoding="utf-8")

    result = ksef_submit.submit(str(xml_file))

    assert result["success"] is False
    assert "KSEF_TOKEN" in result["error"]


def test_submit_persists_ksef_number_and_upo(tmp_path, monkeypatch, isolated_db):
    """Po udanej wysylce do rejestru trafia numer KSeF (nie numer referencyjny) i UPO."""
    _configure_ksef(monkeypatch)
    monkeypatch.setattr(ksef_submit, "DATA_DIR", tmp_path / "data")
    _seed_invoice("A9/06/2026")
    calls: list = []
    acquired = datetime(2026, 6, 1, 10, 30)
    monkeypatch.setattr(
        ksef_submit.KSeFClient,
        "send_invoice",
        _fake_send(
            KSeFResult(
                success=True,
                env="test",
                reference_number="20260601-EE-REF",
                ksef_number=KSEF_NUMBER,
                acquired_at=acquired,
                upo=b"<UPO/>",
            ),
            calls,
        ),
    )
    xml_file = tmp_path / "faktura.xml"
    xml_file.write_text(_xml_with_number("A9/06/2026"), encoding="utf-8")

    result = ksef_submit.submit(str(xml_file))

    assert result["success"] is True and result["registered"] is True
    assert result["ksef_number"] == KSEF_NUMBER
    assert Path(result["upo_path"]).read_bytes() == b"<UPO/>"

    inv = InvoiceRepository().get("A9/06/2026")
    assert inv.status == "sent_ksef"
    assert inv.ksef_number == KSEF_NUMBER
    assert inv.ksef_reference == "20260601-EE-REF"
    assert inv.ksef_acquired_at == acquired


def test_submit_refuses_already_sent_invoice(tmp_path, monkeypatch, isolated_db):
    """Guard przed dublem: faktura z numerem KSeF nie jest wysylana ponownie."""
    _configure_ksef(monkeypatch)
    _seed_invoice("A8/06/2026", ksef_number=KSEF_NUMBER)
    calls: list = []
    monkeypatch.setattr(
        ksef_submit.KSeFClient, "send_invoice", _fake_send(KSeFResult(True, "test"), calls)
    )
    xml_file = tmp_path / "faktura.xml"
    xml_file.write_text(_xml_with_number("A8/06/2026"), encoding="utf-8")

    result = ksef_submit.submit(str(xml_file))

    assert result["success"] is False
    assert result["ksef_number"] == KSEF_NUMBER
    assert "juz wyslana" in result["error"]
    assert calls == [], "Nie wolno wysylac faktury z istniejacym numerem KSeF"


def test_submit_refuses_invoice_not_in_registry(tmp_path, monkeypatch, isolated_db):
    """XML spoza rejestru NIE jest wysylany — inaczej faktura wypadlaby z JPK/VAT."""
    _configure_ksef(monkeypatch)
    calls: list = []
    monkeypatch.setattr(
        ksef_submit.KSeFClient, "send_invoice", _fake_send(KSeFResult(True, "test"), calls)
    )
    xml_file = tmp_path / "faktura.xml"
    xml_file.write_text(_xml_with_number("OBCY/01/2026"), encoding="utf-8")

    result = ksef_submit.submit(str(xml_file))

    assert result["success"] is False
    assert "rejestrze" in result["error"].lower()
    assert calls == [], "Nie wolno wysylac faktury spoza rejestru"


def test_failed_send_does_not_mark_invoice(tmp_path, monkeypatch, isolated_db):
    _configure_ksef(monkeypatch)
    _seed_invoice("A7/06/2026")
    monkeypatch.setattr(
        ksef_submit.KSeFClient,
        "send_invoice",
        _fake_send(KSeFResult(success=False, env="test", error="odrzucona"), []),
    )
    xml_file = tmp_path / "faktura.xml"
    xml_file.write_text(_xml_with_number("A7/06/2026"), encoding="utf-8")

    result = ksef_submit.submit(str(xml_file))

    assert result["success"] is False and result["registered"] is False
    inv = InvoiceRepository().get("A7/06/2026")
    assert inv.ksef_number is None and inv.ksef_reference is None
