"""jdg jpk ..."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Annotated

import typer
from pydantic import BaseModel

from jdg_ksiegowy.app import jpk as app
from jdg_ksiegowy.cli.output import command
from jdg_ksiegowy.cli.params import money, previous_month

jpk = typer.Typer(help="JPK_V7M i JPK_EWP: budowa, walidacja, wysylka do MF.", no_args_is_help=True)


class FilingList(BaseModel):
    filings: list[app.FilingView]


@command(jpk, "build", output=app.JpkBuildResult, prefix="jpk")
def build(
    year: Annotated[int | None, typer.Option(help="Rok (domyslnie poprzedni miesiac).")] = None,
    month: Annotated[int | None, typer.Option(min=1, max=12)] = None,
    correction: Annotated[bool, typer.Option(help="Korekta (CelZlozenia=2).")] = False,
    reason: Annotated[str | None, typer.Option(help="Uzasadnienie korekty (P_ORDZU).")] = None,
) -> app.JpkBuildResult:
    """Zbuduj JPK_V7M za miesiac z rejestru i zwaliduj XSD."""
    default_year, default_month = previous_month()
    return app.build_v7m(
        year or default_year, month or default_month, correction=correction, reason=reason
    )


@command(jpk, "build-ewp", output=app.JpkBuildResult, prefix="jpk")
def build_ewp(
    year: Annotated[int, typer.Option(help="Rok podatkowy.")],
    ryczalt_rate: Annotated[
        Decimal | None, typer.Option(parser=money, help="Stawka (domyslnie z .env).")
    ] = None,
    correction: Annotated[bool, typer.Option()] = False,
) -> app.JpkBuildResult:
    """Zbuduj roczna ewidencje przychodow JPK_EWP (sklada sie do 30.04)."""
    return app.build_ewp(year, ryczalt_rate=ryczalt_rate, correction=correction)


@command(jpk, "validate", output=app.ValidationView, prefix="jpk")
def validate(path: Annotated[Path, typer.Argument(help="Plik JPK (XML).")]) -> app.ValidationView:
    """Walidacja XSD offline (schemat z naglowka pliku)."""
    return app.validate_file(path)


@command(jpk, "submit", output=app.FilingView, prefix="jpk", confirmable=True)
def submit(
    path: Annotated[Path, typer.Argument(help="Plik JPK do wyslania.")],
    confirm: Annotated[str | None, typer.Option(help="Token z podsumowania.")] = None,
    wait: Annotated[int, typer.Option(help="Ile sekund czekac na UPO.")] = 600,
) -> app.FilingView:
    """Wyslij JPK do bramki MF (wymaga potwierdzenia); zapisuje numer i UPO."""
    return app.submit(path, confirm=confirm, wait_seconds=wait)


@command(jpk, "status", output=FilingList, prefix="jpk")
def status(
    reference: Annotated[str | None, typer.Option(help="Numer referencyjny MF.")] = None,
    year: Annotated[int | None, typer.Option()] = None,
    month: Annotated[int | None, typer.Option(min=1, max=12)] = None,
    wait: Annotated[int, typer.Option(help="Czekaj na wynik do N sekund.")] = 0,
) -> FilingList:
    """Zlozone deklaracje; niezakonczone dopytuje w bramce MF."""
    return FilingList(
        filings=app.status(reference=reference, year=year, month=month, wait_seconds=wait)
    )
