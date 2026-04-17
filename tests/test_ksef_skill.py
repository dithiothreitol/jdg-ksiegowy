"""Test skilla KSeF — order-of-checks, sensowne errory bez tokena/pliku."""

import asyncio
import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
KSEF_SUBMIT = REPO_ROOT / "skills" / "ksef" / "scripts" / "submit.py"

_spec = importlib.util.spec_from_file_location("ksef_submit", KSEF_SUBMIT)
ksef_submit = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ksef_submit)


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
