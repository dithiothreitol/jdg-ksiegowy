"""Testy skilla jpk-submit (dry-run + walidacje)."""

import asyncio
import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
JPK_SUBMIT = REPO_ROOT / "skills" / "jpk-submit" / "scripts" / "submit.py"

_spec = importlib.util.spec_from_file_location("jpk_submit", JPK_SUBMIT)
submit = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(submit)


def test_returns_error_for_missing_xml(monkeypatch):
    monkeypatch.setenv("MF_PESEL", "44051401458")
    monkeypatch.setenv("MF_PRIOR_INCOME", "100000")
    result = asyncio.run(submit.run_submit(Path("nieistniejacy.xml"), dry_run=False))
    assert result["success"] is False
    assert "nie istnieje" in result["error"].lower()


def test_dry_run_works_without_cert(monkeypatch, tmp_path):
    monkeypatch.setenv("MF_PESEL", "44051401458")
    monkeypatch.setenv("MF_PRIOR_INCOME", "100000")
    monkeypatch.setenv("MF_CERT_PATH", "")
    xml_file = tmp_path / "JPK.xml"
    xml_file.write_text("<JPK/>", encoding="utf-8")

    # przeladuj settings zeby zlapaly nowe env
    from jdg_ksiegowy.config import MFGatewayConfig, settings

    settings.mf = MFGatewayConfig()

    result = asyncio.run(submit.run_submit(xml_file, dry_run=True))
    assert result["success"] is True
    assert result["dry_run"] is True
    assert result["mf_env"] == "test"
    assert result["auth_fingerprint"].startswith("sha256:")


def test_real_submit_fails_without_cert(monkeypatch, tmp_path):
    monkeypatch.setenv("MF_PESEL", "44051401458")
    monkeypatch.setenv("MF_PRIOR_INCOME", "100000")
    monkeypatch.setenv("MF_CERT_PATH", "")
    xml_file = tmp_path / "JPK.xml"
    xml_file.write_text("<JPK/>", encoding="utf-8")

    from jdg_ksiegowy.config import MFGatewayConfig, settings

    settings.mf = MFGatewayConfig()

    result = asyncio.run(submit.run_submit(xml_file, dry_run=False))
    assert result["success"] is False
    assert "MF_CERT_PATH" in result["error"]


def test_submit_requires_pesel(monkeypatch, tmp_path):
    monkeypatch.setenv("MF_PESEL", "")
    xml_file = tmp_path / "JPK.xml"
    xml_file.write_text("<JPK/>", encoding="utf-8")

    from jdg_ksiegowy.config import MFGatewayConfig, settings

    settings.mf = MFGatewayConfig()

    result = asyncio.run(submit.run_submit(xml_file, dry_run=True))
    assert result["success"] is False
    assert "MF_PESEL" in result["error"]
