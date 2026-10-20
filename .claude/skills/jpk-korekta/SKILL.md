---
name: jpk-korekta
description: Korekta złożonego JPK_V7M (deklaracja VAT + ewidencja) za dowolny miesiąc — generuje plik z CelZlozenia=2 i uzasadnieniem (P_ORDZU), waliduje XSD i wysyła do bramki MF. Użyj gdy user mówi "korekta JPK", "skoryguj deklarację VAT", "korekta VAT-7 / JPK_V7M za marzec", "biuro/księgowa wysłało zerową deklarację", "deklaracja zerowa nadpisała moją", "popraw złożony JPK", "ponownie złóż JPK za miesiąc".
---

# Korekta JPK_V7M

Od 10.2020 deklaracja VAT-7 nie istnieje osobno — jest częścią JPK_V7M. Korekta to **pełny plik
JPK_V7M za ten sam okres z `CelZlozenia = 2`** (formularza ORD-ZU nie ma; uzasadnienie to opcjonalne
pole `P_ORDZU`). W urzędzie obowiązuje **ostatni przyjęty plik** (najnowsze UPO) — dlatego zerowa
deklaracja wysłana przez pełnomocnika po Twojej nadpisuje Twoje rozliczenie, a Twoja korekta
nadpisuje ją z powrotem.

## Kiedy korekta, a kiedy nie

- Za okres istnieje **jakikolwiek** przyjęty plik (Twój albo pełnomocnika) → korekta (`--correction`).
- Za okres nikt nic nie złożył → zwykłe złożenie (`generate_jpk.py` bez flagi); bramka może odrzucić
  korektę bez pierwotnego.
- Nie wiesz, co jest w urzędzie → user sprawdza w e-Urzędzie Skarbowym (Dokumenty → JPK_VAT).
  Nie zgaduj — brak UPO w `data/upo/` nie znaczy, że za okres nic nie ma.

## Przebieg (dla każdego okresu)

```bash
# 1. Korekta z uzasadnieniem — oryginał data/jpk/JPK_V7M_2026_03.xml zostaje, powstaje _K1.xml
python3 skills/jpk/scripts/generate_jpk.py --month 3 --year 2026 --correction \
  --reason "Korekta przywraca prawidłowe rozliczenie za okres. Pełnomocnik (biuro rachunkowe) omyłkowo złożył za ten okres deklarację zerową."

# 2. Walidacja XSD (bramka MF nie jest walidowana lokalnie — błąd wyszedłby dopiero jako 4xx)
python3 skills/jpk/scripts/validate_jpk.py --xml-path data/jpk/JPK_V7M_2026_03_K1.xml

# 3. Wysyłka jak zwykłego JPK (skill jpk-submit) — najpierw --dry-run
python3 skills/jpk-submit/scripts/submit.py --xml-path data/jpk/JPK_V7M_2026_03_K1.xml --dry-run
python3 skills/jpk-submit/scripts/submit.py --xml-path data/jpk/JPK_V7M_2026_03_K1.xml
```

Kolejna korekta tego samego okresu → `_K2.xml` (numer nadawany automatycznie); w XML zawsze `CelZlozenia=2`.

## Przed wysyłką pokaż userowi

Tabelę per okres: P_38 (należny), P_48 (naliczony), P_51 (do zapłaty) **z korekty vs. z oryginalnie
złożonego pliku** (`data/jpk/JPK_V7M_YYYY_MM.xml`). Różnica = rejestr zmienił się od złożenia (np.
dopisane koszty) — user musi świadomie zaakceptować, że korekta wysyła nowe kwoty. Pokaż też treść `P_ORDZU`.

## Po wysyłce

- UPO ląduje w `data/upo/UPO_<ref>.bin` — zawiera `CelZlozenia=2` i okres (`MiesiacCD`). To dowód korekty.
- Jeśli P_51 rośnie względem stanu w urzędzie, a podatek był **zapłacony w terminie** — odsetek nie ma;
  skuteczna korekta + zapłata zwalnia z odpowiedzialności KKS (art. 16a) — czynny żal niepotrzebny.
- Pełnomocnik składał za usera → przypomnij o **OPL-1** (odwołanie UPL-1), inaczej problem wróci.

## Uwagi

- Korygujemy **cały** plik (deklaracja + ewidencja) z aktualnego rejestru — nie edytuj XML ręcznie.
- `MF_ENV=prod` wysyła realną korektę — ta sama ostrożność co w skillu `jpk-submit`.
