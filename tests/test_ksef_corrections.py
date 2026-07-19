"""Regresja: guard "faktura musi byc w rejestrze" nie moze blokowac korekt.

Korekty (RodzajFaktury=KOR) nie maja wlasnego wiersza w rejestrze faktur, a ich
wysylka do KSeF jest obowiazkowa — guard odcinal je bezterminowo.
"""

import asyncio
import importlib.util
from pathlib import Path

import pytest

SKILL = Path(__file__).resolve().parent.parent / "skills" / "ksef" / "scripts" / "submit.py"

FA_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<Faktura xmlns="http://crd.gov.pl/wzor/2025/06/25/13775/">
  <Fa>
    <P_2>{number}</P_2>
    <RodzajFaktury>{kind}</RodzajFaktury>
  </Fa>
</Faktura>
"""


@pytest.fixture
def submit_mod():
    spec = importlib.util.spec_from_file_location("ksef_submit", SKILL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _write(tmp_path, number: str, kind: str) -> str:
    p = tmp_path / "faktura.xml"
    p.write_text(FA_TEMPLATE.format(number=number, kind=kind), encoding="utf-8")
    return str(p)


def test_correction_not_in_registry_is_sent(submit_mod, tmp_path, isolated_db, monkeypatch):
    """KOR spoza rejestru trafia do KSeF (nie jest odrzucana)."""
    sent = {}

    class FakeResult:
        success = True
        reference_number = "20260702-EE-TEST"
        error = None
        details = {"env": "test"}

    class FakeClient:
        def is_configured(self):
            return True

        async def send_invoice(self, xml_content):
            sent["xml"] = xml_content
            return FakeResult()

    monkeypatch.setattr(submit_mod, "KSeFClient", FakeClient)
    path = _write(tmp_path, "AK1/07/2026", "KOR")

    result = asyncio.run(submit_mod.submit(path))

    assert result["success"] is True
    assert result["reference_number"] == "20260702-EE-TEST"
    assert "xml" in sent  # faktycznie poszla do KSeF


def test_regular_invoice_not_in_registry_still_refused(
    submit_mod, tmp_path, isolated_db, monkeypatch
):
    """Zwykla faktura spoza rejestru nadal odrzucana — guard dziala."""

    class FakeClient:
        def is_configured(self):
            return True

        async def send_invoice(self, xml_content):  # pragma: no cover - nie powinno sie wykonac
            raise AssertionError("nie powinno dojsc do wysylki")

    monkeypatch.setattr(submit_mod, "KSeFClient", FakeClient)
    path = _write(tmp_path, "A1/07/2026", "VAT")

    result = asyncio.run(submit_mod.submit(path))

    assert result["success"] is False
    assert "nie istnieje w rejestrze" in result["error"]


def test_malformed_xml_returns_json_error(submit_mod, tmp_path, isolated_db, monkeypatch):
    """Uszkodzony XML -> kontrakt JSON, nie traceback."""

    class FakeClient:
        def is_configured(self):
            return True

    monkeypatch.setattr(submit_mod, "KSeFClient", FakeClient)
    p = tmp_path / "broken.xml"
    p.write_text("<Faktura><Fa><P_2>A1/07/2026", encoding="utf-8")

    result = asyncio.run(submit_mod.submit(str(p)))

    assert result["success"] is False
    assert "Niepoprawny XML" in result["error"]
