# Checklist ksiegowy

Przy kazdym heartbeat uruchom `jdg status` (wynik JSON) i:

## Platnosci
- `overdue_invoices` niepuste → powiadom o fakturach po terminie (numer, kontrahent, kwota).

## Terminy podatkowe
- Przypomnienie z `level` = `urgent` lub `overdue` → powiadom z kwota i terminem.

## Faktury
- Faktury bez numeru KSeF (`jdg invoice list` → `ksef_number` puste, od 1.04.2026) → zapytaj,
  czy wyslac je do KSeF. Wysylka tylko po zgodzie (`jdg ksef send`, protokol z tokenem).

## Deklaracje
- `jdg jpk status` pokazuje `submitted` → MF jeszcze przetwarza; `rejected` → powiadom
  z polem `error`.

Nie wykonuj wysylek z heartbeat bez potwierdzenia uzytkownika.
