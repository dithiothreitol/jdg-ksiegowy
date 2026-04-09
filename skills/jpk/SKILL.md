---
name: jpk-generator
description: Generowanie pliku JPK_V7M (Jednolity Plik Kontrolny — deklaracja VAT) za miesiac
metadata:
  openclaw:
    requires:
      bins:
        - python3
      env:
        - SELLER_NIP
        - SELLER_FIRST_NAME
        - SELLER_LAST_NAME
        - SELLER_BIRTH_DATE
        - SELLER_TAX_OFFICE_CODE
---

# Generator JPK_V7M

Generuje miesieczna deklaracje VAT w formacie XML zgodnym ze schematem JPK_V7M(2).

## Uzycie

```bash
python3 scripts/generate_jpk.py --month <1-12> --year <YYYY>
```

Tworzy plik `data/jpk/JPK_V7M_YYYY_MM.xml` i zwraca JSON z podsumowaniem.

## Przyklady

- "Wygeneruj JPK za marzec 2026"
- "Przygotuj deklaracje VAT za poprzedni miesiac"
