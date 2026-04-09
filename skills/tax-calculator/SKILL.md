---
name: tax-calculator
description: Kalkulacje podatkowe JDG na ryczalcie — VAT, ryczalt, ZUS zdrowotna, terminy platnosci
metadata:
  openclaw:
    requires:
      bins:
        - python3
---

# Kalkulator podatkowy JDG

Oblicza zobowiazania podatkowe z faktury lub za miesiac.

## Uzycie

Uruchom skrypt:

```bash
python3 scripts/calculate.py --netto <kwota> [--vat-rate 23] [--ryczalt-rate 12] [--annual-revenue <kwota>]
```

Zwraca JSON z:
- netto, VAT, brutto
- ryczalt (12% od netto)
- skladka ZUS zdrowotna (prog na podstawie rocznego przychodu)
- terminy platnosci (20-ty: ryczalt+ZUS, 25-ty: VAT)

## Przyklady

- "Oblicz podatki od faktury 10500 netto"
- "Ile wyniesie ZUS przy przychodzie 120000 rocznie?"
- "Jakie mam terminy podatkowe za kwiecien?"
