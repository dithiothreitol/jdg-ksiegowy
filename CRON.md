# Cron Jobs — konfiguracja harmonogramu

Zarejestruj te cron joby w OpenClaw gateway po uruchomieniu:

```
# Przypomnienie: ryczalt + ZUS (3 dni przed terminem 20-go)
openclaw cron add "0 9 17 * *" "Oblicz i przypomnij o ryczalcie i ZUS zdrowotnej za poprzedni miesiac. Uzyj skill tax-calculator."

# Termin: ryczalt + ZUS (20-ty)
openclaw cron add "0 8 20 * *" "DZIS termin ryczaltu i ZUS zdrowotnej! Podaj kwoty i numer mikrorachunku."

# Generuj JPK_V7M + przypomnienie VAT (22-ty)
openclaw cron add "0 9 22 * *" "Wygeneruj JPK_V7M za poprzedni miesiac uzywajac skill jpk-generator. Przypomnij o terminie VAT za 3 dni."

# Termin: VAT JPK_V7M (25-ty)
openclaw cron add "0 8 25 * *" "DZIS termin VAT JPK_V7M! Podaj kwote VAT i przypomnij o wyslaniu przez e-Deklaracje."

# Generowanie faktur cyklicznych (28-go)
openclaw cron add "0 9 28 * *" "Sprawdz aktywne kontrakty i wygeneruj faktury za biezacy miesiac uzywajac skill invoice-generator. Wyslij do KSeF uzywajac skill ksef-submit."
```

Te komendy wystarczy wykonac raz — OpenClaw persystuje cron joby miedzy restartami.
