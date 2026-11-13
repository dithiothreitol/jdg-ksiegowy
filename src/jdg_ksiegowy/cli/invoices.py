"""jdg invoice ... / jdg payment ..."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Annotated

import typer

from jdg_ksiegowy.app import contracts as contracts_app
from jdg_ksiegowy.app import invoices as app
from jdg_ksiegowy.cli.output import command
from jdg_ksiegowy.cli.params import day, money
from jdg_ksiegowy.registry.repository import PeriodBy

invoice = typer.Typer(
    help="Faktury sprzedazy: wystawianie, lista, wysylka mailem.", no_args_is_help=True
)
payment = typer.Typer(
    help="Platnosci: oznaczanie zaplaty, import wyciagu z banku.", no_args_is_help=True
)

Money = Annotated[Decimal, typer.Option(parser=money, help="Kwota netto (PLN).")]


@command(invoice, "issue", output=app.InvoiceView, prefix="invoice")
def issue(
    buyer_nip: Annotated[str, typer.Option(help="NIP nabywcy (10 cyfr).")],
    net: Money,
    buyer_name: Annotated[str | None, typer.Option(help="Nazwa (domyslnie z rejestru).")] = None,
    buyer_address: Annotated[str | None, typer.Option(help="Adres nabywcy.")] = None,
    buyer_email: Annotated[str | None, typer.Option(help="E-mail do wysylki faktury.")] = None,
    description: Annotated[str | None, typer.Option(help="Opis uslugi.")] = None,
    issue_date: Annotated[date | None, typer.Option(parser=day, help="Data wystawienia.")] = None,
    sale_date: Annotated[
        date | None, typer.Option(parser=day, help="Data sprzedazy — okres JPK.")
    ] = None,
    payment_due: Annotated[date | None, typer.Option(parser=day, help="Termin platnosci.")] = None,
    period_from: Annotated[date | None, typer.Option(parser=day)] = None,
    period_to: Annotated[date | None, typer.Option(parser=day)] = None,
    dry_run: Annotated[bool, typer.Option(help="Pokaz fakture bez zapisu.")] = False,
) -> app.InvoiceView:
    """Wystaw fakture VAT: DOCX + XML FA(3) + wpis w rejestrze (bez wysylki do KSeF)."""
    return app.issue_invoice(
        app.IssueInvoiceInput(
            buyer_nip=buyer_nip,
            net=net,
            buyer_name=buyer_name,
            buyer_address=buyer_address,
            buyer_email=buyer_email,
            description=description,
            issue_date=issue_date,
            sale_date=sale_date,
            payment_due=payment_due,
            period_from=period_from,
            period_to=period_to,
        ),
        dry_run=dry_run,
    )


@command(invoice, "list", output=app.InvoiceList, prefix="invoice")
def list_(
    year: Annotated[int | None, typer.Option(help="Rok.")] = None,
    month: Annotated[int | None, typer.Option(min=1, max=12, help="Miesiac (z --year).")] = None,
    by: Annotated[str, typer.Option(help="sale_date | issue_date | income")] = "sale_date",
    unpaid: Annotated[bool, typer.Option(help="Tylko niezaplacone.")] = False,
) -> app.InvoiceList:
    """Lista faktur z okresu (domyslnie wg daty sprzedazy, jak w JPK)."""
    if by not in ("sale_date", "issue_date", "income"):
        raise typer.BadParameter("dozwolone: sale_date, issue_date, income", param_hint="--by")
    period_by: PeriodBy = by  # type: ignore[assignment]
    return app.list_invoices(year=year, month=month, by=period_by, unpaid=unpaid)


@command(invoice, "show", output=app.InvoiceView, prefix="invoice")
def show(
    number: Annotated[str, typer.Argument(help="Numer faktury, np. A1/11/2026.")],
) -> app.InvoiceView:
    """Szczegoly faktury z rejestru."""
    return app.show_invoice(number)


@command(invoice, "mail", output=app.MailResult, prefix="invoice", confirmable=True)
def mail(
    number: Annotated[str, typer.Argument(help="Numer faktury.")],
    to: Annotated[str | None, typer.Option(help="Adresat (domyslnie e-mail nabywcy).")] = None,
    cc: Annotated[list[str] | None, typer.Option(help="Kopia (mozna powtorzyc).")] = None,
    confirm: Annotated[str | None, typer.Option(help="Token z podsumowania.")] = None,
) -> app.MailResult:
    """Wyslij fakture PDF mailem (wymaga potwierdzenia)."""
    return app.mail_invoice(number, to=to, cc=cc, confirm=confirm)


@command(payment, "mark", output=app.InvoiceView, prefix="payment")
def mark(
    number: Annotated[str, typer.Argument(help="Numer faktury.")],
    paid_on: Annotated[date | None, typer.Option(parser=day, help="Data zaplaty.")] = None,
) -> app.InvoiceView:
    """Oznacz fakture jako zaplacona."""
    paid_at = datetime.combine(paid_on, datetime.min.time()) if paid_on else None
    return app.mark_paid(number, paid_at)


@command(payment, "import", output=contracts_app.PaymentImport, prefix="payment")
def import_csv(
    csv_path: Annotated[Path, typer.Argument(help="Wyciag CSV z banku (mBank lub generyczny).")],
    auto_mark: Annotated[bool, typer.Option(help="Oznacz dopasowane jako zaplacone.")] = False,
) -> contracts_app.PaymentImport:
    """Dopasuj wplywy z wyciagu do niezaplaconych faktur."""
    return contracts_app.import_bank_csv(csv_path, auto_mark=auto_mark)
