# Lab J03 — `neospec`, assistant de spécification NeoFlow

> **Starter.** Dix fonctions clés sont à écrire pendant les TP du J03 ; chacune lève `NotImplementedError` et ses tests échouent tant qu'elle n'est pas faite (56 des 58 tests au départ). Le reste (CLI, rendu, modèle simulé, schémas, prompts, fixtures) est fourni. Corrigé : `J03_spec_driven/solutions/labs/spec/`.
>
> | TP | Fonctions | Tests |
> |---|---|---|
> | TP 1 | `llm.ClientClaude.json`, `questions.extraire_questions`, `arbitrage.appliquer_reponses`, `arbitrage.verifier_porte_1` | `tests/test_tp1_*.py` |
> | TP 2 | `validation.gherkin.valider_features`, `steps_java.expression_cucumber` | `tests/test_tp2_*.py` |
> | TP 3 | `validation.openapi.valider_contrat`, `validation.tracabilite.verifier_matrice` | `tests/test_tp3_*.py` |
> | TP fil rouge | `generation.generer`, `correction.boucle_correction` | `tests/test_fr_*.py`, `tests/test_chaine_offline.py` |
>
> Les tests du TP fil rouge et de la chaîne utilisent aussi les fonctions des TP 1 à 3 : faites les TP dans l'ordre. `uv run pytest tests/test_tp1_arbitrage.py` pour un seul fichier ; `grep -rn "TODO TP" neospec` pour la liste.

Assistant en Python qui transforme un ticket ambigu en spécification vérifiable, en appelant l'API Claude avec des sorties structurées, puis vérifie le résultat par des contrôles déterministes.

```
ticket ──1──> questions + hypothèses ──2──> décisions humaines ──3──> exigences, Gherkin, delta OpenAPI,
(docs/tickets)  (JSON Schema, Opus)       (porte 1, YAML ou           matrice, plan, ADR (JSON Schema, Sonnet)
                                           mode interactif)                         │
                                                         ┌──────────────4───────────┘
                                                         ▼
                          validation : parseur Gherkin, validateur OpenAPI, traçabilité
                          échec → correction par le modèle, au plus N tours (boucle bornée)
                                                         │
                                                         └──5──> squelettes de steps Cucumber-JVM (Java)
```

| Étape | Module | Modèle | Contrôle déterministe |
|---|---|---|---|
| 1. Questions | `questions.py` | `claude-opus-5-5`, effort `high` | schéma local strict, identifiants Q-xx / H-xx |
| 2. Arbitrage | `arbitrage.py` | aucun | porte 1 : chaque question tranchée par un humain nommé |
| 3. Génération | `generation.py`, `rendu.py` | `claude-sonnet-5-5`, effort `medium` | schéma local strict ; rendu Markdown par le code |
| 4. Validation et correction | `validation/`, `correction.py` | `claude-sonnet-5-5` (correction) | gherkin-official, openapi-spec-validator, traçabilité ; boucle bornée |
| 5. Steps Java | `steps_java.py` | aucun | compilation `javac` / dry-run Cucumber |

## Installation

```bash
cd labs/spec
uv sync                      # Python 3.11+, dépendances verrouillées dans uv.lock
uv run pytest                # tous les tests tournent hors ligne, sans clé
```

## Utilisation

Mode hors ligne (`--offline`) : modèle simulé déterministe, aucun appel réseau, aucune clé consommée. Il rejoue `fixtures/offline/<TYPE>/` (CONGES, NOTE_DE_FRAIS) ou produit une réponse générique valide pour les autres variantes. C'est le mode des tests, de la préparation et du plan B.

```bash
# Chaîne complète sur CONGES, hors ligne, depuis labs/spec (la racine du dépôt est trouvée seule)
uv run neospec chaine --type CONGES --reponses exemples/reponses_CONGES.yaml --offline \
    --types-parametres exemples/parametres_CONGES.yaml --runner

# Même chaîne avec un Gherkin invalide à la première génération : la boucle le corrige
uv run neospec chaine --type CONGES --reponses exemples/reponses_CONGES.yaml --offline --offline-defaut gherkin

# Pas à pas, avec le vrai modèle (clé dans ANTHROPIC_API_KEY)
uv run neospec questions --type MATERIEL_IT
uv run neospec arbitrer  --type MATERIEL_IT --interactif --decideur "Karim Haddad (DSI)"
uv run neospec generer   --type MATERIEL_IT --max-corrections 2
uv run neospec valider   --type MATERIEL_IT
uv run neospec steps     --type MATERIEL_IT --runner
```

