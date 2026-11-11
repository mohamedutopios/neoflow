# Lab J07 — `tests-ia` : générateur de tests vérifié et assistant de diagnostic

Deux outils Java 21 (Maven) qui appellent l'API Claude avec le SDK officiel `com.anthropic:anthropic-java`, **sous contrôle d'un vérificateur déterministe** :

| Outil | Commande | Ce que fait le modèle | Ce que vérifie le code |
|---|---|---|---|
| Générateur de tests vérifié | `./tests-ia generer` | propose des classes JUnit 5 (sortie structurée `PropositionTests`) à partir d'une classe et d'une spécification | structure, tautologies (JavaParser), compilation (`javax.tools`), exécution (JUnit dans une JVM fille), score de mutation (PIT) ; les rejets repartent au modèle avec leur motif, au plus N tours |
| Assistant de diagnostic | `./tests-ia diagnostiquer` | formule au plus 3 hypothèses (sortie structurée `Hypotheses`), chacune avec un test de reproduction | les faits sont extraits **avant** l'appel (logs ECS, trace Jaeger) ; toute hypothèse qui cite un fait inexistant ou n'a pas de test est rejetée |

Mode `--offline` : `ModeleSimule` rejoue des réponses enregistrées (`src/main/resources/offline/`), sans clé ni réseau. **Utilisez-le pour tout le développement** ; le mode réel (`ModeleClaude`) ne sert qu'une fois les tests verts, avec la clé fournie par Neosoft (`ANTHROPIC_API_KEY`, jamais dans le code ni dans Git).

## Ce que vous codez (TODO du socle)

| TODO | Classe | Tests qui doivent passer |
|---|---|---|
| J07-1 | `modele/ModeleClaude` : requête Messages API (sortie structurée, cache du message système, effort, repli), lecture de la réponse | `ModeleClaudeTest` |
| J07-2 | `generateur/AnalyseurTautologies.analyser` : sept règles anti-tautologie (la 7e est l'extension du TP 1) | `AnalyseurTautologiesTest` |
| J07-3 | `generateur/GenerateurVerifie.generer` : boucle Generator–Verifier bornée | `GenerateurVerifieTest` (exécute aussi PIT) |
| J07-4 | `diagnostic/ExtracteurIndices.extraire` : faits déterministes | `ExtracteurIndicesTest` |
| J07-5 | `diagnostic/ControleHypotheses.controler` : rejet des hypothèses non sourcées | `ControleHypothesesTest`, `AssistantDiagnosticTest` |

Fourni : CLI (`Application`), `ModeleSimule`, prompts, compilateur, exécuteur JUnit, mesure PIT, lecteurs ECS (formats 3.4 et 3.5) et Jaeger, rapports, journal JSONL.

```bash
./mvnw test                       # au départ : 28 tests en échec sur les TODO, 3 verts
./mvnw test -Dtest=AnalyseurTautologiesTest
```

## Utilisation

```bash
./mvnw -q -DskipTests package     # une fois (bibliothèques dans target/lib)

# Générateur, sur le backend NeoFlow (le lab compile le backend et calcule son classpath de test)
./tests-ia generer --projet ../../backend \
  --classe com.neosoft.neoflow.validation.CircuitValidationService \
  --spec specs/circuit-validation.md --offline            # sans --offline : appel réel (clé requise)

# Assistant de diagnostic, sur les artefacts d'un incident
./tests-ia diagnostiquer --logs ../../incident/backend.log --trace ../../incident/trace.json \
  --sources ../../backend/src/main/java --offline
```

Options : `--tours 3`, `--seuil 0.6` (score de mutation visé), `--sans-mutation`, `--modele claude-sonnet-5-5`, `--effort medium`, `--reponses fichier.json` (réponses simulées), `--sortie target/tests-ia`, `--journal fichier.jsonl`, `--trace-id`, `--sans-repli`.

Sorties dans `target/tests-ia/` : `rapport-generation.md`, `acceptes/` et `a-arbitrer/` (sources des tests, **jamais copiées automatiquement dans `src/test`** : relecture humaine), `rapport-diagnostic.md`, `journal.jsonl` (une ligne par appel, avec l'usage en tokens, relu au J10).

## Verdicts du générateur

| Verdict | Signification | Renvoyé au modèle ? |
|---|---|---|
| `ACCEPTE` | compile, passe, rien de tautologique | nom seulement (ne pas reproposer) |
| `ROUGE_A_ARBITRER` | compile mais échoue sur le code actuel : **défaut réel ou oracle faux**, décision humaine | non (sinon le modèle aligne l'oracle sur le code) |
| `REJETE_TAUTOLOGIE`, `REJETE_COMPILATION`, `REJETE_STRUCTURE` | inexploitable | oui, avec le motif |

## Garde-fous

- Commandes lancées uniquement depuis une liste blanche (`java` de la JVM courante, `./mvnw` du projet), avec délai et journal.
- Le lab écrit dans `target/tests-ia/` ; il ne modifie jamais les sources du projet testé.
- Aucun secret dans le code ; `ANTHROPIC_API_KEY` lue par le SDK.
- Modèle par défaut `claude-sonnet-5-5` ; `claude-haiku-5-5` suffit pour des essais à faible coût, `claude-opus-5-5` pour une revue exigeante. Vérifiez les identifiants disponibles et les tarifs avant usage.
