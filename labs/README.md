# Laboratoires NeoFlow

Du J3 au J10, vous **codez** dans ces laboratoires les outils IA que vous appliquez ensuite à votre variante. OpenCode, pratiqué en J1–J2, n'est plus utilisé ici. Chaque lab contient des fonctions clés marquées `TODO`, avec des tests qui échouent tant qu'elles ne sont pas écrites. Vous les complétez, vous faites passer les tests en mode `--offline`, puis vous exécutez l'outil pour de vrai sur votre variante.

Prérequis : Python 3.11+ et `uv` pour les labs Python (un `pyproject.toml` par lab), Java 21 et le wrapper Maven pour les labs Java. Les services Qdrant et Ollama démarrent avec `make up-ia` (profil `ia`), Langfuse avec le profil `obs` (`labs/evals/docker-compose.langfuse.yml`).

## Index

| Dossier | Jour | Langage | Outil que vous codez | Tests | Offline |
|---|---|---|---|---|---|
| [spec/](spec/) | J3 | Python (+ Java Cucumber-JVM) | Assistant de spécification : sorties structurées (JSON Schema), questions et arbitrage, exigences, Gherkin, delta OpenAPI, validations automatiques ; squelettes de steps Cucumber-JVM | `cd labs/spec && uv run pytest` ; partie Java : `./mvnw test` du module | commande de l'assistant avec `--offline` |
| [agent/](agent/) | J4 | Python | Agent de développement `neoagent` : boucle tool use, outils de base, patterns (`neoagent/patterns/`), bornes, approbation, journal JSONL | `cd labs/agent && uv run pytest` | `uv run neoagent --repo ../.. --tache "…" --offline --journal traj.jsonl` |
| [rag/](rag/) | J5 | Python | Chunker AST (Tree-sitter), recherche BM25, vectorielle et hybride RRF, évaluation (Recall@k, MRR), outil `rag_tool` pour `neoagent` (`agent_tool.py`) | `cd labs/rag && uv run pytest` | recherche native et BM25 sans réseau ; génération par Claude avec `--offline` ; embeddings par Ollama local |
| [mcp/](mcp/) | J6 | Python (option Java) | Serveurs FastMCP (retriever, tickets, base en lecture seule), client `outils_mcp` qui fournit des outils à `neoagent` | `uv run --project labs/mcp pytest -q labs/mcp/tests` | serveurs locaux en stdio ; agent client avec `--offline` |
| [tests-ia/](tests-ia/) | J7 | Java (Maven) | Générateur de tests vérifié (compilation, exécution, mutation PIT) et assistant de diagnostic logs et traces, avec le SDK Java Anthropic | `cd labs/tests-ia && ./mvnw test` (ou `backend/mvnw -f labs/tests-ia/pom.xml test`) | outil avec `--offline` |
| [legacy-ia/](legacy-ia/) | J8 | Java (Maven) | Carte de dépendances JavaParser, explication et analyse d'impact par Claude, documentation générée et vérifiée | `cd labs/legacy-ia && ./mvnw test` (ou `backend/mvnw -f labs/legacy-ia/pom.xml test`) | outil avec `--offline` |
| [workflow/](workflow/) | J9 | Python | Nœuds LangGraph (routage, retrieval, proposition, approbation, action idempotente), mémoire, réindexation incrémentale | `cd labs/workflow && uv run pytest` | `uv run python workflow.py lancer --offline …` (ou `NEOFLOW_OFFLINE=1`) |
| [evals/](evals/) | J10 | Python | Évaluations de `neoagent` (critères, trajectoires, appels d'outils) et du RAG, mesure des tokens et des coûts depuis l'usage API, comparaison vibe et structuré | `cd labs/evals && uv run pytest` | scripts avec `--offline` ou `--dry-run` sur des journaux enregistrés |
| [regressions/](regressions/) | J7 | Patch | Régression injectable du TP tests et debugging (aucun code à écrire) | — | — |

Les commandes détaillées et les options de chaque outil sont dans le README du lab, qui fait foi.

## Commandes communes (depuis la racine du dépôt)

```bash
make labs-test                 # tests de chaque lab présent ; labs absents ou sans tests ignorés
make labs-offline              # mêmes tests sans clé API (ANTHROPIC_API_KEY retirée, NEOFLOW_OFFLINE=1),
                               # puis exécution de fumée de neoagent --offline si labs/agent existe
LABS="agent rag" make labs-test   # limiter à certains labs
```

Les cibles appellent `scripts/labs.sh`. Pour un lab Python (un `pyproject.toml` et des fichiers `test_*.py`), le script lance `uv run --all-extras --with pytest pytest -q`. Pour un lab Java (un `pom.xml`), il lance `./mvnw -B -q test` avec le wrapper du lab, ou à défaut `backend/mvnw -f labs/<lab>/pom.xml`. Le bilan indique les labs réussis, ignorés et en échec, et la commande échoue s'il y a au moins un échec.

Tant que les `TODO` d'un lab ne sont pas écrits, ses tests sont rouges : c'est attendu, et `make labs-test` sert à suivre votre avancement.

## Contrat de l'agent `neoagent`

L'agent codé au J4 est réutilisé par les J5, J6, J9 et J10 : respectez son contrat pour que les outils des autres journées s'y branchent.

- `neoagent/tools.py` : classe `Tool(name, description, input_schema, handler, risque)`, avec `risque` dans `lecture`, `ecriture` ou `execution` ; `outils_de_base(repo, politique)`.
- `neoagent/agent.py` : `Agent(tools, modele="claude-sonnet-5-5", max_etapes=30, budget_tokens=200_000, approbateur=…, journal=…, offline=False)` et `agent.executer(tache) -> Resultat`.
- Journal JSONL, une ligne par événement : `ts`, `session`, `etape`, `type` (`llm`, `tool_call`, `tool_result`, `approbation`, `erreur`, `fin`), `outil`, `entree`, `sortie_extrait`, `usage` (`input_tokens`, `output_tokens`, `cache_read_input_tokens`), `modele`.
- CLI : `uv run neoagent --repo CHEMIN --tache "…" [--pattern generator_verifier] [--mode vibe|structure] [--offline] [--journal traj.jsonl] [--outils-externes module:fonction]`.
- Extensions : `labs/rag/agent_tool.py` fournit `rag_tool(config_path=None) -> Tool` (J5) ; `labs/mcp/client/` fournit `outils_mcp(config_path) -> list[Tool]` (J6).

## Régression du J07

```bash
make regression-on    # scripts/injecter-regression.sh : applique labs/regressions/j07-regression.patch
make regression-off   # scripts/retirer-regression.sh : le code revient exactement à l'état du socle
```

Les scripts fonctionnent dans un dépôt Git comme dans une simple copie (`git apply`, ou `patch -p1` en repli) et sont idempotents. Redémarrez le backend après chaque injection ou retrait (`make backend`, `make backend-h2` ou `docker compose up -d --build backend`). Ne lisez pas le patch avant d'avoir terminé votre diagnostic.

## Clés, coûts et données

- Les outils lisent la clé dans `ANTHROPIC_API_KEY` : jamais en dur dans le code, ni dans un journal, une trace ou un fichier versionné.
- Modèles : `claude-sonnet-5-5` par défaut, `claude-haiku-5-5` pour les tâches légères, `claude-opus-5-5` pour la planification et la revue.
- Chaque appel réel journalise l'usage renvoyé par l'API ; les coûts se calculent par formule à partir de la page tarifs, sans prix codé en dur.
- Les tests tournent en `--offline` : ils ne consomment pas la clé.
- Les embeddings sont calculés localement par Ollama (`nomic-embed-text` par défaut, téléchargé par le service `ollama-modeles`).
- Toutes les données sont fictives, et les sorties d'outils sont transmises au modèle comme des données, jamais comme des instructions.
