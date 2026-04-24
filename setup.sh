#!/bin/bash
set -e

echo ""
echo "  ╔══════════════════════════════════════╗"
echo "  ║       JDG Ksiegowy — Setup           ║"
echo "  ║  AI Accounting Assistant for Polish   ║"
echo "  ║  Sole Proprietorships                 ║"
echo "  ╚══════════════════════════════════════╝"
echo ""

# --- Colors ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

ok()   { echo -e "  ${GREEN}[OK]${NC} $1"; }
warn() { echo -e "  ${YELLOW}[!]${NC} $1"; }
fail() { echo -e "  ${RED}[FAIL]${NC} $1"; exit 1; }

# --- 1. Check requirements ---
echo "Step 1/7: Checking requirements..."

command -v python3 >/dev/null 2>&1 || fail "python3 not found. Install: apt install python3 python3-pip"
ok "Python $(python3 --version 2>&1 | awk '{print $2}')"

command -v npm >/dev/null 2>&1 || fail "npm not found. Install: apt install nodejs npm"
ok "Node.js $(node --version 2>&1)"

# --- 2. Detect RAM and choose AI strategy ---
echo ""
echo "Step 2/7: Detecting hardware..."

TOTAL_RAM_MB=$(free -m 2>/dev/null | awk '/Mem:/ {print $2}' || echo "0")

if [ "$TOTAL_RAM_MB" -ge 32000 ]; then
    AI_STRATEGY="ollama"
    OLLAMA_TAG="qwen3.5:35b"
    OLLAMA_SIZE="24 GB"
    ok "RAM: ${TOTAL_RAM_MB} MB — Ollama with qwen3.5:35b (MoE 35B-A3B)"
elif [ "$TOTAL_RAM_MB" -ge 8000 ]; then
    AI_STRATEGY="ollama"
    OLLAMA_TAG="qwen3.5:9b"
    OLLAMA_SIZE="6.6 GB"
    ok "RAM: ${TOTAL_RAM_MB} MB — Ollama with qwen3.5:9b (baseline)"
elif [ "$TOTAL_RAM_MB" -ge 2000 ]; then
    AI_STRATEGY="api"
    warn "RAM: ${TOTAL_RAM_MB} MB — not enough for Ollama, will use Claude API"
else
    AI_STRATEGY="api"
    warn "RAM: ${TOTAL_RAM_MB} MB (or unknown) — will use Claude API"
fi

# --- 3. Install Ollama (if enough RAM) ---
echo ""
echo "Step 3/7: AI model setup..."

if [ "$AI_STRATEGY" = "ollama" ]; then
    if ! command -v ollama >/dev/null 2>&1; then
        echo "  Installing Ollama..."
        curl -fsSL https://ollama.com/install.sh | sh
    fi
    ok "Ollama installed"

    echo "  Pulling ${OLLAMA_TAG} (${OLLAMA_SIZE}, may take a while)..."
    ollama pull "$OLLAMA_TAG"
    ok "Model ${OLLAMA_TAG} ready"

    OPENCLAW_PROVIDER="ollama"
    OPENCLAW_MODEL="$OLLAMA_TAG"
else
    warn "Skipping Ollama (not enough RAM)"
    warn "You will need an Anthropic API key (pay-as-you-go)"
    warn "Get one at: https://console.anthropic.com/settings/keys"
    OPENCLAW_PROVIDER="anthropic"
    OPENCLAW_MODEL="claude-sonnet-4-20250514"
fi

# --- 4. Install OpenClaw ---
echo ""
echo "Step 4/7: Installing OpenClaw..."

if ! command -v openclaw >/dev/null 2>&1; then
    npm install -g openclaw@latest
fi
ok "OpenClaw $(openclaw --version 2>&1 || echo 'installed')"

# --- 5. Install Python dependencies ---
echo ""
echo "Step 5/7: Installing Python dependencies..."

pip install -e . --quiet 2>/dev/null || pip install -e .
ok "Python library installed"

# --- 6. Configure .env ---
echo ""
echo "Step 6/7: Configuration..."

