# Lab J04 — `neoagent`, agent de développement NeoFlow

Agent de développement codé en Python avec l'API Claude (tool use) : boucle observation → décision → action, six patterns agentiques, worktrees Git, garde-fous dans le code et journal de trajectoire. Les labs J05 (outil RAG), J06 (outils MCP), J09 et J10 (évaluations, coûts) s'y branchent par le contrat ci-dessous.

## Démarrer

```bash
cd labs/agent
uv sync                                   # Python 3.11+, SDK anthropic 1.x, pytest
uv run pytest                             # tests hors ligne : aucun appel à l'API, aucune clé nécessaire
uv run neoagent --repo ../.. --tache "Où est calculé le niveau de validation ?" --offline
```

Avec le modèle réel (clé personnelle fournie par Neosoft, jamais écrite dans un fichier) :

```bash
export ANTHROPIC_API_KEY=...              # lue par le SDK
uv run neoagent --repo ../../../neoflow-conges-back --ecriture --pattern generator_verifier \
  --tache "Implémente la tâche T04 de docs/specs/conges/PLAN_TACHES.md (CalendrierConges)" \
  --verificateur "./mvnw -q test -Dtest=CalendrierCongesTest" --journal traj-T04.jsonl
```

Sans `--approbation`, la validation est demandée dans le terminal (`interactif`) ; hors terminal, tout est refusé (`refus`). `accord` est réservé aux tests et aux sandbox jetables.

## Contrat (labs/agent/README.md, section Contrat)

| Élément | API |
|---|---|
| Outil | `Tool(name, description, input_schema, handler, risque="lecture"\|"ecriture"\|"execution", apercu=None)` ; `handler(dict) -> str` |
| Outils de base | `outils_de_base(repo, politique)` : `lire_fichier`, `chercher`, `lister`, `editer_fichier`, `executer_commande` (allowlist), `git_diff` |
| Politique | `Politique(racine, lecture_seule=True, commandes_autorisees, chemins_interdits, chemins_ecriture, chemins_proteges, timeout_commande_s, …)` ; préréglages `Politique.lecture`, `Politique.generateur`, `Politique.redacteur_tests` |
| Agent | `Agent(tools, modele="claude-sonnet-5-5", max_etapes=30, budget_tokens=200_000, approbateur=Approbateur(...), journal=Journal(path), offline=False)` ; `executer(tache) -> Resultat` ; `poursuivre(message) -> Resultat` |
| Résultat | `Resultat(statut, reponse, etapes, usage, session, appels_outils)` ; statut : `termine`, `etapes_max`, `budget_atteint`, `timeout`, `boucle`, `refus_modele`, `erreur` |
| Approbation | `Approbateur("interactif" \| "refus" \| "accord")` avant tout outil `ecriture` ou `execution`, et avant un commit |
| Journal | JSONL, une ligne par événement : `ts, session, etape, type (llm, tool_call, tool_result, approbation, erreur, fin), outil, entree, sortie_extrait, usage {input_tokens, output_tokens, cache_read_input_tokens, cache_creation_input_tokens}, modele` (`cache_creation_input_tokens` = 0 hors ligne) ; relecture `lire_journal(path)` |
| Patterns | `neoagent/patterns/` : `react`, `plan_execute`, `routing`, `generator_verifier`, `evaluator_optimizer`, `orchestrator_workers` |
| Sous-agents | `outil_sous_agent(nom, description, fabrique)` ; rôles prêts : `roles.outil_redacteur_tests(wt, approbateur=…)`, `roles.outil_relecteur(wt)` |
| Mesure | `usage_total(lire_journal(path))` : somme des lignes `llm` (une session poursuivie écrit plusieurs lignes `fin` cumulées) |
| Vérificateurs | `verificateur_maven(cible=None, integration=None)`, `verificateur_vitest()`, `verificateur_perimetre(base)`, `VerificateurCommande(cmd)`, `tous(...)` |
| CLI | `uv run neoagent --repo CHEMIN --tache "..." [--pattern …] [--mode vibe\|structure] [--offline] [--script scenario.json] [--journal traj.jsonl] [--outils-externes module:fonction] [--outils-config CHEMIN] [--ecriture] [--approbation …] [--verificateur "cmd"] [--commit "message"]` |
| Extension | `--outils-externes labs/rag/agent_tool.py:rag_tool` (J05), `--outils-externes …:outils_mcp --outils-config …` (J06) ; la fonction renvoie un `Tool` ou une liste |

