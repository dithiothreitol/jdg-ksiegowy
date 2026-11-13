"""Wtyczka Claude Code / Codex: manifesty, hook zgody i brak dryfu skilli wzgledem `jdg schema`."""

import json
import re
import runpy
import tomllib
from pathlib import Path

import jsonschema
import pytest

from jdg_ksiegowy.cli import mcp_server
from jdg_ksiegowy.cli.main import build_schema

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "jdg-ksiegowy"
SCHEMAS = Path(__file__).parent / "schemas" / "agent-plugins-1.0.0"
COMMANDS = {c["name"]: c for c in build_schema().commands}
NOT_TOOLS = {"schema", "mcp serve"}  # komendy CLI spoza rejestru narzedzi
GLOBAL_FLAGS = {"--json", "--human", "--help", "--verbose", "--version"}


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_manifests_agree_on_name_and_version():
    version = tomllib.loads((ROOT / "pyproject.toml").read_text("utf-8"))["project"]["version"]
    claude = _json(PLUGIN / ".claude-plugin" / "plugin.json")
    portable = _json(PLUGIN / "plugin.json")
    assert claude["name"] == portable["name"] == "jdg-ksiegowy"
    assert claude["version"] == portable["version"] == version
    claude_market = _json(ROOT / ".claude-plugin" / "marketplace.json")
    codex_market = _json(ROOT / ".agents" / "plugins" / "marketplace.json")
    assert [p["source"] for p in claude_market["plugins"]] == ["./plugins/jdg-ksiegowy"]
    assert [p["source"]["path"] for p in codex_market["plugins"]] == ["./plugins/jdg-ksiegowy"]


@pytest.mark.parametrize(("doc", "schema"), [("plugin.json", "plugin"), ("mcp.json", "mcp")])
def test_portable_manifests_match_agent_plugins_schema(doc, schema):
    jsonschema.validate(_json(PLUGIN / doc), _json(SCHEMAS / f"{schema}.schema.json"))


def test_both_hosts_start_the_same_mcp_server():
    claude = _json(PLUGIN / ".mcp.json")["mcpServers"]["jdg"]
    portable = _json(PLUGIN / "mcp.json")["mcpServers"]["jdg"]
    assert (claude["command"], claude["args"]) == (portable["command"], portable["args"])
    assert claude["args"] == ["mcp", "serve"]


# --- hook zgody ---------------------------------------------------------------------------

GATE = runpy.run_path(str(PLUGIN / "hooks" / "confirm_gate.py"))["decision"]


def test_hook_matcher_covers_exactly_confirmable_tools():
    hooks = _json(PLUGIN / "hooks" / "hooks.json")["hooks"]["PreToolUse"]
    matcher = re.compile(next(h["matcher"] for h in hooks if "mcp__" in h["matcher"]))
    prefix = "mcp__plugin_jdg-ksiegowy_jdg__"
    gated = {n for n in mcp_server.tool_defs() if matcher.search(prefix + n)}
    assert gated == {mcp_server.tool_name(n) for n, c in COMMANDS.items() if c["confirmable"]}


@pytest.mark.parametrize(
    ("tool", "tool_input", "asks"),
    [
        ("mcp__plugin_jdg-ksiegowy_jdg__ksef_send", {"number": "A1/11/2026"}, False),
        ("mcp__plugin_jdg-ksiegowy_jdg__ksef_send", {"number": "A1", "confirm": "ab12"}, True),
        ("mcp__plugin_jdg-ksiegowy_jdg__jpk_submit", {"path": "x.xml", "confirm": ""}, False),
        ("Bash", {"command": "jdg ksef send A1/11/2026 --confirm 1a2b3c4d5e6f"}, True),
        ("Bash", {"command": "uv run jdg jpk submit f.xml --confirm abc"}, True),
        ("Bash", {"command": "jdg ksef send A1/11/2026"}, False),
        ("Bash", {"command": "git commit --confirm-paths"}, False),
    ],
)
def test_confirm_gate_asks_only_for_execution_phase(tool, tool_input, asks):
    result = GATE({"tool_name": tool, "tool_input": tool_input})
    if not asks:
        assert result is None
        return
    out = result["hookSpecificOutput"]
    assert (out["hookEventName"], out["permissionDecision"]) == ("PreToolUse", "ask")


