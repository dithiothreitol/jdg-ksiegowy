---
name: administracja
description: Utrzymanie asystenta ksiegowego JDG — diagnostyka konfiguracji, backup, kalendarz terminow Google, dziennik czynnosci, uzupelnienie numerow KSeF. Uzyj gdy user pyta "czy wszystko skonfigurowane", "diagnostyka", "co mam brak w .env", "zrob backup", "synchronizuj kalendarz", "terminy do kalendarza", "co bylo wysylane", "historia operacji".
---

# Administracja

CLI `jdg` (lub `uv run jdg`); kontrakt wyjscia i kody bledow jak w `jdg schema`.

- `jdg doctor` — sprawdza dane sprzedawcy, KSeF, bramke MF, SMTP, OCR, kalendarz. Przy bledach
  pokaz userowi, co uzupelnic; nie edytuj `.env` samodzielnie.
- `jdg config` — skad czytana jest konfiguracja (`JDG_HOME`), srodowiska KSeF/MF, ktore sekrety
  sa ustawione (bez wartosci).
- `jdg backup` — szyfrowana kopia bazy (spojna, `VACUUM INTO`) i dokumentow, weryfikowana po
  zapisie. Wymaga `BACKUP_KEY`; katalog: `BACKUP_DIR` (domyslnie OneDrive lub ~/Documents).
- `jdg calendar sync [--dry-run]` — terminy z kwotami w kalendarzu Google "JDG Podatki"
  (idempotentnie). Konfiguracja jednorazowa: `GCAL_ENABLED`, `GCAL_CREDENTIALS_PATH`, potem
  `uv run python -m jdg_ksiegowy.calendar.auth_setup`.
- `jdg audit` — dziennik: wystawienia, wysylki (z odmowami bez potwierdzenia), backupy.
- `jdg ksef backfill` — podglad numerow KSeF dla faktur wyslanych przed wersja 1.0;
  `--apply` zapisuje je w rejestrze (potrzebne, by JPK mial NrKSeF zamiast BFK).
