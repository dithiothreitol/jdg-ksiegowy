---
name: faktury
description: Faktury sprzedazy JDG — wystawianie (DOCX + XML FA(3)), wysylka do KSeF, wysylka PDF mailem, zaplaty (oznaczanie, import wyciagu CSV), kontrakty cykliczne. Uzyj gdy user mowi "wystaw fakture", "faktura dla...", "wyslij do KSeF", "wyslij fakture mailem", "oznacz jako zaplacona", "kto mi nie zaplacil", "import wyciagu", "faktura co miesiac / kontrakt cykliczny".
---

# Faktury sprzedazy

Wszystko przez CLI `jdg` (gdy nie ma go w PATH: `uv run jdg` w katalogu repozytorium).
Bez terminala `jdg` zwraca JSON `{"ok": true, "data": ...}` albo `{"ok": false, "error": ...}`.
Kody wyjscia: 0 ok, 1 blad danych, 2 zle argumenty, 3 brak konfiguracji, 4 wymaga potwierdzenia,
5 blad uslugi zewnetrznej (`retryable: true` — mozna ponowic). Pelny opis: `jdg schema`.

## Wystawienie

```bash
jdg invoice issue --buyer-nip 5260250274 --net 10500 \
  --buyer-name "Firma ABC Sp. z o.o." --buyer-address "ul. Przykladowa 1, 00-001 Warszawa" \
  --description "Konsultacje AI — listopad 2026" --sale-date 2026-11-30
```

- Dla znanego kontrahenta wystarczy `--buyer-nip` i `--net` (nazwa, adres i opis z rejestru).
- Nowy kontrahent: zapytaj o nazwe, adres i opis — nie zgaduj. Kwoty podaje user, nie liczysz ich sam.
- `--sale-date` decyduje o miesiacu JPK (moment obowiazku VAT). Usluga z pazdziernika fakturowana
  w listopadzie → `--sale-date` w pazdzierniku.
- `--dry-run` pokazuje fakture bez zapisu. Pokaz userowi numer, brutto, termin i sciezki plikow.

`jdg invoice list [--year R --month M] [--unpaid]`, `jdg invoice show A1/11/2026`.

## Wysylka do KSeF i mailem — czynnosci nieodwracalne

`jdg ksef send <numer>` i `jdg invoice mail <numer> [--to adres]` dzialaja dwufazowo:

1. Pierwsze wywolanie nic nie wysyla. Zwraca kod 4 i `error.details`: `summary` (srodowisko,
   kwoty, adresat) oraz `token`.
2. **Pokaz userowi podsumowanie i zapytaj o zgode.** Szczegolnie wyraznie, gdy `env` = `prod`.
3. Dopiero po wyraznym "tak" uruchom to samo z `--confirm <token>`.

Nigdy nie dodawaj `--confirm` bez zgody usera i nie uzywaj tokena z innej rozmowy. Token wygasa
o polnocy i przestaje pasowac po zmianie pliku lub srodowiska — wtedy pokaz nowe podsumowanie.

Po wysylce do KSeF rejestr ma numer KSeF (trafia do JPK jako NrKSeF) i UPO w `data/upo/ksef/`.
Faktury raz wyslanej nie wysyla sie ponownie (`CONFLICT`) — bledy poprawia sie korekta.

## Zaplaty

- `jdg payment mark A1/11/2026 --paid-on 2026-11-20`
- `jdg payment import wyciag.csv` — podglad dopasowan (numer faktury w tytule, potem kwota i termin);
  `--auto-mark` oznacza dopasowane. Najpierw pokaz podglad.

## Kontrakty cykliczne

- `jdg contract add --buyer-name ... --buyer-nip ... --buyer-address ... --description ... --net 2000`
  (`--day-of-month -1` = ostatni dzien roboczy).
- `jdg contract run [--on RRRR-MM-DD]` wystawia faktury wymagalne danego dnia (idempotentnie).
  Wysylka do KSeF i mailem nadal wymaga potwierdzenia jak wyzej.

## Dane z .env

Sprzedawca: `SELLER_*`. KSeF: `KSEF_ENV` (test|demo|prod), `KSEF_TOKEN`. Mail: `SMTP_*`.
Kod 3 (`CONFIG_MISSING`) → powiedz userowi, co uzupelnic (pole `hint`); nie edytuj `.env` sam.
