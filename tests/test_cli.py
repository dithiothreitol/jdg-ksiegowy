"""Kontrakt CLI `jdg`: parytet ze skryptami 0.x, koperta JSON, kody wyjscia, schema."""

import json
import os
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from typer.testing import CliRunner

from jdg_ksiegowy.app.errors import ExitCode
from jdg_ksiegowy.cli.main import build_schema, cli
from jdg_ksiegowy.cli.output import STATE
from tests.helpers import InvoiceRow, save_invoice, seed_parity_dataset

GOLDEN = Path(__file__).parent / "golden"
runner = CliRunner()


def jdg(*args: str) -> tuple[int, dict]:
    result = runner.invoke(cli, list(args))
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        pytest.fail(f"Wyjscie nie jest JSON (exit={result.exit_code}): {result.output}")
    return result.exit_code, payload


def data(*args: str) -> dict:
    code, payload = jdg(*args)
    assert code == 0 and payload["ok"], payload
    return payload["data"]


@pytest.fixture(autouse=True)
def _auto_json():
    STATE.json = None
    yield
    STATE.json = None


def D(value) -> Decimal:  # noqa: N802
    return Decimal(str(value))


# --- parytet z wynikami skryptow 0.x (tests/golden/parity_v0.json) -------------------


@pytest.fixture
def parity(isolated_db):
    seed_parity_dataset()
    return json.loads((GOLDEN / "parity_v0.json").read_text(encoding="utf-8"))


def test_parity_jpk_v7m(parity):
    g = parity["jpk_v7m_2026_10"]
    d = data("jpk", "build", "--year", "2026", "--month", "10")
    assert d["xsd_valid"] is True
    assert (d["invoice_count"], d["expense_count"]) == (g["invoice_count"], g["expense_count"])
    assert D(d["sales_net"]) == D(g["sales_total_net"])
    assert D(d["sales_vat"]) == D(g["sales_total_vat"])
    assert D(d["vat_deductible"]) == D(g["expenses_deductible_vat"])
    assert D(d["vat_due"]) == D(g["vat_due"])
    assert D(d["vat_to_pay"]) == D(g["vat_to_pay"])


def test_parity_ewp_and_pit28(parity):
    d = data("jpk", "build-ewp", "--year", "2026")
    assert d["invoice_count"] == parity["jpk_ewp_2026"]["invoice_count"]
    assert D(d["revenue"]) == D(parity["jpk_ewp_2026"]["total_revenue"])

    g = parity["pit28_2026"]
    p = data("tax", "pit28", "--year", "2026")
    assert D(p["annual_sales_net"]) == D(g["annual_sales_net"])
    # 1.0: ryczalt w pelnych zlotych (art. 63 Ordynacji) — 0.x zaokraglal tylko sume roczna.
    assert D(p["annual_ryczalt"]) == D(g["annual_ryczalt_rounded"])
    assert [(m["month"], D(m["sales_net"])) for m in p["monthly"]] == [
        (m["month"], D(m["sales_net"])) for m in g["monthly"]
    ]


def test_parity_tax_calc(parity):
    g = parity["tax_calc"]
    d = data("tax", "calc", "--net", "10500", "--month", "11", "--year", "2026")
    for new, old in (
        ("vat", "vat_amount"),
        ("gross", "brutto"),
        ("ryczalt", "ryczalt_amount"),
        ("zus_health_monthly", "zus_health_monthly"),
        ("zus_social_monthly", "zus_social_monthly"),
        ("zus_total_monthly", "zus_total_monthly"),
        ("total_monthly_burden", "total_monthly_tax"),
    ):
        assert D(d[new]) == D(g[old]), new
    # 1.0: terminy przesuwane na dzien roboczy — 20.12.2026 (niedziela) -> 21.12,
    # 25.12 (swieto) -> 28.12. 0.x zwracal daty kalendarzowe.
    assert (g["deadlines"]["ryczalt_zus"], d["deadline_ryczalt_zus"]) == (
        "2026-12-20",
        "2026-12-21",
    )
    assert (g["deadlines"]["vat_jpk"], d["deadline_vat_jpk"]) == ("2026-12-25", "2026-12-28")


def test_parity_status(parity):
    g = parity["status_2026_11_13"]
    d = data("status", "--on", "2026-11-13")

    def rows(reminders: list[dict], skip_zus: bool) -> list[tuple]:
        return [
            (r["label"], r["due_date"], r["amount"] and D(r["amount"]))
            for r in reminders
            if not (skip_zus and r["label"].startswith("ZUS"))
        ]

    assert rows(d["reminders"], True) == rows(g["reminders"], True)
    # 1.0: ZUS = zdrowotna wg przychodu NARASTAJACO (20 833 zl -> prog do 60 tys.: 498.35)
    # + spoleczne (tryb pelny 1788.29). 0.x: tylko zdrowotna z "przychod miesiaca x 12".
    (zus,) = [r for r in d["reminders"] if r["label"].startswith("ZUS")]
    assert (zus["label"], D(zus["amount"])) == ("ZUS za 10/2026", D("2286.64"))
    summary = g["month_summary"]
    assert D(d["month_sales_net"]) == D(summary["sales_net"])
    assert D(d["estimated_ryczalt"]) == D(summary["estimated_ryczalt"])
    assert D(d["estimated_zus"]) == D("2286.64")
    assert [i["number"] for i in d["unpaid_invoices"]] == g["unpaid"]
    assert [i["number"] for i in d["overdue_invoices"]] == g["overdue"]


