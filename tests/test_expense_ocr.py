"""Testy OCR faktur zakupu — parsowanie odpowiedzi + fallback chain.

Nie uderzamy realnie w Ollama/Claude — mockujemy httpx/anthropic SDK.
"""

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from jdg_ksiegowy.expenses.models import ExpenseCategory
from jdg_ksiegowy.expenses.ocr import (
    ClaudeOCR,
    ExtractedExpense,
    FallbackOCR,
    OCRError,
    OllamaOCR,
    _parse_ocr_response,
)

VALID_JSON = json.dumps(
    {
        "seller_name": "Hetzner Online GmbH",
        "seller_nip": "DE812871812",
        "seller_country": "DE",
        "document_number": "R0012345",
        "issue_date": "2026-04-15",
        "total_net": "100.00",
        "total_vat": "23.00",
        "vat_rate": "23",
        "description": "Hosting VPS kwiecien 2026",
        "category": "uslugi_obce",
    }
)


# --- Parser ---


def test_parser_extracts_all_fields():
    result = _parse_ocr_response(VALID_JSON, source="ollama")
    assert result.seller_name == "Hetzner Online GmbH"
    assert result.seller_nip == "DE812871812"
    assert result.issue_date == date(2026, 4, 15)
    assert result.total_net == Decimal("100.00")
    assert result.total_vat == Decimal("23.00")
    assert result.category == ExpenseCategory.USLUGI_OBCE
    assert result.source == "ollama"


def test_parser_strips_markdown_fence():
    wrapped = f"```json\n{VALID_JSON}\n```"
    result = _parse_ocr_response(wrapped, source="claude")
    assert result.seller_name == "Hetzner Online GmbH"


def test_parser_rejects_malformed_json():
    with pytest.raises(OCRError, match="nieparsowalny JSON"):
        _parse_ocr_response("to nie jest json", source="ollama")


def test_parser_rejects_missing_required_fields():
    partial = json.dumps({"seller_name": "X"})
    with pytest.raises(OCRError, match="nie pasuje do ExtractedExpense"):
        _parse_ocr_response(partial, source="ollama")


# --- Ollama backend ---


def test_ollama_posts_to_correct_endpoint(tmp_path, respx_mock):
    fake_img = tmp_path / "f.jpg"
    fake_img.write_bytes(b"fake-jpeg")

    route = respx_mock.post("http://localhost:11434/api/generate").mock(
        return_value=httpx.Response(200, json={"response": VALID_JSON})
    )
    ocr = OllamaOCR()
    result = ocr.extract(fake_img)

    assert route.called
    sent = json.loads(route.calls.last.request.content)
    assert sent["model"] == "pixtral:12b"
    assert sent["format"] == "json"
    assert sent["stream"] is False
    assert result.source == "ollama"


# --- Fallback chain ---


class _StubOCR:
    def __init__(self, result_or_exc):
        self._r = result_or_exc
        self.calls = 0

    def extract(self, file_path: Path) -> ExtractedExpense:
        self.calls += 1
        if isinstance(self._r, Exception):
            raise self._r
        return self._r


def _sample_result(source: str) -> ExtractedExpense:
    data = json.loads(VALID_JSON)
    data["source"] = source
    return ExtractedExpense(**data)


def test_fallback_returns_primary_when_ok(tmp_path):
    primary = _StubOCR(_sample_result("ollama"))
    secondary = _StubOCR(_sample_result("claude"))
    chain = FallbackOCR(primary=primary, secondary=secondary)

    result = chain.extract(tmp_path / "f.jpg")

    assert result.source == "ollama"
    assert primary.calls == 1
    assert secondary.calls == 0


def test_fallback_switches_to_secondary_on_error(tmp_path):
    primary = _StubOCR(httpx.ConnectError("connection refused"))
    secondary = _StubOCR(_sample_result("claude"))
    chain = FallbackOCR(primary=primary, secondary=secondary)

    result = chain.extract(tmp_path / "f.jpg")

    assert result.source == "claude"
    assert primary.calls == 1
    assert secondary.calls == 1


def test_fallback_raises_when_both_fail(tmp_path):
    primary = _StubOCR(RuntimeError("ollama down"))
    secondary = _StubOCR(RuntimeError("claude down"))
    chain = FallbackOCR(primary=primary, secondary=secondary)

    with pytest.raises(RuntimeError, match="claude down"):
        chain.extract(tmp_path / "f.jpg")


def test_fallback_raises_when_no_secondary(tmp_path):
    primary = _StubOCR(RuntimeError("ollama down"))
    chain = FallbackOCR(primary=primary, secondary=None)

    with pytest.raises(OCRError, match="brak fallbacku"):
        chain.extract(tmp_path / "f.jpg")


# --- Claude backend (lazy import, jezeli brak klucza -> error) ---


def test_claude_without_key_raises(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    from jdg_ksiegowy.config import settings

    settings.anthropic_api_key = ""
    with pytest.raises(OCRError, match="ANTHROPIC_API_KEY"):
        ClaudeOCR(api_key="")
