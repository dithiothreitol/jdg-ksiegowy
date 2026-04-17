"""OCR faktur zakupu — lokalny Pixtral (Ollama) z fallbackiem na Claude Haiku 4.5.

Strategy pattern: `ExpenseOCR` protocol + 3 implementacje
  - `OllamaOCR` — lokalny vision LLM (domyslnie Pixtral 12B) przez Ollama API
  - `ClaudeOCR` — Anthropic API z tool-use dla structured output
  - `FallbackOCR` — proba Ollama, przy bledzie/timeout -> Claude

User akceptuje wypelnione dane przed zapisem do bazy.
"""

from __future__ import annotations

import base64
import json
import logging
import mimetypes
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Protocol

import httpx
from pydantic import BaseModel, Field

from jdg_ksiegowy.config import settings
from jdg_ksiegowy.expenses.models import ExpenseCategory

logger = logging.getLogger(__name__)

OCR_SYSTEM_PROMPT = """Jestes asystentem ksiegowym analizujacym polskie faktury zakupu.
Wyciagnij z obrazu/PDF faktury nastepujace pola i zwroc JSON:
- seller_name: nazwa sprzedawcy
- seller_nip: NIP (10 cyfr, bez mysnikow i spacji; dla zagranicznego z prefiksem kraju np. 'DE812871812')
- seller_country: dwuliterowy kod kraju ISO (PL dla polskiego NIP)
- document_number: numer faktury
- issue_date: data wystawienia (YYYY-MM-DD)
- total_net: kwota netto (Decimal, kropka jako separator dziesietny)
- total_vat: kwota VAT (Decimal). Jesli sprzedawca zwolniony z VAT -> 0
- vat_rate: stawka VAT procent (23/8/5/0). Domyslnie 23 jesli nieczytelne
- description: krotki opis (max 100 znakow) czego dotyczy faktura
- category: jedna z [uslugi_obce, materialy, media, paliwo, samochod, biuro, sprzet, szkolenia, inne]

Zasady:
- Kwoty jako Decimal z dwoma miejscami po przecinku ('100.00', nie '100,00')
- Daty ZAWSZE w formacie YYYY-MM-DD
- Jesli pole nie jest czytelne, zwroc null — nie zgaduj
- Zwroc WYLACZNIE poprawny JSON, bez zadnych komentarzy ani markdown
"""


class ExtractedExpense(BaseModel):
    """Wynik OCR faktury zakupu — do akceptacji przez usera przed zapisem."""

    seller_name: str
    seller_nip: str
    seller_country: str = "PL"
    document_number: str
    issue_date: date
    total_net: Decimal
    total_vat: Decimal
    vat_rate: Decimal = Decimal("23")
    description: str = ""
    category: ExpenseCategory = ExpenseCategory.INNE
    source: str = Field(default="", description="'ollama' | 'claude' | 'manual'")


class OCRError(Exception):
    """OCR nie byl w stanie wyciagnac danych z dokumentu."""


class ExpenseOCR(Protocol):
    """Interfejs OCR dla faktur zakupu."""

    def extract(self, file_path: Path) -> ExtractedExpense: ...


class OllamaOCR:
    """Lokalny vision LLM przez Ollama API (domyslnie Pixtral 12B)."""

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float | None = None,
    ):
        cfg = settings.ocr
        self.base_url = (base_url or cfg.ollama_url).rstrip("/")
        self.model = model or cfg.ollama_model
        self.timeout = timeout or cfg.ollama_timeout

    def extract(self, file_path: Path) -> ExtractedExpense:
        image_b64 = _file_to_base64(file_path)
        payload = {
            "model": self.model,
            "prompt": OCR_SYSTEM_PROMPT + "\n\nObraz faktury w zalaczniku.",
            "images": [image_b64],
            "format": "json",
            "stream": False,
        }
        with httpx.Client(timeout=self.timeout) as http:
            resp = http.post(f"{self.base_url}/api/generate", json=payload)
            resp.raise_for_status()
            data = resp.json()
        raw_json = data.get("response", "")
        return _parse_ocr_response(raw_json, source="ollama")


class ClaudeOCR:
    """Claude Haiku 4.5 vision przez Anthropic SDK z tool-use dla structured output."""

    def __init__(self, api_key: str | None = None, model: str | None = None):
        # Import lokalnie — anthropic SDK moze nie byc w kazdym srodowisku
        from anthropic import Anthropic

        key = api_key or settings.anthropic_api_key
        if not key:
            raise OCRError(
                "ANTHROPIC_API_KEY nie ustawiony w .env — ClaudeOCR niedostepny"
            )
        self._client = Anthropic(api_key=key)
        self.model = model or settings.ocr.claude_model
        self.max_tokens = settings.ocr.claude_max_tokens

    def extract(self, file_path: Path) -> ExtractedExpense:
        media_type = mimetypes.guess_type(str(file_path))[0] or "image/jpeg"
        if media_type == "application/pdf":
            content_block = {
                "type": "document",
                "source": {
                    "type": "base64",
                    "media_type": "application/pdf",
                    "data": _file_to_base64(file_path),
                },
            }
        else:
            content_block = {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": media_type,
                    "data": _file_to_base64(file_path),
                },
            }

        message = self._client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=OCR_SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": [
                        content_block,
                        {"type": "text", "text": "Wyciagnij dane i zwroc JSON."},
                    ],
                }
            ],
        )
        text = "".join(
            block.text for block in message.content if getattr(block, "type", None) == "text"
        )
        return _parse_ocr_response(text, source="claude")


@dataclass
class FallbackOCR:
    """Probuje primary, przy bledzie -> secondary. Loguje co sie stalo."""

    primary: ExpenseOCR
    secondary: ExpenseOCR | None

    def extract(self, file_path: Path) -> ExtractedExpense:
        try:
            return self.primary.extract(file_path)
        except Exception as e:
            logger.warning("Primary OCR (%s) failed: %s", type(self.primary).__name__, e)
            if self.secondary is None:
                raise OCRError(f"OCR failed, brak fallbacku: {e}") from e
            logger.info("Fallback -> %s", type(self.secondary).__name__)
            return self.secondary.extract(file_path)


def build_default_ocr() -> ExpenseOCR:
    """Skonstruuj OCR wg ustawien. Provider 'auto' = Ollama z fallbackiem na Claude."""
    provider = settings.ocr.provider
    if provider == "ollama":
        return OllamaOCR()
    if provider == "claude":
        return ClaudeOCR()
    if provider == "auto":
        ollama = OllamaOCR()
        try:
            claude: ExpenseOCR | None = ClaudeOCR()
        except OCRError:
            logger.info("Claude fallback niedostepny (brak klucza API) — tylko Ollama")
            claude = None
        return FallbackOCR(primary=ollama, secondary=claude)
    raise ValueError(f"Nieznany OCR_PROVIDER: {provider!r}")


def _file_to_base64(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode("ascii")


def _parse_ocr_response(raw: str, source: str) -> ExtractedExpense:
    """Parsuj JSON output, zwaliduj przez pydantic, dodaj source."""
    raw = raw.strip()
    if raw.startswith("```"):
        # Niektore modele wciaz opakowuja w markdown fence
        raw = raw.strip("`").lstrip("json").strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise OCRError(f"OCR zwrocil nieparsowalny JSON ({source}): {raw[:200]}") from e
    data["source"] = source
    try:
        return ExtractedExpense(**data)
    except Exception as e:
        raise OCRError(f"OCR JSON nie pasuje do ExtractedExpense ({source}): {e}") from e
