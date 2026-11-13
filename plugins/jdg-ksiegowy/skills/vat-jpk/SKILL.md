---
name: vat-jpk
description: Deklaracja VAT JPK_V7M (miesiecznie) i ewidencja JPK_EWP (rocznie) — budowa z rejestru, walidacja XSD, wysylka do bramki MF z UPO, status, korekty. Uzyj gdy user mowi "wygeneruj JPK", "JPK za pazdziernik", "deklaracja VAT", "wyslij JPK do MF", "zloz deklaracje", "korekta JPK", "biuro wyslalo zerowa deklaracje", "ewidencja przychodow / JPK_EWP", "czy MF przyjelo".
---

# JPK_V7M i JPK_EWP

CLI `jdg` (lub `uv run jdg`); kontrakt wyjscia i kody bledow jak w `jdg schema`.

## Budowa

```bash
jdg jpk build                                # poprzedni miesiac (domyslnie)
jdg jpk build --year 2026 --month 10
jdg jpk build-ewp --year 2026                # ewidencja ryczaltu, sklada sie do 30.04
jdg jpk validate data/jpk/JPK_V7M_2026_10.xml
```

Wynik zawiera P_38 (`vat_due`), P_39 (`vat_carry_forward` — nadwyzka z poprzedniej deklaracji,
pobierana automatycznie z P_62 poprzedniego okresu), P_48 (`vat_deductible`), P_51 (`vat_to_pay`),
P_62 (`vat_surplus` — przechodzi na nastepny miesiac) i `xsd_valid`.
`invoice_count == 0` → ostrzez usera (brak faktur albo zly miesiac).
Faktury z numerem KSeF dostaja w JPK `NrKSeF`, pozostale `BFK` — przed budowa sprawdz, czy
faktury z okresu zostaly wyslane do KSeF. Sprzedaz z kodami `np`, `zw`, `0_wdt`, `0_exp`
trafia do wlasciwych pol (K_11/K_12, K_10, K_21, K_22); GTU z pozycji faktury.

## Wysylka — nieodwracalna

```bash
jdg jpk submit data/jpk/JPK_V7M_2026_10.xml            # kod 4: summary + token
jdg jpk submit data/jpk/JPK_V7M_2026_10.xml --confirm <token>
```

1. Pierwsze wywolanie waliduje XSD i zwraca podsumowanie (formularz, okres, cel, P_38/P_48/P_51,
   srodowisko) oraz token. Nic nie wysyla.
2. **Pokaz podsumowanie i zapytaj usera o zgode.** `env: prod` = realna deklaracja w urzedzie.
3. Dopiero po wyraznym "tak" — `--confirm <token>`. Nigdy bez zgody.

Odpowiedz z wysylki zapisuje sie w rejestrze deklaracji. Status `submitted` (MF jeszcze przetwarza)
→ pozniej `jdg jpk status --reference <numer>` albo `jdg jpk status --year 2026 --month 10`
(bez ponownej wysylki). `accepted` = UPO w `data/upo/` — dowod zlozenia.

## Korekta

Gdy za okres jest juz przyjety plik (twoj lub pelnomocnika) — korekta, nie ponowne zlozenie
(`jdg jpk submit` odmowi zlozenia pierwotnego, jesli zna przyjeta deklaracje):

```bash
jdg jpk build --year 2026 --month 3 --correction \
  --reason "Pelnomocnik omylkowo zlozyl deklaracje zerowa; korekta przywraca rozliczenie."
```

Powstaje `JPK_V7M_2026_03_K1.xml` (kolejne: `_K2`...), oryginal zostaje. W urzedzie obowiazuje
ostatni przyjety plik. Przed wysylka pokaz P_38/P_48/P_51 korekty obok oryginalu.
Nie wiesz, co jest w urzedzie → user sprawdza w e-Urzedzie Skarbowym; brak UPO lokalnie nie
znaczy, ze nic nie zlozono. Pelnomocnik skladal za usera → przypomnij o OPL-1.

## Terminy i dane

JPK_V7M do 25. dnia nastepnego miesiaca; JPK_EWP do 30.04 za rok poprzedni (terminy
w weekend lub swieto przesuwaja sie na najblizszy dzien roboczy). VAT placi sie na mikrorachunek
(`tax_microaccount` w `jdg status`); po zaplacie `jdg tax pay vat --amount ... --year R --month M`.
Wymagane w `.env`: `SELLER_NIP/FIRST_NAME/LAST_NAME/BIRTH_DATE/TAX_OFFICE_CODE`, `MF_PESEL`,
`MF_PRIOR_INCOME` (przychod z PIT za rok N-2; brak zeznania = 0), `MF_ENV` (test|prod).
Klucz publiczny MF jest wbudowany; po rotacji przez MF — `MF_CERT_PATH`/`MF_CERT_URL`.
