# Lab MCP (J06) : écrire des serveurs MCP, un client, et les brancher sur votre agent

Vous **codez** : des serveurs FastMCP (tickets, retriever RAG), le client MCP Python qui convertit leurs
outils en `neoagent.tools.Tool` pour l'agent du J4, et la politique de permissions de ce client.
Les fonctions clés sont des `TODO` ; les tests échouent tant qu'elles ne sont pas écrites.
Corrigé complet : `J06_mcp_outils/solutions/labs/mcp/`.

| Fichier | Rôle | À coder (TP) |
|---|---|---|
| `tickets_server.py` | serveur FastMCP du mock de ticketing | **TP 1** : T1.1 outil `get_ticket`, T1.2 ressource `tickets://{ticket_id}`, T1.3 écriture refusée sans confirmation |
| `commun/audit.py` | middleware de journal d'audit JSONL | **TP 1** : T1.4 masquage des arguments |
| `retriever_server.py` | serveur FastMCP au-dessus du RAG du J05 | **TP 2** : T2.1 import tolérant de `labs/rag/search.py` |
| `commun/depot.py` | validation des chemins, Git | **TP 2** : T2.2 `resoudre_chemin` (refus absolu, `..`, lien, sensible) |
| `client/pont.py` | pont MCP → `Tool`, politique | **TP 3** : T3.1 confirmation, T3.2 données non fiables, T3.3 liste blanche |
| `readonly_sql_server.py` | base en lecture seule (4 barrières) | fourni (démo 03) |
| `client/config.py`, `client/connexions.py`, `client/outil.py` | config, sessions stdio persistantes, type `Tool` | fournis |
| `agent_mcp.py` | branche les outils sur un agent (hors ligne ou `neoagent`) | fourni (TP fil rouge) |
| `neoagent_outils.py`, `scenarios/neoagent_neo131.json` | point d'entrée `--outils-externes` du J4, scénario simulé | fournis (TP fil rouge) |
| `mcp_cli.py` | client MCP brut, sans politique (diagnostic) | fourni |
| `java/tickets-server/` | option Java : serveur tickets en lecture seule (SDK MCP Java 2.0.1) | option |
| `configs/mcp_client.json` | serveurs, environnement transmis, outils autorisés et leur risque | à adapter (TP fil rouge) |
| `sandbox/` | conteneur d'isolation (agent + serveurs) et proxy de sortie | fourni (démo 06) |

## Installation

```bash
cd neoflow                                                    # racine du dépôt
uv sync --project labs/mcp --all-extras --frozen
uv run --project labs/mcp pytest -q labs/mcp/tests            # échecs attendus tant que les TODO ne sont pas faits
uv run --project labs/mcp pytest -q labs/mcp/tests/test_tickets.py      # TP 1
uv run --project labs/mcp pytest -q labs/mcp/tests/test_retriever.py    # TP 2
uv run --project labs/mcp pytest -q labs/mcp/tests/test_client.py       # TP 3
```

Avec le corrigé : 93 tests, dont 6 conditionnels (PostgreSQL réel, jar Java, agent du J4 complet ×2, lab J05, migrations Flyway).
Aucun test n'appelle l'API Claude.

## Utiliser les outils depuis un agent

```python
from client import outils_mcp, PolitiqueMCP, confirmer_en_console   # labs/mcp sur sys.path
outils = outils_mcp("labs/mcp/configs/mcp_client.json",
                    PolitiqueMCP(confirmer=confirmer_en_console,          # écriture : accord humain obligatoire
                                 outils=["git_git_log", "rag_*", "tickets_get_ticket"]))   # profil d'agent
# outils : list[neoagent.tools.Tool] (ou dataclass de même forme si labs/agent est absent)
```

Avec l'agent du J4 (`labs/agent`), par son point d'extension `--outils-externes` :

