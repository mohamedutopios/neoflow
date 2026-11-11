# Lab RAG NeoFlow (J05)

RAG local sur le **code et la documentation** de NeoFlow : sélection du corpus, découpage AST Tree-sitter,
embeddings locaux (Ollama, repli fastembed), Qdrant (serveur ou embarqué), BM25 adapté au code, fusion RRF,
re-ranking facultatif, évaluation reproductible, outil RAG pour l'agent `neoagent` (J4), génération de réponses
sourcées par Claude, NéoGen ou Ollama. Fonctionne **sans Docker** et, pour tout ce qui génère, en mode `offline`.

Le lab est **complet** : J06 (`labs/mcp`) et J09 (`labs/workflow`) l'importent. Au J05, les stagiaires écrivent
des composants branchables dans `tp/` (chunker AST, fusion, métriques, sortie de l'outil de l'agent) ; tant
qu'un composant n'est pas déclaré dans `config.yaml > composants`, l'implémentation du lab s'applique.

```text
labs/rag/
├── config.yaml        corpus, chunking, embeddings, Qdrant, recherche, ACL
├── indexer.py         fichiers -> chunks -> embeddings -> Qdrant + chunks.jsonl (BM25) + manifeste
├── search.py          Searcher : native | vector | bm25 | hybrid ; CLI de recherche
├── eval.py            métriques sur ../evals/rag_questions.yaml, rapport Markdown et JSON
├── agent_tool.py      rag_tool() -> Tool : outil RAG de neoagent (contrat neoagent.tools.Tool)
├── repondre.py        réponse sourcée à une question (fournisseur offline, anthropic, ollama, neogen)
├── rag_llm.py         fournisseurs de génération et juge de fidélité (offline, Claude, API compatible OpenAI)
├── rag_metriques.py   métriques de référence (Recall@k, Hit@k, MRR, Précision@k)
├── rag_chunker.py     découpage Java / TypeScript / TSX / JavaScript (AST), Markdown, YAML, SQL
├── rag_common.py      configuration, corpus, Git, tokenisation, embeddings, client Qdrant, composants
├── tests/             tests du lab (pytest, sans réseau)
├── tp/                composants écrits par le stagiaire au J05 (starters : J05_rag_codebase/exercises)
├── corpus_extra/      documentation hors dépôt (décisions, FAQ, bibliothèque interne, un DAT de 2019)
├── pyproject.toml     dépendances (uv), uv.lock
└── .rag_index/        index local (ignoré par Git) : manifest.json, chunks.jsonl, qdrant/
```

## Démarrage

```bash
cd labs/rag
uv sync                                   # Python 3.11+, dépendances verrouillées
ollama pull nomic-embed-text              # facultatif : sinon fastembed est utilisé
uv run python indexer.py --prefetch       # grammaires et modèle (poste ensuite hors ligne)
uv run python indexer.py                  # indexation complète (~20 s sur le socle)
uv run python search.py "Où est calculé le niveau de validation ?" -k 5
uv run python eval.py -k 5                # tableau comparatif des quatre modes
uv run pytest -q                          # tests du lab
```

Avec Docker : `make up-ia` (ou `docker compose --profile ia up -d`) démarre Qdrant (:6333) et Ollama (:11434) ;
le lab utilise alors le serveur Qdrant automatiquement. Sans Docker : Qdrant embarqué dans `.rag_index/qdrant`.

## Commandes

| Commande | Effet |
|---|---|
| `indexer.py` | indexation complète (supprime puis recrée la collection `neoflow`) |
| `indexer.py --incremental` | ne retraite que les fichiers modifiés, ajoutés ou supprimés depuis la dernière indexation |
| `indexer.py --dry-run` | sélection et chunking, sans embeddings |
| `indexer.py --list-files` | fichiers retenus (+) et écartés (-) avec la raison |
| `indexer.py --explain <chemin>` | découpage d'un fichier : lignes, type, symbole |
| `indexer.py --prefetch` | télécharge grammaires Tree-sitter, modèle d'embedding (et re-ranker s'il est activé) |
| `search.py "<question>" [--mode M] [-k K] [--type code\|doc] [--json] [--max-lines N]` | recherche, sortie Markdown citée ou JSON |
| `search.py --compare "<question>"` | les quatre modes côte à côte, avec latence |
| `search.py --rerank "<question>"` | hybride + re-ranking cross-encoder |
| `search.py --info` | commit indexé, HEAD actuel, modèle, taille ; sans argument utilisateur (sûr pour `` !`…` ``) |
| `eval.py [-k 5] [--modes …] [--out f.md] [--json f.json] [--gate MODE:METRIQUE:SEUIL]` | évaluation, seuil bloquant |
| `eval.py --faithfulness N [--fournisseur F] [--juge J]` | fidélité de N réponses générées (défaut `offline` : aucun appel réseau) |
| `repondre.py "<question>" [--fournisseur F]` | réponse sourcée `[Pn]` + liste des sources ; F : `offline`, `anthropic`, `ollama`, `neogen` |
| `agent_tool.py "<question>"` / `agent_tool.py --schema` | ce que l'outil RAG renvoie à l'agent / sa définition |

