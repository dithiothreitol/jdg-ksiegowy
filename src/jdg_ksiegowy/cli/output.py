"""Kontrakt wyjscia CLI: koperta JSON dla agentow, Rich dla ludzi, stale kody wyjscia.

- stdout: wynik (JSON gdy `--json`, JDG_OUTPUT=json albo wyjscie nie jest terminalem),
- stderr: logi i komunikaty dla czlowieka,
- kod wyjscia: `app.errors.ExitCode`.

Czynnosci nieodwracalne: w terminalu pytamy o potwierdzenie; bez terminala
(agent, cron) zwracamy kod 4 z tokenem — bez pytan interaktywnych.
"""

from __future__ import annotations

import functools
import inspect
import json
import os
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

import typer
from pydantic import BaseModel
from rich.console import Console, RenderableType
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from jdg_ksiegowy.app.errors import AppError, ConfirmationRequiredError, ExitCode

stdout = Console(soft_wrap=True)
stderr = Console(stderr=True, soft_wrap=True)


@dataclass
class CommandSpec:
    path: str
    fn: Callable[..., BaseModel | None]
    output: type[BaseModel] | None
    confirmable: bool
    read_only: bool


@dataclass
class _State:
    json: bool | None = None  # None = automatycznie (terminal -> Rich, inaczej JSON)
    registry: dict[str, CommandSpec] = field(default_factory=dict)


STATE = _State()


def json_mode() -> bool:
    if STATE.json is not None:
        return STATE.json
    if os.environ.get("JDG_OUTPUT", "").lower() == "json":
        return True
    return not sys.stdout.isatty()


def interactive() -> bool:
    return not json_mode() and sys.stdin.isatty() and sys.stdout.isatty()


def _jsonable(result: BaseModel | None) -> Any:
    return None if result is None else result.model_dump(mode="json")


def ok_envelope(result: BaseModel | None) -> dict[str, Any]:
    return {"ok": True, "data": _jsonable(result)}


def error_envelope(err: AppError) -> dict[str, Any]:
    return {"ok": False, "error": err.to_dict()}


def emit_ok(result: BaseModel | None) -> None:
    if json_mode():
        print(json.dumps(ok_envelope(result), ensure_ascii=False, indent=2))
        return
    if result is not None:
        render(result)


def emit_error(err: AppError) -> None:
    if json_mode():
        print(json.dumps(error_envelope(err), ensure_ascii=False, indent=2))
        return
    if isinstance(err, ConfirmationRequiredError):
        stderr.print(_summary_panel(err))
        stderr.print(f"[yellow]{err.message}[/]\nPotwierdzenie: [bold]--confirm {err.token}[/]")
        return
    stderr.print(f"[bold red]Błąd ({err.code}):[/] {err.message}")
    if err.hint:
        stderr.print(f"[dim]Podpowiedź:[/] {err.hint}")
    for key, value in err.details.items():
        stderr.print(f"[dim]{key}:[/] {value}")


def _summary_panel(err: ConfirmationRequiredError) -> Panel:
    return Panel(
        _summary_grid(err.summary), title=f"Do potwierdzenia: {err.action}", border_style="yellow"
    )


def _summary_grid(summary: dict[str, Any]) -> Table:
    """Klucz i wartosc; porownanie z poprzednim okresem jako wcieta podtabela."""
    table = Table.grid(padding=(0, 2))
    for key, value in summary.items():
        alarm = key == "uwaga" or (key == "env" and value == "prod")
        table.add_row(f"[dim]{key}[/]", _summary_value(value, "bold red" if alarm else ""))
    return table


def _summary_value(value: Any, style: str) -> RenderableType:
    if isinstance(value, dict):
        return _summary_grid(value)
    text = "\n".join(map(str, value)) if isinstance(value, list) else str(value)
    return Text(text, style=style)  # Text: nawiasy w opisie faktury nie sa znacznikami Rich


# --- renderowanie dla czlowieka ----------------------------------------------------------


