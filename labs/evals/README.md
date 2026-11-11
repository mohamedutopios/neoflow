# labs/evals — Évaluer et mesurer VOS outils IA (J10)

Ce laboratoire Python répond à la question du dossier de preuves : **qu'ont réellement apporté les outils que vous avez codés (J3–J9), à quel coût, avec quelles limites ?** Il évalue `neoagent` (J4) et les autres outils (assistant de spécification J3, RAG J5, générateur de tests J7), à partir de ce qu'ils journalisent et de ce que renvoie l'API.

| Besoin | Outil | Données |
|---|---|---|
| Le RAG retrouve-t-il les bons fichiers ? | `labs/rag/eval.py` (J05) sur `rag_questions.yaml` | index du J05 |
| Vos prompts et vos agents se comportent-ils toujours comme prévu ? | `run_regression.py` + `regression_prompts/*.yaml` | journal JSONL de `neoagent`, sorties des outils |
| Vibe ou structuré : que gagne-t-on, que perd-on ? | `mesure/mesurer.py` + `mesure/controles_qualite.py` | deux journaux, deux worktrees |
| Avant (J1, OpenCode) / après (J10, vos outils) | `mesure/mesurer.py` | fiche J1 (annexe OpenCode) + journal J10 |
| Tokens et coûts | `couts.py` | champ `usage` des réponses de l'API, tarifs datés |
| Ce que voit l'équipe : Git, couverture, CI | `mesure/metriques_git.py` | Git, JaCoCo, Vitest, `gh run list` |
| Traces, latences et coûts des labs | `docker-compose.langfuse.yml`, `mesure/langfuse_labs.py` | Langfuse auto-hébergé |

```
labs/evals/
├── trajectoire.py          lecture tolérante du journal neoagent (contrat neoagent)
├── couts.py                coût = Σ usage × prix / 10⁶, par modèle, tarifs datés (aucun prix codé)
├── criteres.py             critères vérifiables, extensibles par --criteres-externes
├── run_regression.py       régression offline / réelle / rejeu, variance, comparaison à une référence
├── regression_prompts/     cas NA01–NA06 (neoagent), PS01 (spec J3), PT01 (tests-ia J7), fixtures, enregistrements
├── mesure/                 mesurer.py, controles_qualite.py, metriques_git.py, langfuse_labs.py,
│                           tarifs.example.yaml, TACHES_AVANT_APRES.md, RAPPORT_AVANT_APRES_TEMPLATE.md, exemples/
├── tests/                  pytest (faux neoagent et faux assistant de spec : aucun appel API)
├── rag_questions.yaml      jeu de référence du J05 (propriété du J05)
└── docker-compose.langfuse.yml
```

## Démarrage (sans clé, sans appel API)

```bash
cd labs/evals
uv run --group dev pytest                                    # 21 tests
uv run run_regression.py --rejouer regression_prompts/exemples_runs/config-A --label config-A
uv run run_regression.py --rejouer regression_prompts/exemples_runs/config-B --label config-B \
    --reference resultats/config-A.json                      # code 1 : NA05 a régressé
uv run mesure/mesurer.py mesure/exemples/extension_vibe.jsonl mesure/exemples/extension_structure.jsonl \
    --label vibe --label structure --tarifs mesure/exemples/tarifs_fictifs.yaml
uv run mesure/mesurer.py mesure/exemples/j01_baseline_opencode.fiche.json mesure/exemples/j10_structure_stat_types.jsonl \
    --label "J1 (OpenCode)" --label "J10 (neoagent)" --tarifs mesure/exemples/tarifs_fictifs.yaml
```

## Le contrat lu par le banc

Journal de trajectoire de `neoagent` (J4), une ligne JSON par événement :

```json
{"ts": "2026-11-04T11:20:08.568+01:00", "session": "na-aa2de86b", "etape": 1, "type": "llm",
 "outil": null, "entree": null, "sortie_extrait": null, "modele": "claude-sonnet-5-5",
 "usage": {"input_tokens": 4329, "output_tokens": 333, "cache_read_input_tokens": 0}}
```

| `type` | Utilisé pour |
|---|---|
| `llm` | appels au modèle, `usage` et `modele` : tokens et coût par modèle |
| `tool_call` / `tool_result` | trajectoire : outil, entrée, résultat (`entree.is_error`, « REFUS GARDE-FOU », « REFUS HUMAIN »), durée |
| `approbation` | validation humaine, journalisée entre `tool_call` et `tool_result` (`entree.accordee`, motif) |
| `erreur`, `fin` | refus des garde-fous ; statut final (`entree.statut` : termine, etapes_max, budget_atteint…), réponse, usage cumulé |

