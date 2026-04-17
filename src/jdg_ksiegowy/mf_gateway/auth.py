"""Generator metadanych autoryzacyjnych dla bramki MF.

Dane autoryzujace zastepuja podpis kwalifikowany dla osob fizycznych (JDG).
Wymagaja: NIP, PESEL, Imie, Nazwisko, DataUrodzenia, KwotaPrzychodu z PIT za rok N-2.

Na 2026: kwota z PIT za 2024 (PIT-37 poz. 50/83, PIT-28 poz. 20/22/24/62/73,
PIT-36 poz. 67-75/131, PIT-36L poz. 23/25/27/28/33). Brak zeznania -> 0.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class AuthorizationData:
    """Dane autoryzujace osoby fizycznej do wysylki JPK."""

    nip: str
    pesel: str
    first_name: str
    last_name: str
    birth_date: date
    prior_year_income: Decimal  # kwota przychodu z PIT za rok poprzedni-1

    def fingerprint(self) -> str:
        """Skrot do logow (nie wycieka PESEL/kwoty)."""
        h = hashlib.sha256(
            f"{self.nip}|{self.pesel}|{self.prior_year_income}".encode()
        ).hexdigest()
        return f"sha256:{h[:12]}"


def build_authorization_xml(auth: AuthorizationData) -> str:
    """Zbuduj fragment XML z danymi autoryzujacymi.

    UWAGA: schemat MF dla autoryzacji jest osobny od JPK; ponizej forma
    uproszczona, do zlozenia w finalnej wiadomosci dla bramki. Pole 'KwotaPrzychodu'
    formatowane do 2 miejsc po przecinku (do potwierdzenia: cz format/groszy
    w schemacie autoryzacyjnym MF v4.2).
    """
    return (
        "<DaneAutoryzujace>"
        f"<Identyfikator>{auth.nip}</Identyfikator>"
        f"<Pesel>{auth.pesel}</Pesel>"
        f"<ImiePierwsze>{auth.first_name}</ImiePierwsze>"
        f"<Nazwisko>{auth.last_name}</Nazwisko>"
        f"<DataUrodzenia>{auth.birth_date.isoformat()}</DataUrodzenia>"
        f"<KwotaPrzychodu>{auth.prior_year_income:.2f}</KwotaPrzychodu>"
        "</DaneAutoryzujace>"
    )