## Garde-fous (dans le code, pas dans le prompt)

| Borne | Où | Effet |
|---|---|---|
| Chemins limités au worktree | `Politique.resoudre` | `..`, chemins absolus, liens symboliques sortants : refus |
| Chemins interdits | `chemins_interdits` | `.env*`, `.git`, `*secrets*`, clés : refus même en lecture |
| Lecture seule par défaut | `Politique(lecture_seule=True)` | aucune écriture, seules les commandes Git de lecture |
| Tests et spécification protégés | `Politique.generateur` | le générateur n'écrit ni `src/test`, ni `*.test.tsx`, ni `docs/specs`, ni le legacy, ni `pom.xml` |
| Allowlist de commandes | `verifier_commande` | préfixe de jetons, sans shell, sans `; && \| > $()`, sans secrets dans l'environnement |
| Approbation humaine | `Approbateur` | avant toute écriture, exécution et commit |
| Étapes, budget, délai | `Agent(max_etapes, budget_tokens, timeout_s)` | arrêt motivé, statut explicite |
| Détection de boucle | `Agent(seuil_boucle=3)` | même appel trois fois de suite : arrêt |
| Journal | `Journal` | chaque appel, résultat, refus et approbation, avec l'usage en tokens |

## Mode hors ligne

`--offline` remplace Claude par `ModeleSimule` : soit l'explorateur par défaut (lister, chercher, lire, diff, conclure, sans rien modifier), soit un scénario JSON rejoué (`--script scenarios/gv_registre.json`). L'usage en tokens est estimé et le cache simulé, pour tester les budgets. C'est aussi le plan B des démonstrations.

## Tests

```bash
uv run pytest                                                       # hors ligne, < 10 s
NEOAGENT_TESTS_MAVEN=1 NEOFLOW_RACINE=../.. uv run pytest -m maven   # Generator–Verifier réel avec Maven (1 à 2 min)
NEOAGENT_MVN="mvn -o" …                                             # Maven hors ligne si le wrapper ne peut rien télécharger
```

## Fichiers

```
neoagent/  tools.py  garde_fous.py  approbation.py  journal.py  modele.py  agent.py
           verificateurs.py  worktrees.py  sous_agents.py  roles.py  cli.py
           patterns/{react,plan_execute,routing,generator_verifier,evaluator_optimizer,orchestrator_workers}.py
scenarios/ scénarios JSON du modèle simulé (démos, tests)
scripts/   verifier-perimetre.sh (vérificateur de diff, aussi en CI), worktree-feature.sh (create, run détaché, status, remove)
tests/     pytest, hors ligne sauf test_maven.py
```

## Ce que vous codez au J4 (blocs `TODO-J04`)

Ce dossier est le **starter** : sept blocs de fonctions lèvent `NotImplementedError("TODO-J04 …")`. Les tests qui les
couvrent échouent tant qu'elles ne sont pas écrites ; les autres passent déjà.

| TODO | Fichier | Tests qui doivent passer | TP |
|---|---|---|---|
| `garde-fous-chemins` | `neoagent/garde_fous.py` : `resoudre`, `verifier_ecriture` | `tests/test_garde_fous.py::TestChemins`, `TestEcriture` | TP 1 |
| `garde-fous-commandes` | `neoagent/garde_fous.py` : `verifier_commande` | `tests/test_garde_fous.py::TestCommandes`, `tests/test_tools.py` | TP 1 |
| `boucle-tool-use` | `neoagent/agent.py` : `Agent._boucle` | `tests/test_agent.py` | TP 1 |
| `verificateur` | `neoagent/verificateurs.py` : `VerificateurCommande.__call__` | `tests/test_patterns.py -k verificateur` | TP 2 |
| `generator-verifier` | `neoagent/patterns/generator_verifier.py` | `tests/test_patterns.py -k generator`, `tests/test_maven.py` | TP 2 |
| `sous-agents` | `neoagent/roles.py` : `outil_redacteur_tests`, `outil_relecteur` | `tests/test_roles.py` | TP 2 |
| `orchestrateur` | `neoagent/patterns/orchestrator_workers.py` : `orchestrer` | `tests/test_patterns.py -k orchestrator` | TP 3 |

```bash
uv run pytest tests/test_garde_fous.py -x      # avancer TODO par TODO
uv run pytest                                  # tout vert : votre agent est prêt pour le TP fil rouge
```

Corrigé : `supports-nssplus/J04_agent_dev_patterns/solutions/labs/agent/` (à ouvrir après le TP).