# --- dryf skilli ----------------------------------------------------------------------------


def _skill_commands() -> list[tuple[str, str, str]]:
    """(skill, komenda, linia) dla kazdego `jdg ...` w skillach (z kontynuacjami `\\`)."""
    found = []
    for skill in sorted(PLUGIN.glob("skills/*/SKILL.md")):
        text = skill.read_text(encoding="utf-8").replace("\\\n", " ")
        for line in text.splitlines():
            for match in re.finditer(r"\bjdg ((?:[a-z][a-z0-9-]*)(?: [a-z][a-z0-9-]*)?)", line):
                words = match.group(1).split()
                name = " ".join(words) if " ".join(words) in COMMANDS else words[0]
                found.append((skill.parent.name, name, line[match.start() :]))
    return found


def test_skills_reference_only_existing_commands_and_flags():
    occurrences = _skill_commands()
    assert len(occurrences) > 40  # skille faktycznie opisuja komendy
    for skill, name, line in occurrences:
        if name in NOT_TOOLS:
            continue
        assert name in COMMANDS, f"{skill}: nieznana komenda `jdg {name}`"
        flags = {f for p in COMMANDS[name]["params"] for f in p["flags"]}
        segment = re.split(r"`|\s#|\s→|\(MCP", line)[0]  # do konca kodu na tej linii
        for flag in re.findall(r"(?<![\w-])--[a-z][a-z0-9-]*", segment):
            assert flag in flags | GLOBAL_FLAGS, f"{skill}: `jdg {name}` nie ma opcji {flag}"


def test_every_tool_is_described_by_some_skill():
    described = {name for _, name, _ in _skill_commands()}
    missing = set(COMMANDS) - described
    assert not missing, f"komendy bez opisu w skillach: {sorted(missing)}"


# --- ewaluacje (claude plugin eval) -----------------------------------------------------------

EVALS = PLUGIN / "evals"


def test_eval_mocks_carry_current_tool_contract():
    """`_tools.json` = odpowiedz `tools/list` serwera; mocki opisuja tylko istniejace narzedzia."""
    import os

    import mcp_types as types

    tools = [d.tool for d in mcp_server.tool_defs().values()]
    current = types.ListToolsResult(tools=tools).model_dump(
        mode="json", by_alias=True, exclude_none=True
    )
    saved_path = EVALS / "mocks" / "jdg" / "_tools.json"
    if os.environ.get("UPDATE_GOLDEN"):
        saved_path.write_text(json.dumps(current, ensure_ascii=False, indent=2) + "\n", "utf-8")
    assert _json(saved_path) == current
    names = {t["name"] for t in current["tools"]}
    mocked = {p.stem for p in EVALS.glob("**/mocks/jdg/*.md")}
    assert mocked <= names and {p.stem for p in (EVALS / "mocks" / "jdg").glob("*.md")} == names


def test_eval_suite_covers_safety_and_every_irreversible_tool():
    cases = [p.parent for p in EVALS.glob("*/prompt.md")]
    safety = [c for c in cases if '"safety"' in (c / "prompt.md").read_text("utf-8")]
    assert len(cases) >= 30 and len(safety) >= 5
    graders = "\n".join(p.read_text("utf-8") for p in EVALS.glob("*/graders/*.md"))
    for name, command in COMMANDS.items():
        if command["confirmable"]:
            tool = "mcp__plugin_jdg-ksiegowy_jdg__" + mcp_server.tool_name(name)
            assert f'tool: "{tool}"' in graders, f"brak ewaluacji dla {name}"
