---
name: jdg-status
description: Dashboard aktualnego stanu księgowości JDG — nadchodzące terminy podatkowe (20-ty ryczałt+ZUS, 25-ty VAT+JPK), niezapłacone/zaległe faktury, podsumowanie miesiąca (sprzedaż, koszty, estymowany ryczałt i ZUS). Użyj gdy user pyta "co mam do zapłacenia", "jakie mam terminy", "status rozliczeń", "co mi zaległo", "podsumowanie miesiąca", "co powinienem zrobić", "jakie mam faktury niezapłacone".
---

# Dashboard JDG

Kompletny snapshot stanu rozliczeń — bez dotykania sieci (wszystko z SQLite).

## Wywołanie

```bash
# Format JSON (do dalszego przetwarzania)
python3 skills/jdg-status/scripts/status.py

# Format czytelny w terminalu
python3 skills/jdg-status/scripts/status.py --format table

# Z konkretną datą odniesienia (do symulacji / testów)
python3 skills/jdg-status/scripts/status.py --date 2026-05-18
```

## Co pokazuje

**Terminy (posortowane po dacie):**
- Ryczałt za poprzedni miesiąc (20-ty)
- ZUS zdrowotne (20-ty)
- VAT + JPK_V7M (25-ty)
- Niezapłacone faktury kontrahentów (7 dni przed terminem)

**Poziomy (`level`):**
- `overdue` — po terminie (faktura albo podatek!)
- `urgent` — dziś lub jutro
- `warn` — w ciągu tygodnia
- `info` — >7 dni

**Faktury:**
- Zaległe (po terminie, niezapłacone)
- Niezapłacone (jeszcze przed terminem)

**Podsumowanie bieżącego miesiąca:**
- Sprzedaż netto + VAT
- Koszty netto + VAT naliczony
- Estymowany ryczałt (12% × sprzedaż poprzedniego miesiąca)
- Estymowany ZUS zdrowotne (z progu wg `tax/zus.py`)

## Po wywołaniu

Pokaż userowi TYLKO `overdue` i `urgent` na górze (najważniejsze).
Dla `warn` pokaż listę, ale mniej wyraźnie.
`info` — pomiń chyba że user wprost prosi o pełną listę.

Dla typowego flow *"co mam zrobić"*: skup się na 2-3 najpilniejszych akcjach.
Jeśli `overdue` nie ma → zrób userowi pochwałę :)

## Automatyzacja (cron)

Ten skill jest idealny dla cron job — codziennie rano sprawdza status i
wysyła email / notyfikację przy `overdue` lub `urgent`. Zobacz `CRON.md`.
