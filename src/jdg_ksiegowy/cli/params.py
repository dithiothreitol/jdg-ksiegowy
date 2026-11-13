"""Konwersja argumentow CLI na typy domenowe (Decimal, date) z czytelnym bledem."""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

import typer


def money(value: str | Decimal) -> Decimal:
    if isinstance(value, Decimal):  # wartosc domyslna parametru
        return value
    try:
        return Decimal(value.replace(",", ".").replace(" ", ""))
    except InvalidOperation:
        raise typer.BadParameter(f"to nie jest kwota: {value!r}") from None


def day(value: str | date) -> date:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise typer.BadParameter(f"oczekiwano daty RRRR-MM-DD, otrzymano {value!r}") from None


def previous_month(today: date | None = None) -> tuple[int, int]:
    today = today or date.today()
    return (today.year, today.month - 1) if today.month > 1 else (today.year - 1, 12)
