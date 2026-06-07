---
name: calendar-sync
description: Synchronizuje terminy podatkowe JDG (ryczałt, ZUS, VAT+JPK) i przypomnienia o fakturach — z kwotami — do dedykowanego kalendarza Google "JDG Podatki". Idempotentne (tworzy/aktualizuje/usuwa). Użyj gdy user mówi "synchronizuj kalendarz", "dodaj terminy do kalendarza", "wrzuć podatki do Google Calendar", "przypomnienia w kalendarzu", "kalendarz podatkowy", lub gdy pyta czemu nie widzi terminów/kwot w kalendarzu.
---

# Synchronizacja terminów podatkowych z Google Calendar

Czyta przypomnienia z dashboardu (`status/dashboard.py` — terminy podatkowe + niezapłacone/zaległe
faktury, z kwotami) i uzgadnia je z kalendarzem **„JDG Podatki"** przez Google Calendar API.
Wydarzenia całodniowe na termin płatności, z popupami N dni przed i w dniu.

## Wymagana konfiguracja (jednorazowo)

1. Google Cloud Console → utwórz **OAuth client ID** typu „Desktop app", pobierz `credentials.json`.
2. W `.env`: `GCAL_ENABLED=true`, `GCAL_CREDENTIALS_PATH=/sciezka/credentials.json`.
3. `python -m jdg_ksiegowy.calendar.auth_setup` — jednorazowa zgoda w przeglądarce (zapisuje refresh token).

Jeśli skrypt zwróci błąd „nie skonfigurowany" / „Brak tokenu" — przerwij i poprowadź usera przez powyższe kroki.

## Wywołanie

```bash
# Podglad (NIC nie zapisuje) — pokaz co by sie zmienilo:
python3 skills/calendar-sync/scripts/sync.py --dry-run

# Synchronizacja:
python3 skills/calendar-sync/scripts/sync.py
```

Zwraca JSON: `created` / `updated` / `deleted` / `unchanged` (listy kluczy wydarzeń) + `dry_run`.

## Zachowanie

- **Idempotentne**: ponowne uruchomienie bez zmian → wszystko w `unchanged`.
- **Kwoty się aktualizują**: zmiana szacowanej kwoty (np. po dodaniu faktury/kosztu) → `updated`.
- **Zapłacone faktury znikają**: po oznaczeniu faktury jako zapłaconej jej przypomnienie wypada z
  dashboardu → wydarzenie zostaje **usunięte** z kalendarza.
- Dotyka **wyłącznie** wydarzeń utworzonych przez aplikację (oznaczonych `jdg_managed`) — nigdy nie
  rusza prywatnych wpisów usera.

## Automatyzacja

Cron OpenClaw odpala to codziennie (patrz `CRON.md`): `0 7 * * *`. Dzięki temu kwoty są świeże,
a zapłacone faktury automatycznie znikają.

## Uwagi

- Kwota VAT+JPK jest **szacunkowa** (należny − naliczony za poprzedni miesiąc); autorytatywna kwota
  pochodzi ze skilla `jpk`.
- Nigdy nie loguj tokenu OAuth do outputu.
