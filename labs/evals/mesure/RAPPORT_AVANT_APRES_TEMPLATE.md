# Rapport avant / après — <variante> — <pseudonyme>

> Copier dans `ia-toolbox/metrics/RAPPORT_AVANT_APRES.md`. Chaque chiffre renvoie à sa preuve (fichier versionné ou commande rejouable). Une case vide vaut mieux qu'un chiffre inventé.

## 1. Ce qui est comparé

| | Avant (J1) | Après (J10) |
|---|---|---|
| Tâche | `GET /api/demandes/statistiques` par statut, avec son test | `GET /api/demandes/statistiques/types` par type, avec ses tests |
| Configuration | OpenCode <version>, agent build, sans toolbox | vos outils : spec (J3), `neoagent` <version> (pattern, mode), outil RAG, tests-ia |
| Modèle(s) | `anthropic/…` | `anthropic/…` (+ sous-agents : …) |
| Point de départ | commit `<sha>` | worktree depuis `<sha>` + `install.sh` (oui / non) |
| Traces | session OpenCode `ses_…` (+ enfants) → `….fiche.json` | journal `neoagent` `….jsonl` (session `na-…`) |
| Preuves | `metrics/…fiche.json`, `….reprises.yaml` | `metrics/….jsonl`, `….reprises.yaml`, `….controles.json`, `resultats/<label>.json` |

## 2. Résultats

| Indicateur | Avant | Après | Écart | Preuve |
|---|---|---|---|---|
| Délai bout en bout (min) | | | | journal |
| Temps de reprise manuelle (min) | | | | journal |
| Reprises humaines (nombre, par type) | | | | journal, relances |
| Défauts avant PR / après PR | | | | journal, revue, CI |
| Tests ajoutés (unitaires / API / E2E) | | | | `git diff --stat`, rapports |
| Couverture lignes / branches (lignes nouvelles commentées) | | | | JaCoCo, Vitest |
| Étapes, appels LLM, appels d'outils, tests lancés par l'agent | | | | `mesurer.py` |
| Approbations humaines (temps passé) | — | | | journal, reprises |
| `input_tokens` / `output_tokens` / `cache_read` / `cache_creation` | | | | `mesurer.py` (usage de l'API) |
| Coût par formule, par modèle | | | | `--tarifs`, date du relevé : |
| CI verte du premier coup | | | | `metriques_git.py --ci-json` |

Formule de coût utilisée :

```
coût = (input × p_input + output × p_output + cache_read × p_cache_read + cache_write × p_cache_write) / 1 000 000
p_* : page tarifs <URL>, relevée le <date>, modèle <id exact>
```

## 3. Vibe ou structuré (extension de la variante)

| Indicateur | Vibe | Structuré | Preuve |
|---|---|---|---|
| Délai (spécification comprise) | | | journaux humains |
| Défauts relevés | | | relevé, revue |
| Tests ajoutés, contrôles (verify, E2E, Semgrep, Gitleaks) | | | `….controles.json` |
| Tokens et coût | | | `mesurer.py` |

## 4. Évaluations rejouées

| Évaluation | J5 / référence | J10 | Lecture |
|---|---|---|---|
| RAG `eval.py` : Recall@5 / MRR / latence p95 (mode retenu) | | | |
| Régression NA01–NA06, PS01, PT01 (+ vos cas), offline et réelle | | | |
| Écarts après changement de configuration (`--reference`) | | | |

## 5. Biais de mesure

| Biais | Présent ? | Effet probable | Ce qui a été fait pour le réduire |
|---|---|---|---|
| Apprentissage (J1 = découverte de l'outil) | | en faveur du J10 | |
| Tâche non équivalente (patron déjà écrit, cardinalité) | | | |
| Variance du modèle (n = 1 ou 3) | | | |
| Effet d'observation (chrono, journal) | | | |
| Petits échantillons, une seule variante | | | |
| Coût de construction des outils non compté (J3–J9) | | en faveur du J10 | |
| Outils différents (OpenCode / neoagent : prompts système, nombre d'outils) | | | |
| Champs d'usage manquants (`cache_creation_input_tokens`) | | coût J10 sous-estimé | |
| Autre : | | | |

## 6. Conclusion

- **Gains constatés** (avec leur ordre de grandeur et leur preuve) :
- **Coûts et limites** (ce qui coûte plus, ce qui n'a pas marché, ce qui reste manuel) :
- **Ce qu'on peut affirmer / ce qu'on ne peut pas affirmer** avec ces mesures :
- **Recommandation pour une mission** (quand utiliser la toolbox, quand s'en passer) :
