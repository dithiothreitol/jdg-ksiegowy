#!/usr/bin/env python3
"""Wysyłka faktury do KSeF — AgentSkill dla OpenClaw."""

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent / "src"))

from lxml import etree

from jdg_ksiegowy.ksef.client import KSeFClient
from jdg_ksiegowy.registry.db import get_invoice_by_number, init_db, mark_sent_ksef


def _invoice_number(xml_content: str) -> str | None:
    """Wyciągnij numer faktury (P_2) z FA(3) — niezależnie od wersji namespace."""
    root = etree.fromstring(xml_content.encode("utf-8"))
    return root.findtext(".//{*}P_2")


async def submit(xml_path: str) -> dict:
    path = Path(xml_path)
    if not path.exists():
        return {"success": False, "error": f"Plik XML nie istnieje: {xml_path}"}

    client = KSeFClient()
    if not client.is_configured():
        return {
            "success": False,
            "error": "KSeF nie skonfigurowany — ustaw KSEF_NIP i KSEF_TOKEN w .env",
        }

    xml_content = path.read_text(encoding="utf-8")
    number = _invoice_number(xml_content)

    init_db()
    if not number:
        return {
            "success": False,
            "error": "Nie udało się odczytać numeru faktury (P_2) z XML FA(3).",
        }
    existing = get_invoice_by_number(number)

    # Faktura musi być w rejestrze PRZED wysyłką. Wysyłka do KSeF z pominięciem
    # rejestru sprawia, że nie trafia do JPK_V7M ani /jdg-status — wypada z
    # rozliczenia VAT (mark_sent_ksef tylko AKTUALIZUJE istniejący wiersz).
    if existing is None:
        return {
            "success": False,
            "number": number,
            "error": (
                f"Faktura {number} nie istnieje w rejestrze SQLite — wystaw ją "
                "najpierw skillem `invoice`. Wysyłka spoza rejestru pominęłaby "
                "JPK_V7M i /jdg-status (faktura wypadłaby z rozliczenia VAT)."
            ),
        }

    # Guard przed dublem: faktura z numerem KSeF nie jest wysyłana ponownie
    # (KSeF nadałby kolejny numer tej samej fakturze).
    if existing.ksef_reference:
        return {
            "success": False,
            "number": number,
            "reference_number": existing.ksef_reference,
            "error": (
                f"Faktura {number} została już wysłana do KSeF "
                f"({existing.ksef_reference}) — pomijam, by uniknąć dubla."
            ),
        }

    result = await client.send_invoice(xml_content)

    registered = False
    if result.success and result.reference_number and number:
        registered = mark_sent_ksef(number, result.reference_number)

    return {
        "success": result.success,
        "number": number,
        "reference_number": result.reference_number,
        "registered": registered,
        "error": result.error,
        "env": result.details.get("env", "unknown"),
    }


def main():
    parser = argparse.ArgumentParser(description="Wysyłka do KSeF")
    parser.add_argument("--xml-path", required=True, help="Ścieżka do pliku XML FA(3)")
    args = parser.parse_args()

    result = asyncio.run(submit(args.xml_path))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
