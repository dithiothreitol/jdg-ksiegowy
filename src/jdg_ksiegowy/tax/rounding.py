"""Zaokraglanie kwot podatkow i deklaracji."""

from decimal import ROUND_HALF_UP, Decimal


def round_pln(amount: Decimal) -> Decimal:
    """Pelne zlote (art. 63 § 1 Ordynacji podatkowej): podstawy, podatki, pola deklaracji."""
    return amount.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
