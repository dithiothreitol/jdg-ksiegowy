"""Generator metadanych autoryzacyjnych dla bramki MF.

Dane autoryzujace zastepuja podpis kwalifikowany dla osob fizycznych (JDG).

Schemat XSD: SIG-2008_v2-0.xsd (namespace:
http://e-deklaracje.mf.gov.pl/Repozytorium/Definicje/Podpis/), patrz
docs/sig-2008_v2-0.xsd.

Wymagane: NIP lub PESEL (xs:choice), ImiePierwsze, Nazwisko, DataUrodzenia,
Kwota (przychodu z PIT za rok N-2). Na 2026: kwota z PIT za 2024.
  PIT-37: poz. 50/83
  PIT-28: poz. 20/22/24/62/73
  PIT-36: poz. 67-75/131
  PIT-36L: poz. 23/25/27/28/33
Brak zeznania -> 0. Nie sumowac z roznych zeznan.

Finalny XML szyfrowany AES-256-CBC tym samym kluczem co plik JPK
(patrz crypto.encrypt_jpk) i umieszczany w elemencie <AuthData>
metadanych InitUpload.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from lxml import etree

from jdg_ksiegowy.validators import validate_pesel

SIG_NS = "http://e-deklaracje.mf.gov.pl/Repozytorium/Definicje/Podpis/"


@dataclass(frozen=True)
class AuthorizationData:
    """Dane autoryzujace osoby fizycznej do wysylki JPK (SIG-2008)."""

    nip: str
    pesel: str
    first_name: str
    last_name: str
    birth_date: date
    prior_year_income: Decimal  # kwota przychodu z PIT za rok N-2

    def __post_init__(self) -> None:
        if self.pesel and not validate_pesel(self.pesel):
            raise ValueError(f"Nieprawidlowy PESEL: {self.pesel!r}")

    def fingerprint(self) -> str:
        """Skrot do logow (nie wycieka PESEL/kwoty)."""
        h = hashlib.sha256(
            f"{self.nip}|{self.pesel}|{self.prior_year_income}".encode()
        ).hexdigest()
        return f"sha256:{h[:12]}"


def build_authorization_xml(auth: AuthorizationData) -> bytes:
    """Zbuduj DaneAutoryzujace XML wg SIG-2008_v2-0.xsd.

    Kolejnosc elementow i namespace musza byc zgodne z XSD, inaczej bramka
    MF odrzuci z kodem 120 (podpis negatywnie zweryfikowany).
    """
    root = etree.Element(
        f"{{{SIG_NS}}}DaneAutoryzujace", nsmap={None: SIG_NS},
    )

    # xs:choice: NIP | PESEL — zgodnie z praktyka MF:
    # NIP dla osob prowadzacych dzialalnosc (JDG), PESEL tylko gdy brak NIP.
    # Wczesniej kod uzywal PESEL -> status 419.
    # Zrodlo: https://jpk.info.pl/wysylka-jpk/blad-419-status/
    if auth.nip:
        etree.SubElement(root, f"{{{SIG_NS}}}NIP").text = auth.nip
    elif auth.pesel:
        etree.SubElement(root, f"{{{SIG_NS}}}PESEL").text = auth.pesel
    else:
        raise ValueError("AuthorizationData: wymagany NIP lub PESEL")

    etree.SubElement(root, f"{{{SIG_NS}}}ImiePierwsze").text = auth.first_name
    etree.SubElement(root, f"{{{SIG_NS}}}Nazwisko").text = auth.last_name
    etree.SubElement(root, f"{{{SIG_NS}}}DataUrodzenia").text = auth.birth_date.isoformat()
    etree.SubElement(root, f"{{{SIG_NS}}}Kwota").text = f"{auth.prior_year_income:.2f}"

    # Ręczna deklaracja XML z double-quotes (single quotes z lxml powoduja kod 426)
    body = etree.tostring(root, encoding="UTF-8")
    return b'<?xml version="1.0" encoding="UTF-8"?>\n' + body
