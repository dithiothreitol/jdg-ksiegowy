"""jdg tax ... / jdg contract ..."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Annotated

import typer

from jdg_ksiegowy.app import contracts as contracts_app
from jdg_ksiegowy.app import tax as app
from jdg_ksiegowy.cli.output import command
from jdg_ksiegowy.cli.params import day, money

tax = typer.Typer(help="Podatki: kalkulator, terminy, PIT-28, DRA ZUS.", no_args_is_help=True)
contract = typer.Typer(help="Kontrakty cykliczne (faktury co miesiac).", no_args_is_help=True)


@command(tax, "calc", output=app.TaxCalc, prefix="tax")
def calc(
    net: Annotated[Decimal, typer.Option(parser=money, help="Kwota netto.")],
    year: Annotated[int | None, typer.Option()] = None,
    month: Annotated[int | None, typer.Option(min=1, max=12)] = None,
    vat_rate: Annotated[Decimal | None, typer.Option(parser=money)] = None,
    ryczalt_rate: Annotated[Decimal | None, typer.Option(parser=money)] = None,
    annual_revenue: Annotated[
        Decimal | None, typer.Option(parser=money, help="Roczny przychod (prog zdrowotnej).")
    ] = None,
) -> app.TaxCalc:
    """VAT, ryczalt, ZUS i terminy dla kwoty netto."""
    today = date.today()
    return app.calculate(
        net,
        month=month or today.month,
        year=year or today.year,
        vat_rate=vat_rate,
        ryczalt_rate=ryczalt_rate,
        annual_revenue=annual_revenue,
    )


@command(tax, "deadlines", output=app.Deadlines, prefix="tax")
def deadlines(
    year: Annotated[int | None, typer.Option()] = None,
    month: Annotated[int | None, typer.Option(min=1, max=12, help="Miesiac rozliczeniowy.")] = None,
) -> app.Deadlines:
    """Terminy ryczaltu, ZUS i VAT za miesiac."""
    today = date.today()
    return app.deadlines(month or today.month, year or today.year)


@command(tax, "pit28", output=app.Pit28View, prefix="tax")
def pit28(year: Annotated[int, typer.Option(help="Rok podatkowy.")]) -> app.Pit28View:
    """Podsumowanie roczne ryczaltu (PIT-28) z rejestru."""
    return app.pit28(year)


@command(tax, "dra", output=app.DraView, prefix="tax")
def dra(
    month: Annotated[int, typer.Option(min=1, max=12)],
    year: Annotated[int, typer.Option()],
    annual_prior_income: Annotated[
        Decimal, typer.Option(parser=money, help="Przychod za poprzedni rok (prog zdrowotnej).")
    ],
    include_social: Annotated[bool, typer.Option(help="Dolicz skladki spoleczne.")] = False,
    output: Annotated[Path | None, typer.Option(help="Plik XML (domyslnie data/zus/).")] = None,
) -> app.DraView:
    """Deklaracja DRA ZUS (KEDU) do importu w PUE ZUS."""
    return app.dra(
        month,
        year,
        annual_prior_income=annual_prior_income,
        include_social=include_social,
        output=output,
    )


@command(contract, "add", output=contracts_app.ContractView, prefix="contract")
def add(
    buyer_name: Annotated[str, typer.Option()],
    buyer_nip: Annotated[str, typer.Option()],
    buyer_address: Annotated[str, typer.Option()],
    description: Annotated[str, typer.Option(help="Opis uslugi na fakturze.")],
    net: Annotated[Decimal, typer.Option(parser=money)],
    vat_rate: Annotated[Decimal, typer.Option(parser=money)] = Decimal("23"),
    buyer_email: Annotated[str | None, typer.Option()] = None,
    day_of_month: Annotated[
        int, typer.Option(min=-1, max=28, help="-1 = ostatni dzien roboczy.")
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


@command(contract, "list", output=contracts_app.ContractList, prefix="contract")
def list_() -> contracts_app.ContractList:
    """Aktywne kontrakty."""
    return contracts_app.list_contracts()


@command(contract, "run", output=contracts_app.ContractRun, prefix="contract")
def run(
    on: Annotated[date | None, typer.Option(parser=day, help="Dzien (domyslnie dzis).")] = None,
) -> contracts_app.ContractRun:
    """Wystaw faktury z kontraktow wymagalnych danego dnia (idempotentne)."""
    return contracts_app.run(on)
