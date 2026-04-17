---
name: zus-dra
description: Generator DRA ZUS (KEDU v5.05) — miesięczna deklaracja rozliczeniowa dla JDG. Oblicza składki zdrowotne wg przychodu rocznego (ryczałt) i tworzy XML do importu przez PUE ZUS. Użyj gdy user pyta "ZUS DRA", "składka zdrowotna ZUS", "deklaracja ZUS", "KEDU", "rozliczenie ZUS", "ile ZUS".
---

# ZUS DRA (KEDU v5.05)

Generuje XML KEDU z miesięczną DRA do ręcznego importu przez PUE ZUS.

**Uwaga:** PUE ZUS nie oferuje publicznego REST API. Skill generuje XML — użytkownik importuje go ręcznie: PUE → Dokumenty i wiadomości → Import KEDU.

## Wywołanie

```bash
# DRA za marzec 2026, przychód 2024 = 120k PLN (próg II zdrowotnej)
python3 skills/zus-dra/scripts/generate.py \
    --month 3 --year 2026 \
    --annual-prior-income 120000

# Z doliczeniem składek społecznych (pełne ZUS, nie preferencyjny)
python3 skills/zus-dra/scripts/generate.py \
    --month 3 --year 2026 \
    --annual-prior-income 250000 \
    --include-social

# Własna ścieżka output
python3 skills/zus-dra/scripts/generate.py \
    --month 3 --year 2026 --annual-prior-income 60000 \
    --output /tmp/DRA_mar2026.xml
```

## Progi zdrowotne (ryczałt 2026)

Oblicza `jdg_ksiegowy.tax.zus.get_zus_tier(annual_prior_income)`:
| Próg | Przychód rok poprz. | Składka zdrowotna/mies. |
|------|--------------------|-------------------------|
| I    | ≤ 60 000 PLN       | ~ 360 PLN               |
| II   | 60 001 – 300 000   | ~ 600 PLN               |
| III  | > 300 000 PLN      | ~ 1080 PLN              |

## Termin

DRA za miesiąc M składa się do **20-tego miesiąca M+1** (czyli DRA za marzec → do 20 kwietnia).

## Wysyłka

1. Zaloguj na [PUE ZUS](https://www.zus.pl/portal/logowanie.npi)
2. Menu **Dokumenty i wiadomości** → **Import KEDU**
3. Wskaż wygenerowany XML → potwierdź podpisem kwalifikowanym/ePUAP/PUE
