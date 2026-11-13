---
name: podatki
description: Podatki i terminy JDG na ryczalcie — co i kiedy zaplacic (ryczalt, ZUS, VAT), skladki ZUS za miesiac (zdrowotna wg przychodu narastajaco), rejestr wplat, mikrorachunek podatkowy, kalkulator od kwoty netto, rozliczenie roczne PIT-28, dashboard zaleglosci. Uzyj gdy user pyta "ile podatku", "ile ZUS", "ile zdrowotnej", "co mam do zaplacenia", "jakie mam terminy", "na jakie konto", "mikrorachunek", "zaplacilem ryczalt/ZUS/VAT", "status rozliczen", "co mi zaleglo", "PIT-28", "podsumowanie roku", "DRA".
---

# Podatki i terminy

CLI `jdg` (lub `uv run jdg`). Kwoty zawsze z narzedzia — nigdy nie licz podatkow w pamieci.

## Co mam zrobic / zaplacic

`jdg status` — terminy z kwotami, faktury po terminie i niezaplacone, podsumowanie miesiaca,
`tax_microaccount` (mikrorachunek na ryczalt i VAT) oraz `notes` (np. brak parametrow ZUS).
Przypomnienia oplaconych okresow (zapisanych przez `jdg tax pay`) maja poziom `paid`.
Kwota VAT w przypomnieniu to szacunek; wiazaca jest `vat_to_pay` z `jdg jpk build`.

Terminy (przesuwane na najblizszy dzien roboczy, gdy wypadaja w weekend lub swieto):
ryczalt i ZUS do 20. dnia nastepnego miesiaca (ryczalt za grudzien do 20 stycznia),
VAT + JPK_V7M do 25., PIT-28 i JPK_EWP do 30 kwietnia. `jdg tax deadlines --year R --month M`.

## Skladki ZUS

```bash
jdg tax zus --year 2026 --month 10
```

Zdrowotna wg progu przychodu **narastajaco od poczatku roku** (pomniejszonego o zaplacone
skladki spoleczne) — prog zmienia sie od miesiaca przekroczenia. Spoleczne wg trybu z `.env`.
Deklaracje DRA user sklada w PUE/eZUS (`how_to_file`); narzedzie podaje kwoty.

## Zaplaty

```bash
jdg tax pay ryczalt --amount 1250 --year 2026 --month 10 --paid-on 2026-11-18
jdg tax payments --year 2026
```

Rodzaje: `ryczalt | vat | zus_health | zus_social`. Zapis gasi przypomnienie, a zaplacone
skladki wchodza do odliczen (od przychodu: spoleczne; 50% zaplaconej zdrowotnej). Zapisuj
tylko zaplaty potwierdzone przez usera, z kwota faktycznie przelana.

## Kalkulator

```bash
jdg tax calc --net 10500                     # VAT, ryczalt, ZUS, terminy dla kwoty netto
jdg tax calc --net 10500 --annual-revenue 150000
```

Prog zdrowotnej zalezy od przychodu — bez `--annual-revenue` szacunek to netto x 12.
Ryczalt zaokraglany do pelnych zlotych (art. 63 Ordynacji podatkowej).

## Rocznie

- `jdg tax pit28 --year 2026` — przychody, odliczenia, podstawa i ryczalt roczny, zaliczki
  wplacone (`advances_paid` z `jdg tax pay`) i `to_pay` do doplaty, termin. Kwoty pomocnicze —
  przed zlozeniem PIT-28 user porownuje je z wyciagiem.
- `jdg jpk build-ewp --year 2026` — ewidencja do PIT-28 (skill vat-jpk).

## Zastrzezenie

Nie jestes doradca podatkowym. Parametry ZUS na nowy rok trzeba dopisac w kodzie po publikacji
(`jdg doctor` ostrzega). W sprawach niejednoznacznych (nowe przepisy, kontrola, spor z urzedem)
zalec konsultacje z ksiegowym.
