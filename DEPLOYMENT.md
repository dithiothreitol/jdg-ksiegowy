# Plan wdrożenia — serwer Hetzner (środowisko wdrożeniowe)

> **Status: WDROŻENIE ODŁOŻONE.** Ten plik to runbook do wykonania później.
> Najpierw wykonane zostało utwardzenie zależności (patrz [Aneks A](#aneks-a--podniesienie-wersji-bibliotek-i-narzędzi-wykonane)).
> Wdrożenie rusza dopiero po spełnieniu [warunków startu](#0-warunki-startu-blokery).

## Cel

Wdrożyć JDG Ksiegowy (OpenClaw Gateway + skille + biblioteka) na dedykowany serwer
jako **środowisko wdrożeniowe (staging)** i przejść **pełne testy e2e** w trybie
sandbox KSeF/MF — zero skutków prawnych, zgodnie z najlepszymi praktykami i zasadami
bezpieczeństwa.

## Serwer docelowy

| Parametr | Wartość |
|---|---|
| Provider / typ | Hetzner Cloud **CPX22** (3 vCPU AMD, **4 GB RAM**, 80 GB SSD) |
| Hostname / region | `ubuntu-4gb-fsn1-1` — Falkenstein (FSN1) |
| IP v4 / v6 | `167.233.57.77` / `2a01:4f8:c014:2add::/64` |
| OS | Ubuntu (x86_64) |
| Użytkownik startowy | `root` (auth hasłem — do utwardzenia) |

## Decyzje (zatwierdzone)

1. **Dostęp SSH** — user sam dodaje klucz publiczny (`id_ed25519.pub`) przez Hetzner
   Console / hcloud i zgłasza „gotowe". Dalej wszystko jedzie bezhasłowo Twoim kluczem.
2. **Model AI** — **Claude API (pay-as-you-go)**. 4 GB RAM wyklucza Ollama
   (`qwen3.5:9b` = 6,6 GB). Backend = `ANTHROPIC_API_KEY` (sk-ant-…, NIE subskrypcja).
3. **Środowisko** — **staging / sandbox**: `KSEF_ENV=test`, `MF_ENV=test`. Pełne testy
   e2e włącznie z realną wysyłką do sandboxów.
4. **`.env`** — kopiujemy lokalny `.env` (dane ArchXS + sekrety) na serwer, `chmod 600`.

### Konsekwencje 4 GB RAM (ważne)

- **Brak lokalnego LLM** → agent OpenClaw działa wyłącznie na Claude API.
- **OCR też bez lokalnego Pixtral 12B** → na serwerze ustaw `OCR_PROVIDER=claude`
  (lub `auto` — i tak spadnie na Claude Haiku, bo Ollama nie ma). Wymaga
  `ANTHROPIC_API_KEY`.
- **Swap obowiązkowy** — LibreOffice headless (DOCX→PDF) i build obrazu potrafią skoczyć
  z pamięcią; bez swapu OOM-killer ubije kontener. Plan: 4 GB swap.

---

## 0. Warunki startu (blokery)

Wdrożenie **nie rusza**, dopóki nie mamy:

- [ ] **Klucz SSH na serwerze** — user dodał `~/.ssh/id_ed25519.pub` do `root@167.233.57.77`
      (Hetzner Console → Server → … lub `hcloud`). Weryfikacja:
      `ssh -o BatchMode=yes root@167.233.57.77 whoami` → `root`.
- [ ] **`ANTHROPIC_API_KEY`** (pay-as-you-go, sk-ant-…) — do `.env` (model agenta + OCR).
- [ ] **KSeF token TEST** — z https://ksef-test.mf.gov.pl (`KSEF_ENV=test`).
- [ ] **Dane autoryzujące MF TEST** — `MF_PESEL`, `MF_PRIOR_INCOME` (env `test`).
- [ ] (opc.) **SMTP App Password** — jeśli testujemy wysyłkę faktur mailem.

> Sekrety produkcyjne KSeF/MF **nie** trafiają na staging. Jeśli lokalny `.env` zawiera
> tokeny prod — przed kopiowaniem przełączamy `KSEF_ENV=test`/`MF_ENV=test` i podmieniamy
> tokeny na testowe.

---

## 1. Utwardzenie serwera (security baseline)

Wszystko jako jednorazowy bootstrap. Logujemy się `root@167.233.57.77` (już z kluczem).

```bash
# 1.1 Aktualizacja systemu
apt update && apt -y upgrade

# 1.2 Strefa czasu + podstawy
timedatectl set-timezone Europe/Warsaw
apt -y install ufw fail2ban unattended-upgrades git curl ca-certificates

# 1.3 Użytkownik nie-root z dostępem do dockera
adduser --disabled-password --gecos "" deploy
install -d -m 700 -o deploy -g deploy /home/deploy/.ssh
cp /root/.ssh/authorized_keys /home/deploy/.ssh/authorized_keys
chown deploy:deploy /home/deploy/.ssh/authorized_keys && chmod 600 /home/deploy/.ssh/authorized_keys

# 1.4 Swap 4 GB (krytyczne na 4 GB RAM)
fallocate -l 4G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab
sysctl -w vm.swappiness=10 && echo 'vm.swappiness=10' >> /etc/sysctl.d/99-swap.conf
```

### 1.5 Docker (oficjalne repo)

```bash
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
  https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" \
  > /etc/apt/sources.list.d/docker.list
apt update && apt -y install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
usermod -aG docker deploy
systemctl enable --now docker
```

### 1.6 SSH hardening

`/etc/ssh/sshd_config.d/99-hardening.conf`:

```
PasswordAuthentication no
PermitRootLogin prohibit-password   # docelowo: no, gdy potwierdzimy login deploy@
PubkeyAuthentication yes
KbdInteractiveAuthentication no
MaxAuthTries 3
X11Forwarding no
AllowUsers deploy root
```

```bash
# NAJPIERW potwierdź w DRUGIM terminalu, że deploy@ loguje się kluczem:
#   ssh deploy@167.233.57.77 whoami   →   deploy
systemctl reload ssh   # dopiero po potwierdzeniu — inaczej ryzyko lockoutu
```

### 1.7 Firewall (UFW) — port 18789 zostaje lokalny

```bash
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp          # SSH (jedyny port publiczny)
ufw --force enable
# UI OpenClaw (18789) NIE jest wystawiany — dostęp wyłącznie tunelem SSH (patrz §3.4)
```

> Opcjonalnie dorzuć **Hetzner Cloud Firewall** (warstwa chmurowa, przed maszyną):
> ingress tylko TCP 22. Defence-in-depth ponad UFW.

### 1.8 fail2ban + automatyczne aktualizacje

```bash
systemctl enable --now fail2ban          # domyślny jail sshd
dpkg-reconfigure -plow unattended-upgrades   # włącz auto security updates
```

---

## 2. Wdrożenie aplikacji

Jako `deploy@167.233.57.77`.

```bash
# 2.1 Kod
cd ~ && git clone https://github.com/dithiothreitol/jdg-ksiegowy.git
cd jdg-ksiegowy

# 2.2 .env (z lokalnej maszyny, przez SCP) — patrz §2.3
#     po skopiowaniu:
chmod 600 .env
```

### 2.3 Transfer `.env` (z Twojej maszyny Windows → serwer)

```bash
# Lokalnie (Git Bash / PowerShell). Najpierw upewnij się, że .env ma KSEF_ENV=test,
# MF_ENV=test, OCR_PROVIDER=claude, ustawiony ANTHROPIC_API_KEY i tokeny TESTOWE.
scp ./.env deploy@167.233.57.77:/home/deploy/jdg-ksiegowy/.env
```

Wartości do wymuszenia na serwerze (staging):

```env
KSEF_ENV=test
MF_ENV=test
OPENCLAW_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...          # WYMAGANE (model + OCR)
OCR_PROVIDER=claude                    # 4 GB RAM → brak lokalnego Pixtral
GCAL_ENABLED=false                     # kalendarz zostaje na maszynie usera (patrz TODO.md)
```

### 2.4 Build + start

```bash
docker compose build           # obraz: Python 3.13 + LibreOffice + skille (najnowsze liby)
docker compose up -d
docker compose ps
```

### 2.5 Konfiguracja modelu agenta OpenClaw (Claude API)

Bramka startuje na domyślnym modelu i ignoruje `OPENCLAW_MODEL` env (patrz
[INSTALL.md §8](INSTALL.md)). Ustawiamy model **anthropic** raz; konfig żyje w named
volume `openclaw-state`:

```bash
docker exec jdg-ksiegowy openclaw config set agents.defaults.model "anthropic/claude-sonnet-4-6"
docker compose restart
# Weryfikacja — powinno pokazać anthropic/claude-sonnet-4-6 (nie openai/gpt-5.4):
docker logs jdg-ksiegowy 2>&1 | grep -i "agent model"
```

> Model: `claude-sonnet-4-6` (bilans koszt/jakość dla pracy narzędziowej skilli).
> `claude-opus-4-8` jeśli zależy na maksymalnej jakości rozumowania podatkowego.
> `ANTHROPIC_API_KEY` z `.env` autoryzuje providera anthropic w OpenClaw.

---

## 3. Pełne testy na środowisku wdrożeniowym

### 3.1 Testy jednostkowe + lint (w kontenerze)

```bash
docker exec jdg-ksiegowy sh -lc 'cd /home/node/.openclaw/workspace && \
  python -m pip install -e ".[dev]" -q && python -m pytest -q && ruff check . && ruff format --check .'
# Oczekiwane: zielono (test OCR przechodzi — brak .env override na serwerze ustawia OCR=claude)
```

### 3.2 Preflight (doctor)

```bash
docker exec jdg-ksiegowy python skills/doctor/scripts/check.py
# Sprawdza: dane sprzedawcy, KSeF(test), bramka MF(test), SMTP, OCR, (CALENDAR=skip).
```

### 3.3 E2E skille (deterministycznie, na danych przykładowych)

```bash
# Kalkulacja podatku
docker exec jdg-ksiegowy python skills/tax-calculator/scripts/calculate.py --netto 10500
# Faktura: DOCX + XML FA(3) + zapis do SQLite
docker exec jdg-ksiegowy python skills/invoice/scripts/generate.py \
  --buyer-name "Test Sp. z o.o." --buyer-nip 1234567890 --netto 5000
# JPK_V7M (XML) — potem walidacja względem XSD MF (test xsd w pytest)
docker exec jdg-ksiegowy python skills/jpk/scripts/generate_jpk.py --month 5 --year 2026
```

### 3.4 Web UI przez tunel SSH (UI nie jest publiczne)

```bash
# Token UI:
docker exec jdg-ksiegowy openclaw dashboard      # → http://127.0.0.1:18789/#token=...
# Z Twojej maszyny:
ssh -N -L 18789:127.0.0.1:18789 deploy@167.233.57.77
# Otwórz http://localhost:18789/#token=... w przeglądarce
```

### 3.5 Wysyłki do sandboxów (skutki tylko testowe)

```bash
# KSeF test: wyślij ostatnią fakturę sprzedaży
docker exec jdg-ksiegowy python skills/ksef/scripts/... --env test     # ref number z sandboxu
# JPK_V7M → bramka MF test (zwróci UPO testowe)
docker exec jdg-ksiegowy python skills/jpk-submit/scripts/... --env test
# KSeF inbox (rola nabywcy) — sync kosztów
docker exec jdg-ksiegowy python skills/ksef/scripts/... inbox --env test
```

### 3.6 Smoke konwersacyjny (Claude API)

```bash
# Przez Web UI (§3.4) lub kanał, wyślij:
#   "Oblicz podatki od faktury 10500 netto"
#   "Wystaw fakturę dla Test Sp. z o.o., NIP 1234567890, 5000 netto za konsultacje"
# Oczekiwane: agent woła skille, zwraca kwoty + ścieżki plików.
```

**Kryterium akceptacji:** §3.1 zielono • doctor bez błędów (poza CALENDAR=skip) •
§3.3 generuje pliki • §3.5 zwraca ref/UPO z sandboxów • §3.6 odpowiada przez Claude API.

---

## 4. Automatyzacja, backup, monitoring (po zielonych testach)

```bash
# 4.1 Crony OpenClaw (terminy + miesięczne faktury) — patrz CRON.md / setup.sh
docker exec jdg-ksiegowy openclaw cron add "0 9 17 * *" "...ryczałt+ZUS..."
# (komplet 5 wpisów jak w setup.sh / INSTALL.md §9)

# 4.2 Backup bazy + plików (off-site, Fernet) — scripts/backup_offsite.py
#     Wymaga BACKUP_KEY w .env (NIE gubić — bez klucza backupy nieodzyskiwalne).
#     Harmonogram: systemd timer / cron host, np. codziennie 22:00.

# 4.3 Monitoring
docker compose logs -f --tail=100
docker stats jdg-ksiegowy            # pilnuj RAM/swap (4 GB!)
```

---

## 5. Checklista bezpieczeństwa (przed „done")

- [ ] SSH: hasła wyłączone, klucz działa, `MaxAuthTries 3`, (docelowo `PermitRootLogin no`)
- [ ] UFW aktywny, publiczny tylko 22; **18789 lokalny** (tylko tunel SSH)
- [ ] fail2ban (sshd) aktywny; unattended-upgrades włączone
- [ ] Użytkownik `deploy` nie-root w grupie `docker`; praca nie jako root
- [ ] `.env` `chmod 600`, właściciel `deploy`; brak sekretów w gicie (`.gitignore` ✓)
- [ ] KSeF/MF w trybie **test**; brak tokenów prod na stagingu
- [ ] Swap 4 GB aktywny; `vm.swappiness=10`
- [ ] `BACKUP_KEY` zapisany też w password managerze
- [ ] (opc.) Hetzner Cloud Firewall: ingress tylko 22

---

## 6. Rollback / teardown

```bash
docker compose down                 # stop (stan w volume zostaje)
docker compose down -v              # + kasacja openclaw-state (pełny reset konfiguracji)
docker volume rm jdg-ksiegowy_openclaw-state   # wipe identity/konfig OpenClaw
# Dane księgowe: ./data (bind mount) — backup przed kasacją!
```

---

## Aneks A — Podniesienie wersji bibliotek i narzędzi (WYKONANE)

Przed wdrożeniem cały stack podbity do najnowszych kompatybilnych wersji i zweryfikowany
testami (226 pass / lint zielony; jedyny lokalny fail to bleed `.env` OCR, w CI przechodzi).

| Komponent | Było | Jest (najnowsze) |
|---|---|---|
| Python (Dockerfile/runtime) | 3.12 | **3.13** |
| ksef2 | ≥0.12 | **≥0.17.0** |
| cryptography | ≥46.0.7 | **≥49.0.0** |
| anthropic | ≥0.96 | **≥0.109.1** |
| lxml | ≥6.0.4 | **≥6.1.1** |
| pydantic / pydantic-settings | 2.13.2 / 2.13 | **2.13.4 / 2.14.1** |
| sqlalchemy | ≥2.0.49 | **≥2.0.50** |
| pypdf | ≥6.10 | **≥6.13.2** |
| pillow | ≥12.2 | **≥12.2.0** |
| google-api-python-client / -auth / -oauthlib | 2.197 / 2.38 / 1.4 | **2.197.0 / 2.54.0 / 1.4.0** |
| python-docx / xmlschema / httpx | 1.2 / 4.3.1 / 0.28.1 | **1.2.0 / 4.3.1 / 0.28.1** |
| pytest / pytest-asyncio / respx / ruff | 9.0.3 / 1.3 / 0.23 / 0.15.11 | **9.1.0 / 1.4.0 / 0.23.1 / 0.15.17** |
| Node.js (rekomendacja) | 22 LTS | **24 LTS** |
| OpenClaw model (API fallback, setup.sh) | `claude-sonnet-4-20250514` (wycofany 15.06.2026) | **`claude-sonnet-4-6`** |

Dodatkowo: Dockerfile dopełniony o `google-api-python-client`/`google-auth`/`google-auth-oauthlib`
(były w `pyproject.toml`, brakowało ich w obrazie — kontener nie mógł uruchomić skilla
`calendar-sync`). Obrazy bazowe `ghcr.io/openclaw/openclaw:latest` i `ghcr.io/astral-sh/uv:latest`
pinowane tagiem `latest` (już najnowsze).
