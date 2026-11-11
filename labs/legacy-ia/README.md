# Lab J08 — `legacy-ia` : analyser, expliquer et documenter du code legacy, sous contrôle

> **Starter du TP.** Cinq fonctions clés sont à écrire (`TODO TP1-1` à `TP1-4`, `TODO TP5`). Tant qu'elles ne
> le sont pas, les tests correspondants échouent : `./mvnw -q test` liste ce qui reste à faire. Le corrigé est
> fourni par le formateur (`J08_legacy_documentation/solutions/labs/legacy-ia/`).

| TODO | Fichier | Tests qui doivent passer |
|---|---|---|
| TP1-1 complexité cyclomatique | `analyse/ComplexiteCyclomatique.java` | `AnalyseurLegacyTest$Complexite`, `ExportMermaidTest` |
| TP1-2 `==` sur des `String` | `analyse/DetecteurConstats.java` | `AnalyseurLegacyTest$Constats`, `SocleReelTest`, `ExplicateurTest` |
| TP1-3 horloge cachée | `analyse/DetecteurConstats.java` | `AnalyseurLegacyTest$Constats`, `ExplicateurTest` |
| TP1-4 vérification des citations | `ia/VerificateurCitations.java` | `VerificateurCitationsTest`, `ExplicateurTest` |
| TP5 noms inconnus dans la documentation | `doc/VerificateurDocumentation.java` | `GenerateurDocumentationTest` |

La réponse simulée « fidèle » de la traduction n'est pas fournie dans le starter : utilisez
`--reponse-simulee frontend/src/utils/utils.ts` pour rejouer votre propre traduction hors ligne.

Outil Java (Maven, Java 21) du jour 8. Il sépare strictement deux étages :

1. **Faits déterministes** (JavaParser, aucun modèle) : graphe d'appels du module legacy et de ses appelants
   jusqu'aux endpoints HTTP, dépendances de classes, complexité cyclomatique, constats (nombres magiques,
   `==` sur des `String`, horloge cachée, état statique mutable, Locale implicite, division entière).
   Sorties JSON et Mermaid.
2. **Prose par Claude, vérifiée par du code** : explication et risques, analyse d'impact, JavaDoc et README
   technique, traduction JS → TS. Le modèle ne reçoit que les faits et le code numéroté ; il répond en
   **sortie structurée** ; chaque affirmation cite une ligne, et une vérification automatique rejette les
   citations fausses, les signatures et les noms qui n'existent pas, les traductions qui cassent la parité.

```
labs/legacy-ia/
├── pom.xml  mvnw  .mvn/                     Java 21, JavaParser 3.28, SDK com.anthropic:anthropic-java 3.4
└── src/main/java/com/neosoft/neoflow/legacyia/
    ├── Main.java  Projet.java               CLI, localisation du dépôt NeoFlow
    ├── analyse/   AnalyseurLegacy, DetecteurConstats, ComplexiteCyclomatique, Faits, CodeSource,
    │              ExportJson, ExportMermaid
    ├── ia/        ModeleLangage (interface), ModeleClaude, ModeleSimule (--offline), Requete, Reponses,
    │              VerificateurCitations, Explicateur, ImpactDeterministe, Journal
    ├── doc/       GenerateurDocumentation, VerificateurDocumentation
    └── traduction/ TraducteurJsTs, ExecuteurParite, ExecuteurVitest
```

## Lancer

```bash
cd labs/legacy-ia
./mvnw -q test                                                     # aucun appel à l'API (clé neutralisée)
./mvnw -q compile exec:java -Dexec.args="analyser"                 # faits + Mermaid dans target/legacy-ia/
./mvnw -q compile exec:java -Dexec.args="expliquer --offline"      # modèle simulé
export ANTHROPIC_API_KEY=...                                       # clé fournie par Neosoft, jamais committée
./mvnw -q compile exec:java -Dexec.args="expliquer"                # Claude (claude-sonnet-5-5 par défaut)
./mvnw -q compile exec:java -Dexec.args="impact --cible RegleValidationLegacy.java:56 --changement 'remplacer == par equals'"
./mvnw -q compile exec:java -Dexec.args="documenter"
./mvnw -q compile exec:java -Dexec.args="traduire --offline --variante naive"   # parité rouge, original restauré
./mvnw -q compile exec:java -Dexec.args="traduire --conserver"     # garde utils.ts seulement si la parité est verte
```

