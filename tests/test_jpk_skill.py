"""Testy skryptow skilla jpk: numeracja plikow korekty + rozpoznawanie schematu do walidacji."""

import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = REPO_ROOT / "skills" / "jpk" / "scripts"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


generate_jpk = _load("generate_jpk")
validate_jpk = _load("validate_jpk")


def test_first_correction_is_k1(tmp_path):
    (tmp_path / "JPK_V7M_2026_03.xml").touch()  # oryginal (zlozenie) nie liczy sie jako korekta
    n, path = generate_jpk._correction_output_path(tmp_path, 2026, 3)
    assert (n, path.name) == (1, "JPK_V7M_2026_03_K1.xml")


def test_next_correction_number_skips_taken(tmp_path):
    for name in ("JPK_V7M_2026_03_K1.xml", "JPK_V7M_2026_03_K2.xml", "JPK_V7M_2026_04_K1.xml"):
        (tmp_path / name).touch()
    n, path = generate_jpk._correction_output_path(tmp_path, 2026, 3)
    assert (n, path.name) == (3, "JPK_V7M_2026_03_K3.xml")


def test_schema_name_from_kod_systemowy():
    xml = (
        b'<JPK xmlns="urn:x"><Naglowek>'
        b'<KodFormularza kodSystemowy="JPK_V7M (3)">JPK_VAT</KodFormularza>'
        b"</Naglowek></JPK>"
    )
    assert validate_jpk.schema_name(xml) == "JPK_V7M_3"
    assert validate_jpk.schema_name(xml.replace(b"JPK_V7M (3)", b"JPK_EWP (4)")) == "JPK_EWP_4"
