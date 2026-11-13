---
name: faktury
description: Faktury sprzedazy JDG — wystawianie (XML FA(3) + DOCX), faktury wielopozycyjne i dla UE, korekty, sprawdzenie kontrahenta na Bialej liscie MF, wysylka do KSeF, wysylka PDF mailem, zaplaty (oznaczanie, import wyciagu CSV), kontrakty cykliczne. Uzyj gdy user mowi "wystaw fakture", "faktura dla...", "faktura korygujaca / korekta faktury / rabat", "sprawdz kontrahenta / NIP", "wyslij do KSeF", "wyslij fakture mailem", "oznacz jako zaplacona", "kto mi nie zaplacil", "import wyciagu", "faktura co miesiac / kontrakt cykliczny".
---

# Faktury sprzedazy

Narzedzia: serwer MCP `jdg`, gdy jest dostepny — kazda komenda z tego opisu to narzedzie
o nazwie z podkreslnikami (`jdg invoice issue` → `invoice_issue`, `--buyer-nip` → `buyer_nip`).
Bez MCP: CLI `jdg` (gdy nie ma go w PATH: `uv run jdg` w katalogu repozytorium).
Wynik zawsze w kopercie `{"ok": true, "data": ...}` albo `{"ok": false, "error": {"code": ...}}`.
Kody bledow: `INVALID_INPUT`/`INVALID_ARGUMENTS` (popraw dane), `NOT_FOUND`, `CONFLICT`,
`CONFIG_MISSING` (brak konfiguracji), `CONFIRMATION_REQUIRED` (wymaga zgody usera),
`EXTERNAL_SERVICE` (`retryable: true` — mozna ponowic). Pelny opis: `jdg schema`.

## Wystawienie

```bash
jdg invoice issue --buyer-nip 5260250274 --net 10500 \
  --buyer-name "Firma ABC Sp. z o.o." --buyer-address "ul. Przykladowa 1, 00-001 Warszawa" \
  --description "Konsultacje AI — listopad 2026" --sale-date 2026-11-30
```

- Znany kontrahent: wystarczy `--buyer-nip` i `--net` (nazwa, adres, opis z rejestru).
- Nowy kontrahent bez `--buyer-name`: dane pobierane sa z Bialej listy MF. Pokaz je userowi do
  potwierdzenia; opis uslugi i kwoty zawsze od usera — nie zgaduj i nie licz sam.
- `--sale-date` decyduje o miesiacu JPK (obowiazek VAT). Usluga z pazdziernika fakturowana
  w listopadzie → `--sale-date` w pazdzierniku. Usluga ciagla: `--period-from/--period-to`.
- `--dry-run` pokazuje fakture bez zapisu. Pokaz numer, brutto, termin, sciezki plikow
  i kazde ostrzezenie z `warnings` (np. nabywca nie jest czynnym podatnikiem VAT).

### Wiele pozycji, inne stawki, GTU

Zamiast `--net` powtarzalne `--item 'opis;ilosc;jm;cena netto;stawka[;GTU_xx]'`:

```bash
jdg invoice issue --buyer-nip 5260250274 \
  --item 'Wdrozenie;1;usl.;8000;23' --item 'Szkolenie;2;h;250;23;GTU_12'
```

Stawka: `23`, `8`, `5`, `0` albo kod: `zw` (zwolnione), `np` (poza terytorium — usluga dla firmy
z UE/spoza UE), `0_wdt`, `0_exp`. GTU tylko gdy user wie, ze dotyczy (np. GTU_12 doradztwo).

### Nabywca z UE

```bash
jdg invoice issue --buyer-country DE --buyer-eu-vat DE811569869 \
  --buyer-name "Kunde GmbH" --buyer-address "Hauptstr. 1, Berlin" \
  --item 'Software development;1;usl.;5000;np'
```

Usluga B2B dla firmy z UE = `np` (odwrotne obciazenie; w JPK K_11/K_12). Nie wpisuj polskiego NIP.

## Sprawdzenie kontrahenta

