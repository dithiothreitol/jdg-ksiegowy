---
name: contracts
description: Cykliczne kontrakty JDG — automatyczne wystawianie faktur miesięcznych, oznaczanie płatności, import CSV z banku. Użyj gdy user pyta "faktury automatyczne", "kontrakt cykliczny", "auto-fakturowanie", "subskrypcja klienta", "powtarzające się faktury", "oznacz jako zapłacone", "import wyciągu", "CSV bank", "które faktury nie zostały zapłacone".
---

# Cykliczne kontrakty + śledzenie płatności

## 1. Auto-fakturowanie

```bash
# Uruchom na dziś (z crona lub ręcznie)
python3 skills/contracts/scripts/run_contracts.py

# Symulacja na konkretny dzień
python3 skills/contracts/scripts/run_contracts.py --date 2026-04-30
```

## 2. Oznacz fakturę jako zapłaconą

```bash
python3 skills/contracts/scripts/mark_paid.py "A1/04/2026"
python3 skills/contracts/scripts/mark_paid.py "A1/04/2026" --date 2026-04-25
```

## 3. Import CSV z banku

```bash
# Podgląd dopasowań (bez zapisu)
python3 skills/contracts/scripts/import_bank_csv.py wyciag_kwiecien.csv

# Automatyczne oznaczenie zapłaconych po dopasowaniu
python3 skills/contracts/scripts/import_bank_csv.py wyciag_kwiecien.csv --auto-mark
```

Obsługiwane formaty CSV:
- **mBank**: nagłówek `#Data operacji;Opis operacji;...;Kwota;Waluta`
- **Generyczny**: `date/data, amount/kwota, description/opis`

## 4. Dodawanie kontraktu (Python API)

```python
from jdg_ksiegowy.registry.db import ContractRecord, save_contract, init_db
import uuid

init_db()
save_contract(ContractRecord(
    id=str(uuid.uuid4()),
    buyer_name="Firma XYZ",
    buyer_nip="5260250274",
    buyer_address="ul. Przykładowa 1, 00-001 Warszawa",
    buyer_email="kontakt@firma.pl",
    description="Obsługa IT — miesięczna",
    net_amount=2000,
    vat_rate=23,
    cycle="monthly",
    day_of_month=-1,   # -1 = ostatni dzień roboczy
))
```

## Parametry kontraktu

| Pole | Opis |
|------|------|
| `cycle` | `monthly` (jedyne obsługiwane) |
| `day_of_month` | `-1` = ostatni dzień roboczy, `1-28` = konkretny dzień |
| `auto_send_ksef` | Oznaczenie (wysyłkę KSeF wywołujesz osobno skill `ksef`) |
| `auto_send_email` | Oznaczenie (email wysyłasz osobno skill `invoice-send`) |

## Cron (codziennie rano)

```bash
0 7 * * * cd /opt/jdg && python3 skills/contracts/scripts/run_contracts.py >> logs/contracts.log 2>&1
```
