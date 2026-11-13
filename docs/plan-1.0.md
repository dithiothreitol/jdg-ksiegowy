# Plan wydania 1.0

Cztery etapy, każdy na osobnej gałęzi `stage-N/*` łączonej do `release/1.0`.
Każdy etap kończy się bramką testową; etap nie jest skończony, dopóki bramka nie
przechodzi. Na końcu `/code-review high` całego `release/1.0` względem `main`.

Zasady wspólne:

- Testy e2e tylko na sandboxach (`KSEF_ENV=test`, `MF_ENV=test`) i z fikcyjnym
  NIP sprzedawcy — środowisko testowe KSeF jest dostępne dla każdego, kto zna NIP.
- Produkcyjna baza (`data/jdg_ksiegowy.db`) jest migrowana dopiero po backupie
  i udanej próbie na kopii.
- Kwoty w Pythonie zawsze `Decimal`; w bazie skalowane liczby całkowite (grosze).

## Etap 1 — fundament i łańcuch numeru KSeF

1. Zależności podniesione do najnowszych stabilnych, `uv.lock`, Dockerfile na
   `uv sync --frozen`, obrazy bazowe przypięte do tagów.
2. Skrypty bez `sys.path.insert`; `JDG_HOME` wskazuje katalog z `.env` i `data/`.
3. Alembic. Migracja: pozycje faktur, rodzaj faktury, dane zagranicznego
   nabywcy, `ksef_number` + numer sesji + data przyjęcia, tabele `filings`
   i `audit_log`, kwoty jako grosze.
4. Repozytoria zwracające modele domenowe zamiast powielonych mapowań.
5. Klient KSeF zapisuje numer KSeF, datę przyjęcia i UPO; uzupełnienie numerów
   dla faktur już wysłanych.
6. JPK_V7M i JPK_EWP wpisują `NrKSeF` / `K_5` dla sprzedaży i zakupów.
7. Walidacja XSD offline (schematy w pakiecie).

Bramka: pełny pytest z XSD, ruff, mypy, `docker build`; migracja kopii bazy
produkcyjnej z identycznymi sumami miesięcznymi; JPK 09/2026 po migracji
różni się od złożonego tylko znacznikami KSeF; e2e wysyłki na sandbox KSeF.

## Etap 2 — CLI `jdg`, warstwa aplikacyjna, bezpieczna wysyłka

1. Przypadki użycia w `jdg_ksiegowy/app/` z modelami wejścia/wyjścia;
   CLI i MCP są tylko adapterami.
2. CLI w Typer: `invoice`, `ksef`, `expense`, `jpk`, `tax`, `contract`,
   `payment`, `status`, `doctor`, `backup`, `calendar`, `config`, `schema`,
   `mcp`.
3. Interfejs: tabele Rich w terminalu, koperta JSON przy `--json` lub poza
   terminalem; wynik na stdout, logi na stderr; błędy z kodem, podpowiedzią
   i flagą ponowienia; stałe kody wyjścia; `--dry-run` dla mutacji; brak
   pytań poza terminalem; `jdg schema` zwraca JSON Schema komend.
4. Czynności nieodwracalne (`ksef send`, `jpk submit`, `invoice mail`)
   dwufazowo: podsumowanie + skrót, potem `--confirm <skrót>`. Na `prod`
   bez terminala odmowa.
5. `jpk submit` waliduje XSD, zapisuje `filings`; `jpk status` wznawia
   sprawdzanie po timeoucie; klucz MF pobierany automatycznie.
6. Usunięcie `skills/*/scripts/`; `SKILL.md` i `CRON.md` wołają `jdg`;
   port UI tylko na `127.0.0.1`.

Bramka: testy kontraktu każdej komendy, parytet starych skryptów i nowych
komend, testy odmowy bez potwierdzenia (zero wywołań HTTP), plik wzorcowy
`jdg schema`, e2e na sandboxach KSeF i MF.

## Etap 3 — uzupełnienie domeny

1. Jeden potok wystawiania (ręczne, kontrakty, korekty): wiele pozycji
   i stawek, nabywca zagraniczny, GTU; PDF z numerem KSeF i kodem QR.
2. JPK: korekty faktur, nadwyżka do `P_39`, pola K_12/K_21/K_22.
3. Parametry podatkowe per rok; terminy przesuwane na dni robocze; ryczałt
   za grudzień do końca lutego.
4. Składka zdrowotna z przychodu narastająco, odliczenia w ryczałcie
   i PIT-28, ewidencja zapłat, mikrorachunek z NIP.
5. DRA zgodne z XSD KEDU albo sama kalkulacja.
6. OCR ze schematem wyjścia i walidatorami; faktury z KSeF z XML.
7. Dane nabywcy z Białej listy MF.
8. Backup przez `VACUUM INTO` z pełnym katalogiem danych.

Bramka: testy złote JPK z XSD, testy własności sum, tabela terminów
2026–2027, próg trafności OCR, odtworzenie backupu, e2e korekty na sandbox.

Poza zakresem 1.0: VAT-UE, środki trwałe, ulga na złe długi, tryb offline
KSeF, waluty obce.

## Etap 4 — pluginy, MCP, ewaluacje

1. `jdg mcp serve` — narzędzia z tych samych przypadków użycia.
2. Jeden katalog pluginu `plugins/jdg-ksiegowy/` z manifestami dla Claude Code
   i Codex, wspólne skille, `.mcp.json`, hook wymuszający zgodę, `bin/jdg`;
   marketplace'y w `.claude-plugin/` i `.agents/plugins/`.
3. Sekrety tylko w procesie CLI/MCP; OpenClaw korzysta ze skilli pluginu,
   MCP jako osobna usługa w compose.
4. Ewaluacje doboru narzędzi i przypadków bezpieczeństwa w `evals/`.
5. Dokumentacja, CHANGELOG, wersja 1.0.0.

Bramka: `claude plugin validate --strict`, test dymny w Claude Code i Codex,
kontrakt MCP = `jdg schema`, test dryfu skilli, ewaluacje (95% / 100%),
`docker compose up` z healthcheckiem.
