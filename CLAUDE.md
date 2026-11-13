# JDG Ksiegowy — OpenClaw AI Asystent Ksiegowy

## Projekt

AI Asystent Ksiegowy dla JDG (jednoosobowa dzialalnosc gospodarcza) w Polsce.
Oparty o **OpenClaw** + **Ollama** (lokalny model AI) z opcjonalnym fallbackiem na Claude API.
Automatyzuje: fakturowanie, KSeF, JPK_V7M, kalendarz podatkowy, powiadomienia.

## Architektura (hybrid: Ollama + Claude fallback)

```
OpenClaw Gateway
  |
  +-- SOUL.md              # Persona: asystent ksiegowy JDG
  +-- HEARTBEAT.md          # Checklist co 30 min (platnosci, terminy)
  +-- Cron Jobs              # Miesieczne: faktury, JPK, przypomnienia
  |
  +-- plugins/jdg-ksiegowy/skills/   # Skille agenta: faktury, koszty, vat-jpk, podatki,
  |                                  # administracja — wolaja CLI `jdg`
  |
  +-- src/jdg_ksiegowy/      # Biblioteka Python (rdzen logiki)
  |   +-- app/               # Przypadki uzycia (typowane wejscie/wyjscie, potwierdzenia, audyt)
  |   +-- cli/               # CLI `jdg` (Typer + Rich; JSON dla agentow, `jdg schema`)
  |   +-- config.py          # Pydantic Settings z .env (JDG_HOME)
  |   +-- invoice/           # Modele, generator DOCX, generator XML
  |   +-- ksef/              # KSeF API client (ksef2)
  |   +-- tax/               # JPK, ZUS (single source of truth)
  |   +-- registry/          # SQLite rejestr faktur
  |
  +-- data/                  # SQLite DB + wygenerowane faktury/JPK
```

## Model AI

| Warstwa | Model | Koszt |
|---|---|---|
| Codzienna praca (desktop ≥ 32 GB RAM) | **Ollama qwen3.5:35b** (MoE 35B-A3B, lokalny) | 0 PLN |
| Low-RAM baseline (< 16 GB, np. Oracle Free) | Ollama qwen3.5:9b (lokalny) | 0 PLN |
| Fallback (opcjonalny) | Claude API pay-as-you-go | ~2 PLN/mies. |

**UWAGA:** Anthropic zablokowal subskrypcje Claude Pro/Max dla OpenClaw (4.04.2026).
Uzywaj TYLKO API key (pay-as-you-go) lub Ollama.

## Komendy

```bash
# Pelna instalacja (1 polecenie):
./setup.sh

# Reczny setup:
cp .env.example .env && nano .env    # Dane sprzedawcy
uv sync                               # Python deps z uv.lock (venv w .venv/)
ollama pull qwen3.5:35b               # Model AI (MoE 35B-A3B, ~24 GB; na słabszym hoście: qwen3.5:9b)
openclaw onboard                      # Gateway + kanaly
docker compose up -d                  # Uruchom

# Testy i jakosc (bramka kazdego etapu):
uv run pytest -q                      # + walidacja XSD offline
uv run pytest -m sandbox              # e2e na srodowisku testowym KSeF (siec)
uv run ruff check . && uv run ruff format --check . && uv run mypy

# Migracje bazy (Alembic) uruchamiaja sie same przy init_db();
# nowa migracja: uv run alembic revision --autogenerate -m "opis"

# CLI (to samo wywoluja skille agenta):
uv run jdg --help
uv run jdg tax calc --net 10500
uv run jdg schema                       # kontrakt komend dla agentow
uv run jdg mcp serve                    # te same komendy jako narzedzia MCP (stdio; http dla compose)

# Wtyczka (Claude Code / Codex) — wymaga `jdg` w PATH: uv tool install --editable .
claude plugin validate --strict plugins/jdg-ksiegowy && claude plugin validate --strict .
claude plugin eval plugins/jdg-ksiegowy --ablation none   # ewaluacje (platne wywolania modelu)
```

## Darmowy hosting

