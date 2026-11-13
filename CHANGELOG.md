# Changelog

Format: [Keep a Changelog](https://keepachangelog.com/pl/1.1.0/), wersje: [SemVer](https://semver.org/lang/pl/).

## [1.0.1] — 2026-11-13

### Zmienione

- Komunikaty `jdg` z polskimi znakami: pomoc komend i opcji, bledy i podpowiedzi, podsumowania
  zgody, ostrzezenia, etykiety przypomnien ("Ryczałt za 10/2026"), tresc e-maila z faktura dla
  klienta i okno zgody hooka wtyczki. Opisy narzedzi MCP i `jdg schema` zmieniaja sie razem
  z pomoca; klucze JSON, kody wyjscia i parametry komend pozostaja bez zmian.

### Naprawione

- Wizualizacja faktury (DOCX i PDF wysylany klientom): szerokosci kolumn zapisane takze w siatce
  tabeli, dzieki czemu LibreOffice nie lamie kwot w polowie; strona A4 z marginesami 1,5 cm,
  polskie znaki w etykietach ("Do zapłaty", "Termin płatności") i polski zapis kwot
  (`1 230,00` z twarda spacja tysiecy).
- Wyjscie `jdg` w UTF-8 takze w potoku: na Windows Python < 3.15 kodowal je w cp1250/cp1252,
  przez co polskie znaki docieraly do agenta jako bledne bajty, a przy cp1252 polecenie
  konczylo sie bledem `UnicodeEncodeError`.
- Testy wyjscia w terminalu nie zaleza od szerokosci i kolorow terminala, z ktorego zostaly
  uruchomione (`COLUMNS`, `FORCE_COLOR`, `TTY_COMPATIBLE`).

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
  hoscie); OpenClaw dostaje tylko konfiguracje modelu i token MCP. `.dockerignore` z biala
  lista plikow: `.env`, `data/` i lokalne srodowiska nie trafiaja do kontekstu budowania.
- **KSeF**: numer KSeF, data przyjecia i UPO w rejestrze; backfill numerow; kod QR weryfikacji
  i numer KSeF na fakturze; skrzynka zakupowa z opisem z pozycji FA(3).
- **Faktury**: wiele pozycji z kodami stawek (`zw`, `np`, `0_wdt`, `0_exp`) i GTU, nabywcy z UE,
  korekty FA(3) KOR z odwolaniem do numeru KSeF oryginalu, Biala lista MF (`jdg buyer lookup`).
- **JPK**: `NrKSeF` zamiast `BFK`, przeniesienie nadwyzki P_39, pola K_10..K_22, walidacja XSD
  offline, rejestr zlozonych deklaracji ze statusem i odmowa ponownego zlozenia pierwotnej.
- **Podatki**: terminy przesuwane na dni robocze (przypadki brzegowe: #8, dzieki @webglobepl),
  skladka zdrowotna wg przychodu narastajaco, rejestr wplat (`jdg tax pay`), mikrorachunek
  podatkowy, PIT-28 z odliczeniami i doplata, `jdg tax zus`; brak parametrow ZUS na nowy rok
  zglasza `jdg doctor`.
- **Backup** `jdg backup`: spojna kopia (`VACUUM INTO`), szyfrowanie Fernet, weryfikacja,
  retencja dzienna i miesieczna.
- Migracje bazy (Alembic) uruchamiane automatycznie; kwoty w groszach.
- Wysylka do KSeF: faktura przyjeta bez numeru dostaje status `pending` i blokade ponownej
  wysylki; odrzucona (`INVALID_INPUT`) moze byc poprawiona i wyslana ponownie.
- Kontrakty cykliczne nadrabiaja fakture za biezacy miesiac po przerwie w pracy; bledy
  pojedynczych kontraktow trafiaja do `failed`, a pozostale sa wystawiane.

### Zmienione

- OCR na structured outputs (Ollama `format`, Claude `messages.parse`) z deterministycznymi
  kontrolami odczytu, ktore blokuja zapis; domyslny model fallbacku `claude-haiku-5-5`.
- Zaleznosci podniesione do aktualnych wersji, `uv` + `uv.lock`, CI na Pythonie 3.12–3.15
  z mypy, walidacja wtyczki i test dymny serwera MCP w obrazie (Python 3.15).
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
- JPK_V7M: P_37, P_38, P_48 i P_51 liczone z zaokraglonych pol (kontrole logiczne MF).
- FA(3): kody `0_wdt`/`0_exp` jako "0 WDT"/"0 EX", usluga NP dla UE jako "np II" (spojnie
  z K_12 w JPK); stawka 0 bez kodu = krajowe 0%; nieznany kod odrzucany przy wprowadzaniu.
- Token wysylki e-mail obejmuje tez adresy w kopii (`cc`).
- Migracja z 0.x odczytuje kody P_12 (np. "np I", "zw", "0 KR") z plikow FA(3).
- Faktury korygujace in minus nie sa pokazywane jako zalegle naleznosci.
- `jdg jpk build`: brak danych SELLER_* to `CONFIG_MISSING`, bledne dane rejestru — `INVALID_INPUT`.
