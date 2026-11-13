# Harmonogram

Zasada: **czynnosci deterministyczne uruchamia cron bezposrednio (`jdg`), agent AI tylko
powiadamia i rozmawia.** Wysylki nieodwracalne (KSeF, bramka MF, e-mail) nigdy nie startuja
z crona — wymagaja potwierdzenia czlowieka (`--confirm <token>`), wiec cron moze najwyzej
przygotowac podsumowanie.

## Zadania systemowe (crontab hosta lub kontenera)

```cron
# Faktury z kontraktow cyklicznych — wystawienie (bez wysylki), codziennie 07:00
0 7 * * *   cd /home/node/.openclaw/workspace && jdg contract run
# Terminy podatkowe w Google Calendar — codziennie 07:05
5 7 * * *   cd /home/node/.openclaw/workspace && jdg calendar sync
# Szyfrowany backup bazy i dokumentow — codziennie 02:30
30 2 * * *  cd /home/node/.openclaw/workspace && jdg backup
# Dokonczenie statusu wyslanych JPK (gdy MF przetwarzal dluzej) — co godzine
0 * * * *   cd /home/node/.openclaw/workspace && jdg jpk status
```

W kontenerze `jdg` jest w `PATH`, a `JDG_HOME` wskazuje workspace z `data/`.

## Powiadomienia przez agenta (OpenClaw)

Rejestrowane raz; OpenClaw przechowuje je miedzy restartami.

```bash
openclaw cron add "0 9 17 * *" "Uruchom \`jdg status\` i przypomnij o ryczalcie i ZUS (termin 20.) z kwotami."
openclaw cron add "0 9 22 * *" "Uruchom \`jdg jpk build\`, pokaz P_51 i zapytaj, czy wyslac JPK (skill vat-jpk)."
openclaw cron add "0 9 28 * *" "Uruchom \`jdg invoice list --unpaid\` i \`jdg status\`; zapytaj, czy wyslac do KSeF faktury bez numeru KSeF."
```

Agent wysyla cos dopiero po odpowiedzi "tak" od uzytkownika — skille opisuja protokol
dwufazowy (kod wyjscia 4 + token).
