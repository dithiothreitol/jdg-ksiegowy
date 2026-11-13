"""Kod QR weryfikacji faktury w KSeF (KOD I) — dla wizualizacji przekazywanej poza KSeF.

Link: https://qr.ksef.mf.gov.pl/invoice/{NIP sprzedawcy}/{data wystawienia DD-MM-RRRR}/
{SHA-256 pliku XML faktury w Base64URL bez dopelnienia}. Ten sam format generuje ksef2.
"""

from __future__ import annotations

import io
from base64 import urlsafe_b64encode
from datetime import date
from hashlib import sha256

import segno

QR_HOSTS = {
    "prod": "https://qr.ksef.mf.gov.pl",
    "test": "https://qr-test.ksef.mf.gov.pl",
    "demo": "https://qr-demo.ksef.mf.gov.pl",
}


def verification_url(seller_nip: str, issue_date: date, invoice_xml: bytes, env: str) -> str:
    digest = urlsafe_b64encode(sha256(invoice_xml).digest()).decode("ascii").rstrip("=")
    return f"{QR_HOSTS[env]}/invoice/{seller_nip}/{issue_date:%d-%m-%Y}/{digest}"


def qr_png(url: str) -> bytes:
    """PNG kodu QR (korekcja bledow M, jak w SDK) — czysty Python, bez bibliotek natywnych."""
    buf = io.BytesIO()
    segno.make_qr(url, error="m").save(buf, kind="png", scale=6, border=4)
    return buf.getvalue()