| Commande | Entrée | Sorties (`target/legacy-ia/`) |
|---|---|---|
| `analyser` | sources `backend/src/main/java` | `faits.json`, `graphe-appels.mmd`, `dependances.mmd` |
| `expliquer` | faits + code numéroté | `explication.md` (retenues / rejetées / risques), `explication.json` |
| `impact --cible F.java:L --changement "..."` | faits + partie déterministe de l'impact | `impact.md` (appelants, endpoints, nature, conséquences vérifiées) |
| `documenter` | faits + code numéroté | `README_TECHNIQUE.genere.md`, `javadoc.genere.md` (rien n'est écrit dans les sources) |
| `traduire` | `frontend/src/legacy/utils-legacy.js` | `utils.candidat.ts` ; `frontend/src/utils/utils.ts` seulement avec `--conserver` et parité verte |

Options : `--offline`, `--modele claude-haiku-5-5|claude-sonnet-5-5|claude-opus-5-5`, `--sans-repli`,
`--racine <dépôt NeoFlow>` (ou `NEOFLOW_RACINE`), `--paquet`, `--sortie`, `--fuseau` (tests de parité),
`--variante naive|fidele` et `--reponse-simulee fichier.ts` (traduction hors ligne).

## Choix techniques

| Sujet | Choix | Pourquoi |
|---|---|---|
| Analyse | JavaParser, résolution des appels **par nom** (classe statique, type déclaré du champ, du paramètre ou de la variable) | déterministe, explicable ; limites assumées : polymorphisme, lambdas, réflexion |
| Complexité | McCabe, convention lizard/Checkstyle | `determinerNiveau` = 28, `calculer` = 10 (mêmes valeurs que lizard) |
| Appel au modèle | `client.messages().create(...)` avec `outputConfig(Record.class)` | schéma JSON dérivé du record : pas d'analyse de texte libre |
| Cache | consignes système en `cache_control` éphémère | identiques d'un appel à l'autre ; vérifier `cache_read_input_tokens` dans le journal |
| Refus | `fallbacks: "default"` (en-tête `server-side-fallback-2026-07-01`), désactivable par `--sans-repli` | repli serveur si un classifieur refuse ; non testé contre l'API pendant la rédaction |
| Vérification | citations : fichier, ligne, extrait présent ; doc : signature réelle, noms existants ; traduction : tests de parité Vitest | le modèle propose, le code vérifie, l'humain décide |
| Écritures | aucune dans `backend/` ; `utils.ts` seulement avec `--conserver` et parité verte, original sauvegardé | garde-fous du J2 : validation humaine avant écriture |
| Traçabilité | `journal.jsonl` : tâche, modèle, tokens d'entrée, de sortie, lus en cache | coût calculable à partir de l'usage et de la page tarifs |
| Hors ligne | `ModeleSimule` : réponses construites à partir des faits, avec des erreurs volontaires | tests sans clé, plan B des démos |

## Ce que la vérification attrape, et ce qu'elle n'attrape pas

| Erreur du modèle (toutes produites par `ModeleSimule`) | Détectée par | Résultat |
|---|---|---|
| citation d'une ligne inexistante (`RegleValidationLegacy.java:157`) | `VerificateurCitations` | affirmation rejetée |
| extrait inventé (`setScale(2, RoundingMode.HALF_UP)` ligne 40) | `VerificateurCitations` | affirmation rejetée |
| JavaDoc sur une signature inventée | `VerificateurDocumentation` | JavaDoc rejetée |
| nom inventé (`calculerNiveauDsi`, `TauxTvaService`) | `VerificateurDocumentation` | JavaDoc / section rejetée |
| traduction avec `Intl.NumberFormat` | tests de parité Vitest | candidate refusée, original restauré |
| **interprétation fausse, citations exactes** (« la DSI obtient toujours le niveau 1 ») | **rien de mécanique** | retenue comme hypothèse : seul le test de caractérisation `new String("DSI")` la réfute |

## Tests

| Classe | Vérifie |
|---|---|
| `AnalyseurLegacyTest` | graphe d'appels jusqu'à `POST /api/demandes/{id}/soumettre`, complexités, constats aux bonnes lignes |
| `SocleReelTest` | mêmes faits sur le vrai dépôt (ignoré s'il est introuvable) |
| `ExportMermaidTest` | Mermaid produit, JSON relisible |
| `VerificateurCitationsTest` | ligne inexistante, extrait absent, fichier inconnu, affirmation sans citation |
| `ExplicateurTest` | hors ligne : 2 affirmations rejetées, l'interprétation fausse retenue ; impact de la ligne 56 |
| `GenerateurDocumentationTest` | signature et noms inventés rejetés, parties calculées présentes |
| `TraducteurJsTsTest` | candidate rejetée si parité rouge, gardée seulement si demandée |
| `ModeleClaudeTest` | requête Claude construite sans réseau : modèle, cache, schéma, repli |

Les tests unitaires analysent des copies figées du socle (`src/test/resources/socle-extrait/`).
