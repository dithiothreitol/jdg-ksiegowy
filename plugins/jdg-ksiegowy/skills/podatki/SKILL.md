---
name: podatki
description: Podatki i terminy JDG na ryczalcie — co i kiedy zaplacic (ryczalt, ZUS, VAT), kalkulator od kwoty netto, podsumowanie roczne PIT-28, deklaracja DRA ZUS, dashboard zaleglosci. Uzyj gdy user pyta "ile podatku", "ile ZUS", "co mam do zaplacenia", "jakie mam terminy", "status rozliczen", "co mi zaleglo", "PIT-28", "podsumowanie roku", "DRA", "skladka zdrowotna".
---

# Podatki i terminy

CLI `jdg` (lub `uv run jdg`). Kwoty zawsze z narzedzia — nigdy nie licz podatkow w pamieci.

## Co mam zrobic / zaplacic

`jdg status` — terminy (ryczalt i ZUS do 20., VAT + JPK do 25.) z kwotami, faktury po terminie
i niezaplacone, podsumowanie miesiaca. Kwota VAT w przypomnieniu to szacunek; wiazaca jest
`vat_to_pay` z `jdg jpk build`.

## Kalkulator

```bash
jdg tax calc --net 10500                     # VAT, ryczalt, ZUS, terminy dla kwoty netto
jdg tax calc --net 10500 --annual-revenue 150000
jdg tax deadlines --year 2026 --month 11
```

Prog skladki zdrowotnej zalezy od rocznego przychodu — bez `--annual-revenue` szacunek to
netto x 12; podaj realny przychod, jesli user go zna.

## Rocznie

- `jdg tax pit28 --year 2026` — przychody i ryczalt miesiac po miesiacu (wg daty uzyskania
  przychodu). Kwoty pomocnicze — przed zlozeniem PIT-28 porownaj z wplaconymi zaliczkami.
- `jdg jpk build-ewp --year 2026` — ewidencja do PIT-28 (skill vat-jpk).

## ZUS DRA

```bash
jdg tax dra --month 11 --year 2026 --annual-prior-income 150000 [--include-social]
```

Tworzy XML KEDU do importu w PUE ZUS (Dokumenty i wiadomosci → Import KEDU). Termin: 20. dnia
nastepnego miesiaca.

## Zastrzezenie

Nie jestes doradca podatkowym. W sprawach niejednoznacznych (nowe przepisy, kontrola, spor
z urzedem) zalec konsultacje z ksiegowym.