```bash
uv run --project labs/agent --with "fastmcp>=4.1,<4.2" --with "jsonschema>=4.23,<5" python -m neoagent.cli \
  --repo . --tache "Instruis le ticket NEO-131 : sources, refus, commentaire proposé" --approbation interactif \
  --outils-externes labs/mcp/neoagent_outils.py:outils_mcp --outils-config labs/mcp/configs/mcp_client.json
# (« python -m neoagent.cli » et non « neoagent » : le script installé ne voit pas les paquets ajoutés par --with)
# hors ligne, scénario rejoué par le modèle simulé du J4 :
#   ... --offline --script labs/mcp/scenarios/neoagent_neo131.json --approbation accord
```

L'`Approbateur` de neoagent valide les outils `ecriture` en montrant l'aperçu fourni par le client
(`Tool.apercu`) ; le client n'exécute que l'appel dont les arguments ont été présentés (usage unique, 2 min).
Hors neoagent, c'est `PolitiqueMCP(confirmer=...)` qui demande l'accord. En ligne de commande :

```bash
alias agentmcp="uv run --project labs/mcp python labs/mcp/agent_mcp.py"
agentmcp outils                                   # outils exposés, risque, description
agentmcp outils --profil analyste                 # profil sans aucune écriture
agentmcp appeler rag_search_code '{"query": "calculerNiveau"}'
agentmcp scenario neo-131 --offline               # modèle simulé : inspection, contexte, refus, écriture confirmée
agentmcp scenario injection --offline --naif      # le modèle simulé « obéit » au ticket piégé NEO-142
agentmcp scenario neo-131 --neoagent --offline    # avec l'agent du J4, s'il est présent dans labs/agent
```

## Politique du client (`configs/mcp_client.json` + `client/pont.py`)

