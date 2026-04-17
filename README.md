<p align="center">
  <h1 align="center">JDG Ksiegowy</h1>
  <p align="center">
    <strong>Open-source AI accounting assistant for Polish sole proprietorships (JDG)</strong>
    <br />
    Invoicing &bull; KSeF &bull; JPK_V7M &bull; JPK_EWP &bull; Ryczalt &bull; ZUS &bull; MF Gateway submit
    <br /><br />
    <a href="#quick-start">Quick Start</a> &bull;
    <a href="INSTALL.md">Installation</a> &bull;
    <a href="#features">Features</a> &bull;
    <a href="#status">Status</a> &bull;
    <a href="#po-polsku">Po polsku</a>
  </p>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.12+-blue?logo=python&logoColor=white" alt="Python" />
  <img src="https://img.shields.io/badge/KSeF-FA(3)-green" alt="KSeF" />
  <img src="https://img.shields.io/badge/JPK__V7M-shipped-green" alt="JPK_V7M" />
  <img src="https://img.shields.io/badge/JPK__EWP-awaiting_official_XSD-yellow" alt="JPK_EWP" />
  <img src="https://img.shields.io/badge/MF_Gateway-REST_+_AES%2BRSA-blue" alt="MF Gateway" />
  <img src="https://img.shields.io/badge/OpenClaw-agent-orange?logo=lobster" alt="OpenClaw" />
  <img src="https://img.shields.io/badge/license-MIT-lightgrey" alt="License" />
  <img src="https://img.shields.io/badge/status-beta-yellow" alt="Status" />
</p>

---

## Why this exists

If you run a JDG in Poland, your monthly cycle looks like this:

1. Issue invoices &rarr; send to client + upload to KSeF
2. Track costs &rarr; post them to your books
3. Calculate ryczalt + ZUS + VAT &rarr; remember three deadlines
4. Generate JPK_V7M &rarr; upload to MF e-Dokumenty
5. Once a year, generate JPK_EWP + PIT-28

Accounting SaaS (wFirma, inFakt, Fakturownia) charges 50&ndash;150 PLN/month to do this. They own your data. They lock you into their UI. And none of them let you just say &laquo;wystaw fakture Acme za kwiecien&raquo; from Telegram at 11 PM.

**JDG Ksiegowy replaces the core of that workflow** &mdash; self-hosted, AI-first, chat-native, on Ollama (free) or any LLM you like.

```
You: "Wystaw fakture Acme Sp. z o.o., NIP 1234567890, 10500 netto, kwiecien 2026"

Agent: Faktura A1/04/2026 wygenerowana:
       - DOCX: data/faktury/2026/04/faktura_A1_04_2026.docx
       - KSeF: wyslana, numer: KSeF-2026-04-00001234
       - Netto: 10 500,00 PLN | VAT 23%: 2 415,00 PLN | Brutto: 12 915,00 PLN

       Terminy podatkowe na maj:
       - 20 maja: ryczalt 12% = 1 260,00 PLN + ZUS 498,35 PLN
       - 25 maja: VAT (JPK_V7M) = 2 415,00 PLN
```

---

## Features

