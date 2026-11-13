"""jdg expense ..."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Annotated

import typer

from jdg_ksiegowy.app import expenses as app
from jdg_ksiegowy.cli.output import command
from jdg_ksiegowy.cli.params import day, money
from jdg_ksiegowy.expenses.models import ExpenseCategory

expense = typer.Typer(help="Koszty: faktury zakupu (ręcznie, OCR), lista.", no_args_is_help=True)


@command(expense, "add", output=app.ExpenseView, prefix="expense")
def add(
    seller_name: Annotated[str, typer.Option()],
    seller_nip: Annotated[str, typer.Option(help="NIP lub numer VAT-UE sprzedawcy.")],
    document_number: Annotated[str, typer.Option(help="Numer faktury sprzedawcy.")],
    issue_date: Annotated[date, typer.Option(parser=day)],
    net: Annotated[Decimal, typer.Option(parser=money)],
    vat: Annotated[Decimal | None, typer.Option(parser=money, help="Kwota VAT.")] = None,
    vat_rate: Annotated[Decimal, typer.Option(parser=money)] = Decimal("23"),
    receive_date: Annotated[
        date | None, typer.Option(parser=day, help="Data wpływu — okres odliczenia.")
    ] = None,
    seller_country: Annotated[str, typer.Option()] = "PL",
    description: Annotated[str, typer.Option()] = "",
    category: Annotated[ExpenseCategory, typer.Option()] = ExpenseCategory.INNE,
    vat_deduction_pct: Annotated[Decimal, typer.Option(parser=money)] = Decimal("100"),
    reverse_charge: Annotated[
        bool, typer.Option(help="Import usług: VAT należny i naliczony po stronie nabywcy.")
    ] = False,
    file_path: Annotated[str | None, typer.Option(help="Dowód (PDF/JPG/XML).")] = None,
    notes: Annotated[str | None, typer.Option()] = None,
    dry_run: Annotated[bool, typer.Option()] = False,
) -> app.ExpenseView:
    """Zarejestruj fakturę zakupu."""
    return app.add_expense(
        app.AddExpenseInput(
            seller_name=seller_name,
            seller_nip=seller_nip,
            document_number=document_number,
            issue_date=issue_date,
            net=net,
            vat=vat,
            vat_rate=vat_rate,
            receive_date=receive_date,
            seller_country=seller_country,
            description=description,
            category=category,
            vat_deduction_pct=vat_deduction_pct,
            reverse_charge=reverse_charge,
            file_path=file_path,
            notes=notes,
        ),
        dry_run=dry_run,
    )


@command(expense, "scan", output=app.ScanResult, prefix="expense")
def scan(
    file: Annotated[Path, typer.Argument(help="Faktura PDF/JPG/PNG.")],
    save: Annotated[bool, typer.Option(help="Zapisz (domyślnie podgląd do akceptacji).")] = False,
) -> app.ScanResult:
    """Odczytaj fakturę zakupu przez OCR (lokalny model, fallback Claude)."""
    return app.scan_expense(file, save=save)


@command(expense, "list", output=app.ExpenseList, prefix="expense", read_only=True)
def list_(
    year: Annotated[int | None, typer.Option()] = None,
    month: Annotated[int | None, typer.Option(min=1, max=12)] = None,
) -> app.ExpenseList:
    """Koszty wg miesiąca wpływu."""
    return app.list_expenses(year=year, month=month)
