# syntax=docker/dockerfile:1.7
# ---------------------------------------------------------------------------
# Sandbox J06 : votre agent (labs/mcp/agent_mcp.py, ou neoagent du J4) et les serveurs MCP du lab,
# sans accès au reste de la machine. Contexte de build : RACINE du dépôt NeoFlow (docker-compose.yml).
# En mission : épingler les images par digest (docker buildx imagetools inspect <image>) et reconstruire
# à chaque mise à jour de labs/mcp/uv.lock.
# ---------------------------------------------------------------------------
FROM ghcr.io/astral-sh/uv:0.9.5 AS uv

FROM python:3.12-slim-bookworm

ARG UID=1000
ARG GID=1000

ENV DEBIAN_FRONTEND=noninteractive \
    # venv des serveurs et du client MCP construit dans l'image (pas celui du poste, souvent macOS)
    UV_PROJECT_ENVIRONMENT=/opt/venvs/labs-mcp \
    UV_PYTHON_DOWNLOADS=never \
    UV_CACHE_DIR=/tmp/uv-cache \
    PYTHONDONTWRITEBYTECODE=1

# Outils strictement nécessaires : git (mcp-server-git), ripgrep (repli du retriever), tini (signaux).
# Pas de curl, wget, ssh ni compilateur.
RUN apt-get update \
 && apt-get install -y --no-install-recommends git ripgrep ca-certificates tini \
 && rm -rf /var/lib/apt/lists/*

COPY --from=uv /uv /uvx /usr/local/bin/

# Dépendances figées par uv.lock (aucune résolution au démarrage).
COPY labs/mcp/pyproject.toml labs/mcp/uv.lock /opt/labs-mcp/
RUN uv sync --project /opt/labs-mcp --frozen --all-extras --no-dev \
 && rm -rf /tmp/uv-cache

# Utilisateur non root ; UID/GID alignables sur l'hôte Linux pour les fichiers du dépôt monté.
RUN groupadd -o -g "${GID}" agent \
 && useradd -o -m -u "${UID}" -g "${GID}" -s /usr/sbin/nologin agent \
 && chown -R agent:agent /opt/venvs \
 && git config --system --add safe.directory /workspace

USER agent
WORKDIR /workspace
ENTRYPOINT ["/usr/bin/tini", "--"]
# Par défaut : scénario hors ligne (modèle simulé), confirmations refusées. Mode réel : voir README.
CMD ["uv", "run", "--no-sync", "--project", "labs/mcp", "python", "labs/mcp/agent_mcp.py", "scenario", "neo-131", "--offline", "--non"]
