# Changelog

Format: [Keep a Changelog](https://keepachangelog.com/pl/1.1.0/), wersje: [SemVer](https://semver.org/lang/pl/).

## [1.0.0] — 2026-11-13

Wersja 1.0 przebudowuje projekt ze zbioru skryptow skilli w biblioteke z warstwa przypadkow
uzycia, jednym CLI `jdg`, serwerem MCP i wtyczka dla OpenClaw, Claude Code i Codex.

### Dodane

- **CLI `jdg`** (Typer + Rich): tabele w terminalu, koperta JSON dla agentow i skryptow, stale
  kody wyjscia, `jdg schema` z opisem wszystkich komend (pilnowany zlotym plikiem).
- **Dwufazowe czynnosci nieodwracalne** (`ksef send`, `invoice mail`, `jpk submit`): token
  wiaze tresc, srodowisko i date; dziennik audytu (`jdg audit`).
- **Serwer MCP** `jdg mcp serve` (stdio i streamable HTTP z tokenem Bearer): 34 narzedzia
  generowane z rejestru komend CLI — te same parametry, funkcje i koperta wyniku.
- **Wtyczka** `plugins/jdg-ksiegowy` dla Claude Code (`.claude-plugin/`) i Codex (Agent Plugins
  1.0: `plugin.json`, `mcp.json`) + marketplace'y w `.claude-plugin/` i `.agents/plugins/`.
  Hook `PreToolUse` wymusza zgode czlowieka na wywolanie z tokenem potwierdzenia.
- **Ewaluacje** `claude plugin eval` (30 przypadkow, mockowane narzedzia MCP): dobor narzedzi
  oraz bezpieczenstwo (prompt injection z KSeF, Bialej listy, OCR i wyniku narzedzia; zgoda
  "z gory"; prosba spoza dziedziny).
- **Docker compose**: osobna usluga `jdg-mcp` z sekretami i danymi (healthcheck, bez portu na
  hoscie); OpenClaw dostaje tylko konfiguracje modelu i token MCP.
- **KSeF**: numer KSeF, data przyjecia i UPO w rejestrze; backfill numerow; kod QR weryfikacji
  i numer KSeF na fakturze; skrzynka zakupowa z opisem z pozycji FA(3).
- **Faktury**: wiele pozycji z kodami stawek (`zw`, `np`, `0_wdt`, `0_exp`) i GTU, nabywcy z UE,
  korekty FA(3) KOR z odwolaniem do numeru KSeF oryginalu, Biala lista MF (`jdg buyer lookup`).
- **JPK**: `NrKSeF` zamiast `BFK`, przeniesienie nadwyzki P_39, pola K_10..K_22, walidacja XSD
  offline, rejestr zlozonych deklaracji ze statusem i odmowa ponownego zlozenia pierwotnej.
- **Podatki**: terminy przesuwane na dni robocze, skladka zdrowotna wg przychodu narastajaco,
  rejestr wplat (`jdg tax pay`), mikrorachunek podatkowy, PIT-28 z odliczeniami i doplata,
  `jdg tax zus`; brak parametrow ZUS na nowy rok zglasza `jdg doctor`.
- **Backup** `jdg backup`: spojna kopia (`VACUUM INTO`), szyfrowanie Fernet, weryfikacja,
  retencja dzienna i miesieczna.
- Migracje bazy (Alembic) uruchamiane automatycznie; kwoty w groszach.

### Zmienione

- OCR na structured outputs (Ollama `format`, Claude `messages.parse`) z deterministycznymi
  kontrolami odczytu, ktore blokuja zapis; domyslny model fallbacku `claude-haiku-5-5`.
- Zaleznosci podniesione do aktualnych wersji, `uv` + `uv.lock`, CI na Pythonie 3.12–3.14
  z mypy, walidacja wtyczki i test dymny serwera MCP w obrazie.
- Skille skonsolidowane do pieciu (`faktury`, `koszty`, `vat-jpk`, `podatki`, `administracja`)
  i opisuja komendy CLI / narzedzia MCP; test pilnuje, by nie odwolywaly sie do nieistniejacych
  komend ani opcji.

### Usuniete

- Skrypty skilli 0.x (zastapione przez `jdg`), generator KEDU DRA (zastapiony przez
  `jdg tax zus` — kwoty do deklaracji w PUE/eZUS).

### Naprawione

- Migracja 0002 nie kasuje pozycji faktur przy wlaczonych kluczach obcych.
- Backup zamyka polaczenia SQLite (blokada pliku tymczasowego na Windows).
- PIT-28 i JPK_EWP: termin 30 kwietnia; ryczalt za grudzien do 20 stycznia.
