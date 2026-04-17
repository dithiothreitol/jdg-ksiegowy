#!/usr/bin/env python3
"""Kalkulator podatkowy JDG — ryczalt, VAT, ZUS.

Wywolywany jako AgentSkill przez OpenClaw.
Importuje logike z src/jdg_ksiegowy/tax/ (single source of truth).
"""

import argparse
import json
import sys
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

# Dodaj src/ do PYTHONPATH
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent / "src"))

from jdg_ksiegowy.tax.zus import get_zus_tier
from jdg_ksiegowy.invoice.calculator import get_tax_deadlines


def main():
    parser = argparse.ArgumentParser(description="Kalkulator podatkowy JDG")
    parser.add_argument("--netto", type=str, required=True, help="Kwota netto")
    parser.add_argument("--vat-rate", type=str, default="23", help="Stawka VAT (procent)")
    parser.add_argument("--ryczalt-rate", type=str, default="12", help="Stawka ryczaltu (procent)")
    parser.add_argument("--annual-revenue", type=str, default="0", help="Szacunkowy roczny przychod")
    parser.add_argument("--month", type=int, default=date.today().month)
    parser.add_argument("--year", type=int, default=date.today().year)
    args = parser.parse_args()

    netto = Decimal(args.netto)
    vat_rate = Decimal(args.vat_rate)
    ryczalt_rate = Decimal(args.ryczalt_rate)

    vat = (netto * vat_rate / 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    brutto = netto + vat
    ryczalt = (netto * ryczalt_rate / 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    annual = Decimal(args.annual_revenue) if Decimal(args.annual_revenue) > 0 else netto * 12
    tier = get_zus_tier(annual)
    zus_deductible = (tier.monthly_contribution * Decimal("0.5")).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )

    deadlines = get_tax_deadlines(args.month, args.year)

    result = {
        "netto": str(netto),
        "vat_rate": f"{vat_rate}%",
        "vat_amount": str(vat),
        "brutto": str(brutto),
        "ryczalt_rate": f"{ryczalt_rate}%",
        "ryczalt_amount": str(ryczalt),
        "zus_health_monthly": str(tier.monthly_contribution),
        "zus_tier": tier.label,
        "zus_deductible_monthly": str(zus_deductible),
        "estimated_annual_revenue": str(annual),
        "deadlines": {
            "ryczalt_zus": deadlines["ryczalt"].isoformat(),
            "vat_jpk": deadlines["vat_jpk"].isoformat(),
        },
        "total_monthly_tax": str(ryczalt + tier.monthly_contribution + vat),
    }

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
