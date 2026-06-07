# TODO

## Pełny automat synchronizacji Google Calendar (on-machine)

**Status:** kod gotowy (commit `352fb32`), automat **NIEAKTYWNY** — czeka na jednorazową aktywację.

### Cel
Bezobsługowa, miesięczna synchronizacja terminów podatkowych (ryczałt, ZUS, VAT+JPK) oraz
przypomnień o niezapłaconych/zaległych fakturach — **z kwotami** — do dedykowanego kalendarza
Google **„JDG Podatki"**. Musi działać **na maszynie użytkownika** (tam jest lokalna baza
SQLite z księgami) — chmurowy harmonogram (np. scheduled remote agent) nie ma dostępu do
`data/` ani do liczonych kwot.

### Co już jest w repo
- `src/jdg_ksiegowy/calendar/gcal.py` — klient Google Calendar API (app-native OAuth, lazy import).
- `src/jdg_ksiegowy/calendar/sync.py` — reconcile `Dashboard.reminders` ↔ wydarzenia (create/update/delete osieroconych).
- `src/jdg_ksiegowy/calendar/auth_setup.py` — jednorazowa zgoda OAuth → refresh token.
- Skill `calendar-sync` (`skills/calendar-sync/scripts/sync.py`, flaga `--dry-run`).
- `CalendarConfig` (prefix `GCAL_`) w `config.py`; check `_check_calendar` w doctorze.
- Wpis crona w `CRON.md` (codziennie 07:00).
- Idempotencja: `extendedProperties.private` (`jdg_managed`/`jdg_key`); zapłacone faktury znikają z kalendarza.

### Aktywacja — checklista
- [ ] `pip install -e .` (dociąga google-api-python-client / google-auth / google-auth-oauthlib)
- [ ] Google Cloud Console: projekt → włącz **Google Calendar API** → **OAuth client „Desktop app"** → pobierz `credentials.json`
- [ ] `.env`: `GCAL_ENABLED=true`, `GCAL_CREDENTIALS_PATH=/abs/sciezka/credentials.json`
- [ ] `python -m jdg_ksiegowy.calendar.auth_setup` (zgoda w przeglądarce → token w `data/gcal_token.json`)
- [ ] `python skills/calendar-sync/scripts/sync.py --dry-run` → weryfikacja różnicy; potem bez `--dry-run`
- [ ] Zarejestruj cron OpenClaw (linijka jest w `CRON.md`): `openclaw cron add "0 7 * * *" "...calendar-sync"`
- [ ] `python skills/doctor/scripts/check.py` → obszar `CALENDAR` = OK

### Migracja z obecnego stanu (WAŻNE — uniknięcie duplikatów)
07.06.2026 utworzono **ręcznie przez MCP** 3 zdarzenia za 05/2026 w kalendarzu **GŁÓWNYM**
(`dariusz.tyszka@gmail.com`), bez znaczników `jdg_*`. App-native reconcile ich nie rozpozna i
przy pierwszym syncu założy kalendarz „JDG Podatki" + własne kopie → **duplikat za 05/2026**.
Przy aktywacji:
- [ ] usuń te 3 zdarzenia z kalendarza głównego (ID): `d32rjlev9br11p33d6h0gvvjvk` (Ryczałt),
      `10a19sojh5klt6lqvt9ovdanac` (ZUS), `1mddm3673n8oltf18dceou7fjg` (VAT)
- [ ] od tego momentu wszystkim zarządza app-native sync w kalendarzu „JDG Podatki"

### Alternatywa bez OAuth (jeśli OpenClaw ma własny konektor Google Calendar)
Zamiast app-native: cron OpenClaw odpala **prompt** „policz terminy (dashboard) i zsynchronizuj
przez MCP". Działa, gdy runtime OpenClaw ma podpięty Google Calendar MCP + dostęp do `data/`
(jest przez mount w docker-compose). Wtedy **nie trzeba** Google Cloud OAuth. Do zweryfikowania:
czy MCP jest dostępny w headless runtime OpenClaw (w sesji Claude Code — jest).

### Uwagi
- Kwota VAT w przypomnieniu jest **szacunkowa** (należny − naliczony za poprzedni miesiąc, dashboard);
  autorytatywna kwota pochodzi ze skilla `jpk`.
- Decyzje projektowe: app-native OAuth refresh token (nie service account); dedykowany kalendarz
  „JDG Podatki" (auto-tworzony, id w `data/gcal_state.json`); popup 3 dni przed + dzień przed.
- Dopóki automat nieaktywny: synchronizacja ręczna w sesji asystenta (hasło „zsynchronizuj kalendarz").
