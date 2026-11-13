"""Walidacja XSD plikow JPK przed wysylka do bramki MF — offline.

Schematy MF (wraz z importowanymi typami crd.gov.pl) sa wbudowane w pakiet
(`jdg_ksiegowy/schemas/<nazwa>/schemat.xsd`), a ladowanie odbywa sie w trybie
`allow="local"`: walidator nigdy nie siega do sieci.

Aktualizacja schematu po zmianie przez MF:
    xmlschema.XMLSchema(url).export(target=..., save_remote=True)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import cache
from pathlib import Path

import xmlschema
from lxml import etree

SCHEMAS_DIR = Path(__file__).resolve().parent.parent / "schemas"

# kodSystemowy z naglowka JPK -> katalog schematu w pakiecie
SCHEMA_DIRS: dict[str, str] = {
    "JPK_V7M_3": "jpk_v7m_3",  # JPK_V7M(3), od 01.02.2026
    "JPK_EWP_4": "jpk_ewp_4",  # JPK_EWP(4), od 01.01.2026
}


@dataclass(frozen=True)
class ValidationResult:
    valid: bool
    errors: list[str] = field(default_factory=list)

    def raise_if_invalid(self) -> None:
        if not self.valid:
            raise XSDValidationError(self.errors)


class XSDValidationError(Exception):
    """Plik JPK nie przechodzi walidacji XSD MF."""

    def __init__(self, errors: list[str]):
        self.errors = errors
        summary = "; ".join(errors[:3])
        if len(errors) > 3:
            summary += f" (+{len(errors) - 3} wiecej)"
        super().__init__(f"XSD validation failed: {summary}")


@cache
def _schema(name: str) -> xmlschema.XMLSchema:
    directory = SCHEMA_DIRS.get(name)
    if directory is None:
        raise ValueError(f"Nieznany schemat JPK: {name!r} (dostepne: {sorted(SCHEMA_DIRS)})")
    return xmlschema.XMLSchema(str(SCHEMAS_DIR / directory / "schemat.xsd"), allow="local")


def schema_name(xml: bytes) -> str:
    """Nazwa schematu z naglowka: kodSystemowy 'JPK_V7M (3)' -> 'JPK_V7M_3'."""
    kod = etree.fromstring(xml).find(".//{*}KodFormularza")
    if kod is None or not kod.get("kodSystemowy"):
        raise ValueError("Brak KodFormularza@kodSystemowy — to nie jest plik JPK")
    return kod.get("kodSystemowy", "").replace(" (", "_").rstrip(")")


def validate_jpk(xml: str | bytes, schema: str | None = None) -> ValidationResult:
    """Zwaliduj JPK wzgledem wbudowanego XSD; schemat rozpoznawany z naglowka."""
    xml_bytes = xml.encode("utf-8") if isinstance(xml, str) else xml
    xsd = _schema(schema or schema_name(xml_bytes))
    errors = [str(e) for e in xsd.iter_errors(xml_bytes)]
    return ValidationResult(valid=not errors, errors=errors)
