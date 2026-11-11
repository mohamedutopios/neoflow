# Tâches de la mesure avant / après (J1 → J10)

La comparaison n'a de valeur que si les deux tâches sont **équivalentes** et mesurées **de la même façon**. Ce document fige les deux énoncés, la grille d'équivalence et le protocole.

## Tâche baseline du J1 (figée, ne pas modifier)

> Ajouter l'endpoint `GET /api/demandes/statistiques` qui renvoie le nombre de demandes par statut, avec son test.

Réalisée en J1 avec OpenCode, sans toolbox (pas d'`AGENTS.md`, ni Rules, ni Skills), mesurée dans `ia-toolbox/metrics/baseline.md`. Pour la comparaison, sa session est convertie en fiche normalisée par l'annexe OpenCode (`solutions/annexe-opencode/mesure/analyse_session.py --format fiche`).

## Tâche rejouée en J10 (équivalente)

> Ajouter l'endpoint `GET /api/demandes/statistiques/types` qui renvoie le nombre de demandes par type, avec ses tests.

Réalisée avec **vos outils** : spécification par l'assistant du J3, implémentation par `neoagent --mode structure --pattern generator_verifier` (J4), outil RAG (J5) si utile, tests et scans. Le cas `regression_prompts/NA06_tache_statistiques_types.yaml` en donne une version automatisée.

## Critères d'acceptation communs

Ceux du corrigé formateur de la baseline (J01, `solutions/tache_baseline/`), transposés du statut au type :

| Id | J1 — par statut | J10 — par type | Vérification |
|---|---|---|---|
| A1 | `GET /api/demandes/statistiques` : 200 en JSON pour tout utilisateur authentifié | `GET /api/demandes/statistiques/types` : idem | test IT |
| A2 | `{"total": n, "parStatut": {"BROUILLON": n, …}}` | `{"total": n, "parType": {"GENERIQUE": n, "CONGES": n, …}}` | test IT |
| A3 | les 5 statuts toujours présents, 0 si aucune demande | les 11 types toujours présents, 0 si aucune demande | test unitaire |
| A4 | comptage en base (`GROUP BY`), pas de `findAll()` en mémoire | idem | revue du diff |
| A5 | 401 sans authentification | idem | test IT |
| A6 | aucune nouvelle dépendance, aucun test existant modifié ou supprimé, `./mvnw verify` vert | idem | `git diff --stat`, build |

Les tests d'intégration du socle (`*IT`, plugin failsafe) ne tournent qu'avec `./mvnw verify` ; `./mvnw test` ne lance que les `*Test`. Un `-Dtest='DemandeStatistiques*'` ciblé remplace les inclusions de surefire et exécute aussi les `*IT` correspondants : pratique pendant le développement, insuffisant comme preuve finale.

## Grille d'équivalence

| Dimension | J1 (par statut) | J10 (par type) | Équivalent ? |
|---|---|---|---|
| Couches touchées | repository, service, contrôleur, DTO, test | identiques | oui |
| Requête | agrégation `group by statut` | agrégation `group by type` | oui |
| Cardinalité du résultat | 5 statuts | 11 types | proche (plus de cas à zéro) |
| Sécurité | authentification HTTP Basic, tous rôles | identique | oui |
| Critères d'acceptation communs | réponse JSON typée ; valeurs à 0 présentes ; 401 sans authentification ; test d'intégration | identiques | oui |
| Connaissance préalable | aucune | **le patron J1 existe dans le dépôt** | **non** : biais en faveur du J10 |
| Expérience de l'outil | première utilisation d'OpenCode en agent | dix jours de pratique, outil codé soi-même | **non** : biais d'apprentissage |
| Outil | assistant du marché (OpenCode) | votre agent (`neoagent`) | **non** : on compare deux outillages, pas seulement deux pratiques |

Les deux écarts non équivalents ne se corrigent pas, ils se **déclarent** dans le rapport et se réduisent par le protocole ci-dessous.

## Protocole

1. **Même point de départ** : rejouer la tâche J10 dans un worktree créé depuis le commit de départ du J1 (`git worktree add ../neoflow-j10 <commit-J1>`), puis installer la toolbox par `ia-toolbox/install.sh ../neoflow-j10` (configuration J1–J2 et labs). Le patron par statut n'existe alors pas : le biais de connaissance préalable disparaît (pas celui d'apprentissage).
2. **Même critère de fin** : PR prête, tests verts, revue humaine faite. Le chrono démarre à la lecture du ticket et s'arrête à l'ouverture de la PR.
3. **Même instrumentation** : J1, export OpenCode (parent et sous-agents) converti en fiche ; J10, journal `neoagent` complet (`--journal`) ; dans les deux cas, journal humain `*.reprises.yaml` tenu pendant la tâche et métriques Git/CI de la branche. Coût recalculé des deux côtés par `couts.py` depuis les tokens.
4. **Même modèle** si possible (`claude-sonnet-5-5` pour l'agent ; noter l'identifiant exact), même poste.
5. **Plusieurs exécutions** si le budget le permet (`NA06` en `--reel --repetitions 3`) : une mesure unique (n = 1) donne un ordre de grandeur, pas une preuve.

## Ce qui se mesure

| Indicateur | Définition opérationnelle | Source |
|---|---|---|
| Délai bout en bout | lecture du ticket → PR ouverte, tests verts | journal (`debut`, `fin`) |
| Temps de reprise manuelle | somme des minutes passées à corriger, relancer, relire, déboguer à la main | journal (`reprises`) |
| Reprises humaines | nombre d'interventions, par type | journal + relances dans la session |
| Défauts | défauts trouvés avant PR (revue, tests, sous-agent) et après PR (pair, CI, recette) | journal (`defauts`) |
| Couverture | couverture de lignes et de branches, commentée sur les lignes nouvelles | JaCoCo (`target/site/jacoco/` unitaires, `target/site/jacoco-it/` intégration, après `./mvnw verify`), Vitest |
| Tokens et coûts | `input_tokens`, `output_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens` par modèle ; coût par formule | journal `neoagent` (`usage` de l'API) ; fiche J1 (annexe OpenCode) ; `couts.py` |
| Métriques Git/CI | commits, correctifs, taille, part de tests, runs CI verts du premier coup | `metriques_git.py` |
