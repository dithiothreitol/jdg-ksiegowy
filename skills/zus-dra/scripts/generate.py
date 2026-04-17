#!/usr/bin/env python3
"""Generator DRA ZUS (KEDU v5.05) dla JDG — import ręczny via PUE."""

import argparse
import json
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent / "src"))

from jdg_ksiegowy.zus.dra import DRARequest, dra_deadline, generate_dra_xml


def main():
    parser = argparse.ArgumentParser(description="Generator DRA ZUS (KEDU v5.05)")
    parser.add_argument("--month", type=int, required=True, help="Miesiac 1-12")
    parser.add_argument("--year", type=int, required=True, help="Rok")
    parser.add_argument(
        "--annual-prior-income",
        type=Decimal,
        required=True,
        help="Przychod roczny za poprzedni rok (dla progu zdrowotnego)",
    )
    parser.add_argument(
        "--include-social", action="store_true",
        help="Dolicz skladki spoleczne (domyslnie tylko zdrowotne)",
    )
    parser.add_argument(
        "--output", type=Path, default=None,
        help="Sciezka do pliku XML KEDU (domyslnie: data/zus/DRA_MM_RRRR.xml)",
    )
    args = parser.parse_args()

    req = DRARequest(
        month=args.month,
        year=args.year,
        annual_prior_income=args.annual_prior_income,
        include_social=args.include_social,
    )
    result = generate_dra_xml(req)

    if args.output is None:
        output = Path("data/zus") / f"DRA_{args.month:02d}_{args.year}.xml"
    else:
        output = args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(result.xml, encoding="utf-8")

    deadline = dra_deadline(args.month, args.year)
    print(json.dumps({
        "xml_path": str(output),
        "health_contribution": f"{result.health_contribution:.2f}",
        "social_contribution": f"{result.social_contribution:.2f}",
        "total": f"{result.total:.2f}",
        "deadline": deadline.isoformat(),
        "how_to_send": "Zaloguj do PUE ZUS, zakladka 'Dokumenty i wiadomosci' > 'Import KEDU' i wskaz wygenerowany plik XML.",
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
