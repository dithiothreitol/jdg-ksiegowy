# Polityka bezpieczeństwa

`jdg-ksiegowy` przetwarza dane wrażliwe: NIP-y, faktury, tokeny KSeF, dane
autoryzujące do bramki MF, dane SMTP. Bardzo poważnie podchodzimy do zgłoszeń
luk bezpieczeństwa.

## Wspierane wersje

Wspierana jest jedynie najnowsza wersja na `main`. Projekt jest pre-1.0 —
breaking changes są możliwe między wersjami minor.

## Zgłaszanie podatności

**Nie otwieraj publicznego issue.** Użyj jednej z poniższych ścieżek:

1. **GitHub Security Advisory** (preferowane):
   https://github.com/dithiothreitol/jdg-ksiegowy/security/advisories/new
2. **Email**: `dariusz.tyszka@gmail.com` z tematem zaczynającym się od
   `[SECURITY] jdg-ksiegowy`.

W zgłoszeniu zawrzyj:

- Opis luki i potencjalny wpływ (np. wyciek tokenu KSeF, podpisanie cudzej
  faktury, błędna kwota podatku w JPK).
- Kroki do odtworzenia / proof of concept.
- Wersję / commit hash.
- Twoje dane kontaktowe (do uznania w advisory, opcjonalnie).

## Czas odpowiedzi

- Potwierdzenie odbioru: do 72h.
- Wstępna ocena: do 7 dni.
- Fix lub plan działania: zależy od wagi (cel: critical < 14 dni).

## Co jest poza zakresem

- Brak HTTPS lokalnego dev serwera.
- Brak rate limitingu w skryptach CLI uruchamianych ręcznie.
- Słabość lokalnego `.env` jeśli host jest skompromitowany.
- Błędy w zewnętrznych zależnościach (zgłoś u nich; my zaktualizujemy).

## Zasady dla kontrybutorów

- Nigdy nie commituj `.env`, `data/`, `*.db`, `credentials.json`, `*.pem`,
  `*.key` — `.gitignore` to obsługuje, ale weryfikuj `git status` przed push.
- Nie wklejaj realnych NIP-ów / numerów faktur w testach — używaj fixture'ów.
- Sekrety w CI: tylko via GitHub Secrets, nigdy w `*.yml`.