def test_parity_expenses(parity):
    d = data("expense", "list", "--year", "2026", "--month", "10")
    assert d["count"] == parity["expenses_2026_10"]["count"]
    assert sorted(e["id"] for e in d["expenses"]) == parity["expenses_2026_10"]["ids"]


def test_tax_zus_replaces_dra(parity):
    """1.0: `tax zus` liczy prog z rejestru (narastajaco), zamiast pytac o przychod z roku
    poprzedniego jak DRA w 0.x; plik KEDU nie jest juz generowany."""
    d = data("tax", "zus", "--year", "2026", "--month", "10")
    assert D(d["revenue_ytd"]) == D("20833.33")
    assert (D(d["health"]), D(d["social"]), D(d["total"])) == (
        D("498.35"),
        D("1788.29"),
        D("2286.64"),
    )
    assert d["deadline"] == "2026-11-20"


# --- koperta, kody wyjscia --------------------------------------------------------


def test_every_command_has_help():
    for spec in build_schema().commands:
        result = runner.invoke(cli, [*spec["name"].split(), "--help"])
        assert result.exit_code == 0, spec["name"]


def test_outputs_validate_against_declared_models(isolated_db):
    """Wynik `data` kazdej komendy odczytowej da sie zwalidowac modelem z `jdg schema`."""
    from jdg_ksiegowy.cli.output import STATE as S

    save_invoice(
        InvoiceRow(number="A1/11/2026", issue_date=date(2026, 11, 3), total_net=Decimal("100"))
    )
    cases = {
        "invoice list": ["invoice", "list"],
        "invoice show": ["invoice", "show", "A1/11/2026"],
        "expense list": ["expense", "list"],
        "tax deadlines": ["tax", "deadlines", "--month", "11", "--year", "2026"],
        "status": ["status", "--on", "2026-11-13"],
        "config": ["config"],
        "doctor": ["doctor"],
        "jpk status": ["jpk", "status"],
        "contract list": ["contract", "list"],
        "audit": ["audit"],
    }
    for name, args in cases.items():
        payload = data(*args)
        S.registry[name].output.model_validate(payload)


def test_not_found_is_domain_error(isolated_db):
    code, payload = jdg("invoice", "show", "BRAK/1/2026")
    assert code == ExitCode.DOMAIN
    assert payload["error"]["code"] == "NOT_FOUND"
    assert payload["error"]["hint"]


def test_invalid_input_has_hint(isolated_db):
    code, payload = jdg(
        "invoice", "issue", "--buyer-nip", "5260250274", "--net", "100", "--no-lookup"
    )
    assert code == ExitCode.DOMAIN
    assert payload["error"]["code"] == "INVALID_INPUT"
    assert "--buyer-name" in payload["error"]["hint"]


def test_usage_error_exit_code():
    result = runner.invoke(cli, ["invoice", "issue", "--net", "abc", "--buyer-nip", "1"])
    assert result.exit_code == ExitCode.USAGE


def test_config_missing_exit_code(isolated_db, monkeypatch):
    from jdg_ksiegowy.config import settings

    monkeypatch.setattr(settings.ksef, "env", "prod")
    monkeypatch.setattr(settings.ksef, "token", "")
    code, payload = jdg("ksef", "inbox")
    assert code == ExitCode.CONFIG
    assert payload["error"]["code"] == "CONFIG_MISSING"


def test_human_mode_renders_tables(isolated_db):
    save_invoice(
        InvoiceRow(number="A1/11/2026", issue_date=date(2026, 11, 3), total_net=Decimal("1000"))
    )
    result = runner.invoke(cli, ["--human", "invoice", "list"])
    assert result.exit_code == 0
    assert "A1/11/2026" in result.stdout and "1 230.00" in result.stdout
    assert not result.stdout.lstrip().startswith("{")


def test_dry_run_issue_writes_nothing(isolated_db):
    d = data(
        "invoice",
        "issue",
        "--buyer-nip",
        "5260250274",
        "--buyer-name",
        "Klient",
        "--net",
        "1000",
        "--description",
        "Usluga",
        "--dry-run",
    )
    assert d["number"].startswith("A1/") and d["docx_path"] is None
    assert data("invoice", "list")["count"] == 0


# --- schema ---------------------------------------------------------------------


def test_schema_matches_golden():
    """Zmiana kontraktu komend (nazwy, parametry, modele wyjscia) musi byc swiadoma.

    Aktualizacja: UPDATE_GOLDEN=1 uv run pytest tests/test_cli.py -k schema
    """
    schema = build_schema().model_dump(mode="json")
    schema.pop("version")
    path = GOLDEN / "schema.json"
    rendered = json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if os.environ.get("UPDATE_GOLDEN"):
        path.write_text(rendered, encoding="utf-8")
    assert json.loads(path.read_text(encoding="utf-8")) == json.loads(rendered)


def test_schema_marks_irreversible_commands():
    confirmable = {c["name"] for c in build_schema().commands if c["confirmable"]}
    assert confirmable == {"ksef send", "jpk submit", "invoice mail"}
