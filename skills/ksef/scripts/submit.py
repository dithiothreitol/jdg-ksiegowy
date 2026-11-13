#!/usr/bin/env python3
"""Wysylka faktury do KSeF — AgentSkill dla OpenClaw."""

import argparse
import json
from pathlib import Path

from lxml import etree

from jdg_ksiegowy.config import DATA_DIR
from jdg_ksiegowy.ksef.client import KSeFClient
from jdg_ksiegowy.registry.repository import InvoiceRepository


def _parse_invoice(xml_content: str) -> tuple[str | None, str | None]:
    """(numer faktury P_2, RodzajFaktury) z FA(3) — niezaleznie od namespace."""
    root = etree.fromstring(xml_content.encode("utf-8"))
    return root.findtext(".//{*}P_2"), root.findtext(".//{*}RodzajFaktury")


def submit(xml_path: str) -> dict:
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
    try:
        number, kind = _parse_invoice(xml_content)
    except etree.XMLSyntaxError as e:
        return {"success": False, "error": f"Niepoprawny XML FA(3): {e}"}
    if not number:
        return {
            "success": False,
            "error": "Nie udalo sie odczytac numeru faktury (P_2) z XML FA(3).",
        }

    repo = InvoiceRepository()
    existing = repo.get(number)

    # Faktura musi byc w rejestrze PRZED wysylka — inaczej wypada z JPK_V7M i statusu.
    # Korekty (KOR*) nie maja jeszcze wlasnego wiersza w rejestrze, a ich wysylka
    # jest obowiazkowa — dlatego guard ich nie obejmuje.
    is_correction = (kind or "").upper().startswith("KOR")
    if existing is None and not is_correction:
        return {
            "success": False,
            "number": number,
            "error": (
                f"Faktura {number} nie istnieje w rejestrze — wystaw ja najpierw skillem "
                "`invoice`. Wysylka spoza rejestru pominelaby JPK_V7M i /jdg-status."
            ),
        }

    # Guard przed dublem: KSeF nadalby tej samej fakturze kolejny numer.
    if existing is not None and (existing.ksef_number or existing.ksef_reference):
        return {
            "success": False,
            "number": number,
            "ksef_number": existing.ksef_number,
            "reference_number": existing.ksef_reference,
            "error": f"Faktura {number} zostala juz wyslana do KSeF — pomijam, by uniknac dubla.",
        }

    result = client.send_invoice(xml_content)

    upo_path = None
    if result.success and result.upo and result.ksef_number:
        upo_path = DATA_DIR / "upo" / "ksef" / f"UPO_{result.ksef_number}.xml"
        upo_path.parent.mkdir(parents=True, exist_ok=True)
        upo_path.write_bytes(result.upo)

    registered = False
    if result.success and existing is not None:
        repo.mark_sent_ksef(
            number,
            reference=result.reference_number or "",
            ksef_number=result.ksef_number,
            acquired_at=result.acquired_at,
            upo_path=str(upo_path) if upo_path else None,
        )
        registered = True

    return {
        "success": result.success,
        "number": number,
        "ksef_number": result.ksef_number,
        "reference_number": result.reference_number,
        "upo_path": str(upo_path) if upo_path else None,
        "registered": registered,
        "error": result.error,
        "env": result.env,
    }


def main():
    parser = argparse.ArgumentParser(description="Wysylka do KSeF")
    parser.add_argument("--xml-path", required=True, help="Sciezka do pliku XML FA(3)")
    args = parser.parse_args()
    print(json.dumps(submit(args.xml_path), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
