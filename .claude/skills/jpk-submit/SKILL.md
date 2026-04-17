---
name: jpk-submit
description: Wysyła wygenerowany plik JPK_V7M lub JPK_EWP do bramki Ministerstwa Finansów (REST API e-dokumenty.mf.gov.pl) z autoryzacją "danymi autoryzującymi" (bez podpisu kwalifikowanego). Zwraca numer referencyjny i UPO (Urzędowe Poświadczenie Odbioru). Użyj gdy user mówi "wyślij JPK do MF", "złóż deklarację VAT", "wyślij JPK_V7M", "wyślij ewidencję ryczałtu", "submituj JPK", lub bezpośrednio po wygenerowaniu pliku JPK.
---

# Wysyłka JPK do bramki MF

Pełny flow: szyfrowanie XML (AES-256-CBC + RSA klucz publiczny MF) → init upload → PUT na Azure Blob → finish → polling status → pobranie UPO.

## Wymagane dane

- **xml-path** — ścieżka do pliku JPK (zwykle z `data/jpk/JPK_V7M_*.xml` lub `data/jpk/JPK_EWP_*.xml`)

W `.env` muszą być:
- `MF_PESEL` — PESEL podatnika
- `MF_PRIOR_INCOME` — kwota przychodu z PIT za rok N-2 (dla wysyłki w 2026 → PIT za 2024). Pozycje zgodnie z formularzem PIT-37/28/36/36L. Brak zeznania → `0`.
- `MF_CERT_PATH` — ścieżka do klucza publicznego MF (PEM/DER) — pobierz z [podatki.gov.pl, sekcja klucze publiczne](https://www.podatki.gov.pl/jednolity-plik-kontrolny/jpk-vat-z-deklaracja/pliki-do-pobrania/)
- `MF_ENV=test` (domyślnie) lub `prod`
- `SELLER_FIRST_NAME`, `SELLER_LAST_NAME`, `SELLER_BIRTH_DATE`, `SELLER_NIP`

## Wywołanie — DRY-RUN (zalecane przed pierwszą wysyłką)

```bash
python3 skills/jpk-submit/scripts/submit.py --xml-path data/jpk/JPK_V7M_2026_04.xml --dry-run
```

Pokazuje co byłoby wysłane (rozmiar, env, fingerprint danych autoryzujących) bez dotykania bramki.

## Wywołanie — wysyłka

```bash
python3 skills/jpk-submit/scripts/submit.py --xml-path data/jpk/JPK_V7M_2026_04.xml
```

Zwraca JSON:
```json
{
  "success": true,
  "reference_number": "20260417-...",
  "status_code": 200,
  "upo_path": "data/upo/UPO_20260417-...bin",
  "mf_env": "test"
}
```

Polling statusu trwa do 10 minut (interwał 15s). Status 200 = sukces + UPO; 401-420 = błędy MF (zła XSD, certyfikat, autoryzacja).

## ⚠️ KRYTYCZNE — przed wysyłką na PROD

1. **Najpierw przetestuj na bramce TEST** (`MF_ENV=test`). Bramka prod = `e-dokumenty.mf.gov.pl`, test = `test-e-dokumenty.mf.gov.pl`.
2. **Zweryfikuj kwotę przychodu z PIT za rok N-2** — błąd → odrzucenie autoryzacji. Konkretne pozycje: PIT-37 poz. 50/83, PIT-28 poz. 20/22/24/62/73, PIT-36 poz. 67-75/131, PIT-36L poz. 23/25/27/28/33. Brak zeznania = 0. Nie wolno sumować z różnych zeznań.
3. **Sprawdź certyfikat MF** — aktualizowany okresowo (ostatnio 18.07.2025). Nieaktualny → init zwróci błąd `404`.
4. **Zachowaj UPO** — `data/upo/UPO_*.bin` to dowód złożenia. Bez UPO uznaje się że JPK nie został złożony.
5. **Termin** — JPK_V7M do 25-go następnego miesiąca; JPK_EWP do 30.04 następnego roku.

## Po sukcesie

Pokaż userowi: `reference_number`, `mf_env`, ścieżkę UPO (jako klikalny link).
Jeśli `mf_env=test` — wyraźnie zaznacz że to **wysyłka TESTOWA, nie produkcyjna**.

## Implementacja MVP — disclaimer

Klient został napisany od zera (brak oficjalnego SDK MF dla Pythona). Jeśli MF zmieni format `InitUploadSigned` (do potwierdzenia: nazwa endpointu dla danych autoryzujących vs. podpis kwalifikowany) — wymaga to aktualizacji [src/jdg_ksiegowy/mf_gateway/client.py](src/jdg_ksiegowy/mf_gateway/client.py).
