#!/usr/bin/env python3
"""Walidacja XSD pliku JPK (V7M / EWP) przed wysylka do bramki MF.

Uzycie:
    python3 validate_jpk.py --xml-path data/jpk/JPK_V7M_2026_03_K1.xml

Schemat rozpoznawany z KodFormularza@kodSystemowy ("JPK_V7M (3)" -> JPK_V7M_3);
schematy MF sa wbudowane w pakiet — walidacja dziala offline.
Zwraca JSON {valid, schema, errors}; exit 1 gdy plik nie przechodzi walidacji.
"""

import argparse
import json
import sys
from pathlib import Path

from jdg_ksiegowy.tax.validation import schema_name, validate_jpk


def main() -> None:
    parser = argparse.ArgumentParser(description="Walidacja XSD pliku JPK")
    parser.add_argument("--xml-path", required=True, help="Sciezka do XML JPK")
    args = parser.parse_args()

    xml = Path(args.xml_path).read_bytes()
    schema = schema_name(xml)
    result = validate_jpk(xml, schema)
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
