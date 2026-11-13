"""jdg tax ... / jdg contract ..."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Annotated

import typer

from jdg_ksiegowy.app import contracts as contracts_app
from jdg_ksiegowy.app import tax as app
from jdg_ksiegowy.cli.output import command
from jdg_ksiegowy.cli.params import day, money, previous_month

tax = typer.Typer(help="Podatki: kalkulator, terminy, PIT-28, DRA ZUS.", no_args_is_help=True)
contract = typer.Typer(help="Kontrakty cykliczne (faktury co miesiąc).", no_args_is_help=True)


@command(tax, "calc", output=app.TaxCalc, prefix="tax", read_only=True)
def calc(
    net: Annotated[Decimal, typer.Option(parser=money, help="Kwota netto.")],
    year: Annotated[int | None, typer.Option()] = None,
    month: Annotated[int | None, typer.Option(min=1, max=12)] = None,
    vat_rate: Annotated[Decimal | None, typer.Option(parser=money)] = None,
    ryczalt_rate: Annotated[Decimal | None, typer.Option(parser=money)] = None,
    annual_revenue: Annotated[
        Decimal | None, typer.Option(parser=money, help="Roczny przychód (próg zdrowotnej).")
    ] = None,
) -> app.TaxCalc:
    """VAT, ryczałt, ZUS i terminy dla kwoty netto."""
    today = date.today()
    return app.calculate(
        net,
        month=month or today.month,
        year=year or today.year,
        vat_rate=vat_rate,
        ryczalt_rate=ryczalt_rate,
        annual_revenue=annual_revenue,
    )


@command(tax, "deadlines", output=app.Deadlines, prefix="tax", read_only=True)
def deadlines(
    year: Annotated[int | None, typer.Option()] = None,
    month: Annotated[int | None, typer.Option(min=1, max=12, help="Miesiąc rozliczeniowy.")] = None,
) -> app.Deadlines:
    """Terminy ryczałtu, ZUS i VAT za miesiąc."""
    today = date.today()
    return app.deadlines(month or today.month, year or today.year)


@command(tax, "pit28", output=app.Pit28View, prefix="tax", read_only=True)
def pit28(year: Annotated[int, typer.Option(help="Rok podatkowy.")]) -> app.Pit28View:
    """Podsumowanie roczne ryczałtu (PIT-28) z rejestru."""
    return app.pit28(year)


@command(tax, "zus", output=app.ZusView, prefix="tax", read_only=True)
def zus(
    year: Annotated[int | None, typer.Option(help="Rok (domyślnie poprzedni miesiąc).")] = None,
    month: Annotated[int | None, typer.Option(min=1, max=12)] = None,
) -> app.ZusView:
    """Składki ZUS za miesiąc: zdrowotna wg przychodu narastająco + społeczne."""
    default_year, default_month = previous_month()
    return app.zus(month or default_month, year or default_year)


@command(tax, "pay", output=app.PaymentView, prefix="tax")
def pay(
    kind: Annotated[str, typer.Argument(help="ryczalt | vat | zus_health | zus_social")],
    amount: Annotated[Decimal, typer.Option(parser=money, help="Zapłacona kwota.")],
    year: Annotated[int, typer.Option(help="Rok okresu, którego dotyczy zapłata.")],
    month: Annotated[int, typer.Option(min=1, max=12, help="Miesiąc okresu.")],
    paid_on: Annotated[date | None, typer.Option(parser=day, help="Data zapłaty.")] = None,
) -> app.PaymentView:
    """Zapisz zapłatę podatku lub składki (gasi przypomnienie, wchodzi do odliczeń)."""
    if kind not in ("ryczalt", "vat", "zus_health", "zus_social"):
        raise typer.BadParameter("dozwolone: ryczalt, vat, zus_health, zus_social")
    return app.record_payment(kind, year, month, amount, paid_on)  # type: ignore[arg-type]


@command(tax, "payments", output=app.PaymentList, prefix="tax", read_only=True)
def payments(year: Annotated[int | None, typer.Option()] = None) -> app.PaymentList:
    """Ewidencja zapłat podatków i składek."""
    return app.list_payments(year)


@command(contract, "add", output=contracts_app.ContractView, prefix="contract")
def add(
    buyer_name: Annotated[str, typer.Option()],
    buyer_nip: Annotated[str, typer.Option()],
    buyer_address: Annotated[str, typer.Option()],
    description: Annotated[str, typer.Option(help="Opis usługi na fakturze.")],
    net: Annotated[Decimal, typer.Option(parser=money)],
    vat_rate: Annotated[Decimal, typer.Option(parser=money)] = Decimal("23"),
    buyer_email: Annotated[str | None, typer.Option()] = None,
    day_of_month: Annotated[
        int, typer.Option(min=-1, max=28, help="-1 = ostatni dzień roboczy.")
    ] = -1,
) -> contracts_app.ContractView:
    """Dodaj kontrakt cykliczny."""
    return contracts_app.add_contract(
        contracts_app.AddContractInput(
            buyer_name=buyer_name,
            buyer_nip=buyer_nip,
            buyer_address=buyer_address,
            description=description,
            net=net,
            vat_rate=vat_rate,
            buyer_email=buyer_email,
            day_of_month=day_of_month,
        )
    )


@command(contract, "list", output=contracts_app.ContractList, prefix="contract", read_only=True)
def list_() -> contracts_app.ContractList:
    """Aktywne kontrakty."""
    return contracts_app.list_contracts()


@command(contract, "run", output=contracts_app.ContractRun, prefix="contract")
def run(
    on: Annotated[date | None, typer.Option(parser=day, help="Dzień (domyślnie dziś).")] = None,
) -> contracts_app.ContractRun:
    """Wystaw faktury z kontraktów wymagalnych danego dnia (idempotentne)."""
    return contracts_app.run(on)
