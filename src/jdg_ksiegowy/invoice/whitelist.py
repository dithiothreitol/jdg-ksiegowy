"""Wykaz podatnikow VAT (Biala lista MF) — dane kontrahenta po NIP.

API publiczne, bez klucza: https://wl-api.mf.gov.pl (limit zapytan dziennych). Zwraca nazwe,
adres, status VAT i rachunki z wykazu — status inny niz "Czynny" to sygnal ostrzegawczy.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import httpx

WL_API = "https://wl-api.mf.gov.pl/api/search/nip/{nip}"


@dataclass(frozen=True)
class WhiteListSubject:
    nip: str
    name: str
    address: str
    vat_status: str  # Czynny | Zwolniony | brak w wykazie
    accounts: list[str]


class WhiteListError(RuntimeError):
    """Biala lista niedostepna albo odrzucila zapytanie."""


def lookup(nip: str, on: date, *, timeout: float = 10.0) -> WhiteListSubject | None:
    """Dane podatnika z wykazu na dzien `on`; None, gdy NIP nie figuruje w wykazie."""
    try:
        resp = httpx.get(WL_API.format(nip=nip), params={"date": on.isoformat()}, timeout=timeout)
    except httpx.HTTPError as e:
        raise WhiteListError(f"Biała lista niedostępna: {e}") from e
    if resp.status_code != 200:
        message = resp.json().get("message") if resp.content else resp.reason_phrase
        raise WhiteListError(f"Biała lista: HTTP {resp.status_code} — {message}")
    subject = resp.json().get("result", {}).get("subject")
    if not subject:
        return None
    return WhiteListSubject(
        nip=subject.get("nip") or nip,
        name=subject.get("name") or "",
        address=subject.get("workingAddress") or subject.get("residenceAddress") or "",
        vat_status=subject.get("statusVat") or "",
        accounts=list(subject.get("accountNumbers") or []),
    )
