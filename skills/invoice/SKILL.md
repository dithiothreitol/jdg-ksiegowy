---
name: invoice-generator
description: Generowanie faktur VAT — DOCX do wyslki/druku + XML FA(3) dla KSeF
metadata:
  openclaw:
    requires:
      bins:
        - python3
      env:
        - SELLER_NAME
        - SELLER_NIP
        - SELLER_ADDRESS
        - SELLER_BANK_ACCOUNT
        - SELLER_BANK_NAME
---

# Generator faktur VAT

Generuje fakture w dwoch formatach:
- **DOCX** — do wyslki emailem lub druku
- **XML FA(3)** — do wyslki do KSeF (obowiazkowy od 1.04.2026)

## Uzycie

```bash
python3 scripts/generate.py \
  --buyer-name "Firma ABC Sp. z o.o." \
  --buyer-nip "1234567890" \
  --buyer-address "ul. Przykladowa 1, 00-001 Warszawa" \
  --description "Konsultacja w zakresie AI i automatyzacji" \
  --netto 10500 \
  --period "01.04.2026-30.04.2026"
```

Tworzy pliki w `data/faktury/YYYY/MM/` i zwraca JSON z numerem faktury, kwotami i sciezkami.

## Przyklady

- "Wystaw fakture dla Firma XYZ, NIP 1234567890, kwota 10500 netto za konsultacje AI"
- "Wygeneruj fakture za kwiecien dla stalego klienta"
