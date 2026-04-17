"""Walidacja identyfikatorów podatkowych: NIP, PESEL, REGON."""

from __future__ import annotations

import re


def validate_nip(nip: str) -> bool:
    """Sprawdź poprawność NIP (cyfry+suma kontrolna wg wag 6,5,7,2,3,4,5,6,7)."""
    digits = re.sub(r"[\s\-]", "", nip)
    if not re.fullmatch(r"\d{10}", digits):
        return False
    if digits == "0000000000":
        return False
    weights = (6, 5, 7, 2, 3, 4, 5, 6, 7)
    total = sum(w * int(d) for w, d in zip(weights, digits))
    r = total % 11
    if r == 10:
        return False
    return r == int(digits[9])


def validate_pesel(pesel: str) -> bool:
    """Sprawdź poprawność PESEL (11 cyfr + suma kontrolna wg wag 1,3,7,9,1,3,7,9,1,3)."""
    digits = pesel.strip()
    if not re.fullmatch(r"\d{11}", digits):
        return False
    weights = (1, 3, 7, 9, 1, 3, 7, 9, 1, 3)
    total = sum(w * int(d) for w, d in zip(weights, digits))
    check = (10 - (total % 10)) % 10
    return check == int(digits[10])


def validate_regon(regon: str) -> bool:
    """Sprawdź poprawność REGON (9 lub 14 cyfr).

    Wagi wg GUS: https://api.regon.stat.gov.pl/
    """
    digits = re.sub(r"\s", "", regon)
    if digits in ("000000000", "00000000000000"):
        return False
    if re.fullmatch(r"\d{9}", digits):
        weights = (8, 9, 2, 3, 4, 5, 6, 7)
        total = sum(w * int(d) for w, d in zip(weights, digits))
        r = total % 11
        check = 0 if r == 10 else r
        return check == int(digits[8])
    if re.fullmatch(r"\d{14}", digits):
        weights = (2, 4, 8, 5, 0, 9, 7, 3, 6, 1, 2, 4, 8)
        total = sum(w * int(d) for w, d in zip(weights, digits))
        r = total % 11
        check = 0 if r == 10 else r
        return check == int(digits[13])
    return False


EU_COUNTRY_CODES: frozenset[str] = frozenset({
    "AT", "BE", "BG", "CY", "CZ", "DE", "DK", "EE", "ES", "FI",
    "FR", "GR", "HR", "HU", "IE", "IT", "LT", "LU", "LV", "MT",
    "NL", "PT", "RO", "SE", "SI", "SK",
})


def normalize_nip(nip: str) -> str:
    """Usuń separatory, zwróć 10 cyfr lub rzuć ValueError."""
    digits = re.sub(r"[\s\-]", "", nip)
    if not re.fullmatch(r"\d{10}", digits):
        raise ValueError(f"NIP musi miec 10 cyfr: {nip!r}")
    return digits
