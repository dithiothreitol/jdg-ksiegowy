---
name: expense
description: Dodaje fakturę zakupu (koszt) do rejestru SQLite — zapisuje sprzedawcę, NIP, kwoty, kategorię, datę wpływu. Obsługuje wprowadzanie ręczne ORAZ OCR z pliku (PDF/JPG/PNG) przez lokalny Pixtral 12B z fallbackiem na Claude Haiku 4.5. Na ryczałcie koszty NIE pomniejszają podatku, ale VAT naliczony idzie do JPK_V7M jako odliczalny. Użyj gdy user mówi "dodaj fakturę zakupu", "zarejestruj koszt", "wprowadź wydatek", "kupiłem laptopa za...", "fakturę za hosting/SaaS/internet/paliwo", "dorzuć fakturę kosztową", "zeskanuj fakturę", "wczytaj PDF-a z fakturą", lub gdy user przesyła plik faktury.
---

# Dodawanie faktury zakupu (koszt)

Zapisuje koszt do tabeli `expenses` w SQLite. Używane potem przez skill `jpk` do wyliczenia VAT naliczonego do odliczenia.

## Wymagane dane od usera

- **seller-name** — nazwa sprzedawcy
- **seller-nip** — NIP sprzedawcy (10 cyfr; dla zagranicznego: też string, ustaw `--seller-country`)
- **document-number** — numer faktury (z faktury sprzedawcy)
- **issue-date** — data wystawienia (`YYYY-MM-DD`)
- **netto** — kwota netto
- **vat** — kwota VAT (jeśli sprzedawca zwolniony — wpisz `0`)

Opcjonalnie:
- `receive-date` — data wpływu (domyślnie = issue-date). To ona decyduje o miesiącu w JPK_V7M.
- `description` — co kupiłeś
- `category` — `uslugi_obce | materialy | media | paliwo | samochod | biuro | sprzet | szkolenia | inne`
- `vat-rate` — stawka (domyślnie `23`)
- `--no-vat-deductible` — flaga jeśli VAT NIE podlega odliczeniu (paliwo do auta osobowego, koszty reprezentacji)
- `file-path` — ścieżka do PDF/JPG zachowanego skanu

Dopytaj usera jeśli czegoś brakuje, zwłaszcza NIP i kwot. Nie wymyślaj.

## Wywołanie

```bash
python3 skills/expense/scripts/add.py \
  --seller-name "Hetzner Online GmbH" \
  --seller-nip "DE812871812" \
  --seller-country DE \
  --document-number "R0012345" \
  --issue-date "2026-04-15" \
  --description "Hosting VPS kwiecien 2026" \
  --category uslugi_obce \
  --netto 100 \
  --vat 23
```

Zwraca JSON z `id` rekordu, datami i statusem `saved`.

## OCR z pliku (PDF/JPG/PNG)

Zamiast przepisywać dane, user może podać plik faktury:

```bash
# Podglad (preview, bez zapisu):
python3 skills/expense/scripts/scan.py --file faktura.pdf

# Zapis od razu:
python3 skills/expense/scripts/scan.py --file faktura.pdf --save
```

**Flow:**
1. Bez `--save` skrypt zwraca JSON z wyciągniętymi polami + `source` (`ollama` | `claude`).
2. Pokaż userowi preview i spytaj o akceptację/poprawki.
3. Po akceptacji odpal ten sam skrypt z `--save` lub `skills/expense/scripts/add.py` z poprawionymi polami.

Backend domyślny: **Pixtral 12B** przez Ollama (`http://localhost:11434`). Przy błędzie/timeout → fallback na **Claude Haiku 4.5** (wymaga `ANTHROPIC_API_KEY`).
Konfiguracja przez `OCR_PROVIDER` (`auto` | `ollama` | `claude`) w `.env`.

## Listowanie

```bash
python3 skills/expense/scripts/list.py --month 4 --year 2026
```

## Po zapisaniu

Pokaż userowi: sprzedawca, numer dokumentu, kwoty, czy VAT odliczalny.
Jeśli `vat_deductible=true` — przypomnij że ten koszt zwiększy VAT do odliczenia w JPK_V7M za dany miesiąc.

## Uwagi

- **Ryczałt**: koszty nie zmniejszają podatku dochodowego. Jedyny powód rejestracji to (a) wymóg przechowywania dowodów (art. 15 ustawy o ryczałcie), (b) odliczenie VAT.
- **Zagraniczny sprzedawca** (kraj UE): wpisz NIP z prefiksem kraju (np. `DE812871812`), ustaw `--seller-country DE`. Standardowy reverse charge — VAT nadal idzie do K_42/K_43, ale skomplikuje się sprawozdawczo (poza zakresem tego skilla).
- **Rabat / korekta**: dodaj jako osobny wpis z ujemnymi kwotami i tym samym `document_number` z prefiksem `KOR-`.
