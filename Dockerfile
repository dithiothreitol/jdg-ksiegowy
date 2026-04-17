# Bazowy obraz OpenClaw + zależności Python dla AgentSkills
FROM ghcr.io/openclaw/openclaw:latest

# Instalacja Pythona i zależności (AgentSkills wymagają ksef2, python-docx, lxml)
USER root
RUN apt-get update && apt-get install -y python3 python3-pip libreoffice && \
    pip3 install --no-cache-dir --break-system-packages \
      "ksef2>=0.12" \
      "python-docx>=1.2" \
      "lxml>=6.0.4" \
      "xmlschema>=4.3.1" \
      "pydantic>=2.13.2" \
      "pydantic-settings>=2.13" \
      "sqlalchemy>=2.0.49" \
      "cryptography>=46.0.7" \
      "anthropic>=0.96" \
      "pillow>=12.2" \
      "pypdf>=6.10" \
      "httpx>=0.28.1" && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

USER node

COPY --chown=node:node SOUL.md /home/node/.openclaw/workspace/SOUL.md
COPY --chown=node:node HEARTBEAT.md /home/node/.openclaw/workspace/HEARTBEAT.md
COPY --chown=node:node skills/ /home/node/.openclaw/workspace/skills/
COPY --chown=node:node src/ /home/node/.openclaw/workspace/src/
