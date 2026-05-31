---
name: ksef
description: Integracja z KSeF (Krajowy System e-Faktur) — WYSYŁKA faktur sprzedaży XML FA(3) ORAZ ODPYTANIE inboxu faktur zakupowych (rola nabywcy) z zapisem kosztów. Użyj do wysyłki gdy user prosi "wyślij do KSeF", "submituj e-fakturę", "potwierdź w KSeF". Użyj do odpytania inboxu gdy user mówi "sprawdź KSeF", "co przyszło na KSeF", "faktury przychodzące/zakupowe z KSeF", "pobierz koszty z KSeF", "zsynchronizuj zakupy z KSeF", lub gdy ma paragon/potwierdzenie transakcji (np. Shell) i właściwa faktura jest w KSeF.
---

# Wysyłka faktury do KSeF

Wysyła plik XML FA(3) do KSeF API (środowiska: `test` / `demo` / `prod`) przez SDK `ksef2`.
Zwraca numer referencyjny KSeF lub opis błędu.

## Wymagane dane

- **xml-path** — pełna ścieżka do pliku XML FA(3) (zwykle `data/faktury/YYYY/MM/faktura_*.xml`)

Jeśli user mówi "wyślij fakturę A1/04/2026" ale nie podaje ścieżki — znajdź w `data/faktury/` po numerze, nie wymyślaj ścieżki.

## Wywołanie

```bash
python3 skills/ksef/scripts/submit.py --xml-path data/faktury/2026/04/faktura_A1_04_2026.xml
```

Zwraca JSON:
```json
{
  "success": true,
  "reference_number": "20260417-...",
  "error": null,
  "env": "test"
}
```

## Zmienne środowiskowe (z .env)

- `KSEF_TOKEN` — token autoryzacyjny z portalu KSeF (**wymagane**)
- `KSEF_NIP` — NIP podatnika
- `KSEF_ENV` — `test` | `demo` | `prod` (domyślnie `test`)

Jeśli skrypt zwróci `"KSeF nie skonfigurowany"` — przerwij i poinstruuj usera żeby ustawił `KSEF_TOKEN` w `.env`.

## Po wysyłce

- Sukces: pokaż `reference_number` i środowisko (`env`). Jeśli `env=test`, zaznacz wyraźnie że to wysyłka testowa, nie produkcyjna.
- Błąd: pokaż `error` dosłownie i zasugeruj sprawdzenie tokena / poprawności XML.

## Odpytanie inboxu (faktury zakupowe → koszty)

Pobiera metadane faktur, w których podatnik jest **nabywcą** (rola `buyer`), i opcjonalnie
zapisuje je jako koszty w rejestrze SQLite. Użyteczne gdy user ma paragon/„potwierdzenie
transakcji" (Shell, Orlen…) — właściwa faktura VAT jest w KSeF, więc zamiast OCR-ować
paragon pobieramy autorytatywne dane wprost z systemu.

```bash
# Preview (NIC nie zapisuje) — pokaż co jest w KSeF za maj 2026:
python3 skills/ksef/scripts/inbox.py --month 5 --year 2026

# Zapis nowych faktur do rejestru (pobiera też XML jako dowód):
python3 skills/ksef/scripts/inbox.py --month 5 --year 2026 --save
```

Każda faktura w odpowiedzi ma `status`:
- `new` — jest w KSeF, jeszcze nie w rejestrze (zapisze się przy `--save`),
- `exists` — już w rejestrze (pomijana, idempotentnie),
- `manual` — korekta / waluta obca / samofakturowanie → **nie zapisuj automatycznie**,
  pokaż `manual_reason` i obsłuż ręcznie (skill `expense`),
- `saved` — właśnie zapisana (tylko przy `--save`).

**Tryb pracy:** najpierw uruchom BEZ `--save` i pokaż user listę. Dla kategorii
`paliwo`/`samochod` skill `inbox.py` ustawia domyślnie 100% odliczenia VAT i dopisuje
podpowiedź w `notes`. **Zapytaj usera o tryb auta** zanim dodasz `--save`:
- auto osobowe użytkowane mieszanie / prywatne służbowo → `--vat-deduction-pct 50`,
- pełne odliczenie (VAT-26, auto wyłącznie firmowe) → `100` (default),
- brak odliczenia → `0`.

Daty: domyślnie bieżący miesiąc; alternatywnie `--date-from`/`--date-to` (dowolny zakres —
klient sam dzieli na okna ≤2 mies.). Korekty domyślnie pomijane; `--include-corrections` je pokazuje.

## Uwagi bezpieczeństwa

- **Nigdy nie loguj tokena** ani treści XML do user-facing output.
- Domyślne środowisko to `test` — to celowe. Nie zmieniaj na `prod` bez wyraźnej zgody usera.
- Odpytanie inboxu na `prod` czyta **realne** faktury zakupowe podatnika — traktuj dane jak wrażliwe.
