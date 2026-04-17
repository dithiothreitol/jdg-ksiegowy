# Claude Code Skills — JDG Księgowość

Zestaw skilli dla [Claude Code](https://docs.claude.com/en/docs/claude-code/overview) do prowadzenia rozliczeń JDG na ryczałcie.

## Skille

| Skill | Co robi | Trigger |
|---|---|---|
| `invoice` | Generuje fakturę DOCX + XML FA(3), zapisuje do rejestru | "wystaw fakturę dla..." |
| `tax-calculator` | Liczy VAT, ryczałt 12%, ZUS zdrowotne, terminy | "ile podatku z...", "co mam zapłacić" |
| `ksef` | Wysyła XML FA(3) do KSeF (test/demo/prod) | "wyślij do KSeF" |
| `jpk` | Generuje JPK_V7M za miesiąc z rejestru | "JPK za marzec" |

## Jak to działa

Każdy skill to wrapper na istniejący skrypt z [skills/](../../skills/) — czyli ta sama logika, której używa OpenClaw. SKILL.md mówi modelowi **kiedy** odpalić skrypt i **z jakimi argumentami**, a sam skrypt (Python, wszystko w `Decimal`) zwraca JSON.

## Uruchomienie

Skille są ładowane automatycznie gdy Claude Code wystartuje w tym repo (folder `.claude/skills/` jest skanowany przy starcie sesji).

Przed pierwszym użyciem upewnij się że:
1. `.env` jest wypełnione (skopiuj z `.env.example`) — dane sprzedawcy, KSEF_TOKEN
2. Zależności są zainstalowane: `pip install -e .`
3. (opcjonalnie) Inicjalizacja DB nastąpi przy pierwszym wywołaniu `invoice`

## Typowy flow miesięczny

1. **W trakcie miesiąca:** "wystaw fakturę dla X, NIP Y, kwota 10500 netto" → skill `invoice`
2. **(opcjonalnie) od razu:** "wyślij ją do KSeF" → skill `ksef`
3. **Po faktúrze:** "ile mi z tego podatku?" → skill `tax-calculator`
4. **Po końcu miesiąca:** "wygeneruj JPK za poprzedni miesiąc" → skill `jpk`
5. **Wysyłka JPK:** ręcznie przez bramkę MF (nie zautomatyzowane)

## Różnica vs OpenClaw

OpenClaw wywołuje te skrypty deterministycznie przez własny gateway. Tutaj decyzję podejmuje model na podstawie `description` w SKILL.md — jeśli zauważysz że jakiś skill nie odpala się gdy powinien, dodaj więcej fraz-trigger do `description`.
