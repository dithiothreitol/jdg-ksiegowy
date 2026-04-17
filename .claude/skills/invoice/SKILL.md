---
name: invoice
description: Wystawia fakturę VAT dla JDG — generuje DOCX (do wysyłki/druku) i XML FA(3) (do KSeF), zapisuje do rejestru SQLite i zwraca numer faktury + ścieżki plików. Użyj gdy user prosi o "wystaw fakturę", "wygeneruj fakturę", "fakturę dla...", "faktura za usługę/konsultację/miesiąc".
---

# Wystawianie faktury VAT (JDG)

Generuje fakturę w dwóch formatach jednocześnie:
- `DOCX` — do wysyłki mailem lub druku
- `XML FA(3)` — wymagany format KSeF (obowiązkowy od 1.04.2026)

Zapisuje rekord do `data/registry.sqlite` i pliki do `data/faktury/YYYY/MM/`.

## Wymagane dane od usera

Zanim odpalisz skrypt, upewnij się że masz:
- **buyer-name** — nazwa nabywcy
- **buyer-nip** — NIP (10 cyfr)
- **netto** — kwota netto w PLN (Decimal — nie float!)

Opcjonalnie: `buyer-address`, `buyer-email`, `description`, `period` (`DD.MM.YYYY-DD.MM.YYYY`).

Jeśli czegoś brakuje — dopytaj usera, nie zgaduj.

## Wywołanie

```bash
python3 skills/invoice/scripts/generate.py \
  --buyer-name "Firma ABC Sp. z o.o." \
  --buyer-nip "1234567890" \
  --buyer-address "ul. Przykladowa 1, 00-001 Warszawa" \
  --description "Konsultacja w zakresie AI i automatyzacji" \
  --netto 10500 \
  --period "01.04.2026-30.04.2026"
```

Skrypt zwraca JSON na stdout:
```json
{
  "number": "A1/04/2026",
  "netto": "10500.00",
  "vat": "2415.00",
  "brutto": "12915.00",
  "docx_path": "data/faktury/2026/04/faktura_A1_04_2026.docx",
  "xml_path": "data/faktury/2026/04/faktura_A1_04_2026.xml",
  "payment_due": "2026-05-01",
  "status": "generated"
}
```

## Po wygenerowaniu

Pokaż userowi numer faktury, kwotę brutto, termin płatności i ścieżki plików (jako klikalne markdown linki).
Jeśli user chce od razu wysłać do KSeF — użyj skilla `ksef`, przekazując `xml_path` zwrócone tutaj.

## Zmienne środowiskowe (z .env)

Skrypt sam czyta dane sprzedawcy: `SELLER_NAME`, `SELLER_NIP`, `SELLER_ADDRESS`, `SELLER_BANK_ACCOUNT`, `SELLER_BANK_NAME`. Jeśli skrypt zwróci błąd o braku zmiennej — powiedz userowi że trzeba uzupełnić `.env`.
