# Sandbox J06 : l'agent et ses serveurs MCP dans un conteneur

Objectif : exécuter votre agent (`labs/mcp/agent_mcp.py`, ou `neoagent` du J4) et les serveurs MCP avec un
**périmètre fichiers** réduit au dépôt et un **réseau sortant** limité à l'API Anthropic. C'est la condition
pour accorder plus d'autonomie (tâches longues, serveur MCP tiers en évaluation, confirmation automatique).

```
            réseau « sortie » (Internet)
                     │
              ┌──────┴──────┐  liste blanche : api.anthropic.com
              │   egress    │  (Squid, CONNECT 443 uniquement, journal des refus)
              └──────┬──────┘
   réseau « interne » (internal: true, aucune route vers Internet)
              ┌──────┴───────────────────────────────────────────────┐
              │ agent : python 3.12 + uv + client MCP + serveurs MCP  │
              │  /workspace  <- le dépôt NeoFlow (bind mount)         │
              │  rootfs en lecture seule, cap_drop ALL, non root      │
              │  pas de ~/.ssh, ~/.aws, ni config d'assistant de l'hôte │
              └──────────────────────────────────────────────────────┘
```

## Démarrer

```bash
cd labs/mcp/sandbox
docker compose build                       # image agent + proxy (contexte : racine du dépôt)
docker compose run --rm agent              # scénario NEO-131 hors ligne, confirmations refusées
docker compose run --rm agent uv run --no-sync --project labs/mcp python labs/mcp/agent_mcp.py outils
```

Mode réel (agent du J4 appelant Claude) : `export ANTHROPIC_API_KEY=...` (clé de formation plafonnée), puis
`docker compose run --rm agent uv run --no-sync --project labs/mcp python labs/mcp/agent_mcp.py scenario neo-131 --neoagent`.
Les dépendances de `labs/agent` doivent alors être installées dans l'image (ajouter son `pyproject.toml` et
son `uv.lock` au Dockerfile sur le modèle de `labs/mcp`) : aucun paquet ne peut être téléchargé à l'exécution.

Sous Linux, si votre UID n'est pas 1000 : `SANDBOX_UID=$(id -u) SANDBOX_GID=$(id -g) docker compose build`.

## Vérifier l'isolation (démo 06)

```bash
# 1. Sortie refusée vers une destination non listée (Python suit HTTPS_PROXY)
docker compose run --rm agent python3 -c \
  "import urllib.request as u; u.urlopen('https://example.com', timeout=5)"
#    -> urllib.error.URLError: Tunnel connection failed: 403 Forbidden

# 2. Sortie directe sans proxy : aucune route
docker compose run --rm -e HTTPS_PROXY= agent python3 -c \
  "import socket; socket.create_connection(('1.1.1.1', 443), timeout=5)"
#    -> OSError: [Errno 101] Network is unreachable (ou délai dépassé)

# 3. Le proxy journalise les décisions
docker compose logs egress | grep -E 'TCP_DENIED|TCP_TUNNEL'

# 4. Le conteneur ne voit pas le reste du poste
docker compose run --rm agent sh -c 'ls ~/.ssh ~/.aws 2>&1; ls /workspace | head'
```

## Ce que la sandbox protège, et ce qu'elle ne protège pas

| Risque | Couvert | Comment / limite |
|---|---|---|
| Lecture de fichiers hors dépôt (clés SSH, autres projets) | oui | seul le dépôt est monté |
| Exfiltration HTTP(S) vers un domaine arbitraire | oui | réseau interne + proxy à liste blanche |
| `git push`, téléchargement de paquets au vol | oui | aucune destination autorisée (installer dans l'image) |
| Écriture hors dépôt, persistance dans l'image | oui | rootfs en lecture seule, tmpfs |
| Lecture de `ANTHROPIC_API_KEY` par un outil | **non** | la clé est dans l'environnement de l'agent : clé de formation à plafond ; le client MCP ne la transmet pas aux serveurs (`env_hote`) |
| Destruction de fichiers du dépôt | **non** | le dépôt est monté en écriture : Git, branche de travail, confirmation des écritures |
| Exfiltration via le modèle (le contenu part chez le fournisseur) | **non** | fonctionnement normal : classification des données (J2) |
| Résolution DNS externe | selon version | vérifier `getent hosts example.com` dans le conteneur |

## Points d'attention

- **Venv dédié** : l'image construit `/opt/venvs/labs-mcp` depuis `labs/mcp/uv.lock` (`UV_PROJECT_ENVIRONMENT`) ;
  la configuration du client (`configs/mcp_client.json`) transmet cette variable aux serveurs par `env_hote`.
- **Contexte de build** : `Dockerfile.dockerignore` n'envoie que `labs/mcp/pyproject.toml` et `uv.lock` (ni `.env`, ni `target/`).
- **Images** : épingler par digest en mission ; reconstruire après chaque mise à jour de `uv.lock`.
- Confirmation automatique des écritures (`--oui`) : seulement **dans** cette sandbox, jamais sur le poste.
