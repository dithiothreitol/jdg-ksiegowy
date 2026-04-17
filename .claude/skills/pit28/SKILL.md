---
name: pit28
description: Raport roczny PIT-28 (ryczałt) — agregacja przychodów miesięcznych z rejestru faktur, obliczenie ryczałtu do zapłaty. Użyj gdy user pyta "PIT-28", "zeznanie roczne", "podsumowanie roku", "roczny raport podatkowy", "ile zapłaciłem ryczałtu", "przychody za rok".
---

# Raport PIT-28

Agreguje przychody netto z faktur w SQLite i oblicza ryczałt za rok.

## Wywołanie

```bash
# Raport tekstowy za poprzedni rok (domyślnie)
python3 skills/pit28/scripts/pit28_report.py

# Konkretny rok
python3 skills/pit28/scripts/pit28_report.py --year 2025

# Format JSON (do dalszego przetwarzania)
python3 skills/pit28/scripts/pit28_report.py --year 2025 --format json
```

## Co pokazuje

- Przychód netto miesięcznie (z faktur wg daty wystawienia)
- Ryczałt należny miesięcznie (stawka z `.env` × przychód)
- Suma roczna + zaokrąglona kwota do PIT-28

## Ważne uwagi

- **Podstawa to faktury wystawione** (data wystawienia), nie wpłynięte płatności
- Stawka ryczałtu pochodzi z `SELLER_RYCZALT_RATE` w `.env`
- Raport jest **pomocniczy** — przed złożeniem PIT-28 zweryfikuj z zaliczkami miesięcznymi i ewentualnymi korektami
- Termin złożenia PIT-28: **30 kwietnia** za rok poprzedni (od 2022)

## Gdzie wpisać w PIT-28

| Raport | Poz. w PIT-28 |
|--------|---------------|
| `annual_sales_net` | Poz. 20/22/24 (zależy od źródła) |
| `annual_ryczalt` | Poz. 107-119 (suma zryczałtowanego podatku) |
