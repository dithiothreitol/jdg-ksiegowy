#!/usr/bin/env python3
"""Walidacja XSD pliku JPK (V7M / EWP) przed wysylka do bramki MF.

Uzycie:
    python3 validate_jpk.py --xml-path data/jpk/JPK_V7M_2026_03_K1.xml

Schemat rozpoznawany z KodFormularza@kodSystemowy ("JPK_V7M (3)" -> JPK_V7M_3).
Zwraca JSON {valid, schema, errors}; exit 1 gdy plik nie przechodzi walidacji.
"""

import argparse
import json
import sys
from pathlib import Path

from lxml import etree

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent / "src"))

from jdg_ksiegowy.config import DATA_DIR
from jdg_ksiegowy.tax.validation import JPKValidator

XSD_DIR = DATA_DIR / "xsd"


def schema_name(xml: bytes) -> str:
    """'JPK_V7M (3)' -> 'JPK_V7M_3' (klucz w DEFAULT_XSD_URLS)."""
    kod = etree.fromstring(xml).find(".//{*}KodFormularza")
    return kod.get("kodSystemowy").replace(" (", "_").rstrip(")")


def main() -> None:
    parser = argparse.ArgumentParser(description="Walidacja XSD pliku JPK")
    parser.add_argument("--xml-path", required=True, help="Sciezka do XML JPK")
    args = parser.parse_args()

    xml = Path(args.xml_path).read_bytes()
    schema = schema_name(xml)
    result = JPKValidator(XSD_DIR).validate(xml, schema=schema)
    print(
        json.dumps(
            {
                "xml_path": args.xml_path,
                "schema": schema,
                "valid": result.valid,
                "errors": result.errors[:10],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    sys.exit(0 if result.valid else 1)


if __name__ == "__main__":
    main()
