# NeoFlow

Application interne de **gestion de demandes** : création en brouillon, soumission, circuit de validation, clôture, journal d'audit. C'est le socle du fil rouge de la formation NSS+ « Dev Full Stack assisté par IA » : chaque stagiaire y implémente une variante métier (un type de demande et ses règles).

| | |
|---|---|
| Backend | Spring Boot 3.5.16, Java 21, Maven wrapper, JPA, Flyway, Spring Security (HTTP Basic), springdoc-openapi, Actuator, Micrometer Tracing + OTLP |
| Frontend | React 18, TypeScript, Vite 6, React Router 6, Vitest + Testing Library |
| E2E | Playwright (TypeScript) |
| Infra | docker compose : PostgreSQL 16, Jaeger ; profil `ia` : Qdrant, Ollama |

Architecture détaillée : [docs/architecture/ARCHITECTURE.md](docs/architecture/ARCHITECTURE.md).

## Prérequis

- Java 21 (`java -version`), Node.js 20 ou plus (`node -v`), Git, `make`.
- Docker et docker compose pour le démarrage complet (facultatif : voir « Sans Docker »).
- Ports libres : 8080 (API), 5173 (frontend), 5432 (PostgreSQL), 16686, 4317 et 4318 (Jaeger).

## Démarrage avec Docker

```bash
cp .env.example .env        # facultatif : ports et identifiants de la base
make up                     # postgres, jaeger, backend, frontend (premier build : quelques minutes)
```

| Service | URL |
|---|---|
| Application | http://localhost:5173 |
| API | http://localhost:8080/api |
| Swagger UI | http://localhost:8080/swagger-ui.html |
| Jaeger | http://localhost:16686 (service `neoflow-backend`) |

Pour développer avec rechargement à chaud, ne démarrez dans Docker que l'infrastructure :

```bash
make infra                  # postgres + jaeger
make backend                # terminal 1 : API sur :8080 (profil dev)
make frontend               # terminal 2 : Vite sur :5173, /api relayé vers :8080
```

Laboratoires IA (J3 à J10, voir [labs/README.md](labs/README.md)) : Python 3.11+ et `uv`, Java 21. `make up-ia` ajoute Qdrant (:6333) et Ollama (:11434) et télécharge le modèle d'embeddings (RAG du J5, MCP du J6).

## Démarrage sans Docker

```bash
make backend-h2             # terminal 1 : API sur :8080, base H2 en mémoire (recréée à chaque démarrage)
make frontend               # terminal 2 : http://localhost:5173
```

Le profil `dev-h2` charge les mêmes migrations et données de démonstration que PostgreSQL. Les traces ne sont pas exportées (pas de Jaeger), mais chaque ligne de log porte son `traceId`.

## Comptes de démonstration

| Login | Mot de passe | Rôle | Peut |
|---|---|---|---|
| `alice` | `neoflow` | DEMANDEUR | créer, modifier et soumettre ses demandes |
| `bob` | `neoflow` | VALIDEUR | valider, refuser |
| `admin` | `neoflow` | ADMIN | clôturer |

```bash
curl -u alice:neoflow "http://localhost:8080/api/demandes?page=0&size=5"
```

## Commandes

| Commande | Effet |
|---|---|
| `make help` | Liste des cibles |
| `make test` | Tests backend (`./mvnw verify` : unitaires et intégration) et frontend (`npm test`) |
| `make lint` | ESLint et vérification de types du frontend, compilation du backend |
| `make e2e` | Tests Playwright (application démarrée ; installe Chromium au premier lancement) |
| `make labs-test` | Tests des laboratoires présents dans `labs/` (labs absents ou sans tests ignorés) |
| `make labs-offline` | Mêmes tests sans clé API, en mode `--offline`, plus une exécution de fumée de `neoagent` |
| `make down` | Arrête la stack docker (les volumes sont conservés) |
| `make regression-on` / `make regression-off` | Injecte ou retire la régression du TP J07 |

Dans `backend/` : `./mvnw test` (tests unitaires seuls), `./mvnw verify` (tous les tests, rapports JaCoCo dans `target/site/`). Dans `frontend/` : `npm run dev`, `npm run lint`, `npm test`, `npm run build`, `npm run test:coverage`. Dans `e2e/` : `npx playwright test`, `npx playwright test --list`.

## Organisation du dépôt

```
neoflow/
├── backend/           API Spring Boot (code, migrations Flyway, tests)
├── frontend/          SPA React + TypeScript (Vite)
├── e2e/               tests Playwright
├── docs/              architecture, ADR, spécifications, tickets des variantes
├── labs/              outils IA à coder du J3 au J10 (spec, agent, rag, mcp, tests-ia, legacy-ia, workflow, evals)
│                      et régression J07
├── scripts/           régression J07, tests des labs (labs.sh), initialisation du dépôt
├── docker-compose.yml, Makefile, .env.example
└── .github/workflows/ci.yml   build et tests
```

## Règles du projet

- Données fictives uniquement ; aucune donnée ni aucun compte client.
- Aucun secret dans le dépôt : `.env` est ignoré, seul `.env.example` est versionné. Votre clé API Anthropic reste dans votre environnement.
- Le module `backend/.../legacy/` et `frontend/src/legacy/` n'est pas modifié avant le J8.
- Toute évolution du schéma passe par une nouvelle migration Flyway (`V3__...`), jamais par la modification de `V1` ou `V2`.
