---
name: tax-calculator
description: Liczy zobowiązania podatkowe JDG na ryczałcie — VAT (23%), ryczałt (12% domyślnie), składkę zdrowotną ZUS (z progiem na podstawie rocznego przychodu) i terminy płatności (20-ty: ryczałt+ZUS, 25-ty: VAT+JPK). Użyj gdy user pyta "ile podatku", "ile ZUS", "ile VAT", "kiedy termin", "rozlicz fakturę X netto", "co mam zapłacić w tym miesiącu".
---

# Kalkulator podatkowy JDG (ryczałt)

Liczy podatki z pojedynczej faktury lub z miesięcznego przychodu.

## Wymagane dane

- **netto** — kwota netto w PLN

Opcjonalnie:
- `vat-rate` — domyślnie `23`
- `ryczalt-rate` — domyślnie `12`
- `annual-revenue` — szacunkowy roczny przychód (do wyznaczenia progu ZUS); jeśli nie podasz, skrypt zakłada `netto * 12`
- `month`, `year` — domyślnie bieżący

## Wywołanie

```bash
python3 skills/tax-calculator/scripts/calculate.py --netto 10500
```

Z pełnym kontekstem:
```bash
python3 skills/tax-calculator/scripts/calculate.py \
  --netto 10500 --vat-rate 23 --ryczalt-rate 12 --annual-revenue 126000
```

Zwraca JSON na stdout:
```json
{
  "netto": "10500",
  "vat_rate": "23%",
  "vat_amount": "2415.00",
  "brutto": "12915.00",
  "ryczalt_rate": "12%",
  "ryczalt_amount": "1260.00",
  "zus_health_monthly": "...",
  "zus_tier": "...",
  "zus_deductible_monthly": "...",
  "estimated_annual_revenue": "126000",
  "deadlines": {
    "ryczalt_zus": "2026-05-20",
    "vat_jpk": "2026-05-25"
  },
  "total_monthly_tax": "..."
}
```

## Po obliczeniu

Pokaż userowi w czytelnej tabeli (nie surowy JSON): VAT, ryczałt, ZUS zdrowotne, łącznie do zapłaty + dwa terminy.
Zaznacz że kwota ZUS to składka zdrowotna (społeczne nie liczone — zakładamy stałą stawkę).

## Uwagi

- Wszystkie kwoty jako Decimal — nigdy float.
- Próg ZUS jest wyliczany w `src/jdg_ksiegowy/tax/zus.py` (single source of truth) — nie hardkoduj progów.
- Stawka ryczałtu 12% jest domyślna dla JDG IT/konsulting; jeśli user ma inną branżę — dopytaj.