Variables d'environnement : `NEOFLOW_RAG_CONFIG` (fichier de config), `NEOFLOW_REPO_ROOT` (dépôt à indexer),
`NEOFLOW_RAG_HOME` (dossier d'index), `QDRANT_URL`, `OLLAMA_HOST`.

## API Python (stable, utilisée par `labs/mcp` en J06 et `labs/workflow` en J09)

```python
import sys; sys.path.insert(0, "<neoflow>/labs/rag")
from search import Searcher

searcher = Searcher(config_path=None)       # None : labs/rag/config.yaml
hits = searcher.search("Où est calculé le niveau de validation ?", mode="hybrid", k=5)
code = searcher.search("PageRequest.of", mode="bm25", k=5, source_type="code")   # "code" | "doc" | None
chunk = searcher.get_chunk(hits[0]["chunk_id"])
state = searcher.info()     # indexed_commit, head_commit, index_behind_head, embedding, qdrant, chunks
searcher.close()            # libère le verrou du Qdrant embarqué (ou : with Searcher() as s: ...)
```

`search(query: str, mode: str = "hybrid", k: int = 5, *, source_type=None, rerank=None) -> list[dict]`,
modes `native`, `vector`, `bm25`, `hybrid`. Chaque résultat contient au moins :

| Clé | Contenu |
|---|---|
| `path` | chemin relatif à la racine du dépôt (séparateur `/`) |
| `start_line`, `end_line` | lignes 1-based inclusives |
| `symbol` | `Classe.methode`, `Composant`, `Titre > Sous-titre`, clé YAML, `CREATE TABLE x` (chaîne vide possible) |
| `commit` | commit court au moment de l'indexation (`+dirty` si le fichier n'était pas commité, `nogit` hors Git) ; en mode `native`, HEAD courant |
| `score` | cosinus (vector), BM25, RRF (hybrid), score de fenêtre (native) : comparable seulement dans un même mode |
| `text` | extrait exact (pour un `class_summary` : squelette synthétique du type) |
| `source_type` | `"code"` ou `"doc"` (Markdown, texte) |

