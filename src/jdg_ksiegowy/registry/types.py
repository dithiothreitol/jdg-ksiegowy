"""Typy kolumn dla kwot i stawek — dokladne Decimal po stronie Pythona.

SQLite nie ma typu dziesietnego: `Numeric` laduje jako REAL i gubi grosze przy
sumowaniu. Kwoty i stawki trzymamy wiec jako liczby calkowite przeskalowane
o 100 (grosze / setne procenta), a ilosci i ceny jednostkowe (do 8 miejsc
po przecinku w FA(3)) — jako tekst.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import Integer, String
from sqlalchemy.types import TypeDecorator

_CENT = Decimal("0.01")


def to_decimal(value: Any) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


class _Hundredths(TypeDecorator[Decimal]):
    """Decimal z dwoma miejscami po przecinku zapisany jako INTEGER (x100)."""

    impl = Integer
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Any) -> int | None:
        if value is None:
            return None
        return int(to_decimal(value).quantize(_CENT, rounding=ROUND_HALF_UP) * 100)

    def process_result_value(self, value: Any, dialect: Any) -> Decimal | None:
        if value is None:
            return None
        return (Decimal(int(value)) / 100).quantize(_CENT)


class Money(_Hundredths):
    """Kwota w PLN, w bazie w groszach."""

    cache_ok = True


class Percent(_Hundredths):
    """Stawka procentowa (VAT, odliczenie), w bazie w setnych procenta."""

    cache_ok = True


class DecimalText(TypeDecorator[Decimal]):
    """Decimal o dowolnej precyzji zapisany jako tekst (ilosc, cena jednostkowa)."""

    impl = String
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Any) -> str | None:
        return None if value is None else str(to_decimal(value))

    def process_result_value(self, value: Any, dialect: Any) -> Decimal | None:
        return None if value is None else Decimal(value)
