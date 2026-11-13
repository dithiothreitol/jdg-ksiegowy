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
buyer = typer.Typer(help="Kontrahenci: dane z Bialej listy MF.", no_args_is_help=True)
payment = typer.Typer(
    help="Platnosci: oznaczanie zaplaty, import wyciagu z banku.", no_args_is_help=True
)

Money = Annotated[Decimal, typer.Option(parser=money, help="Kwota netto (PLN).")]


def _item(value: str) -> app.ItemInput:
    """'opis;ilosc;jm;cena netto;stawka[;GTU_xx]' — stawka liczbowa albo kod np/zw/0/0_wdt/0_exp."""
    parts = [p.strip() for p in value.split(";")]
    if len(parts) not in (5, 6):
        raise typer.BadParameter("format: 'opis;ilosc;jm;cena netto;stawka[;GTU_xx]'")
    description, quantity, unit, price, rate = parts[:5]
    is_code = not rate.replace(".", "", 1).isdigit()
    return app.ItemInput(
        description=description,
        quantity=money(quantity),
        unit=unit,
        unit_price_net=money(price),
        vat_rate=None if is_code else money(rate),
        vat_code=rate.upper() if is_code else None,
        gtu=parts[5].upper() if len(parts) == 6 else None,
    )


ItemOption = Annotated[
    list[str] | None,
    typer.Option(
        "--item",
        help="Pozycja 'opis;ilosc;jm;cena netto;stawka[;GTU_xx]' (powtarzalne). "
        "Stawka: 23/8/5 albo kod np (poza terytorium), zw, 0, 0_wdt, 0_exp.",
    ),
]


@command(invoice, "issue", output=app.InvoiceView, prefix="invoice")
def issue(
    buyer_nip: Annotated[str, typer.Option(help="NIP nabywcy (PL).")] = "",
    net: Annotated[
        Decimal | None, typer.Option(parser=money, help="Netto jednej pozycji (zamiast --item).")
    ] = None,
    item: ItemOption = None,
    buyer_name: Annotated[str | None, typer.Option(help="Nazwa (domyslnie z rejestru).")] = None,
    buyer_address: Annotated[str | None, typer.Option(help="Adres nabywcy.")] = None,
    buyer_email: Annotated[str | None, typer.Option(help="E-mail do wysylki faktury.")] = None,
    buyer_country: Annotated[str, typer.Option(help="Kod kraju nabywcy (ISO).")] = "PL",
    buyer_eu_vat: Annotated[str | None, typer.Option(help="Numer VAT-UE nabywcy z UE.")] = None,
    description: Annotated[str | None, typer.Option(help="Opis uslugi (z --net).")] = None,
    issue_date: Annotated[date | None, typer.Option(parser=day, help="Data wystawienia.")] = None,
    sale_date: Annotated[
        date | None, typer.Option(parser=day, help="Data sprzedazy — okres JPK.")
    ] = None,
    payment_due: Annotated[date | None, typer.Option(parser=day, help="Termin platnosci.")] = None,
    period_from: Annotated[
        date | None, typer.Option(parser=day, help="Okres uslugi od (P_6 okres na fakturze).")
    ] = None,
    period_to: Annotated[date | None, typer.Option(parser=day, help="Okres uslugi do.")] = None,
    lookup: Annotated[
        bool, typer.Option(help="Nowy nabywca bez nazwy: dane z Bialej listy MF.")
    ] = True,
    dry_run: Annotated[bool, typer.Option(help="Pokaz fakture bez zapisu.")] = False,
) -> app.InvoiceView:
    """Wystaw fakture VAT: XML FA(3) + DOCX + wpis w rejestrze (bez wysylki do KSeF)."""
    return app.issue_invoice(
        app.IssueInvoiceInput(
            buyer_nip=buyer_nip,
            net=net,
            items=[_item(i) for i in item or []],
            buyer_name=buyer_name,
            buyer_address=buyer_address,
            buyer_email=buyer_email,
            buyer_country=buyer_country.upper(),
            buyer_eu_vat=buyer_eu_vat,
            description=description,
            issue_date=issue_date,
            sale_date=sale_date,
            payment_due=payment_due,
            period_from=period_from,
            period_to=period_to,
            lookup_buyer=lookup,
        ),
        dry_run=dry_run,
    )


@command(invoice, "correct", output=app.InvoiceView, prefix="invoice")
def correct(
    number: Annotated[str, typer.Argument(help="Numer korygowanej faktury.")],
    item: ItemOption,
    reason: Annotated[str, typer.Option(help="Przyczyna korekty (trafia do FA(3)).")],
    issue_date: Annotated[
        date | None, typer.Option(parser=day, help="Data wystawienia korekty.")
    ] = None,
    dry_run: Annotated[bool, typer.Option(help="Pokaz korekte bez zapisu.")] = False,
) -> app.InvoiceView:
    """Faktura korygujaca: pozycje roznicowe (ujemna cena = zmniejszenie)."""
    return app.correct_invoice(
        number,
        [_item(i) for i in item or []],
        reason=reason,
        issue_date=issue_date,
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


@command(buyer, "lookup", output=app.BuyerLookup, prefix="buyer")
def buyer_lookup(nip: Annotated[str, typer.Argument(help="NIP kontrahenta.")]) -> app.BuyerLookup:
    """Status VAT, nazwa, adres i rachunki kontrahenta z Bialej listy MF."""
    return app.lookup_buyer(nip)
