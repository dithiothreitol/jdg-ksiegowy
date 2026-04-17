---
name: ksef
description: Wysyła wygenerowaną fakturę XML FA(3) do Krajowego Systemu e-Faktur (KSeF) i zwraca numer referencyjny. Użyj gdy user prosi "wyślij do KSeF", "wyślij fakturę XYZ do KSeF", "submituj e-fakturę", "potwierdź w KSeF", lub gdy bezpośrednio po wystawieniu faktury user mówi "wyślij ją".
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

## Uwagi bezpieczeństwa

- **Nigdy nie loguj tokena** ani treści XML do user-facing output.
- Domyślne środowisko to `test` — to celowe. Nie zmieniaj na `prod` bez wyraźnej zgody usera.
