"""jdg ksef ..."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Annotated

import typer

from jdg_ksiegowy.app import ksef as app
from jdg_ksiegowy.cli.output import command
from jdg_ksiegowy.cli.params import day, money
from jdg_ksiegowy.expenses.models import ExpenseCategory

ksef = typer.Typer(
    help="KSeF: wysylka faktur, faktury zakupowe, numery KSeF.", no_args_is_help=True
)


@command(ksef, "send", output=app.KsefSendResult, prefix="ksef", confirmable=True)
def send(
    number: Annotated[str, typer.Argument(help="Numer faktury z rejestru.")],
    confirm: Annotated[str | None, typer.Option(help="Token z podsumowania.")] = None,
) -> app.KsefSendResult:
    """Wyslij fakture do KSeF (wymaga potwierdzenia); zapisuje numer KSeF i UPO."""
    return app.send_invoice(number, confirm=confirm)


@command(ksef, "inbox", output=app.InboxResult, prefix="ksef")
def inbox(
    year: Annotated[int | None, typer.Option(help="Rok (z --month).")] = None,
    month: Annotated[int | None, typer.Option(min=1, max=12)] = None,
    date_from: Annotated[date | None, typer.Option(parser=day, help="Poczatek zakresu.")] = None,
    date_to: Annotated[date | None, typer.Option(parser=day, help="Koniec zakresu.")] = None,
    role: Annotated[str, typer.Option(help="buyer (zakupy) | seller (sprzedaz)")] = "buyer",
    include_corrections: Annotated[bool, typer.Option()] = False,
    seller_nip: Annotated[str | None, typer.Option(help="Filtr po NIP sprzedawcy.")] = None,
    category: Annotated[ExpenseCategory | None, typer.Option()] = None,
    vat_deduction_pct: Annotated[
        Decimal, typer.Option(parser=money, help="Odliczenie VAT %: 100 | 50 (auto) | 0.")
    ] = Decimal("100"),
    save: Annotated[bool, typer.Option(help="Zapisz nowe faktury jako koszty.")] = False,
) -> app.InboxResult:
    """Faktury z KSeF (domyslnie zakupowe, biezacy miesiac); bez --save tylko podglad."""
    if role not in ("buyer", "seller"):
        raise typer.BadParameter("dozwolone: buyer, seller", param_hint="--role")
    start, end = _range(year, month, date_from, date_to)
    return app.inbox(
        start,
        end,
        role="seller" if role == "seller" else "buyer",
        include_corrections=include_corrections,
        seller_nip=seller_nip,
        category=category,
        vat_deduction_pct=vat_deduction_pct,
        save=save,
    )


def _range(
    year: int | None, month: int | None, date_from: date | None, date_to: date | None
) -> tuple[date, date]:
    if date_from and date_to:
        if date_from > date_to:
            raise typer.BadParameter("--date-from jest pozniejsze niz --date-to")
        return date_from, date_to
    today = date.today()
    y, m = year or today.year, month or today.month
    end = date(y + 1, 1, 1) if m == 12 else date(y, m + 1, 1)
    return date(y, m, 1), date.fromordinal(end.toordinal() - 1)


@command(ksef, "backfill", output=app.BackfillView, prefix="ksef")
def backfill(
    apply: Annotated[bool, typer.Option(help="Zapisz numery (domyslnie podglad).")] = False,
) -> app.BackfillView:
    """Uzupelnij numery KSeF faktur wyslanych przed wersja 1.0."""
    return app.backfill(apply=apply)
