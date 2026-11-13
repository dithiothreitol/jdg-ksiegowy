"""Indywidualny rachunek podatkowy (mikrorachunek) — wyliczany z NIP.

Struktura NRB: LK + 10100071222 (NBP, staly ciag) + 2 (identyfikator = NIP) + NIP + 00.
Liczba kontrolna LK jak w IBAN (mod 97). Na mikrorachunek placi sie PIT/ryczalt i VAT;
skladki ZUS ida na osobny rachunek ZUS.
"""

from __future__ import annotations

from jdg_ksiegowy.validators import validate_nip

_FIXED = "10100071222"
_NIP_MARKER = "2"
_PL = "2521"  # P=25, L=21 (IBAN)


def microaccount(nip: str) -> str:
    """26 cyfr mikrorachunku dla NIP (bez spacji)."""
    if not validate_nip(nip):
        raise ValueError(f"Nieprawidłowy NIP: {nip!r}")
    bban = f"{_FIXED}{_NIP_MARKER}{nip}00"
    check = 98 - int(bban + _PL + "00") % 97
    return f"{check:02d}{bban}"


def is_valid_nrb(account: str) -> bool:
    digits = account.replace(" ", "")
    if len(digits) != 26 or not digits.isdigit():
        return False
    return int(digits[2:] + _PL + digits[:2]) % 97 == 1


def format_nrb(account: str) -> str:
    """'12345...' -> '12 3456 7890 ...' (grupy po 4 cyfry jak na przelewie)."""
    return account[:2] + " " + " ".join(account[i : i + 4] for i in range(2, 26, 4))
