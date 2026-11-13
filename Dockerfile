# OpenClaw gateway + pakiet jdg-ksiegowy (zaleznosci z uv.lock).
# Obrazy bazowe przypiete do wersji — aktualizacja swiadomie, przez Dependabot/PR.
FROM ghcr.io/openclaw/openclaw:2026.11.3

# Obraz bazowy ma Pythona 3.11; ksef2 wymaga 3.12+, wiec uv instaluje 3.13 obok.
USER root
RUN apt-get update && apt-get install -y --no-install-recommends \
      libreoffice ca-certificates && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.11.18 /uv /usr/local/bin/uv

ENV UV_PYTHON_INSTALL_DIR=/opt/python \
    UV_PROJECT_ENVIRONMENT=/opt/jdg-venv \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    JDG_HOME=/home/node/.openclaw/workspace

WORKDIR /opt/jdg
# Najpierw sam lock — warstwa zaleznosci cache'uje sie niezaleznie od kodu.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project --python 3.13
COPY src/ src/
RUN uv sync --frozen --no-dev --python 3.13
# venv pierwszy w PATH: `python`/`python3` ze skilli OpenClaw widza pakiet jdg_ksiegowy
# (symlink do /usr/local/bin gubi wykrycie pyvenv.cfg).
ENV PATH="/opt/jdg-venv/bin:${PATH}"

RUN mkdir -p /home/node/.openclaw/workspace /home/node/.openclaw/logs/stability && \
    chown -R node:node /home/node/.openclaw

USER node

COPY --chown=node:node SOUL.md /home/node/.openclaw/workspace/SOUL.md
COPY --chown=node:node HEARTBEAT.md /home/node/.openclaw/workspace/HEARTBEAT.md
COPY --chown=node:node plugins/jdg-ksiegowy/skills/ /home/node/.openclaw/workspace/skills/