Honest state per feature &mdash; see [Status](#status) below for the full picture.

### Shipped and tested

- **Invoicing** &mdash; DOCX (Polish, client-ready) + XML FA(3) (KSeF schema) from one command
- **Expense registry** &mdash; purchase invoices in SQLite with categories and `vat_deductible` flag
- **Input VAT deduction in JPK_V7M** &mdash; expenses feed P_42 / P_43 automatically
- **KSeF submission** &mdash; via [ksef2](https://github.com/artpods56/ksef2) SDK, token auth, test + prod
- **JPK_V7M generator** &mdash; schema v2 (namespace `crd.gov.pl/wzor/2021/12/27/11148/`), K-field mapping per VAT rate
- **MF Gateway submission** &mdash; direct REST POST to e-dokumenty.mf.gov.pl with AES-256-CBC + RSA-OAEP encryption, ZIP compression, status polling, UPO retrieval
- **Tax calculator** &mdash; ryczalt, VAT, ZUS with 2026 rates and progressive health-contribution thresholds
- **`Decimal`-based math** &mdash; tax numbers never touch a float or an LLM

### Partial / awaiting upstream

- **JPK_EWP generator** &mdash; code generates XML for schema v4, but the TNS namespace is marked `# placeholder do potwierdzenia` in [ewp.py:22](src/jdg_ksiegowy/tax/ewp.py#L22) &mdash; will be finalized when MF publishes the official XSD

### Documented but not wired yet

- **Proactive cron reminders** &mdash; [CRON.md](CRON.md) lists the jobs; you register them manually with `openclaw cron add`. No daemon ships in this repo.
- **HEARTBEAT payment monitoring** &mdash; [HEARTBEAT.md](HEARTBEAT.md) describes the logic; `InvoiceStatus.OVERDUE` exists in the model but nothing sets it today

Contributions on any of the above are very welcome.

---

<a id="status"></a>

## Status

Verified against the actual codebase on 2026-04-17:

| Area | State | Evidence |
|------|:-----:|----------|
| Invoice DOCX + FA(3) XML | **Shipped** | [generator_docx.py](src/jdg_ksiegowy/invoice/generator_docx.py), [generator_xml.py](src/jdg_ksiegowy/invoice/generator_xml.py), [test_invoice_models.py](tests/test_invoice_models.py) |
| Expense registry | **Shipped** | [expenses/models.py](src/jdg_ksiegowy/expenses/models.py), [registry/db.py](src/jdg_ksiegowy/registry/db.py) |
| KSeF submission | **Shipped** | [ksef/client.py](src/jdg_ksiegowy/ksef/client.py), [test_ksef_skill.py](tests/test_ksef_skill.py) |
| JPK_V7M (with expense deduction) | **Shipped** | [tax/jpk.py](src/jdg_ksiegowy/tax/jpk.py), [test_jpk_with_expenses.py](tests/test_jpk_with_expenses.py) |
| MF Gateway submit (AES+RSA, UPO) | **Shipped** | [mf_gateway/crypto.py](src/jdg_ksiegowy/mf_gateway/crypto.py), [mf_gateway/client.py](src/jdg_ksiegowy/mf_gateway/client.py), [test_mf_crypto.py](tests/test_mf_crypto.py) |
| Tax calculator (2026 rates) | **Shipped** | [tax/zus.py](src/jdg_ksiegowy/tax/zus.py) |
| JPK_EWP | **Partial** | Works; namespace placeholder until MF publishes final XSD |
| Cron / HEARTBEAT reminders | **Docs only** | Manual setup per [CRON.md](CRON.md) |
| Payment overdue detection | **Missing** | Enum state exists; no logic sets or alerts on it |

All claims above are grep-able in the repo. If you find a discrepancy, file an issue.

---

## Architecture

```mermaid
graph TB
    User["You (WhatsApp / Telegram / Slack)"]
    OC["OpenClaw Gateway"]
    AI["AI Model<br/>(Ollama / Claude / OpenAI)"]
    Skills["AgentSkills<br/>(deterministic Python)"]
    DB[("SQLite Registry<br/>invoices + expenses")]
    KSeF["KSeF API"]
    MF["MF Gateway<br/>e-dokumenty.mf.gov.pl"]

    User <-->|natural language| OC
    OC <--> AI
    OC -->|calls| Skills
    Skills -->|reads/writes| DB
    Skills -->|FA(3) XML| KSeF
    Skills -->|JPK_V7M / JPK_EWP| MF
```

```
jdg-ksiegowy/
├── SOUL.md                     # Agent persona & Polish tax knowledge
├── HEARTBEAT.md                # Periodic checks (docs only, not wired yet)
├── CRON.md                     # Scheduled jobs setup guide
├── setup.sh                    # One-command installation
│
├── skills/                     # OpenClaw AgentSkills (Python entry points)
│   ├── tax-calculator/         #   VAT, ryczalt, ZUS, deadlines
│   ├── invoice/                #   DOCX + XML FA(3) generation
│   ├── expense/                #   Register purchase invoices
│   ├── ksef/                   #   Submit sales invoice to KSeF
│   ├── jpk/                    #   Generate JPK_V7M (monthly VAT)
│   ├── jpk-ewp/                #   Generate JPK_EWP (annual ryczalt, partial)
│   └── jpk-submit/             #   Submit JPK to MF Gateway, fetch UPO
│
├── src/jdg_ksiegowy/           # Python library (core, reusable)
│   ├── config.py               #   Pydantic Settings from .env
│   ├── invoice/                #   Models, DOCX generator, FA(3) XML
│   ├── expenses/               #   Expense models + SQLite ops
│   ├── ksef/                   #   KSeF client (ksef2 SDK wrapper)
│   ├── mf_gateway/             #   REST submit, AES-256-CBC + RSA-OAEP
│   ├── tax/                    #   JPK_V7M, JPK_EWP, ZUS rates
│   └── registry/               #   SQLite registry (invoices, expenses)
│
├── tests/                      # Pytest (~500 lines of real tests)
└── data/                       # Database + generated files (git-ignored)
```

---

## Quick Start

### Prerequisites

- Linux, macOS, or Windows + WSL2
- Python 3.12+
- Docker (optional, for OpenClaw runtime)
- 8 GB RAM minimum if running Ollama locally; any machine works if you use a cloud LLM

### Install

```bash
git clone https://github.com/dithiothreitol/jdg-ksiegowy.git
cd jdg-ksiegowy
./setup.sh
```

The script installs Ollama, pulls a model, installs OpenClaw, installs Python deps, creates `.env` interactively, initializes SQLite, and walks you through connecting a messaging channel.

### Try it without OpenClaw / AI

You can use the Python skills as plain CLI tools &mdash; no AI runtime required:

```bash
pip install -e .
cp .env.example .env && nano .env

# Tax calc
python3 skills/tax-calculator/scripts/calculate.py --netto 10500

# Invoice generation (DOCX + FA(3) XML + registry row)
python3 skills/invoice/scripts/generate.py \
  --buyer-name "Acme Sp. z o.o." --buyer-nip "1234567890" --netto 10500

# Register a cost invoice
python3 skills/expense/scripts/add.py \
  --seller-name "Hetzner" --seller-nip "DE812871812" \
  --netto 50 --vat 11.50 --category infrastructure --vat-deductible true

# JPK_V7M for April 2026 (pulls invoices + deductible expenses from SQLite)
python3 skills/jpk/scripts/generate_jpk.py --month 4 --year 2026

# Submit the generated JPK to MF Gateway (dry-run available)
python3 skills/jpk-submit/scripts/submit.py --file data/jpk/2026_04.xml --dry-run
```

Full guide: [INSTALL.md](INSTALL.md)

---

## Configuration

All business data is in `.env` (never hardcoded). See [`.env.example`](.env.example) for the full list. Minimum required:

| Variable | Required | Example |
|----------|----------|---------|
| `SELLER_NAME` | Yes | `Acme Jan Kowalski` |
| `SELLER_NIP` | Yes | `1234567890` |
| `SELLER_ADDRESS` | Yes | `ul. Przykladowa 1, 00-001 Warszawa` |
| `SELLER_BANK_ACCOUNT` | Yes | `00 0000 0000 0000 0000 0000 0000` |
| `SELLER_EMAIL` | Yes | `kontakt@firma.pl` |
| `SELLER_TAX_FORM` | No | `ryczalt` (default) |
| `SELLER_RYCZALT_RATE` | No | `12` (default, percent) |
| `SELLER_VAT_RATE` | No | `23` (default, percent) |
| `SELLER_FIRST_NAME` / `LAST_NAME` / `BIRTH_DATE` | For JPK | &mdash; |
| `SELLER_TAX_OFFICE_CODE` | For JPK | `1471` |
| `KSEF_ENV` | No | `test` (default) &rarr; switch to `prod` when ready |
| `KSEF_TOKEN` | For KSeF | Generate at ksef.mf.gov.pl |
| `MF_*` | For JPK submit | *dane autoryzujace* &mdash; see [INSTALL.md](INSTALL.md) |

---

## AI Model

JDG Ksiegowy is **model-agnostic**. The AI handles natural-language intent; all tax math is deterministic Python.

Ollama tags confirmed against [ollama.com/library](https://ollama.com/library) at time of writing:

| Role | Model | Notes |
|------|-------|-------|
| **Primary** (daily chat, JSON output) | [`qwen3.5`](https://ollama.com/library/qwen3.5) | general-purpose, solid JSON mode |
| **Vision** (OCR for paper receipts) | [`qwen3-vl:8b`](https://ollama.com/library/qwen3-vl:8b) or [`qwen3-vl:4b`](https://ollama.com/library/qwen3-vl:4b) | required for OCR roadmap item |
| **Fallback** (tricky tax Q&A) | Claude API (pay-as-you-go) | ~2 PLN/mo typical |

Polish-native models ([Bielik](https://bielik.ai)) are not currently in the Ollama registry under that name &mdash; you can import GGUF manually if you want best-in-class Polish fluency.

> **Note:** Anthropic blocked Claude Pro/Max subscriptions for OpenClaw agents on 2026-04-04. Use Claude API keys (pay-as-you-go) or stick with Ollama.

---

## Free hosting options

| Provider | RAM | Local AI? | Monthly cost |
|----------|-----|-----------|--------------|
| **Oracle Cloud** Always Free | 24 GB | Yes (Ollama) | 0 PLN forever |
| Your existing VPS | depends | If &ge; 8 GB | already paying |
| Small VPS + Claude API | any | No (cloud LLM) | ~20 PLN + API |
| Railway / Fly.io free tier | 512 MB | No | 0 PLN |

Oracle Cloud Always Free (4 ARM OCPU, 24 GB RAM, 200 GB disk) is enough for OpenClaw + Ollama for a single user.

---

## KSeF timeline (what the law actually says)

From the Polish Ministry of Finance, as of 2026-04-17:

| Date | Obligation |
|------|------------|
| **2026-02-01** | Mandatory KSeF for large taxpayers (2024 sales &gt; 200 M PLN gross) |
| **2026-04-01** | Mandatory KSeF for everyone else (most JDG users are here) |
| **2027-01-01** | Mandatory KSeF for micro-taxpayers (&le; 10 k PLN/month sales) |

From 2026-02-01 onwards, **receiving** KSeF invoices is mandatory for everyone, even before you need to issue them there.

Sources: [ksef.podatki.gov.pl](https://ksef.podatki.gov.pl/informacje-ogolne-ksef-20/podstawy-prawne-oraz-kluczowe-terminy/), [gov.pl](https://www.gov.pl/web/ias-bialystok/obowiazkowy-ksef-przesuniety-na-1-lutego-2026-r).

---

## Polish tax context

Built for 2026 regulations:

- **KSeF** &mdash; *Krajowy System e-Faktur*, mandatory per timeline above
- **JPK_V7M** &mdash; monthly VAT declaration, schema v2 (supported); schema v3 update is on the roadmap
- **JPK_EWP** &mdash; annual *ewidencja przychodow* for ryczalt, v4 schema (XSD pending final MF release)
- **Ryczalt** &mdash; flat-rate income tax (12% for most IT services)
- **ZUS** &mdash; health contribution only for ryczalt, progressive by annual income bracket
- **Dane autoryzujace** &mdash; personal + prior-year income data used to authenticate JPK submissions without a qualified signature

---

<a id="po-polsku"></a>

## Po polsku

**JDG Ksiegowy** to open-source'owy asystent ksiegowy AI dla jednoosobowej dzialalnosci gospodarczej w Polsce. Zastepuje rdzen pracy, ktora dzis robisz w wFirmie / inFakcie / Fakturowni, za **0 PLN/miesiac** &mdash; na Twoim serwerze, z rozmowa po polsku przez WhatsApp, Telegram lub Slack.

### Co dziala dzis (zweryfikowane w kodzie)

- Wystawia faktury (DOCX + XML FA(3)) i wysyla do **KSeF**
- Rejestruje faktury kosztowe i odlicza **VAT naliczony** w JPK_V7M
- Generuje **JPK_V7M** co miesiac
- Wysyla JPK bezposrednio do **bramki MF** (REST + AES + RSA, bez podpisu kwalifikowanego, z odbiorem UPO)
- Liczy ryczalt, VAT, ZUS ze stawkami 2026

### Co jest czesciowe

- **JPK_EWP** (roczna ewidencja ryczaltowca) &mdash; kod generuje XML v4, ale finalny namespace czeka na oficjalny XSD z MF

### Czego jeszcze nie ma

- Automatycznego daemona od przypomnien (tylko instrukcja w [CRON.md](CRON.md))
- Wykrywania przeterminowanych platnosci (pole w bazie jest, logiki jeszcze brak)

### Szybki start

```bash
git clone https://github.com/dithiothreitol/jdg-ksiegowy.git
cd jdg-ksiegowy
./setup.sh
```

Pelna instrukcja: [INSTALL.md](INSTALL.md)

### Dlaczego warto

- **0 PLN/miesiac** zamiast 50&ndash;150 PLN za SaaS
- **Dane zostaja u Ciebie** &mdash; SQLite na Twoim serwerze, zero chmury
- **Rozmowa po polsku** &mdash; nie klikasz przez formularze
- **MIT License** &mdash; mozesz modyfikowac, forkowac, uzywac komercyjnie
- **Deterministyczna matematyka** &mdash; LLM nigdy nie liczy podatkow

---

## Roadmap

- [ ] Cron/heartbeat daemon (currently only documented)
- [ ] Payment overdue detection + alert
- [ ] JPK_EWP final namespace once MF XSD is published
- [ ] JPK_V7M schema v3 migration
- [ ] *Zasady ogolne* and *podatek liniowy* tax forms
- [ ] PIT-28 annual declaration generator
- [ ] OCR for paper receipts (qwen3-vl)
- [ ] Web UI dashboard (read-only)
- [ ] Multi-user mode (accountants managing several JDGs)
- [ ] CI integration tests against KSeF test environment

---

## Contributing

PRs, bug reports, and tax-regulation corrections are very welcome. See [CONTRIBUTING.md](CONTRIBUTING.md).

If you are a Polish tax advisor or accountant and spot something wrong, please open an issue &mdash; accuracy matters more than speed here.

---

## Security

JDG Ksiegowy handles sensitive data: NIPs, bank accounts, income figures, KSeF tokens, MF Gateway authorization data.

- Secrets stay in `.env` (git-ignored)
- Data lives in local SQLite (no network sync)
- MF Gateway payloads are encrypted per MF spec: **AES-256-CBC** (PKCS#7 padding) for content, **RSA-OAEP** for the session key
- No telemetry, no analytics, no third-party calls beyond KSeF / MF Gateway / your chosen LLM

If you find a security issue, open a private advisory on GitHub or email the maintainer instead of filing a public issue.

---

## License

[MIT](LICENSE) &mdash; use it, fork it, ship it, sell services on top of it. Attribution appreciated but not required.

---

## Acknowledgements

- [OpenClaw](https://github.com/openclaw/openclaw) &mdash; the agent runtime
- [ksef2](https://github.com/artpods56/ksef2) &mdash; Python SDK for KSeF v2.0 API
- [CIRFMF/ksef-docs](https://github.com/CIRFMF/ksef-docs) &mdash; official MF KSeF documentation
- [Ollama](https://ollama.com) &mdash; local LLM runtime

---

<p align="center">
  <strong>If this saves you an hour a month, star the repo.</strong><br/>
  <sub>Built for Polish freelancers who'd rather talk to an AI than click through accounting software.</sub>
</p>
