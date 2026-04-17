"""Registry klucza publicznego MF z cache'owaniem na dysku.

MF rotuje klucz publiczny okresowo (ostatnio 18.07.2025). Zamiast recznie
pobierac i ustawiac `MF_CERT_PATH`, ten modul:

1. probuje wczytac z cache (data/mf_cert/<env>.pem)
2. jesli brak lub przekroczony TTL -> pobiera z opublikowanego URL-a MF
3. waliduje strukture (X.509 cert z kluczem RSA) i zwraca RSAPublicKey

URL-e potwierdzone na 2026-04 (podatki.gov.pl, sekcja 'Specyfikacja
Interfejsow Uslug JPK' + 'Klucze publiczne'). W razie zmiany MF -> nadpisz
przez config MF_CERT_URL.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey

logger = logging.getLogger(__name__)

# UWAGA: MF nie udostepnia stabilnego "well-known" URL-a do klucza publicznego.
# Rotacje sa ogloszone jako osobne "komunikaty techniczne" na podatki.gov.pl,
# a plik PEM wisi pod zmieniajacym sie URL-em `/media/...`. Praktyka:
#
#   1. wpisz URL z ostatniego komunikatu do MF_CERT_URL w .env (pinned)
#   2. monitoruj daty waznosci cert.not_valid_after (ten modul loguje ostrzezenie
#      30 dni przed wygasnieciem)
#   3. gdy MF oglosi rotacje, zaktualizuj URL
#
# Lista komunikatow:
# https://www.podatki.gov.pl/komunikaty-techniczne/
# Prod (ostatnia rotacja 18.07.2025):
# https://www.podatki.gov.pl/komunikaty-techniczne/aktualizacja-certyfikatu-klucza-publicznego-do-uslugi-e-dokumenty-mf-gov-pl-jpk-cuk-alk/
DEFAULT_CERT_URLS: dict[str, str] = {}

DEFAULT_TTL = timedelta(days=30)


@dataclass(frozen=True)
class PublicKeyInfo:
    """Metadane pobranego klucza."""

    key: RSAPublicKey
    fetched_at: datetime
    source_url: str
    not_valid_after: datetime | None  # jesli byl cert X.509


class MFPublicKeyRegistry:
    """Cache + pobieranie klucza publicznego MF.

    Zapis cache: `data/mf_cert/{env}.pem` + `data/mf_cert/{env}.meta`
    (meta = ISO timestamp + source URL, prosty plik tekstowy).
    """

    def __init__(
        self,
        cache_dir: Path,
        env: str = "test",
        cert_url: str | None = None,
        ttl: timedelta = DEFAULT_TTL,
        http_timeout: float = 30.0,
    ):
        self.cache_dir = cache_dir
        self.env = env
        self.cert_url = cert_url or DEFAULT_CERT_URLS.get(env)
        self.ttl = ttl
        self.http_timeout = http_timeout

    @property
    def _cert_path(self) -> Path:
        return self.cache_dir / f"{self.env}.pem"

    @property
    def _meta_path(self) -> Path:
        return self.cache_dir / f"{self.env}.meta"

    def get(self, force_refresh: bool = False) -> PublicKeyInfo:
        """Zwroc aktualny klucz — z cache jesli swiezy, inaczej pobierz."""
        if not force_refresh and self._cache_fresh():
            return self._load_from_cache()
        return self.refresh()

    def refresh(self) -> PublicKeyInfo:
        """Pobierz klucz z URL-a MF, zapisz do cache, zwroc."""
        if not self.cert_url:
            raise ValueError(
                f"Brak URL klucza publicznego MF dla env={self.env!r}. Ustaw MF_CERT_URL w .env."
            )
        logger.info("Pobieram klucz publiczny MF z %s", self.cert_url)
        with httpx.Client(timeout=self.http_timeout, follow_redirects=True) as http:
            resp = http.get(self.cert_url)
            resp.raise_for_status()
            raw = resp.content
        info = _parse_public_key(raw, source_url=self.cert_url)
        self._write_cache(raw, info)
        return info

    def _cache_fresh(self) -> bool:
        if not self._cert_path.exists() or not self._meta_path.exists():
            return False
        try:
            meta = self._meta_path.read_text(encoding="utf-8").strip().splitlines()
            fetched_iso = meta[0]
            fetched = datetime.fromisoformat(fetched_iso)
        except (OSError, ValueError, IndexError):
            return False
        return datetime.now(tz=UTC) - fetched < self.ttl

    def _load_from_cache(self) -> PublicKeyInfo:
        raw = self._cert_path.read_bytes()
        meta_lines = self._meta_path.read_text(encoding="utf-8").splitlines()
        fetched_at = datetime.fromisoformat(meta_lines[0])
        source_url = meta_lines[1] if len(meta_lines) > 1 else self.cert_url or ""
        info = _parse_public_key(raw, source_url=source_url)
        _warn_if_expiring_soon(info.not_valid_after)
        return PublicKeyInfo(
            key=info.key,
            fetched_at=fetched_at,
            source_url=source_url,
            not_valid_after=info.not_valid_after,
        )

    def _write_cache(self, raw: bytes, info: PublicKeyInfo) -> None:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._cert_path.write_bytes(raw)
        self._meta_path.write_text(
            f"{info.fetched_at.isoformat()}\n{info.source_url}\n",
            encoding="utf-8",
        )


ROTATION_WARNING_WINDOW = timedelta(days=30)


def _warn_if_expiring_soon(not_after: datetime | None) -> None:
    if not_after is None:
        return
    remaining = not_after - datetime.now(tz=UTC)
    if remaining < ROTATION_WARNING_WINDOW:
        logger.warning(
            "Klucz publiczny MF wygasa %s (za %s). Sprawdz komunikaty techniczne "
            "podatki.gov.pl i zaktualizuj MF_CERT_URL.",
            not_after.isoformat(),
            remaining,
        )


def _parse_public_key(raw: bytes, source_url: str) -> PublicKeyInfo:
    """Rozpoznaj PEM/DER cert X.509 lub sam klucz RSA, zwroc PublicKeyInfo."""
    not_after: datetime | None = None
    key: RSAPublicKey | None = None

    if raw.lstrip().startswith(b"-----BEGIN"):
        if b"CERTIFICATE" in raw:
            cert = x509.load_pem_x509_certificate(raw)
            public_key = cert.public_key()
            not_after = cert.not_valid_after_utc
        else:
            public_key = serialization.load_pem_public_key(raw)
    else:
        try:
            cert = x509.load_der_x509_certificate(raw)
            public_key = cert.public_key()
            not_after = cert.not_valid_after_utc
        except ValueError:
            public_key = serialization.load_der_public_key(raw)

    if not isinstance(public_key, RSAPublicKey):
        raise ValueError("Klucz publiczny MF musi byc RSA")
    key = public_key

    return PublicKeyInfo(
        key=key,
        fetched_at=datetime.now(tz=UTC),
        source_url=source_url,
        not_valid_after=not_after,
    )