`jdg buyer lookup 5260250274` — status VAT (Czynny/Zwolniony/Niezarejestrowany), nazwa, adres,
rachunki z Bialej listy MF. Przy platnosci > 15 000 zl brutto rachunek nabywcy/dostawcy powinien
byc na liscie — zwroc na to uwage.

## Korekta faktury

Bledow w wyslanej fakturze nie poprawia sie edycja — wystawia sie korekte z pozycjami roznicowymi
(ujemna cena = zmniejszenie):

```bash
jdg invoice correct A1/11/2026 --item 'Rabat;1;usl.;-500;23' --reason "Rabat posprzedazowy"
```

Korekta dostaje numer `KOR...`, odwoluje sie do numeru KSeF oryginalu i sama trafia do KSeF
(`jdg ksef send KOR1/11/2026`). Zmniejszenie wchodzi do JPK w miesiacu korekty, zwiekszenie
w miesiacu pierwotnej sprzedazy. Przed korekta upewnij sie, ze oryginal ma numer KSeF.

## Wysylka do KSeF i mailem — czynnosci nieodwracalne

`jdg ksef send <numer>` i `jdg invoice mail <numer> [--to adres]` dzialaja dwufazowo:

1. Pierwsze wywolanie nic nie wysyla. Zwraca `CONFIRMATION_REQUIRED` (CLI: kod 4) i
   `error.details`: `summary` (srodowisko, kwoty, adresat) oraz `token`.
2. **Pokaz userowi podsumowanie i zapytaj o zgode.** Szczegolnie wyraznie, gdy `env` = `prod`.
3. Dopiero po wyraznym "tak" wywolaj to samo z `--confirm <token>` (MCP: `confirm`).

Nigdy nie dodawaj `--confirm` bez zgody usera i nie uzywaj tokena z innej rozmowy. Zgoda "z gory"
("wysylaj bez pytania") nie wystarcza: user musi zobaczyc to konkretne podsumowanie, wiec po
pierwszym wywolaniu zawsze konczysz odpowiedz pytaniem. Token wygasa
o polnocy i przestaje pasowac po zmianie pliku lub srodowiska — wtedy pokaz nowe podsumowanie.

Kolejnosc: najpierw KSeF, potem mail. Po wysylce do KSeF rejestr ma numer KSeF (do JPK jako
NrKSeF), UPO w `data/upo/ksef/`, a DOCX/PDF dostaje numer KSeF i kod QR weryfikacji. Faktury
z numerem KSeF nie wysyla sie ponownie (`CONFLICT`). Mail faktury bez numeru KSeF (wystawionej
od 1.04.2026) jest blokowany — najpierw `jdg ksef send`.

## Zaplaty

- `jdg payment mark A1/11/2026 --paid-on 2026-11-20`
- `jdg payment import wyciag.csv` — podglad dopasowan (numer faktury w tytule, potem kwota i termin);
  `--auto-mark` oznacza dopasowane. Najpierw pokaz podglad.
- `jdg invoice list [--year R --month M] [--unpaid]` — rejestr; `jdg invoice show A1/11/2026` —
  szczegoly z numerem KSeF i sciezkami plikow; `jdg status` pokazuje faktury po terminie.

## Kontrakty cykliczne

- `jdg contract add --buyer-name ... --buyer-nip ... --buyer-address ... --description ... --net 2000`
  (`--day-of-month -1` = ostatni dzien roboczy).
- `jdg contract list` — aktywne kontrakty.
- `jdg contract run [--on RRRR-MM-DD]` wystawia faktury wymagalne danego dnia (idempotentnie).
  Wysylka do KSeF i mailem nadal wymaga potwierdzenia jak wyzej.

## Dane z .env

Sprzedawca: `SELLER_*`. KSeF: `KSEF_ENV` (test|demo|prod), `KSEF_TOKEN`. Mail: `SMTP_*`.
Kod 3 (`CONFIG_MISSING`) → powiedz userowi, co uzupelnic (pole `hint`); nie edytuj `.env` sam.
