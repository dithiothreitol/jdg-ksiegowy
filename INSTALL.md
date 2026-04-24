# Installation & Configuration Guide

Complete step-by-step guide to deploying JDG Ksiegowy on your own server.

---

## Table of Contents

1. [Requirements](#1-requirements)
2. [Server Setup](#2-server-setup)
3. [Install Ollama (local AI)](#3-install-ollama)
4. [Install OpenClaw](#4-install-openclaw)
5. [Install JDG Ksiegowy](#5-install-jdg-ksiegowy)
6. [Configure Business Data](#6-configure-business-data)
7. [Initialize Database](#7-initialize-database)
8. [Connect Messaging Channel](#8-connect-messaging-channel)
9. [Register Cron Jobs](#9-register-cron-jobs)
10. [Test Everything](#10-test-everything)
11. [KSeF: Test → Production](#11-ksef-test--production)
12. [Oracle Cloud Free Tier Setup](#12-oracle-cloud-free-tier)
13. [Backup & Maintenance](#13-backup--maintenance)
14. [Troubleshooting](#14-troubleshooting)

---

## 1. Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| OS | Ubuntu 22.04+ / Debian 12+ | Ubuntu 24.04 ARM |
| RAM | 2 GB (Claude API only) | **8+ GB** (Ollama) |
| Disk | 10 GB | 30 GB |
| CPU | 1 vCPU | 4 ARM cores |
| Python | 3.12+ | 3.12+ |
| Node.js | 18+ | 22 LTS |
| Docker | 24+ | Latest |

**If RAM < 4 GB:** Skip Ollama, use Claude API as primary model (~$0.50/month for 3 invoices).

---

## 2. Server Setup

### Option A: Existing VPS

```bash
ssh root@your-server-ip
apt update && apt upgrade -y
apt install -y python3 python3-pip python3-venv nodejs npm docker.io docker-compose-v2 git
systemctl enable docker && systemctl start docker
```

### Option B: Oracle Cloud Always Free (recommended)

See [Section 12](#12-oracle-cloud-free-tier) for the Oracle Cloud specific guide.

### Option C: Local machine (development)

Works on Linux, macOS, and WSL2 on Windows. Same commands apply.

---

## 3. Install Ollama

> Skip this section if you're using Claude API only (< 4 GB RAM).

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

Pull a model matching your host RAM. Qwen3.5 is the default — native multimodal, strong Polish, strong tool-use / structured JSON. Pick the largest your RAM allows:

```bash
# Recommended for desktop / 32 GB+ RAM workstations (best quality on this project)
# MoE 35B total / 3B active per token — quality of ~30B dense at speed of a 3B model
ollama pull qwen3.5:35b            # ~24 GB

# Mid-tier — 16-32 GB RAM hosts
ollama pull qwen3.5:27b            # ~17 GB, dense

# Baseline — small VPS / Oracle Cloud Free Tier (24 GB RAM shared with everything else)
ollama pull qwen3.5:9b             # ~6.6 GB

# Low-RAM fallback (< 8 GB)
# ollama pull qwen3.5:4b           # ~3.4 GB — noticeably weaker at tool calling

# Polish-native alternative (if Qwen3.5 output quality is not enough for free-form Polish)
# ollama pull bielik:11b           # ~8 GB
```

Then set the chosen tag in `.env`:

```env
OPENCLAW_MODEL=qwen3.5:35b         # whatever you pulled above
```

Verify:

```bash
ollama run qwen3.5:35b "Ile wynosi VAT 23% od kwoty 10000 PLN netto?"
# Expected: ~2300 PLN
```

> **Note on tag choice for this project:** on a ryczalt JDG, the agent rarely needs long-form generation — most of its work is tool calls (invoice/ksef/jpk skills) with a short natural-language wrapper. That means **tool-calling reliability matters more than raw eloquence**. Qwen3.5 dense variants and the `35b-a3b` MoE are all strong tool-callers. Going bigger than `35b` buys marginal improvement for this workload — skip `122b` unless you have 90+ GB RAM free.

---

## 4. Install OpenClaw

```bash
npm install -g openclaw@latest
```

Verify:

```bash
openclaw --version
```

---

## 5. Install JDG Ksiegowy

```bash
cd /root  # or your preferred directory
git clone https://github.com/YOUR_USER/jdg-ksiegowy.git
cd jdg-ksiegowy
pip install -e .
```

Verify Python library:

```bash
python3 -c "from jdg_ksiegowy.tax.zus import get_zus_tier; print(get_zus_tier(100000))"
# Expected: ZUSHealthTier(max_annual_revenue=Decimal('300000'), ..., monthly_contribution=Decimal('830.58'), ...)
```

---

## 6. Configure Business Data

```bash
cp .env.example .env
nano .env
```

### Required fields

```env
# === Your business data ===
SELLER_NAME=Acme Jan Kowalski          # Full company name
SELLER_NIP=1234567890                       # Tax identification number
SELLER_ADDRESS=ul. Przykladowa 1, 00-001 Warszawa
SELLER_BANK_ACCOUNT=00 0000 0000 0000 0000 0000 0000
SELLER_BANK_NAME=Bank Example
SELLER_EMAIL=kontakt@example.pl

# === Tax settings ===
SELLER_TAX_FORM=ryczalt                     # ryczalt | zasady_ogolne | liniowy
SELLER_RYCZALT_RATE=12                      # Flat tax rate (%)
SELLER_VAT_RATE=23                          # VAT rate (%)

# === Personal data (required for JPK_V7M) ===
SELLER_FIRST_NAME=Jan
SELLER_LAST_NAME=Kowalski
SELLER_BIRTH_DATE=1985-03-15               # YYYY-MM-DD format
SELLER_TAX_OFFICE_CODE=1471                # Your tax office code
```

### Finding your tax office code

Your tax office code (*kod urzedu skarbowego*) can be found at:
- Your last PIT declaration (field "Kod urzedu skarbowego")
- https://www.podatki.gov.pl/mikrorachunek-podatkowy/ (after entering NIP)
- Common codes: 1471 (Warszawa-Ursynow), 0271 (Bialystok), 1061 (Krakow-Krowodrza)

### KSeF configuration

```env
KSEF_ENV=test                               # Start with test!
KSEF_TOKEN=your-token-here                  # From ksef.mf.gov.pl portal
```

**How to get a KSeF token:**

1. Go to https://ksef-test.mf.gov.pl (test) or https://ksef.mf.gov.pl (production)
2. Log in with Trusted Profile (*Profil Zaufany*) or qualified signature
3. Navigate to *Tokeny autoryzacyjne* → *Generuj token*
4. Choose scope: *Wystawianie faktur* + *Odczyt faktur*
5. Copy the generated token to `KSEF_TOKEN` in `.env`

### AI model (optional — for Claude API fallback)

```env
ANTHROPIC_API_KEY=sk-ant-...                # Optional, pay-as-you-go only
```

> **Warning:** Do NOT use Claude Pro/Max subscription keys with OpenClaw. Anthropic blocked subscription access for third-party agents on April 4, 2026. Use API keys only.

---

## 7. Initialize Database

```bash
python3 -c "from jdg_ksiegowy.registry.db import init_db; init_db()"
```

This creates `data/jdg_ksiegowy.db` with tables for invoices, contracts, and tax payments.

Verify:

```bash
python3 -c "
from jdg_ksiegowy.registry.db import get_session, InvoiceRecord
with get_session() as s:
    print(f'Invoices: {s.query(InvoiceRecord).count()}')
"
# Expected: Invoices: 0
```

---

## 8. Connect Messaging Channel

Run the OpenClaw onboarding wizard:

```bash
openclaw onboard
```

The wizard will ask:

1. **AI Provider** → Choose `ollama`
2. **Model** → Type the tag you pulled in §3 (e.g. `qwen3.5:35b`)
3. **Channel** → Choose `whatsapp` or `telegram`

### If you skipped `openclaw onboard` (Docker-compose setup)

When running via `docker compose up`, onboarding isn't interactive — OpenClaw starts with its default agent model (`openai/gpt-5.4`) and ignores `OPENCLAW_PROVIDER` / `OPENCLAW_MODEL` env vars. You need to write the config explicitly once; a named Docker volume keeps it across recreates.

```bash
# 1. Tell OpenClaw which model to use as default
docker exec jdg-ksiegowy openclaw config set agents.defaults.model "ollama/qwen3.5:35b"

# 2. Register the Ollama provider pointing to the host (NOT localhost — localhost inside
#    the container is the container itself; use host.docker.internal on Docker Desktop
#    or the host's LAN IP on Linux without Docker Desktop)
docker exec jdg-ksiegowy sh -c 'cat > /tmp/ollama-provider.json << "EOF"
[
  {
    "path": "models.providers.ollama",
    "value": {
      "baseUrl": "http://host.docker.internal:11434",
      "models": [
        { "id": "qwen3.5:35b", "name": "Qwen3.5 35B (MoE A3B)", "api": "ollama", "input": ["text", "image"] },
        { "id": "pixtral:12b", "name": "Pixtral 12B", "api": "ollama", "input": ["text", "image"] }
      ]
    }
  }
]
EOF
openclaw config set --batch-file /tmp/ollama-provider.json'

# 3. Restart to apply
docker compose restart

# 4. Verify — this line should show ollama/qwen3.5:35b, not openai/gpt-5.4
docker logs jdg-ksiegowy 2>&1 | grep "agent model"
```

Config persists in the `openclaw-state` named volume (defined in [docker-compose.yml](../docker-compose.yml)), so you only need to do this once. `docker compose down && up -d` keeps the config; `docker volume rm openclaw-state` wipes it.

### WhatsApp setup

When prompted:
1. Open WhatsApp on your phone
2. Go to *Settings → Linked Devices → Link a Device*
3. Scan the QR code displayed in terminal

### Telegram setup

1. Message [@BotFather](https://t.me/BotFather) on Telegram
2. Send `/newbot`, follow instructions to create a bot
3. Copy the bot token
4. Paste into OpenClaw when prompted

### Verify connection

Send a message to your bot:

```
Hi
```

The agent should respond (using SOUL.md persona).

### Alternative: Web Dashboard (Control UI)

Besides WhatsApp/Telegram, you can talk to the agent through the built-in web UI served by the gateway on port `18789`. Useful for local development and when you don't want to link a messaging account.

**Get the tokenized URL:**

```bash
# If running via docker compose:
docker exec jdg-ksiegowy openclaw dashboard

# If running openclaw directly on host:
openclaw dashboard
```

Output looks like:

```
Dashboard URL: http://127.0.0.1:18789/#token=37b07683b26e7b...
```

Open that URL in your browser — the `#token=...` fragment auto-fills the Control UI auth form, so **Connect** works without manual paste.

**Reusing the same token after restart** — the default token is regenerated on each gateway start. To pin it (so you can bookmark the URL), set in `.env`:

```env
OPENCLAW_GATEWAY_TOKEN=your-long-random-secret
```

Then `docker compose restart`. The token you put here is the value after `#token=` in the URL.

**Accessing from another machine** — the gateway binds to localhost only. Tunnel over SSH:

```bash
ssh -N -L 18789:127.0.0.1:18789 user@your-server
# then open http://localhost:18789/#token=... on your laptop
```

---

## 9. Register Cron Jobs

```bash
# Tax reminders
openclaw cron add "0 9 17 * *" \
  "Oblicz i przypomnij o ryczalcie i ZUS za poprzedni miesiac. Uzyj skill tax-calculator."

openclaw cron add "0 8 20 * *" \
  "DZIS termin ryczaltu i ZUS! Podaj kwoty i mikrorachunek."

# JPK + VAT
openclaw cron add "0 9 22 * *" \
  "Wygeneruj JPK_V7M uzywajac skill jpk-generator. Przypomnij o VAT za 3 dni."

openclaw cron add "0 8 25 * *" \
  "DZIS termin VAT JPK_V7M! Podaj kwote i przypomnij o e-Deklaracje."

# Monthly invoices
openclaw cron add "0 9 28 * *" \
  "Wygeneruj faktury za miesiac uzywajac skill invoice-generator, wyslij do KSeF uzywajac skill ksef-submit."
```

Verify:

```bash
openclaw cron list
```

---

## 10. Test Everything

### Test 1: Tax calculation

Send via WhatsApp/Telegram:

```
Oblicz podatki od faktury 10500 netto
```

Expected: VAT 2415.00, brutto 12915.00, ryczalt 1260.00, ZUS 498.35 or 830.58

### Test 2: Invoice generation

```
Wystaw fakture dla Test Sp. z o.o., NIP 1234567890, 5000 netto za konsultacje
```

Expected: DOCX + XML generated in `data/faktury/`

### Test 3: KSeF submission (test environment)

```
Wyslij ostatnia fakture do KSeF
```

Expected: reference number from KSeF test environment

### Test 4: Manual skill execution

```bash
python3 skills/tax-calculator/scripts/calculate.py --netto 10500
python3 skills/invoice/scripts/generate.py \
  --buyer-name "Test Sp. z o.o." --buyer-nip "1234567890" --netto 5000
python3 skills/jpk/scripts/generate_jpk.py --month 4 --year 2026
```

---

## 11. KSeF: Test → Production

After successful tests:

1. Get a **production** KSeF token from https://ksef.mf.gov.pl
2. Update `.env`:

```env
KSEF_ENV=prod
KSEF_TOKEN=your-production-token
```

3. Restart OpenClaw:

```bash
openclaw restart
```

> **Important:** KSeF penalties start January 1, 2027. Until then, there's a grace period — no sanctions for errors. Use 2026 to test and refine your setup.

---

## 12. Oracle Cloud Free Tier

The recommended free hosting option. 4 ARM CPUs, 24 GB RAM, 200 GB disk — forever free.

### Step-by-step

1. **Create account** at https://www.oracle.com/cloud/free/
   - Credit card required for verification (never charged for Always Free resources)
   - Choose a home region close to you (e.g., Frankfurt for EU)

2. **Create a VM instance**
   - Shape: `VM.Standard.A1.Flex` (ARM)
   - OCPUs: 4, RAM: 24 GB
   - Image: Ubuntu 24.04
   - Add your SSH key

3. **Open firewall ports**
   - In OCI Console → Networking → Security Lists
   - Add ingress rule: TCP port 443 (HTTPS for webhooks)

4. **Connect and install**

```bash
ssh ubuntu@<your-oracle-cloud-ip>
sudo apt update && sudo apt install -y python3 python3-pip nodejs npm docker.io git
sudo usermod -aG docker ubuntu
# Log out and back in for Docker group

git clone https://github.com/YOUR_USER/jdg-ksiegowy.git
cd jdg-ksiegowy
./setup.sh
```

### Prevent idle reclamation

Oracle may reclaim instances with zero CPU usage for 7+ days. Since OpenClaw and cron jobs run periodically, this shouldn't happen. As extra safety:

```bash
# Add a minimal keepalive cron (system cron, not OpenClaw)
crontab -e
# Add: */30 * * * * uptime > /dev/null 2>&1
```

---

## 13. Backup & Maintenance

### Backup (run monthly or before updates)

```bash
cd /root/jdg-ksiegowy

# Database + all generated invoices/JPK files
tar czf ~/backup/jdg_$(date +%Y%m%d).tar.gz data/

# Or just the database
cp data/jdg_ksiegowy.db ~/backup/jdg_$(date +%Y%m%d).db
```

### Update

```bash
cd /root/jdg-ksiegowy
git pull
pip install -e .
openclaw restart
```

### Logs

```bash
openclaw logs          # OpenClaw gateway logs
openclaw cron list     # Scheduled jobs status
```

---

## 14. Troubleshooting

### "SELLER_NAME required" on startup

You haven't filled in `.env`. Run `nano .env` and set all required `SELLER_*` fields.

### "ksef2 not installed"

```bash
pip install ksef2
```

### "Ollama connection refused"

```bash
# Check if Ollama is running
systemctl status ollama

# Start it
systemctl start ollama

# Or run manually
ollama serve &
```

### "KSeF token expired"

KSeF tokens have an expiration date. Generate a new one at:
- Test: https://ksef-test.mf.gov.pl
- Production: https://ksef.mf.gov.pl

### OpenClaw doesn't see skills

Skills must be in the `skills/` directory of the OpenClaw workspace. Check:

```bash
openclaw skills list
```

If empty, ensure the workspace path is correct:

```bash
ls ~/.openclaw/workspace/skills/
```

### "ValueError: SELLER_FIRST_NAME required for JPK"

JPK_V7M generation requires personal data. Add to `.env`:

```env
SELLER_FIRST_NAME=Jan
SELLER_LAST_NAME=Kowalski
SELLER_BIRTH_DATE=1990-01-01
SELLER_TAX_OFFICE_CODE=1471
```

### WhatsApp QR code expired

```bash
openclaw channels login whatsapp
```

Scan the new QR code.

### Control UI: "unauthorized: gateway token missing"

You opened `http://127.0.0.1:18789/` without the `#token=...` fragment, so the UI has nothing to authenticate with. Fix:

```bash
docker exec jdg-ksiegowy openclaw dashboard
```

Open the full URL that command prints (it includes `#token=...`). If the token keeps changing on restart, pin it via `OPENCLAW_GATEWAY_TOKEN` in `.env` — see [Section 8 → Alternative: Web Dashboard](#alternative-web-dashboard-control-ui).

---

## Next Steps

After installation:

1. **Add your first contract** — tell the agent: *"Dodaj kontrakt: Firma XYZ, NIP 1234567890, 10500 netto miesiecznie za konsultacje AI"*
2. **Test invoice generation** — *"Wystaw fakture testowa"*
3. **Switch KSeF to production** when ready (see [Section 11](#11-ksef-test--production))
4. **Set up backup** — see [Section 13](#13-backup--maintenance)
