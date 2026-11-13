---
name: koszty
description: Koszty JDG (faktury zakupu) — pobranie z KSeF, odczyt OCR z PDF/zdjecia, wpis reczny, lista. Na ryczalcie koszty nie zmniejszaja podatku, ale VAT naliczony trafia do JPK_V7M. Uzyj gdy user mowi "dodaj fakture zakupu", "zarejestruj koszt", "co przyszlo na KSeF", "pobierz koszty z KSeF", "zeskanuj fakture", "kupilem laptopa za...", "faktura za hosting/paliwo/SaaS", albo przesyla plik faktury.
---

# Koszty (faktury zakupu)

CLI `jdg` (lub `uv run jdg`); kontrakt wyjscia i kody bledow jak w `jdg schema`.

## Kolejnosc zrodel

1. **KSeF** — faktury od polskich firm (paliwo, SaaS, uslugi). Dokladne kwoty i numer KSeF,
   ktory trafia do JPK. Paragon / "potwierdzenie transakcji" (np. Shell) = faktura jest w KSeF.
2. **OCR** — papier, PDF mailem, faktury zagraniczne.
3. **Recznie** — gdy user poda dane.

## KSeF

```bash
jdg ksef inbox --year 2026 --month 11          # podglad: status new / exists / manual
jdg ksef inbox --year 2026 --month 11 --save   # zapis nowych (z XML jako dowodem)
```

Najpierw podglad. Pozycje `manual` (korekta, waluta obca, samofakturowanie, niespojne kwoty) nie
zapisuja sie same — pokaz `manual_reason` i wprowadz recznie po decyzji usera.
Paliwo / auto: **zapytaj o tryb auta** przed `--save` → `--vat-deduction-pct 50` (uzytek mieszany),
`100` (wylacznie firmowe, VAT-26), `0` (brak odliczenia).

## OCR

```bash
jdg expense scan faktura.pdf          # podglad do akceptacji
jdg expense scan faktura.pdf --save   # zapis po akceptacji usera
```

Pokaz odczytane pola i zapytaj o poprawki. Bledy popraw przez `jdg expense add` z wlasciwymi danymi.

## Recznie

```bash
jdg expense add --seller-name "Hetzner Online GmbH" --seller-nip DE812871812 --seller-country DE \
  --document-number R0012345 --issue-date 2026-11-05 --net 100 --reverse-charge \
  --category uslugi_obce --description "VPS listopad"
```

- `--receive-date` (data wplywu) decyduje o miesiacu odliczenia; domyslnie data wystawienia.
- Import uslug (faktura zagraniczna bez VAT): `--reverse-charge` — VAT nalezny i naliczony
  liczone z netto x stawka; efekt na kwote do zaplaty zwykle zerowy.
- Kategorie: `uslugi_obce | materialy | media | paliwo | samochod | biuro | sprzet | szkolenia | inne`.
- Brak NIP lub kwot → dopytaj, nie wymyslaj.

`jdg expense list --year 2026 --month 11` — lista z VAT do odliczenia.