if [ ! -f .env ]; then
    cp .env.example .env
    echo ""
    echo -e "  ${YELLOW}IMPORTANT: Edit .env with your business data!${NC}"
    echo ""
    echo "  Required fields:"
    echo "    SELLER_NAME        — Your company name"
    echo "    SELLER_NIP         — Tax ID (NIP)"
    echo "    SELLER_ADDRESS     — Business address"
    echo "    SELLER_BANK_ACCOUNT — Bank account number"
    echo "    SELLER_BANK_NAME   — Bank name"
    echo "    SELLER_EMAIL       — Contact email"
    echo "    KSEF_TOKEN         — From ksef.mf.gov.pl portal"
    echo ""
    echo "  For JPK_V7M generation also set:"
    echo "    SELLER_FIRST_NAME, SELLER_LAST_NAME"
    echo "    SELLER_BIRTH_DATE, SELLER_TAX_OFFICE_CODE"
    echo ""

    if [ "$AI_STRATEGY" = "api" ]; then
        echo -e "  ${YELLOW}Also required (no Ollama):${NC}"
        echo "    ANTHROPIC_API_KEY  — From console.anthropic.com"
        echo ""
    fi

    read -p "  Press Enter after editing .env (nano .env in another terminal)... " _
else
    ok ".env already exists"
fi

# --- 7. Initialize database ---
echo ""
echo "Step 7/7: Initializing database..."

python3 -c "from jdg_ksiegowy.registry.db import init_db; init_db()"
ok "Database: data/jdg_ksiegowy.db"

# --- 8. OpenClaw onboarding ---
echo ""
echo "═══════════════════════════════════════"
echo "  OpenClaw Setup"
echo "═══════════════════════════════════════"
echo ""
echo "  The wizard will ask you to:"
echo "  1. Choose AI provider -> select '${OPENCLAW_PROVIDER}'"
echo "  2. Choose model -> type '${OPENCLAW_MODEL}'"
echo "  3. Connect a channel -> choose 'whatsapp' or 'telegram'"
echo ""

openclaw onboard

# --- 9. Register cron jobs ---
echo ""
echo "Registering cron jobs..."

openclaw cron add "0 9 17 * *" \
  "Oblicz i przypomnij o ryczalcie i ZUS za poprzedni miesiac. Uzyj skill tax-calculator." 2>/dev/null && \
  ok "Cron: ryczalt+ZUS reminder (17th)" || warn "Cron registration failed — add manually (see CRON.md)"

openclaw cron add "0 8 20 * *" \
  "DZIS termin ryczaltu i ZUS! Podaj kwoty i mikrorachunek." 2>/dev/null && \
  ok "Cron: ryczalt+ZUS deadline (20th)" || true

openclaw cron add "0 9 22 * *" \
  "Wygeneruj JPK_V7M uzywajac skill jpk-generator. Przypomnij o VAT za 3 dni." 2>/dev/null && \
  ok "Cron: JPK+VAT reminder (22nd)" || true

openclaw cron add "0 8 25 * *" \
  "DZIS termin VAT JPK_V7M! Podaj kwote i przypomnij o e-Deklaracje." 2>/dev/null && \
  ok "Cron: VAT deadline (25th)" || true

openclaw cron add "0 9 28 * *" \
  "Wygeneruj faktury za miesiac uzywajac skill invoice-generator, wyslij do KSeF uzywajac skill ksef-submit." 2>/dev/null && \
  ok "Cron: monthly invoices (28th)" || true

# --- Done ---
echo ""
echo "  ╔══════════════════════════════════════╗"
echo "  ║            SETUP COMPLETE            ║"
echo "  ╚══════════════════════════════════════╝"
echo ""
echo "  Your AI accounting assistant is ready!"
echo ""
echo "  Send a message on WhatsApp/Telegram:"
echo "    \"Oblicz podatki od faktury 10500 netto\""
echo "    \"Wystaw fakture dla Firma XYZ, NIP 1234567890, 10500 netto\""
echo ""
echo "  Useful commands:"
echo "    openclaw logs          — View agent logs"
echo "    openclaw cron list     — List scheduled jobs"
echo "    openclaw skills list   — List loaded skills"
echo ""
echo "  Documentation:"
echo "    INSTALL.md             — Full installation guide"
echo "    CRON.md                — Cron job configuration"
echo "    CONTRIBUTING.md        — How to contribute"
echo ""
