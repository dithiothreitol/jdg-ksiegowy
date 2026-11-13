"""Serwer MCP: kontrakt = `jdg schema`, ta sama koperta wyniku, dwufazowosc, autoryzacja HTTP."""

import httpx
import pytest
from mcp import Client

from jdg_ksiegowy.cli import mcp_server
from jdg_ksiegowy.cli.main import build_schema
from jdg_ksiegowy.registry.repository import InvoiceRepository

SCHEMA = build_schema()
KSEF = "1234567890-20261110-ABCDEF-ABCDEF-01"


def test_tools_match_cli_schema():
    tools = mcp_server.tool_defs()
    assert set(tools) == {mcp_server.tool_name(c["name"]) for c in SCHEMA.commands}
    for command in SCHEMA.commands:
        tool = tools[mcp_server.tool_name(command["name"])].tool
        props = tool.input_schema["properties"]
        assert set(props) == {p["name"] for p in command["params"]}, command["name"]
        required = {p["name"] for p in command["params"] if p["required"]}
        assert set(tool.input_schema.get("required", [])) == required, command["name"]
        assert tool.annotations.read_only_hint is command["read_only"]
        assert ("confirm" in props) is command["confirmable"]
        if command["confirmable"]:
            assert tool.annotations.destructive_hint is True
            assert "CONFIRMATION_REQUIRED" in (tool.description or "")


def test_call_returns_cli_envelope(isolated_db):
    result = mcp_server.call(mcp_server.tool_defs(), "tax_calc", {"net": "10500", "year": 2026})
    assert result["ok"] is True
    assert result["data"]["vat"] == "2415.00" and result["data"]["ryczalt"] == "1260"


def test_invalid_arguments_are_reported_not_raised(isolated_db):
    tools = mcp_server.tool_defs()
    bad_type = mcp_server.call(tools, "tax_calc", {"net": "sto"})
    unknown = mcp_server.call(tools, "tax_calc", {"net": "1", "rm_rf": True})
    in_body = mcp_server.call(tools, "invoice_list", {"by": "kolor"})
    out_of_range = mcp_server.call(tools, "tax_zus", {"year": 2026, "month": 13})
    for result in (bad_type, unknown, in_body, out_of_range):
        assert result["ok"] is False and result["error"]["code"] == "INVALID_ARGUMENTS"
    assert "kolor" not in in_body["error"]["message"] and "dozwolone" in in_body["error"]["message"]
    assert mcp_server.call(tools, "nie_ma", {})["error"]["code"] == "INVALID_ARGUMENTS"


def test_domain_error_keeps_code(isolated_db):
    result = mcp_server.call(mcp_server.tool_defs(), "invoice_show", {"number": "X1/01/2026"})
    assert result == {"ok": False, "error": result["error"]}
    assert result["error"]["code"] == "NOT_FOUND"


def test_issue_and_send_two_phase_over_mcp(isolated_db, monkeypatch):
    from jdg_ksiegowy.app import audit
    from jdg_ksiegowy.config import settings
    from jdg_ksiegowy.ksef.client import KSeFClient, KSeFResult

    monkeypatch.setattr(settings.ksef, "env", "test")
    monkeypatch.setattr(settings.ksef, "nip", "1234567890")
    sent: list[str] = []

    def fake_send(self, xml_content):
        sent.append(xml_content)
        return KSeFResult(
            success=True, env="test", reference_number="REF", ksef_number=KSEF, upo=b"<UPO/>"
        )

    monkeypatch.setattr(KSeFClient, "send_invoice", fake_send)
    tools = mcp_server.tool_defs()
    issued = mcp_server.call(
        tools,
        "invoice_issue",
        {
            "buyer_nip": "5260250274",
            "buyer_name": "Klient",
            "buyer_address": "ul. X 1, 00-001 Warszawa",
            "item": ["Konsultacje;2;h;250;23;GTU_12"],
            "issue_date": "2026-11-10",
        },
    )
    assert issued["ok"], issued
    number = issued["data"]["number"]
    assert issued["data"]["gross"] == "615.00"

    first = mcp_server.call(tools, "ksef_send", {"number": number})
    assert first["error"]["code"] == "CONFIRMATION_REQUIRED" and sent == []
    assert first["error"]["details"]["summary"]["env"] == "test"
    wrong = mcp_server.call(tools, "ksef_send", {"number": number, "confirm": "0" * 12})
    assert wrong["error"]["code"] == "CONFIRMATION_REQUIRED" and sent == []

    token = first["error"]["details"]["token"]
    done = mcp_server.call(tools, "ksef_send", {"number": number, "confirm": token})
    assert done["ok"] and done["data"]["ksef_number"] == KSEF and len(sent) == 1
    assert InvoiceRepository().get(number).ksef_number == KSEF
    assert {e.actor for e in audit.recent(10)} == {"mcp"}


@pytest.mark.asyncio
async def test_protocol_roundtrip(isolated_db):
    async with Client(mcp_server.build_server()) as client:
        listed = await client.list_tools()
        assert len(listed.tools) == len(SCHEMA.commands)
        ok = await client.call_tool("tax_deadlines", {"year": 2026, "month": 12})
        assert ok.is_error is False
        assert ok.structured_content["data"]["ryczalt"] == "2027-01-20"
        failed = await client.call_tool("invoice_show", {"number": "X1/01/2026"})
        assert failed.is_error is True
        assert failed.structured_content["error"]["code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_http_requires_bearer_token():
    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    guarded = mcp_server.guarded(app, "s3cret")
    transport = httpx.ASGITransport(app=guarded)
    async with httpx.AsyncClient(transport=transport, base_url="http://jdg-mcp") as http:
        assert (await http.get("/healthz")).status_code == 200
        assert (await http.post("/mcp")).status_code == 401
        bad = await http.post("/mcp", headers={"Authorization": "Bearer nope"})
        assert bad.status_code == 401
        good = await http.post("/mcp", headers={"Authorization": "Bearer s3cret"})
        assert good.status_code == 204


def test_http_refuses_to_start_without_token(monkeypatch):
    from typer.testing import CliRunner

    from jdg_ksiegowy.cli.main import cli
    from jdg_ksiegowy.config import settings

    monkeypatch.setattr(settings, "mcp_token", "")
    result = CliRunner().invoke(cli, ["--json", "mcp", "serve", "--transport", "http"])
    assert result.exit_code == 3 and "JDG_MCP_TOKEN" in result.output
