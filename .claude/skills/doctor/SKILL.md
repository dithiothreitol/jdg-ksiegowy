---
name: doctor
description: Preflight-check konfiguracji JDG przed wysyłką faktur / JPK do sandboxów. Sprawdza dane sprzedawcy, KSeF, bramkę MF, SMTP, OCR. Użyj gdy user pyta "czy wszystko skonfigurowane", "diagnostyka", "preflight", "co mam brak", "czy działa konfiguracja", "audyt setupu".
---

# Doctor — sprawdzanie konfiguracji

Waliduje `.env` i obecność plików (certyfikaty, klucze) przed wysyłką do KSeF/MF. Nie dotyka sieci.

## Wywołanie

```bash
# Raport tekstowy
python3 skills/doctor/scripts/check.py

# Format JSON
python3 skills/doctor/scripts/check.py --format json

# Exit code != 0 gdy są błędy (do CI)
python3 skills/doctor/scripts/check.py --fail-on-error
```

## Co sprawdza

**[SELLER]** — dane sprzedawcy z `.env`:
- `SELLER_NIP` (z walidacją sumy kontrolnej)
- `SELLER_NAME`, `SELLER_ADDRESS`, `SELLER_BANK_ACCOUNT/NAME`
- `SELLER_EMAIL`, `SELLER_FIRST_NAME/LAST_NAME`, `SELLER_BIRTH_DATE`, `SELLER_TAX_OFFICE_CODE` (dla JPK)

**[KSEF]**:
- `KSEF_ENV` (test/demo/prod), pochodny URL API
- `KSEF_NIP` + `KSEF_TOKEN`

**[MF]** (bramka JPK):
- `MF_ENV` (test/prod), pochodny URL
- `MF_PESEL` (z walidacją), `MF_CERT_PATH`/`MF_CERT_URL`

**[SMTP]** — wysyłka email (opcjonalne):
- `SMTP_HOST`, `SMTP_USERNAME`, `SMTP_PASSWORD`

**[OCR]** — provider i klucze:
- `OCR_PROVIDER` (auto/ollama/claude), `ANTHROPIC_API_KEY` jeśli claude

## Poziomy

- **OK** — obszar gotowy
- **WARN** — brak nieblokujący (np. SMTP) — część funkcjonalności niedostępna
- **ERROR** — krytyczny — wysyłka zadziała dopiero po naprawie

## Flow po doctor

Jeśli wszystko OK → możesz ruszać z wysyłkami:
```bash
# Dry-run na sandboxie KSeF
python3 skills/ksef/scripts/submit.py --dry-run --invoice-file faktury/A1.xml

# Dry-run JPK (sandbox MF)
python3 skills/jpk-submit/scripts/submit.py --dry-run data/jpk/JPK_V7M_04_2026.xml
```
