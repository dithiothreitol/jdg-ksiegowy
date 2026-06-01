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

    # Guard przed dublem: jeśli faktura jest już w rejestrze z numerem KSeF,
    # nie wysyłaj jej drugi raz (KSeF nadałby kolejny numer tej samej fakturze).
    init_db()
    existing = get_invoice_by_number(number) if number else None
    if existing is not None and existing.ksef_reference:
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
