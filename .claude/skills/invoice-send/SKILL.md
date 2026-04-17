---
name: invoice-send
description: Konwertuje wygenerowaną fakturę DOCX na PDF (LibreOffice headless) i wysyła mailem do kontrahenta z treścią po polsku. Używa SMTP skonfigurowanego w `.env`. Użyj gdy user mówi "wyślij fakturę mailem", "wyślij PDF fakturę do X", "roześlij fakturę A1/04/2026", "wyślij ostatnią fakturę", "mail do klienta z fakturą".
---

# Wysyłka faktury mailem

Konwertuje DOCX fakturę na PDF (przez LibreOffice) i wysyła mailem z załącznikiem.

## Wymagane dane

- **--number** LUB **--latest** — która faktura (numer albo ostatnia)
- **--to** — email kontrahenta

Opcjonalnie: `--cc`, `--subject`, `--body`.

## Wymagane w .env

```
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587               # 465 dla SSL, 587 dla STARTTLS
SMTP_USERNAME=you@gmail.com
SMTP_PASSWORD=<app-password>  # Gmail wymaga App Password, nie glownego hasla
SMTP_FROM=                  # pusty = uzywa SMTP_USERNAME
SMTP_USE_SSL=false          # true dla portu 465
```

## Wymagania systemowe

- **LibreOffice** zainstalowany (`apt install libreoffice` / `brew install libreoffice`)
- Alternatywa: ustaw `LIBREOFFICE_BIN` w `.env` na ścieżkę do `soffice`

## Wywołanie

```bash
# Wyślij konkretną fakturę:
python3 skills/invoice-send/scripts/send.py \
  --number "A1/04/2026" \
  --to "kontrahent@example.com"

# Wyślij ostatnią fakturę z CC:
python3 skills/invoice-send/scripts/send.py \
  --latest \
  --to "kontrahent@example.com" \
  --cc "ksiegowosc@mojafirma.pl"
```

Zwraca JSON:
```json
{
  "success": true,
  "to": "kontrahent@example.com",
  "subject": "Faktura A1/04/2026",
  "pdf_path": "data/faktury/2026/04/faktura_A1_04_2026.pdf"
}
```

## Po wysłaniu

Pokaż userowi: adresata, subject, ścieżkę PDF-a.
Domyślny subject: `Faktura {numer}`, domyślna treść po polsku z kwotą brutto i terminem.

## Uwagi bezpieczeństwa

- **Nigdy nie loguj treści maila** ani hasła SMTP.
- Gmail blokuje "less secure apps" od 2022 → użyj **App Password** (panel Google → Bezpieczeństwo → Hasła do aplikacji).
- Dla Office 365: SMTP wymaga włączonego SMTP AUTH w Exchange (może być wyłączony dla nowych tenantów).