Le lecteur tolère : horodatage ISO ou epoch, plusieurs sessions dans un fichier, un **dossier** de journaux (workers d'un orchestrateur), lignes de log parasites, types inconnus. Il signale ce qui fausse la mesure, en particulier l'**absence de `cache_creation_input_tokens`** : le champ fait partie du contrat neoagent (ajouté en cours de parcours) et l'écriture du cache est facturée, au prix `cache_write` ; un journal plus ancien sans ce champ est accepté, mais son coût est sous-estimé (avertissement). Les journaux d'exemple, produits avant l'ajout, en donnent l'illustration. Journalisez le `usage` complet de la réponse de l'API.

CLI de `neoagent` utilisée (J4) : `uv run neoagent --repo CHEMIN --tache "..." [--pattern P] [--mode vibe|structure] [--offline] [--journal traj.jsonl] [--ecriture] [--approbation interactif|refus|accord] [--outils-externes module:fonction]`. Sans `--ecriture`, l'agent est en lecture seule ; hors terminal, `--approbation` vaut `refus`. Le banc passe `--ecriture --approbation accord` aux cas qui écrivent (`worktree: true`), toujours dans un worktree jetable : les approbations restent journalisées. Avec le pattern `generator_verifier`, les verdicts du vérificateur (Maven) sont dans le **rapport JSON** imprimé par la CLI, pas dans le journal : le banc le lit sur la sortie standard (`runN.stdout.txt`) ; pour une mesure, sauvegardez-le en `X.rapport.json` à côté du journal. Si votre CLI diffère, passez un gabarit : `--neoagent-cmd "..."` ou `NEOAGENT_CMD`, marqueurs `{repo} {tache} {pattern} {mode} {journal} {offline} {ecriture} {approbation} {outils_externes} {agent_dir}`.

## Régression des prompts et des comportements

```bash
uv run run_regression.py --filtre 'NA0*' --label offline-1.4                        # défaut : --offline
uv run run_regression.py --reel --repetitions 3 --worktree --label reel-1.4          # API Claude, coûte
uv run run_regression.py --reel --repetitions 3 --worktree --label reel-1.5-rc --reference resultats/reel-1.4.json
uv run run_regression.py --rag-questions rag_questions.yaml --filtre 'RAG-Q0*' --reel  # jeu du J05 via l'outil RAG
uv run run_regression.py --criteres-externes mes_criteres --label perso               # vos propres critères
```

| Mode | Ce qui tourne | Ce qu'il prouve |
|---|---|---|
| offline (défaut) | vos outils avec `--offline` (modèle simulé déterministe) | plomberie, gabarits de prompts, formats de sortie, outils, garde-fous codés ; gratuit, en CI |
| `--reel` | vos outils avec l'API Claude | comportement du modèle avec vos prompts ; variance : `--repetitions 3` minimum |
| `--rejouer DOSSIER` | rien : réévaluation d'enregistrements | tester un nouveau critère sans repayer les runs |

Deux familles de cas (format : [`regression_prompts/README.md`](regression_prompts/README.md)) :
- `outil: neoagent` : la tâche est passée à `neoagent` ; critères sur la trajectoire (outil appelé ou interdit, approbation avant écriture, tests après la dernière écriture, boucle Generator–Verifier, statut de fin), la réponse, le diff et des commandes de contrôle ;
- `outil: commande` : toute autre CLI ; critères sur le code de retour, la sortie ou un fichier produit (`fichier_sortie`), les fichiers écrits, des commandes de contrôle (marqueurs `{dossier}`, `{repo}`, `{journal}`) et le journal d'usage s'il existe. PS01 rejoue `neospec chaine --type CONGES --reponses labs/spec/exemples/reponses_CONGES.yaml --racine {repo} --journal {journal} --max-corrections 2 [--offline]` (J3, écrit dans le worktree) ; PT01 rejoue `labs/tests-ia/tests-ia generer --projet backend --classe com.neosoft.neoflow.validation.CircuitValidationService --spec labs/tests-ia/specs/circuit-validation.md --sortie {dossier} --journal {journal} --sans-mutation [--offline]` (J7). Lanceurs adaptables par `SPEC_CMD` et `TESTS_IA_CMD`. Vérifiés le 2026-11-04 hors ligne contre les corrigés du J3 et du J7 : 1/1 chacun (spécification EN REVUE et `neospec valider` vert ; 4 tests ACCEPTE).

Lecture des résultats : `réussis/n`, verdict selon le seuil (fraction exacte `"2/3"`), borne basse de Wilson à 95 %, médianes de tokens et d'appels, et, avec `--reference`, `REGRESSION`, `BAISSE`, `AMELIORATION`, `STABLE_OK`, `KO_PERSISTANT` avec les critères dont le taux a changé. Code de sortie 1 en cas de régression : utilisable en CI (offline à chaque PR, réel en tâche planifiée).

## Vibe ou structuré

```bash
# 1. Deux worktrees depuis le même commit
git worktree add ../wt-vibe HEAD && git worktree add ../wt-structure HEAD
# 2. Même extension, deux modes (l'approbateur reste actif : vous validez ou refusez chaque écriture)
uv run --project labs/agent neoagent --repo ../wt-vibe --mode vibe --pattern react --ecriture --approbation interactif \
    --tache "Ajoute un calendrier d'équipe des absences" --journal ia-toolbox/metrics/extension_vibe.jsonl
uv run --project labs/agent neoagent --repo ../wt-structure --mode structure --pattern generator_verifier \
    --ecriture --approbation interactif --tache "Implémente docs/specs/CONG-EXT-CALENDRIER.md" \
    --journal ia-toolbox/metrics/extension_structure.jsonl > ia-toolbox/metrics/extension_structure.rapport.json
# 3. Mêmes contrôles sur les deux résultats
(cd ../wt-vibe && uv run --project ../neoflow/labs/evals ../neoflow/labs/evals/mesure/controles_qualite.py \
    --base main --sortie ../neoflow/ia-toolbox/metrics/extension_vibe.controles.json)
# 4. Comparaison (journaux de reprises extension_*.reprises.yaml tenus pendant les deux sessions)
uv run --project labs/evals labs/evals/mesure/mesurer.py ia-toolbox/metrics/extension_vibe.jsonl \
    ia-toolbox/metrics/extension_structure.jsonl --label vibe --label structure --tarifs labs/evals/mesure/tarifs.yaml
```

Sur l'exemple fourni (fictif) : le mode vibe livre en 24 min un prototype à 0,014 UC, avec 6 défauts relevés, aucun test ajouté et un Semgrep KO ; le mode structuré prend 47 min (spécification comprise) et coûte 0,067 UC, avec un défaut mineur, 4 fichiers de tests et tous les contrôles verts.

## Mesurer une tâche, comparer à la baseline du J1

- **Après (J10)** : le journal `neoagent` de la tâche, plus le journal humain `X.reprises.yaml` (début, fin, reprises typées et minutées, défauts avec leur phase, couverture) et éventuellement `X.controles.json`.
- **Avant (J1)** : la baseline a été réalisée avec OpenCode. Sa mesure se fait avec l'annexe `J10_mesure_demos/solutions/annexe-opencode/` (`analyse_session.py --format fiche`), qui produit une **fiche normalisée** `X.fiche.json` lue ici comme un journal.
- **Coût** : `couts.py` recalcule les deux à méthode égale, depuis les tokens et les tarifs de `mesure/tarifs.yaml` (recopiés depuis la page tarifs, datés), sans utiliser le coût affiché par un outil.

Définition des tâches et protocole : `mesure/TACHES_AVANT_APRES.md` ; gabarit de rapport : `mesure/RAPPORT_AVANT_APRES_TEMPLATE.md`.

## Langfuse pour les laboratoires

```bash
docker compose -f docker-compose.langfuse.yml up -d          # ou podman compose ; LANGFUSE_PORT=3100 si 3000 est pris
curl -s http://localhost:3000/api/public/health              # {"status":"OK","version":"3.227.0"}
export LANGFUSE_HOST=http://localhost:3000 LANGFUSE_PUBLIC_KEY=pk-lf-neoflow-lab LANGFUSE_SECRET_KEY=sk-lf-neoflow-lab
uv run --extra langfuse mesure/langfuse_labs.py verifier
uv run --extra langfuse mesure/langfuse_labs.py journal ia-toolbox/metrics/*.jsonl --tag J10 --tarifs mesure/tarifs.yaml
uv run --project ../rag --with "langfuse>=3" python mesure/langfuse_labs.py rag \
    --questions rag_questions.yaml --modes hybrid,bm25 -k 5 --label chunking-ast
```

- `journal` : une trace par session `neoagent`, une `generation` par appel LLM (modèle, usage, coût par formule), un `tool` par appel d'outil, les approbations en événements, les refus en avertissement.
- `rag` : chaque recherche du jeu J05 en observation `retriever`, avec scores `recall_at_k` et `rr`.
- Workflow LangGraph du J09 : `CallbackHandler` de `langfuse.langchain`, une ligne (`config={"callbacks": [CallbackHandler()]}`).
- Vérifié le 2026-11-04 (Podman 5, Langfuse 3.227.0, SDK Python 5.1.0) : traces, coûts et scores visibles par l'API publique. Les images `minio/minio` ne sont plus téléchargeables (image Chainguard épinglée par digest, bucket créé par `minio-init`) ; le SDK 5.x envoie les scores en lot, format refusé par un serveur 3.x : le script les poste un par un.

## Confidentialité et coûts

Aucun appel réel n'a lieu sans `--reel` (ou sans lancer vous-même vos outils hors `--offline`). Les runs bruts (`resultats/runs/`) contiennent du code et des sorties d'outils : ils sont ignorés par Git. Les journaux de missions clientes ne vont que dans une instance Langfuse autorisée par la politique d'usage IA.
