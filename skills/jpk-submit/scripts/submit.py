#!/usr/bin/env python3
"""Wysylka pliku JPK_V7M / JPK_EWP do bramki MF.

Tryby:
  --dry-run       wyswietl co byloby wyslane (bez dotykania bramki)
  default         pelna wysylka: encrypt -> init -> upload -> finish -> poll status -> UPO
"""

import argparse
import asyncio
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent / "src"))

from jdg_ksiegowy.config import DATA_DIR, settings
from jdg_ksiegowy.mf_gateway.auth import AuthorizationData
from jdg_ksiegowy.mf_gateway.client import MFGatewayClient


def build_auth() -> AuthorizationData:
    s = settings.seller
    mf = settings.mf
    if not mf.pesel:
        raise ValueError("MF_PESEL wymagany w .env")
    if not s.first_name or not s.last_name or not s.birth_date:
        raise ValueError("SELLER_FIRST_NAME/LAST_NAME/BIRTH_DATE wymagane")
    return AuthorizationData(
        nip=s.nip,
        pesel=mf.pesel,
        first_name=s.first_name,
        last_name=s.last_name,
        birth_date=date.fromisoformat(s.birth_date),
        prior_year_income=mf.prior_income,
    )


async def run_submit(xml_path: Path, dry_run: bool) -> dict:
    if not xml_path.exists():
        return {"success": False, "error": f"Plik nie istnieje: {xml_path}"}

    try:
        auth = build_auth()
    except Exception as e:
        return {"success": False, "error": str(e)}

    if dry_run:
        return {
            "success": True,
            "dry_run": True,
            "xml_path": str(xml_path),
            "xml_size": xml_path.stat().st_size,
            "mf_env": settings.mf.env,
            "mf_base_url": settings.mf.base_url,
            "auth_fingerprint": auth.fingerprint(),
            "message": "DRY-RUN: nic nie wyslano. Uruchom bez --dry-run zeby wyslac.",
        }

    if not settings.mf.cert_path:
        return {
            "success": False,
            "error": "MF_CERT_PATH nie ustawiony — pobierz klucz publiczny MF i ustaw sciezke",
        }

    client = MFGatewayClient()
    xml = xml_path.read_text(encoding="utf-8")
    inner = xml_path.name
    result = await client.submit(xml, auth, xml_filename=inner)

    out = {
        "success": result.success,
        "reference_number": result.reference_number,
        "status_code": result.status_code,
        "error": result.error,
        "mf_env": settings.mf.env,
    }
    if result.success and result.upo_base64:
        upo_path = DATA_DIR / "upo" / f"UPO_{result.reference_number}.bin"
        client.save_upo(result.upo_base64, upo_path)
        out["upo_path"] = str(upo_path)
    return out


def main():
    parser = argparse.ArgumentParser(description="Wysylka JPK do bramki MF")
    parser.add_argument("--xml-path", required=True, help="Sciezka do XML JPK")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Pokaz co byloby wyslane bez dotykania bramki MF",
    )
    args = parser.parse_args()

    result = asyncio.run(run_submit(Path(args.xml_path), args.dry_run))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if result.get("success") else 1)


if __name__ == "__main__":
    main()
