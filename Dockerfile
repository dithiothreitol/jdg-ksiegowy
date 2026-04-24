# Bazowy obraz OpenClaw + zależności Python dla AgentSkills
FROM ghcr.io/openclaw/openclaw:latest

# Base image = Debian 12 z Pythonem 3.11; ksef2>=0.12 wymaga Pythona 3.12+,
# więc instalujemy standalone 3.12 przez uv i podmieniamy /usr/local/bin/python3.
USER root
RUN apt-get update && apt-get install -y --no-install-recommends \
      libreoffice ca-certificates && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

ENV UV_PYTHON_INSTALL_DIR=/opt/python
RUN uv python install 3.12 && \
    ln -sf "$(uv python find 3.12)" /usr/local/bin/python3 && \
    ln -sf /usr/local/bin/python3 /usr/local/bin/python && \
    uv pip install --system --break-system-packages --python /usr/local/bin/python3 \
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
      "httpx>=0.28.1"

RUN mkdir -p /home/node/.openclaw/workspace /home/node/.openclaw/logs/stability && \
    chown -R node:node /home/node/.openclaw

USER node

COPY --chown=node:node SOUL.md /home/node/.openclaw/workspace/SOUL.md
COPY --chown=node:node HEARTBEAT.md /home/node/.openclaw/workspace/HEARTBEAT.md
COPY --chown=node:node skills/ /home/node/.openclaw/workspace/skills/
COPY --chown=node:node src/ /home/node/.openclaw/workspace/src/
