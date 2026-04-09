# Bazowy obraz OpenClaw + zależności Python dla AgentSkills
FROM ghcr.io/openclaw/openclaw:latest

# Instalacja Pythona i zależności (AgentSkills wymagają ksef2, python-docx, lxml)
USER root
RUN apt-get update && apt-get install -y python3 python3-pip && \
    pip3 install --no-cache-dir \
      ksef2>=0.11 \
      python-docx>=1.1 \
      lxml>=5.3 \
      pydantic>=2.10 \
      pydantic-settings>=2.7 \
      sqlalchemy>=2.0 \
      httpx>=0.28 && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

USER node

COPY --chown=node:node SOUL.md /home/node/.openclaw/workspace/SOUL.md
COPY --chown=node:node HEARTBEAT.md /home/node/.openclaw/workspace/HEARTBEAT.md
COPY --chown=node:node skills/ /home/node/.openclaw/workspace/skills/
COPY --chown=node:node src/ /home/node/.openclaw/workspace/src/
