"""Walidacja XSD plikow JPK przed wysylka do bramki MF.

MF publikuje oficjalne XSD na podatki.gov.pl. Zamiast wysylac "na slepo" i
czekac na blad 401 z bramki, walidujemy lokalnie — szybszy feedback loop.

Cache: `data/xsd/<schema_name>.xsd` (pobierane raz, rzadko sie zmienia).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import httpx
import xmlschema

logger = logging.getLogger(__name__)


# Oficjalne URL-e XSD MF (potwierdzone na 2026-04, za research sub-agent).
# V7M(3) obowiazuje od 01.02.2026, EWP(4) od 01.01.2026.
DEFAULT_XSD_URLS: dict[str, str] = {
    "JPK_V7M_3": "https://www.podatki.gov.pl/media/qord0r0j/schemat_jpk_v7m-3-_v1-0e.xsd",
    "JPK_EWP_4": "https://www.gov.pl/attachment/67b55c59-e05c-42f0-be4c-28afcca460b6",
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


class JPKValidator:
    """Waliduje JPK XML wg oficjalnego XSD z podatki.gov.pl.

    Uzycie:
        v = JPKValidator(cache_dir=Path("data/xsd"))
        v.validate(xml_bytes, schema="JPK_V7M_3").raise_if_invalid()
    """

    def __init__(
        self,
        cache_dir: Path,
        urls: dict[str, str] | None = None,
        http_timeout: float = 30.0,
    ):
        self.cache_dir = cache_dir
        self.urls = urls or DEFAULT_XSD_URLS
        self.http_timeout = http_timeout
        self._schema_cache: dict[str, xmlschema.XMLSchema] = {}

    def validate(self, xml: str | bytes, schema: str) -> ValidationResult:
        """Zwaliduj XML wg nazwanego schematu (np. 'JPK_V7M_3')."""
        xsd = self._get_schema(schema)
        xml_bytes = xml.encode("utf-8") if isinstance(xml, str) else xml
        errors = [str(e) for e in xsd.iter_errors(xml_bytes)]
        return ValidationResult(valid=not errors, errors=errors)

    def _get_schema(self, name: str) -> xmlschema.XMLSchema:
        if name in self._schema_cache:
            return self._schema_cache[name]
        path = self._ensure_cached(name)
        schema = xmlschema.XMLSchema(str(path))
        self._schema_cache[name] = schema
        return schema

    def _ensure_cached(self, name: str) -> Path:
        path = self.cache_dir / f"{name}.xsd"
        if path.exists():
            return path
        url = self.urls.get(name)
        if not url:
            raise ValueError(f"Nieznany schemat JPK: {name!r} (dodaj do DEFAULT_XSD_URLS)")
        logger.info("Pobieram XSD %s z %s", name, url)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        with httpx.Client(timeout=self.http_timeout, follow_redirects=True) as http:
            resp = http.get(url)
            resp.raise_for_status()
            path.write_bytes(resp.content)
        return path
