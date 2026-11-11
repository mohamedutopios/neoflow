# Exemples de mesure (fictifs)

Fichiers **fictifs mais cohérents entre eux**, pour faire tourner le banc sans clé ni appel API. Les journaux `neoagent` suivent le contrat du J4 (labs/agent/README.md) ; la fiche J1 a été produite par l'annexe OpenCode à partir d'un export d'exemple au format observé sur OpenCode 1.19.

| Fichier | Contenu |
|---|---|
| `j01_baseline_opencode.fiche.json` | baseline J1 (OpenCode, sans toolbox) en fiche normalisée, reprises et défauts inclus |
| `j10_structure_stat_types.jsonl` + `.reprises.yaml` | tâche équivalente J10 : `neoagent --mode structure --pattern generator_verifier`, approbations humaines, évaluateur Opus |
| `extension_vibe.jsonl` + `.reprises.yaml` + `.controles.json` | extension CONGES « calendrier d'équipe » en mode vibe, relevé des 6 défauts, contrôles |
| `extension_structure.jsonl` + `.reprises.yaml` + `.controles.json` | même extension en mode structuré (spec J3, Generator–Verifier, tests, E2E, Semgrep) |
| `jacoco_exemple.xml`, `gh_runs_exemple.json` | entrées de `metriques_git.py` |
| `tarifs_fictifs.yaml` | **tarifs fictifs par modèle** (unités arbitraires « UC ») : aucun prix réel |

Attendus (`--tarifs mesure/exemples/tarifs_fictifs.yaml`) :
- J1 → J10 : délai 46 → 27 min, reprise manuelle 21 → 14 min (dont 5 min d'approbations), défauts avant PR 3 → 1, tokens 500 210 → 116 585, coût 0,1121 → 0,0477 UC. Le coût J10 est **sous-estimé** : le journal ne contient pas `cache_creation_input_tokens`.
- vibe → structure : délai 24 → 47 min, défauts 6 → 1, tests ajoutés 0 → 4, Semgrep KO → OK, coût 0,0140 → 0,0667 UC.