| Fichier produit | Contenu |
|---|---|
| `docs/specs/<type>/neospec/questions.json`, `decisions.json`, `generation.json` | traces des étapes 1 à 3 (à versionner : c'est le journal des décisions) |
| `docs/specs/<TYPE>.md` | spécification, statut `EN REVUE` (ou `BROUILLON` si la validation échoue) |
| `docs/specs/<type>/features/*.feature`, `openapi/<type>-delta.yaml`, `MATRICE_TRACABILITE.md`, `PLAN_TACHES.md` | artefacts vérifiés |
| `docs/adr/ADR-NNN-<slug>.md` | ADR au statut `Proposé` |
| `backend/src/test/java/com/neosoft/neoflow/acceptance/<type>/<Type>Steps.java` (+ lanceur) | squelettes Cucumber-JVM, exécutés au J7 |
| `labs/spec/journal/<type>.jsonl` | une ligne par appel : étape, modèle, usage (tokens, cache), durée |

Codes de sortie : 0 succès ; 1 validation en échec ; 2 porte non franchie, écriture refusée ou correction épuisée ; 3 erreur du modèle (refus, sortie tronquée ou invalide, réseau).

## Fichier de réponses (porte 1)

```yaml
decideur: Sophie Garnier (DRH)
date: 2026-11-16
decisions:
  Q-01: valider                      # l'hypothèse proposée est acceptée
  Q-03:
    decision: remplacer               # l'humain la réécrit
    hypothese: "Solde disponible = acquis − pris − en cours, par sous-type…"
    decideur: Bertrand Collin (paie)
  Q-07: {decision: rejeter, motif: "Hors périmètre v1"}
ajouts:                               # vu après coup : pair, puis VARIANTES.md
  - {question: "Durée maximale ?", source: "VARIANTES (R5, non vu)", decision: "20 jours ouvrés"}
```

La génération refuse de démarrer (code 2, aucun token dépensé) tant qu'une question n'a pas de décision, ou qu'un décideur n'est pas un humain nommé.

## Garde-fous

- Écriture limitée à `docs/specs`, `docs/adr`, `backend/src/test/java`, `backend/src/test/resources/features` (`rendu.chemin_autorise`).
- Une spécification au statut `PRÊTE` n'est jamais réécrite (porte 4 humaine), sauf `--forcer`.
- Le contenu du ticket est traité comme une donnée (consigne dans chaque prompt système).
- Aucune donnée réelle ; clé lue dans l'environnement, jamais écrite.

## Détails d'appel à l'API (SDK `anthropic` 2.x)

- `client.beta.messages.stream(...)` puis `get_final_message()` : sorties longues (`max_tokens` 64 000) sans délai d'expiration HTTP.
- `output_config = {"effort": …, "format": {"type": "json_schema", "schema": …}}` : la réponse est un JSON conforme. Le schéma envoyé n'utilise que les mots-clés acceptés (types, `enum`, `required`, `additionalProperties: false`) ; les contraintes plus fines (motifs d'identifiants, listes non vides) sont vérifiées localement par `jsonschema` (`schemas.py`).
- Prompt système en premier bloc avec `cache_control` : le préfixe est réutilisé d'un appel à l'autre ; `cache_read_input_tokens` dans le journal le confirme.
- `fallbacks: "default"` (bêta `server-side-fallback-2026-07-01`) : si un classifieur refuse, l'API rejoue la requête sur un modèle de repli ; `ClientClaude(repli=False)` le désactive. Un `stop_reason` `refusal` final lève `RefusModele`, `max_tokens` lève `SortieTronquee`.
- Aucun `temperature` ni `thinking` : les modèles 5.5 raisonnent par défaut ; la profondeur se règle par `effort`.

## Steps Cucumber-JVM

`steps` lit les scénarios (pickles : plans développés, « Et » résolus) et produit une méthode par formulation distincte : texte entre guillemets → `{string}`, entier → `{int}`, décimal à virgule → `{decimal}` (type déclaré), alternatives du fichier `--types-parametres` → type personnalisé. Annotations `io.cucumber.java.fr` (`@Soit`, `@Quand`, `@Alors`), corps `PendingException`, commentaire d'origine et d'exigences. Dépendances à ajouter au `pom.xml` du backend au J7 : `io.cucumber:cucumber-java`, `io.cucumber:cucumber-junit-platform-engine`, `org.junit.platform:junit-platform-suite` (scope test) ; copier les `.feature` dans `src/test/resources/features/<type>/`.