**Oracle Cloud Always Free** — 4 ARM OCPU, 24 GB RAM, 200 GB disk, 0 PLN na zawsze.
Na tej maszynie użyj qwen3.5:9b (6.6 GB) — 35b się nie zmieści w 24 GB RAM.

## Konwencje

- Python 3.12+, Decimal (nie float) dla kwot
- ZUS/podatki: single source of truth w `src/jdg_ksiegowy/tax/zus.py`
- Nowa funkcja = przypadek uzycia w `app/` (model wejscia/wyjscia) + komenda w `cli/`;
  czynnosci nieodwracalne przez `require_confirmation` (dwufazowo, z audytem)
- Kontrakt CLI pilnuje `tests/golden/schema.json` (UPDATE_GOLDEN=1 po swiadomej zmianie;
  odswieza tez `plugins/jdg-ksiegowy/evals/mocks/jdg/_tools.json`)
- Kazda komenda z `@command` jest automatycznie narzedziem MCP; komendy tylko do odczytu
  oznaczaj `read_only=True`, nieodwracalne `confirmable=True` (+ matcher w hooks.json)
- Skille opisuja komendy `jdg`; test dryfu odrzuca nieistniejace komendy/opcje i komendy bez opisu
- Logika biznesowa dostaje modele domenowe z `registry.repository`, nie rekordy ORM
- Kwoty w bazie jako grosze (INTEGER), w Pythonie `Decimal`
- Dane sprzedawcy TYLKO z .env (zero hardkodu)

## Zasady pracy (wytyczne developera AI)

Przy KAZDEJ zmianie kodu w tym projekcie:

1. **Najlepsze wzorce i standardy** — clean architecture (domena/aplikacja/infra),
   single responsibility, dependency injection gdzie naturalne, nie kombinuj
   ponad potrzebe. Code smells (long methods, magic numbers, god objects) —
   refaktoryzuj od razu. Typowanie (PEP 604: `str | None`), pydantic dla
   walidacji, dataclass dla frozen value objects.

2. **Najnowsze wersje bibliotek i narzedzi** — przed dodaniem zaleznosci
   sprawdz aktualna wersje (np. `pip index versions <pkg>` lub pypi). Nie
   kopiuj przestarzalych wzorcow. Python 3.12+ idiomy (match statements,
   generic syntax PEP 695, `@override`). Jesli lib ma >1 roku od
   ostatniego release — rozwaz alternatywe.

3. **Bez over-engineeringu** — minimum viable feature, bez hipotetycznych
   rozszerzen. Trzy podobne linie lepsze niz przedwczesna abstrakcja.
   Brak feature flag / kompatybilnosci wstecznej tam gdzie mozna po prostu
   zmienic. Brak try/except "na wszelki wypadek". Walidacja TYLKO na granicy
   systemu (user input, zewnetrzne API) — zaufaj wewnetrznemu kodowi.

4. **Odwoluj sie do kontekstu** — przed zmiana sprawdz: CLAUDE.md (ten plik),
   pydantic models w `src/jdg_ksiegowy/`, istniejace skille, `.env.example`,
   `pyproject.toml`. Nie duplikuj logiki — jesli cos juz istnieje (np.
   `totals_by_vat_rate`), uzyj. Jesli konwencja istnieje (np. argparse
   skrypt zwracajacy JSON na stdout) — trzymaj sie jej. Nie wymyslaj
   wlasnej notacji kategorii/stawek/kodow pol gdy MF ma wlasna.

5. **Weryfikacja, nie deklaracja** — po zmianie uruchom testy (`uv run pytest`),
   end-to-end skrypt na przykladowych danych, sprawdz wynikowy XML lxml-em.
   Nie mow "gotowe" zanim wszystko nie zadziala na czysto.

## Zapisywanie "wytycznych"

Jesli user mowi "zapisz w wytycznych" lub "dopisz do wytycznych" — aktualizuj
te sekcje tego pliku (CLAUDE.md) I rownolegle utworz memory typu `feedback`
z kluczowym punktem, zeby nie zgubilo sie miedzy sesjami.