Autres clés : `rank`, `mode`, `kind`, `language`, `members`, `branch`, `file_commit`, `file_date`, `status`,
`acl`, `stale` (fichier modifié depuis l'indexation), `chunk_id`, `citation` (`chemin:début-fin@commit`),
`ranks` (rang dans chaque liste fusionnée, mode hybride).

Erreurs : index absent → `IndexMissingError` (sous-classe de `FileNotFoundError`) ; Ollama, serveur Qdrant ou
verrou du Qdrant embarqué → `BackendUnavailableError` (sous-classe de `ConnectionError`) ; mode ou
`source_type` invalide → `ValueError`. Le mode `native` ne dépend ni d'Ollama ni de Qdrant.

Concurrence : le Qdrant **embarqué** n'accepte qu'un processus à la fois (indexeur, serveur MCP, workflow).
Pour un usage simultané, démarrer le serveur Qdrant (`make up-ia`) et réindexer.

## Outil RAG pour l'agent (J4, J10)

```python
from agent_tool import rag_tool
outil = rag_tool()          # Tool(name="rag_neoflow", description, input_schema, handler, risque="lecture")
texte = outil.handler({"question": "Où est calculé le niveau de validation ?", "mode": "hybrid", "k": 5})
```

`uv run neoagent --repo .. --outils-externes agent_tool:rag_tool --tache "…"` (labs/rag dans le `PYTHONPATH`).
Le handler valide l'entrée, interroge le `Searcher`, bascule en recherche native tracée si l'index, Ollama ou
Qdrant manque, et renvoie un texte encadré (`<sources_rag …>`, passages `[Sn] chemin:début-fin@commit`,
budget de 6 000 caractères, alertes `PÉRIMÉ`). Import tolérant : `neoagent.tools.Tool` si présent, sinon une
dataclass de même forme.

## Composants de TP

| Clé `config.yaml > composants` | Contrat | Repli |
|---|---|---|
| `chunker_code: tp/chunker_ast.py:decouper` | `(chemin, source, langage, options) -> list[dict] \| None` | `None` : chunker du lab |
| `fusion: tp/fusion.py:rrf` | `(classements, k, poids) -> list[(id, score)]` | RRF du lab |
| `metriques: tp/metriques.py` | `recall_at_k`, `hit_at_k`, `reciprocal_rank`, `precision_at_k`, `mrr` | fonction par fonction |
| `formateur_outil: tp/outil_rag.py:formater` | `(question, hits, etat, budget) -> str` | mise en forme du lab |

Surcharge ponctuelle par variable d'environnement : `NEOFLOW_RAG_CHUNKER_CODE`, `NEOFLOW_RAG_FUSION`,
`NEOFLOW_RAG_METRIQUES`, `NEOFLOW_RAG_FORMATEUR_OUTIL`. Les composants actifs figurent dans le manifeste et en
tête du rapport d'évaluation. Une sortie de chunker invalide (lignes hors fichier, champs manquants) lève une
`ValueError` explicite.

## Fournisseurs de génération (`config.yaml > llm`)

| Fournisseur | Client | Usage |
|---|---|---|
| `offline` (défaut) | aucun : réponse extractive, juge heuristique | tests, préparation, plan B |
| `anthropic` | SDK `anthropic`, `ANTHROPIC_API_KEY` ; `claude-sonnet-5-5` répond, `claude-opus-5-5` juge | session de formation |
| `ollama` | client `openai`, `base_url: http://localhost:11434/v1` | génération locale |
| `neogen` | client `openai`, `base_url` NéoGen, clé dans `NEOGEN_API_KEY` | souveraineté |

## Ce que fait chaque brique

| Étape | Implémentation | Rôle de LlamaIndex |
|---|---|---|
| Sélection du corpus | `git ls-files` (tous les `.gitignore`), liste blanche, exclusions, taille, binaires, fichiers générés | — |
| Masquage des secrets | valeurs `password`, `mot-de-passe`, `api-key`, `token`… remplacées par `***MASQUE***` (lignes conservées) | — |
| Chunking | Tree-sitter (wheels `tree-sitter-java`, `tree-sitter-typescript`, `tree-sitter-javascript`, repli `tree-sitter-language-pack`) ; sections Markdown ; clés YAML ; instructions SQL | — |
| Modèle de données | `TextNode` : texte exact + métadonnées ; `excluded_embed_metadata_keys` choisit ce que voit l'embedding | oui |
| Embeddings et écriture | `IngestionPipeline([embed_model], vector_store=QdrantVectorStore)` ; modèle `BaseEmbedding` maison (préfixes `search_document:` / `search_query:`) | oui |
| Recherche vectorielle | `VectorStoreIndex.from_vector_store(...).as_retriever(similarity_top_k, filters=MetadataFilters)` | oui |
| BM25 | `rank_bm25` sur chemin + symbole + membres + code, tokens camelCase / snake_case, racinisation Snowball | — |
| Fusion | RRF (`k = 60`, poids par liste), au plus `max_per_file` passages par fichier | — (équivalent : `QueryFusionRetriever`) |
| Re-ranking | `fastembed` `TextCrossEncoder` (`BAAI/bge-reranker-v2-m3-int8`), passages tronqués à `max_chars` | — |

Règles de découpage du code (`chunking.code`) : type de 60 lignes ou moins → un chunk ; type plus long →
résumé (en-tête, champs, signatures) + un chunk par méthode ; Javadoc / JSDoc incluse ; méthode de plus de
80 lignes → fenêtres de 80 avec recouvrement de 5 ; membres adjacents de 4 lignes ou moins (accesseurs)
regroupés ; lignes restantes significatives → chunk `module`. Fichier YAML de 40 lignes ou moins → un chunk.

## Fraîcheur, ACL, documents obsolètes

- Le manifeste note commit, branche, modèle et empreinte de chaque fichier. `search.py --info` compare au HEAD ;
  chaque résultat porte `stale: true` si son fichier a changé depuis l'indexation.
- `indexer.py --incremental` supprime les points des fichiers modifiés ou supprimés et n'embarque que ceux-là.
- `acl.rules` étiquette les chunks par motif de chemin ; `search.allowed_acl` filtre à la recherche. Pour un
  cloisonnement fort, une collection (ou un dépôt d'index) par périmètre.
- Front matter `statut: obsolete` dans un Markdown → exclu par `search.exclude_status` (le document reste lisible).

## Évaluation

`eval.py` lit `../evals/rag_questions.yaml` (20 questions + questions de variante) et calcule par mode :
Recall@1/3/5/10, Hit@5, MRR, Précision@5, Symbole@5, Évidence@5, Obsolète@5 (dont « avant la vérité »),
latence p50/p95. Le rapport embarque commit, branche, modèle et paramètres : il est rejouable.
`--faithfulness N` ajoute, pour N questions : réponse générée à partir du top-5 hybride avec citations `[Pn]`,
taux de citations valides, mots-clés attendus, et fidélité jugée affirmation par affirmation. Par défaut tout
est `offline` (aucun appel réseau) ; `--fournisseur` et `--juge` choisissent Claude, Ollama ou NéoGen.

## Dépannage

| Symptôme | Cause probable | Action |
|---|---|---|
| `Index absent` | pas encore indexé, ou `NEOFLOW_RAG_HOME` différent | `uv run python indexer.py` |
| `Ollama ... indisponible` à la recherche | l'index a été construit avec Ollama | relancer Ollama, ou `embedding.provider: fastembed` puis réindexer |
| `Storage folder ... is already accessed` | autre processus sur le Qdrant embarqué | fermer l'autre processus, ou Qdrant serveur |
| Re-ranking très lent | cross-encoder sur CPU | réduire `rerank.top_n` / `max_chars`, ou ne l'activer que pour l'évaluation |
| `Tree-sitter : {}` dans la sortie | grammaires absentes | `uv sync`, puis `indexer.py --prefetch` |
| Résultats périmés | HEAD a avancé | `uv run python indexer.py --incremental` |