| Règle | Où | Effet |
|---|---|---|
| Liste blanche | `serveurs.<nom>.outils` | un outil non listé n'est jamais exposé (ni appelable, ni payé en tokens) |
| Risque décidé par le client | `"lecture"` / `"ecriture"` / `"execution"` | les annotations du serveur sont des indices ; une incohérence avouée est refusée au chargement |
| Confirmation humaine | automatique pour `ecriture` / `execution`, option `"confirmation": true` pour une lecture sensible (`git_show`) | accord de l'hôte (aperçu présenté à l'`Approbateur` du J4) ou `confirmer` du client ; sinon refus |
| Auto-confirmation impossible | `"parametre_confirmation": "confirm"` | `confirm` retiré du schéma montré au modèle, posé par le client après accord |
| Arguments validés | JSON Schema (`jsonschema`) | refus avant envoi, sans déranger l'humain |
| Sorties = données | `<resultat_outil ... confiance="non_fiable" alertes="...">` | balise de fin neutralisée, alertes recalculées, taille bornée |
| Environnement explicite | `env_hote` + `env` (`${VAR}` lu dans l'hôte) | le SDK `mcp` n'hérite que de PATH, HOME, USER… ; rien d'autre n'est transmis |
| Pas de `roots` | `client/connexions.py` | un serveur comme server-filesystem garde ses propres dossiers |
| Journal | `labs/mcp/var/client.jsonl` | connexion (exposés / masqués), appel, décision, durée ; stderr des serveurs dans `var/<serveur>.stderr.log` |

## Serveurs

- **tickets** : `list_tickets`, `get_ticket`, ressource `tickets://{ticket_id}`, prompt `analyser_ticket`,
  `comment_ticket` (écriture : `NEOFLOW_TICKETS_WRITE=on`, `confirm`, anti-secret, anti-URL, idempotence,
  auteur = `NEOFLOW_MCP_ACTOR`). Données fictives `data/tickets.json` ; NEO-142 contient une injection volontaire.
- **rag** : `search_code`, `search_docs`, `get_chunk`, ressource `rag://statut`. Import tolérant du J05 :
  `rag:<mode>` → `rag:native` (index ou Qdrant absents) → `lexical-local` (module absent). Chaque résultat porte
  `citation` (`path:start-end@commit`) et `stale`. Mode hybride complet : lancer le serveur dans l'environnement
  du J05 (`uv run --project labs/rag --with "fastmcp>=4.1,<4.2" python labs/mcp/retriever_server.py`).
  Qdrant **embarqué** n'accepte qu'un processus à la fois : utiliser le serveur Qdrant pour travailler en parallèle.
- **db** : base SQLite générée depuis les **migrations Flyway du dépôt** (même schéma et données que
  l'application ; repli `data/neoflow_demo.sql`), plus la table sensible fictive `data/jeton_integration.sql`.
  Barrières : analyse sqlglot (1 SELECT, tables et fonctions filtrées), SQL regénéré + `LIMIT n+1`, connexion
  lecture seule (SQLite `mode=ro` + authorizer ; PostgreSQL : rôle `neoflow_ro`, `sql/role_lecture_seule_postgres.sql`,
  mot de passe dans `~/.pgpass`), délai maximal. Test PostgreSQL : `NEOFLOW_TEST_PG_URL=... pytest -k postgres`.
- **git** : `mcp-server-git==2026.10.19`, serveur tiers verrouillé dans `uv.lock` (extra `git`) ; seuls les
  outils de lecture sont listés, `git_show` exige une confirmation (il lit tout l'historique).
- **tickets-java** (option, `"actif": false`) : `java/tickets-server/` (`./mvnw -q package`).

## Diagnostic sans politique

```bash
alias mcpcli="uv run --project labs/mcp python labs/mcp/mcp_cli.py"
mcpcli tickets tools                                  # découverte brute + coût en contexte estimé
mcpcli tickets call get_ticket '{"ticket_id": "NEO-142"}'
mcpcli rag read rag://statut
npx -y @modelcontextprotocol/inspector uv run --project labs/mcp python labs/mcp/tickets_server.py
```

## Journaux

- `labs/mcp/var/audit.jsonl` : côté **serveurs** maison (`server_start`, `tools_list`, `tool_call` avec
  `decision`, `reason`, arguments masqués, `result_sha256`, `sources`, `injection_flags`).
- `labs/mcp/var/client.jsonl` : côté **client** (outils exposés et masqués, décisions de politique, confirmations).
- `labs/mcp/var/trajectoire.jsonl` : trajectoire de l'agent au format du J4.

```bash
jq -c 'select(.event=="tool_call") | [.ts, .server, .tool, .decision, .reason]' labs/mcp/var/audit.jsonl
jq -c 'select(.event=="appel") | [.outil, .decision, .raison, .confirme_par]' labs/mcp/var/client.jsonl
```

## Variables d'environnement des serveurs

| Variable | Défaut | Rôle |
|---|---|---|
| `NEOFLOW_REPO` | racine du dépôt | dépôt lu par `rag` |
| `NEOFLOW_RAG_DIR`, `NEOFLOW_RAG_CONFIG`, `NEOFLOW_RAG_MODE` | `../rag`, config J05, `auto` | accès au lab J05 (`rag` exige, `lexical` force le repli) |
| `NEOFLOW_MCP_ACTOR` | `acteur-non-declare` | identité technique des journaux et des commentaires |
| `NEOFLOW_MCP_AUDIT` | `labs/mcp/var/audit.jsonl` | journal des serveurs |
| `NEOFLOW_MCP_DENY` | (vide) | motifs de chemins interdits supplémentaires |
| `NEOFLOW_TICKETS_WRITE` | `off` | active l'écriture du serveur tickets |
| `NEOFLOW_DB_URL`, `NEOFLOW_DB_MIGRATIONS`, `NEOFLOW_DB_TABLES`, `NEOFLOW_DB_MAX_ROWS`, `NEOFLOW_DB_TIMEOUT_MS` | SQLite depuis Flyway, 3 tables, 100, 3000 | base en lecture seule |
| `NEOFLOW_MCP_HTTP_TOKEN` | (aucun) | jeton Bearer de `retriever_server.py --http <port>` (Streamable HTTP sur 127.0.0.1) |
| `NEOFLOW_MCP_CLIENT_CONFIG` | `configs/mcp_client.json` | configuration du client |

Aucun secret dans ce dossier : les valeurs `FAUX-JETON-DEMO-...` sont factices.
