"""`jdg` — CLI asystenta ksiegowego JDG.

Dla ludzi: tabele Rich i pytanie o potwierdzenie przy czynnosciach nieodwracalnych.
Dla agentow: JSON na stdout (automatycznie, gdy wyjscie nie jest terminalem),
stale kody wyjscia, `jdg schema` z opisem wszystkich komend.
"""

from __future__ import annotations

import logging
from datetime import date
from enum import Enum
from pathlib import Path
from typing import Annotated, Any

import typer
from pydantic import BaseModel
from rich.logging import RichHandler

from jdg_ksiegowy import __version__
from jdg_ksiegowy.app import audit as audit_app
from jdg_ksiegowy.app import system as app
from jdg_ksiegowy.app.errors import ExitCode
from jdg_ksiegowy.cli.expenses import expense
from jdg_ksiegowy.cli.invoices import invoice, payment
from jdg_ksiegowy.cli.jpk import jpk
from jdg_ksiegowy.cli.ksef import ksef
from jdg_ksiegowy.cli.output import STATE, command, stderr
from jdg_ksiegowy.cli.params import day
from jdg_ksiegowy.cli.tax import contract, tax

cli = typer.Typer(
    name="jdg",
    help="Asystent ksiegowy JDG: faktury, KSeF, JPK, podatki.",
    no_args_is_help=True,
    pretty_exceptions_enable=False,
)
calendar = typer.Typer(help="Terminy podatkowe w Google Calendar.", no_args_is_help=True)

for group, name in (
    (invoice, "invoice"),
    (payment, "payment"),
    (ksef, "ksef"),
    (expense, "expense"),
    (jpk, "jpk"),
    (tax, "tax"),
    (contract, "contract"),
    (calendar, "calendar"),
):
    cli.add_typer(group, name=name)


def _version(value: bool) -> None:
    if value:
        print(__version__)
        raise typer.Exit()


@cli.callback()
def root(
    json_output: Annotated[
        bool | None, typer.Option("--json/--human", help="Format wyjscia (domyslnie: auto).")
    ] = None,
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Logi na stderr.")] = False,
    version: Annotated[
        bool, typer.Option("--version", callback=_version, is_eager=True, help="Wersja.")
    ] = False,
) -> None:
    STATE.json = json_output
    logging.basicConfig(
        level=logging.INFO if verbose else logging.WARNING,
        format="%(message)s",
        handlers=[RichHandler(console=stderr, show_path=False)],
        force=True,
    )


@command(cli, "status", output=app.StatusView, prefix="")
def status(
    on: Annotated[date | None, typer.Option(parser=day, help="Dzien odniesienia.")] = None,
) -> app.StatusView:
    """Terminy, niezaplacone faktury i podsumowanie miesiaca."""
    return app.status(on)


@command(cli, "doctor", output=app.DoctorView, prefix="")
def doctor() -> app.DoctorView:
    """Diagnostyka konfiguracji (.env, KSeF, bramka MF, SMTP, OCR, kalendarz)."""
    return app.doctor()


@command(cli, "backup", output=app.BackupView, prefix="")
def backup(
    output_dir: Annotated[Path | None, typer.Option(help="Katalog docelowy.")] = None,
    keep_days: Annotated[int, typer.Option(min=1)] = 30,
    keep_monthly: Annotated[int, typer.Option(min=1)] = 12,
) -> app.BackupView:
    """Szyfrowany backup bazy i dokumentow (weryfikowany po zapisie)."""
    return app.backup(output_dir=output_dir, keep_days=keep_days, keep_monthly=keep_monthly)


@command(cli, "config", output=app.ConfigView, prefix="")
def config() -> app.ConfigView:
    """Efektywna konfiguracja (sekrety tylko jako ustawiony/nieustawiony)."""
    return app.show_config()


class AuditEntry(BaseModel):
    ts: str
    actor: str
    action: str
    target: str | None
    outcome: str


class AuditList(BaseModel):
    entries: list[AuditEntry]


@command(cli, "audit", output=AuditList, prefix="")
def audit(limit: Annotated[int, typer.Option(min=1, max=1000)] = 30) -> AuditList:
    """Ostatnie wpisy dziennika czynnosci."""
    return AuditList(
        entries=[
            AuditEntry(
                ts=r.ts.isoformat(timespec="seconds"),
                actor=r.actor,
                action=r.action,
                target=r.target,
                outcome=r.outcome,
            )
            for r in audit_app.recent(limit)
        ]
    )


@command(calendar, "sync", output=app.CalendarSyncView, prefix="calendar")
def calendar_sync(
    dry_run: Annotated[bool, typer.Option(help="Pokaz roznice bez zapisu.")] = False,
    on: Annotated[date | None, typer.Option(parser=day)] = None,
) -> app.CalendarSyncView:
    """Uzgodnij terminy podatkowe z kalendarzem Google 'JDG Podatki'."""
    return app.calendar_sync(dry_run=dry_run, today=on)


# --- schema ------------------------------------------------------------------------


class Schema(BaseModel):
    name: str
    version: str
    exit_codes: dict[str, int]
    output_envelope: dict[str, Any]
    commands: list[dict[str, Any]]


def _param(p: Any) -> dict[str, Any]:
    annotation = p.type_descriptor.annotation
    is_enum = isinstance(annotation, type) and issubclass(annotation, Enum)
    default = p.default
    if isinstance(default, Enum):
        default = default.value
    elif not isinstance(default, str | int | float | bool):
        default = None if default is None else str(default)
    return {
        "name": p.name,
        "kind": p.param_type_name,
        "flags": [*p.opts, *p.secondary_opts],
        "type": "str" if is_enum else getattr(annotation, "__name__", str(annotation)),
        "choices": [e.value for e in annotation] if is_enum else None,
        "multiple": bool(getattr(p, "multiple", False)),
        "required": bool(p.required),
        "default": default,
        "help": getattr(p, "help", None),
    }


def build_schema() -> Schema:
    root_cmd = typer.main.get_command(cli)
    commands = []

    def walk(cmd: Any, path: list[str]) -> None:
        for name, sub in sorted(getattr(cmd, "commands", {}).items()):
            walk(sub, [*path, name])
        spec = STATE.registry.get(" ".join(path))
        if spec is None:
            return
        commands.append(
            {
                "name": spec.path,
                "help": (cmd.help or "").strip().splitlines()[0] if cmd.help else "",
                "confirmable": spec.confirmable,
                "params": [_param(p) for p in cmd.params if p.name != "json_output"],
                "output_schema": spec.output.model_json_schema() if spec.output else None,
            }
        )

    walk(root_cmd, [])
    return Schema(
        name="jdg",
        version=__version__,
        exit_codes={
            name.lower(): getattr(ExitCode, name)
            for name in ("OK", "DOMAIN", "USAGE", "CONFIG", "CONFIRMATION", "EXTERNAL")
        },
        output_envelope={
            "ok": {"ok": True, "data": "<output_schema>"},
            "error": {
                "ok": False,
                "error": {
                    "code": "str",
                    "message": "str",
                    "hint": "str|null",
                    "retryable": "bool",
                    "details": "object (CONFIRMATION_REQUIRED: action, token, summary)",
                },
            },
        },
        commands=sorted(commands, key=lambda c: c["name"]),
    )


@cli.command("schema")
def schema() -> None:
    """Opis wszystkich komend (parametry, wyjscie, kody bledow) jako JSON."""
    print(build_schema().model_dump_json(indent=2))


def main() -> None:
    cli()
