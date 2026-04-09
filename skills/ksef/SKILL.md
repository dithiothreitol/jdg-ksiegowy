---
name: ksef-submit
description: Wyslka faktury XML FA(3) do Krajowego Systemu e-Faktur (KSeF)
metadata:
  openclaw:
    requires:
      bins:
        - python3
      env:
        - KSEF_TOKEN
    primaryEnv: KSEF_TOKEN
---

# Wyslka do KSeF

Wysyla wygenerowany XML FA(3) do KSeF API via ksef2 SDK.

## Uzycie

```bash
python3 scripts/submit.py --xml-path <sciezka_do_xml>
```

Zwraca JSON z numerem referencyjnym KSeF lub opisem bledu.

## Zmienne srodowiskowe

- `KSEF_ENV`: test | demo | prod (domyslnie: test)
- `KSEF_NIP`: NIP podatnika
- `KSEF_TOKEN`: token autoryzacyjny z portalu KSeF

## Przyklady

- "Wyslij fakture A1/04/2026 do KSeF"
- "Sprawdz status faktury w KSeF"
