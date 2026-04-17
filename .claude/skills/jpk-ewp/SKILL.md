---
name: jpk-ewp
description: Generuje JPK_EWP — Ewidencję Przychodów ryczałtowca za cały rok (XML). Składasz raz w roku do 30.04 następnego roku, razem z PIT-28. Obowiązkowy od 1.01.2026 dla ryczałtowców rozliczających VAT miesięcznie. Użyj gdy user mówi "wygeneruj JPK_EWP", "ewidencja ryczałtu za 2026", "roczna ewidencja przychodów", "JPK do PIT-28".
---

# Generator JPK_EWP (ewidencja ryczałtu, roczna)

Generuje plik `JPK_EWP_{rok}.xml` na podstawie wszystkich faktur sprzedażowych z rejestru za dany rok.

## Wymagane dane

- **year** — rok podatkowy (4 cyfry)

Opcjonalnie:
- `ryczalt-rate` — stawka ryczałtu jako procent (`12`, `8.5`, `15`...). Domyślnie z `.env` (`SELLER_RYCZALT_RATE`).

Stawki dozwolone (słownik MF): `17, 15, 14, 12.5, 12, 10, 8.5, 5.5, 3`.

## Wywołanie

```bash
python3 skills/jpk-ewp/scripts/generate_ewp.py --year 2026
```

Lub z inną stawką:
```bash
python3 skills/jpk-ewp/scripts/generate_ewp.py --year 2026 --ryczalt-rate 8.5
```

Zwraca JSON:
```json
{
  "year": 2026,
  "invoice_count": 48,
  "total_revenue": "245000.00",
  "file_path": "data/jpk/JPK_EWP_2026.xml"
}
```

## Po wygenerowaniu

Pokaż userowi: rok, liczbę faktur, sumę przychodów, ścieżkę pliku (jako klikalny link).
Przypomnij: termin = **30.04 następnego roku** (razem z PIT-28).
Po wygenerowaniu możesz wysłać do MF skillem `jpk-submit`.

## ⚠️ Ważne

- JPK_EWP ma **inny schemat** niż JPK_V7M (XML namespace inny, struktura wierszy inna).
- Pierwsza obligatoryjna wysyłka dla ryczałtowców z VAT: **2026** (do złożenia 30.04.2027).
- Dla pozostałych ryczałtowców (bez VAT lub z kwartalnym JPK) — od **2027**.
- **Implementacja MVP**: namespace XSD JPK_EWP(4) jest ustawiony jako placeholder — przed wysyłką na PROD zweryfikuj zgodność ze schematem opublikowanym przez MF (do potwierdzenia po publikacji na gov.pl).
