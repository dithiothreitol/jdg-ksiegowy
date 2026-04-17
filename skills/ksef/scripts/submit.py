#!/usr/bin/env python3
"""Wysyłka faktury do KSeF — AgentSkill dla OpenClaw."""

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent / "src"))

from jdg_ksiegowy.ksef.client import KSeFClient


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
    result = await client.send_invoice(xml_content)

    return {
        "success": result.success,
        "reference_number": result.reference_number,
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