def _cell(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, Decimal):
        return f"{value:,.2f}".replace(",", " ")
    if isinstance(value, list):
        return ", ".join(map(str, value))
    return str(value)


def _table_of(rows: list[BaseModel], title: str) -> Table:
    table = Table(title=title, title_justify="left", header_style="bold")
    model = type(rows[0])
    columns = list(getattr(model, "table_columns", None) or model.model_fields)
    for col in columns:
        sample = getattr(rows[0], col)
        table.add_column(col, justify="right" if isinstance(sample, Decimal) else "left")
    for row in rows:
        table.add_row(*(_cell(getattr(row, col)) for col in columns))
    return table


def render(result: BaseModel) -> None:
    scalars = Table.grid(padding=(0, 2))
    lists: list[tuple[str, list[BaseModel]]] = []
    for name in type(result).model_fields:
        value = getattr(result, name)
        if isinstance(value, list) and value and isinstance(value[0], BaseModel):
            lists.append((name, value))
        elif isinstance(value, BaseModel):
            lists.append((name, [value]))
        elif not (isinstance(value, list) and not value):
            scalars.add_row(f"[dim]{name}[/]", _cell(value))
    if scalars.row_count:
        stdout.print(scalars)
    for name, rows in lists:
        stdout.print(_table_of(rows, name))


# --- dekorator komend --------------------------------------------------------------------

_JSON_OPTION = inspect.Parameter(
    "json_output",
    inspect.Parameter.KEYWORD_ONLY,
    default=typer.Option(None, "--json/--human", help="Wymuś format wyjścia (domyślnie: auto)."),
    annotation=bool | None,
)


def command(
    group: typer.Typer,
    name: str,
    *,
    output: type[BaseModel] | None,
    prefix: str,
    confirmable: bool = False,
    read_only: bool = False,
) -> Callable[[Callable[..., BaseModel | None]], Callable[..., BaseModel | None]]:
    """Zarejestruj komende: obsluga bledow, koperta wyjscia, potwierdzanie, wpis do `schema`.

    Funkcja komendy zwraca model wyniku (pydantic). Komenda z `confirmable=True` musi
    przyjmowac parametr `confirm`. `read_only=True` — komenda niczego nie zapisuje
    ani nie wysyla (adnotacja narzedzia MCP, pole `read_only` w `schema`).
    """

    def deco(fn: Callable[..., BaseModel | None]) -> Callable[..., BaseModel | None]:
        # eval_str: moduly komend uzywaja `from __future__ import annotations`, a Typer
        # czyta jawna __signature__ wrappera bez rozwiazywania napisow.
        signature = inspect.signature(fn, eval_str=True)

        @functools.wraps(fn)
        def wrapper(**kwargs: Any) -> None:
            forced = kwargs.pop("json_output", None)
            if forced is not None:
                STATE.json = forced
            try:
                result = _run(fn, kwargs, confirmable)
            except AppError as err:
                emit_error(err)
                raise typer.Exit(err.exit_code) from None
            emit_ok(result)

        params = [*signature.parameters.values(), _JSON_OPTION]
        wrapper.__signature__ = signature.replace(parameters=params)  # type: ignore[attr-defined]
        wrapper.__annotations__ = {p.name: p.annotation for p in params}
        group.command(name)(wrapper)
        path = f"{prefix} {name}".strip()
        STATE.registry[path] = CommandSpec(
            path=path, fn=fn, output=output, confirmable=confirmable, read_only=read_only
        )
        return fn

    return deco


def _run(fn: Callable[..., BaseModel | None], kwargs: dict[str, Any], confirmable: bool) -> Any:
    try:
        return fn(**kwargs)
    except ConfirmationRequiredError as err:
        if not (confirmable and interactive()):
            raise
        stderr.print(_summary_panel(err))
        if not typer.confirm("Wykonać?", default=False, err=True):
            raise typer.Exit(ExitCode.CONFIRMATION) from None
        return fn(**{**kwargs, "confirm": err.token})
