---
name: administracja
description: Utrzymanie asystenta ksiegowego JDG — diagnostyka konfiguracji, backup, kalendarz terminow Google, dziennik czynnosci, uzupelnienie numerow KSeF. Uzyj gdy user pyta "czy wszystko skonfigurowane", "diagnostyka", "co mam brak w .env", "zrob backup", "synchronizuj kalendarz", "terminy do kalendarza", "co bylo wysylane", "historia operacji".
---

# Administracja

Narzedzia: serwer MCP `jdg`, gdy jest dostepny — kazda komenda z tego opisu to narzedzie
o nazwie z podkreslnikami (`jdg invoice issue` → `invoice_issue`, `--buyer-nip` → `buyer_nip`).
Bez MCP: CLI `jdg` (gdy nie ma go w PATH: `uv run jdg` w katalogu repozytorium).
Kontrakt wyniku i kody bledow: `jdg schema`.

- `jdg doctor` — sprawdza dane sprzedawcy, KSeF, bramke MF, SMTP, OCR, kalendarz i obecnosc
  parametrow ZUS na biezacy rok. Przy bledach pokaz userowi, co uzupelnic; nie edytuj `.env`
  samodzielnie. Brak parametrow ZUS = zmiana w kodzie (`tax/zus.py`), nie w konfiguracji.
- `jdg config` — skad czytana jest konfiguracja (`JDG_HOME`), srodowiska KSeF/MF, ktore sekrety
  sa ustawione (bez wartosci).
- `jdg backup` — szyfrowana kopia bazy (spojna, `VACUUM INTO`) i dokumentow, weryfikowana po
  zapisie (odszyfrowanie + `integrity_check`). Wymaga `BACKUP_KEY`; katalog: `BACKUP_DIR`.
  Retencja: ostatnie 30 kopii + pierwsza kopia z kazdego z 12 miesiecy (`--keep-days`,
  `--keep-monthly`). Bez `BACKUP_KEY` kopii nie da sie odtworzyc — user trzyma klucz w menedzerze
  hasel.
- `jdg calendar sync [--dry-run]` — terminy z kwotami w kalendarzu Google "JDG Podatki"
  (idempotentnie). Konfiguracja jednorazowa: `GCAL_ENABLED`, `GCAL_CREDENTIALS_PATH`, potem
  `uv run python -m jdg_ksiegowy.calendar.auth_setup`.
- `jdg audit` — dziennik: wystawienia, wysylki (z odmowami bez potwierdzenia), backupy.
- `jdg ksef backfill` — podglad numerow KSeF dla faktur wyslanych przed wersja 1.0;
  `--apply` zapisuje je w rejestrze (potrzebne, by JPK mial NrKSeF zamiast BFK).
