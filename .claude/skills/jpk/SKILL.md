---
name: jpk
description: Generuje miesięczną deklarację VAT JPK_V7M (Jednolity Plik Kontrolny) jako XML z faktur z rejestru SQLite. Użyj gdy user prosi "wygeneruj JPK", "JPK za marzec", "deklaracja VAT za miesiąc", "przygotuj JPK_V7M", "rozliczenie VAT do urzędu".
---

# Generator JPK_V7M

Generuje miesięczną deklarację VAT (`JPK_V7M(2)`) na podstawie faktur zapisanych w `data/registry.sqlite`.
Plik wynikowy: `data/jpk/JPK_V7M_YYYY_MM.xml` — gotowy do wysyłki przez bramkę MF lub e-Mikrofirma.

## Wymagane dane

- **month** — miesiąc (1-12)
- **year** — rok (np. 2026)

Jeśli user mówi "JPK za poprzedni miesiąc" — policz miesiąc/rok względem daty bieżącej (`2026-04-17`), nie wymyślaj.

## Wywołanie

```bash
python3 skills/jpk/scripts/generate_jpk.py --month 3 --year 2026
```

Zwraca JSON:
```json
{
  "period": "03/2026",
  "invoice_count": 4,
  "total_net": "42000.00",
  "total_vat": "9660.00",
  "file_path": "data/jpk/JPK_V7M_2026_03.xml"
}
```

## Po wygenerowaniu

Pokaż userowi: okres, liczbę faktur, sumę netto + VAT, ścieżkę pliku (jako klikalny markdown link).
Przypomnij: termin wysyłki JPK_V7M to **25-ty następnego miesiąca**.
Plik trzeba wysłać przez bramkę MF — ten skill nie wysyła automatycznie (na razie).

## Wymagane dane sprzedawcy (z .env)

`SELLER_NIP`, `SELLER_FIRST_NAME`, `SELLER_LAST_NAME`, `SELLER_BIRTH_DATE`, `SELLER_TAX_OFFICE_CODE`.
Jeśli skrypt rzuci błąd o braku któregoś — przerwij i powiedz userowi żeby uzupełnił `.env`.

## Uwagi

- Skrypt liczy sumy z rejestru, nie z surowych XML — upewnij się że wszystkie faktury miesiąca zostały wygenerowane przez skill `invoice` (czyli są w SQLite).
- Jeśli `invoice_count == 0` — ostrzeż usera, prawdopodobnie zapomniał wystawić faktury albo pomylił miesiąc.
