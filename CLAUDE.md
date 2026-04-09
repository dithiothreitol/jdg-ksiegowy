# JDG Ksiegowy — OpenClaw AI Asystent Ksiegowy

## Projekt

AI Asystent Ksiegowy dla JDG (jednoosobowa dzialalnosc gospodarcza) w Polsce.
Oparty o **OpenClaw** + **Ollama** (lokalny model AI) z opcjonalnym fallbackiem na Claude API.
Automatyzuje: fakturowanie, KSeF, JPK_V7M, kalendarz podatkowy, powiadomienia.

## Architektura (hybrid: Ollama + Claude fallback)

```
OpenClaw Gateway
  |
  +-- SOUL.md              # Persona: asystent ksiegowy JDG
  +-- HEARTBEAT.md          # Checklist co 30 min (platnosci, terminy)
  +-- Cron Jobs              # Miesieczne: faktury, JPK, przypomnienia
  |
  +-- skills/                # AgentSkills (deterministyczna logika Python)
  |   +-- tax-calculator/    # VAT, ryczalt, ZUS (importuje z tax/zus.py)
  |   +-- invoice/           # DOCX + XML FA(3) + zapis do SQLite
  |   +-- ksef/              # Wyslka do KSeF via ksef2 SDK
  |   +-- jpk/               # JPK_V7M generator
  |
  +-- src/jdg_ksiegowy/      # Biblioteka Python (rdzen logiki)
  |   +-- config.py          # Pydantic Settings z .env
  |   +-- invoice/           # Modele, generator DOCX, generator XML
  |   +-- ksef/              # KSeF API client (ksef2)
  |   +-- tax/               # JPK, ZUS (single source of truth)
  |   +-- registry/          # SQLite rejestr faktur
  |
  +-- data/                  # SQLite DB + wygenerowane faktury/JPK
```

## Model AI

| Warstwa | Model | Koszt |
|---|---|---|
| Codzienna praca | **Ollama qwen3.5:9b** (lokalny) | 0 PLN |
| Fallback (opcjonalny) | Claude API pay-as-you-go | ~2 PLN/mies. |

**UWAGA:** Anthropic zablokowal subskrypcje Claude Pro/Max dla OpenClaw (4.04.2026).
Uzywaj TYLKO API key (pay-as-you-go) lub Ollama.

## Komendy

```bash
# Pelna instalacja (1 polecenie):
./setup.sh

# Reczny setup:
cp .env.example .env && nano .env    # Dane sprzedawcy
pip install -e .                      # Python deps
ollama pull qwen3.5:9b                # Model AI
openclaw onboard                      # Gateway + kanaly
docker compose up -d                  # Uruchom

# Test skills:
python3 skills/tax-calculator/scripts/calculate.py --netto 10500
python3 skills/invoice/scripts/generate.py --buyer-name "Firma" --buyer-nip 1234567890 --netto 10500
```

## Darmowy hosting

**Oracle Cloud Always Free** — 4 ARM OCPU, 24 GB RAM, 200 GB disk, 0 PLN na zawsze.
Wystarczy na OpenClaw + Ollama z qwen3.5:9b.

## Konwencje

- Python 3.12+, Decimal (nie float) dla kwot
- ZUS/podatki: single source of truth w `src/jdg_ksiegowy/tax/zus.py`
- Skill scripts importuja z `src/` via sys.path
- Dane sprzedawcy TYLKO z .env (zero hardkodu)
