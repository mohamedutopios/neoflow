"""Recherche dans NeoFlow : native (ripgrep), vectorielle (Qdrant via LlamaIndex), BM25, hybride (RRF).

API stable (utilisée par labs/mcp en J06) :

    from search import Searcher
    s = Searcher()                                   # ou Searcher("chemin/config.yaml")
    hits = s.search("Où est calculé le niveau de validation ?", mode="hybrid", k=5)
    hits[0]["path"], hits[0]["start_line"], hits[0]["end_line"], hits[0]["symbol"],
    hits[0]["commit"], hits[0]["score"], hits[0]["text"], hits[0]["source_type"]   # "code" | "doc"

    s.search(q, mode="bm25", k=5, source_type="doc")  # filtre code/doc (search_code / search_docs)
    s.get_chunk(hits[0]["chunk_id"])                  # chunk complet par identifiant
    s.info()                                          # commit indexé, HEAD actuel, fraîcheur

CLI :
    uv run python search.py "question" [--mode hybrid|vector|bm25|native] [-k 5] [--type code|doc]
                                       [--json] [--compare] [--max-lines 30]
"""
from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import subprocess
import sys
import threading
import time
import warnings
from collections import Counter, defaultdict
from pathlib import Path

from rag_common import (
    BackendUnavailableError, IndexMissingError, charger_composant, citation, embed_text, git_info, head_commit, load_config,
    make_embed_model, qdrant_client, query_terms, read_chunks, read_manifest, resolve_embedding,
    select_corpus, sha256_text, source_type_of, tokenize,
)

MODES = ("native", "vector", "bm25", "hybrid")
warnings.filterwarnings("ignore", message="Payload indexes have no effect")


def rrf(rankings: dict[str, list[str]], k: int = 60, weights: dict[str, float] | None = None) -> list[tuple[str, float, dict]]:
    """Reciprocal Rank Fusion : score(d) = somme_i w_i / (k + rang_i(d)). Retourne (id, score, rangs)."""
    scores: dict[str, float] = defaultdict(float)
    ranks: dict[str, dict] = defaultdict(dict)
    for name, ids in rankings.items():
        w = (weights or {}).get(name, 1.0)
        for rank, doc_id in enumerate(ids, start=1):
            scores[doc_id] += w / (k + rank)
            ranks[doc_id][name] = rank
    return sorted(((d, s, ranks[d]) for d, s in scores.items()), key=lambda x: -x[1])


class Searcher:
    """Point d'entrée unique des quatre stratégies de recherche."""

    def __init__(self, config_path: str | None = None):
        self.cfg = load_config(config_path)
        self.root = Path(self.cfg["_repo_root"])
        self.scfg = self.cfg.get("search", {})
        self._manifest: dict | None = None
        self._records: list[dict] | None = None
        self._by_id: dict[str, dict] = {}
        self._by_path: dict[str, list[dict]] = defaultdict(list)
        self._bm25 = None
        self._index = None
        self._client = None
        self._reranker = None
        self._files: list[str] | None = None
        self._lock = threading.Lock()
        self.native_backend: str | None = None  # ripgrep | grep | python (dernier utilisé)
        self._fusion = None                     # composant de TP (composants.fusion), chargé à la demande

    # ------------------------------------------------------------------ #
    # Chargement paresseux
    # ------------------------------------------------------------------ #
    @property
    def manifest(self) -> dict:
        if self._manifest is None:
            self._manifest = read_manifest(self.cfg)
            if self._manifest is None:
                raise IndexMissingError("Index absent : lancer d'abord `uv run python indexer.py` (dans labs/rag).")
        return self._manifest

    def _load_records(self) -> list[dict]:
        if self._records is None:
            self._records = read_chunks(self.cfg)
            for r in self._records:
                self._by_id[r["id"]] = r
                self._by_path[r["path"]].append(r)
        return self._records

    def _bm25_index(self):
        if self._bm25 is None:
            from rank_bm25 import BM25Okapi

            records = self._load_records()
            if not records:
                raise IndexMissingError("Aucun chunk BM25 : lancer `uv run python indexer.py`.")
            self._bm25 = BM25Okapi([tokenize(embed_text(r)) for r in records])
        return self._bm25

    def _vector_index(self):
        if self._index is None:
            from llama_index.core import VectorStoreIndex
            from llama_index.vector_stores.qdrant import QdrantVectorStore

            manifest = self.manifest
            spec = resolve_embedding(self.cfg, forced=manifest["embedding"])
            self._client, _ = qdrant_client(self.cfg, forced_mode=manifest["qdrant"])
            if not self._client.collection_exists(self.cfg["collection"]):
                raise IndexMissingError(f"Collection Qdrant '{self.cfg['collection']}' absente : relancer indexer.py.")
            store = QdrantVectorStore(client=self._client, collection_name=self.cfg["collection"])
            self._index = VectorStoreIndex.from_vector_store(store, embed_model=make_embed_model(spec))
        return self._index

    def _corpus_files(self) -> list[str]:
        if self._files is None:
            self._files = select_corpus(self.cfg).files
        return self._files

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client, self._index = None, None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # ------------------------------------------------------------------ #
    # API publique
    # ------------------------------------------------------------------ #
    def search(self, query: str, mode: str = "hybrid", k: int = 5, *, source_type: str | None = None,
               rerank: bool | None = None) -> list[dict]:
        """Recherche `query` ; retourne au plus k passages (dicts) triés par pertinence."""
        if mode not in MODES:
            raise ValueError(f"mode inconnu {mode!r} ; attendus : {', '.join(MODES)}")
        if source_type not in (None, "code", "doc"):
            raise ValueError("source_type doit valoir None, 'code' ou 'doc'")
        n = max(int(self.scfg.get("candidates", 30)), 4 * k)
        if mode == "native":
            ranked = self._native(query, n, source_type)
        elif mode == "vector":
            ranked = [(r, s, {}) for r, s in self._vector(query, n, source_type)]
        elif mode == "bm25":
            ranked = [(r, s, {}) for r, s in self._bm25_search(query, n, source_type)]
        else:
            ranked = self._hybrid(query, n, source_type)
            use_rerank = self.scfg.get("rerank", {}).get("enabled", False) if rerank is None else rerank
            if use_rerank:
                ranked = self._rerank(query, ranked)
        return self._finalize(ranked, k, mode)

    def get_chunk(self, chunk_id: str) -> dict | None:
        self._load_records()
        rec = self._by_id.get(chunk_id)
        return self._to_result(rec, 0.0, "get_chunk", 0, {}) if rec else None

    def info(self) -> dict:
        m = self.manifest
        head = head_commit(self.root)
        indexed = m["git"]["commit"]
        return {
            "collection": m["collection"], "indexed_at": m["indexed_at"], "indexed_commit": indexed,
            "branch": m["git"]["branch"], "head_commit": head,
            "index_behind_head": m["git"]["is_repo"] and head != indexed,
            "embedding": m["embedding"], "qdrant": m["qdrant"], "chunks": m["chunks"],
            "files": len(m["files"]),
        }

    # ------------------------------------------------------------------ #
    # Stratégies
    # ------------------------------------------------------------------ #
    def _vector(self, query: str, n: int, source_type: str | None) -> list[tuple[dict, float]]:
        from llama_index.core.vector_stores import MetadataFilter, MetadataFilters

        index = self._vector_index()
        filters = MetadataFilters(filters=[MetadataFilter(key="source_type", value=source_type)]) if source_type else None
        with self._lock:
            nodes = index.as_retriever(similarity_top_k=n, filters=filters).retrieve(query)
        self._load_records()
        out = []
        for nws in nodes:
            rec = self._by_id.get(nws.node.node_id) or dict(nws.node.metadata, id=nws.node.node_id, text=nws.node.get_content())
            out.append((rec, float(nws.score or 0.0)))
        return out

    def _bm25_search(self, query: str, n: int, source_type: str | None) -> list[tuple[dict, float]]:
        bm25 = self._bm25_index()
        tokens = tokenize(query)
        if not tokens:
            return []
        scores = bm25.get_scores(tokens)
        order = sorted(range(len(scores)), key=lambda i: -scores[i])
        wanted = set(tokens)
        out = []
        for i in order:
            # on garde tout chunk qui contient un terme de la requête : sur un très petit corpus, l'IDF
            # Okapi d'un terme présent dans plus de la moitié des chunks devient négatif
            if not wanted & bm25.doc_freqs[i].keys():
                continue
            rec = self._records[i]
            if source_type and rec["source_type"] != source_type:
                continue
            out.append((rec, float(scores[i])))
            if len(out) >= n:
                break
        return out

    def _hybrid(self, query: str, n: int, source_type: str | None) -> list[tuple[dict, float, dict]]:
        rankers = self.scfg.get("hybrid_rankers", ["vector", "bm25"])
        rankings: dict[str, list[str]] = {}
        if "vector" in rankers:
            rankings["vector"] = [r["id"] for r, _ in self._vector(query, n, source_type)]
        if "bm25" in rankers:
            rankings["bm25"] = [r["id"] for r, _ in self._bm25_search(query, n, source_type)]
        if "native" in rankers:
            ids = []
            for rec, _, _ in self._native(query, n, source_type):
                cid = rec.get("chunk_id")
                if cid and cid not in ids:
                    ids.append(cid)
            rankings["native"] = ids
        k_rrf, weights = int(self.scfg.get("rrf_k", 60)), self.scfg.get("weights")
        if self._fusion is None:
            self._fusion = charger_composant(self.cfg, "fusion") or False
        if self._fusion:   # fusion écrite en TP : (id, score) ; les rangs par liste sont recalculés ici
            positions = {name: {d: r for r, d in enumerate(ids, start=1)} for name, ids in rankings.items()}
            fused = [(d, float(sc), {n: pos[d] for n, pos in positions.items() if d in pos})
                     for d, sc in self._fusion(rankings, k=k_rrf, poids=weights)]
        else:
            fused = rrf(rankings, k=k_rrf, weights=weights)
        self._load_records()
        return [(self._by_id[d], s, ranks) for d, s, ranks in fused if d in self._by_id]

    def _rerank(self, query: str, ranked: list[tuple[dict, float, dict]]) -> list[tuple[dict, float, dict]]:
        rcfg = self.scfg.get("rerank", {})
        top_n = int(rcfg.get("top_n", 20))
        if self._reranker is None:
            from fastembed.rerank.cross_encoder import TextCrossEncoder

            cache = self.cfg.get("embedding", {}).get("fastembed", {}).get("cache_dir")
            self._reranker = TextCrossEncoder(model_name=rcfg.get("model", "BAAI/bge-reranker-v2-m3-int8"),
                                              **({"cache_dir": cache} if cache else {}))
        head, tail = ranked[:top_n], ranked[top_n:]
        max_chars = int(rcfg.get("max_chars", 1500))  # le coût d'un cross-encoder croît avec la longueur
        scores = list(self._reranker.rerank(query, [embed_text(r)[:max_chars] for r, _, _ in head]))
        reordered = sorted(zip(head, scores), key=lambda x: -x[1])
        return [(r, float(s), dict(ranks, rrf=round(old, 5))) for (r, old, ranks), s in reordered] + tail

    # -- recherche native : ce que fait un agent avec grep/glob -------------- #
    def _native(self, query: str, n: int, source_type: str | None) -> list[tuple[dict, float, dict]]:
        terms = query_terms(query)
        if not terms:
            return []
        files = [f for f in self._corpus_files() if not source_type or source_type_of(f) == source_type]
        if not files:
            return []
        raw_hits = self._grep([t["regex"] for t in terms], files)
        compiled = [(t["key"], re.compile(t["regex"], re.IGNORECASE)) for t in terms]
        line_terms: dict[str, dict[int, set[str]]] = defaultdict(dict)
        for path, line_no, text in raw_hits:
            keys = {key for key, rx in compiled if rx.search(text)}
            if keys:
                line_terms[path][line_no] = keys
        path_terms = {f: {key for key, rx in compiled if rx.search(f)} for f in files}
        df = Counter()
        for f in files:
            present = set(path_terms[f])
            for keys in line_terms.get(f, {}).values():
                present |= keys
            df.update(present)
        idf = {key: math.log(1 + len(files) / df[key]) for key in df}
        ctx = int(self.scfg.get("native_context_lines", 4))
        windows = []
        for path, lines in line_terms.items():
            best = None
            for center in sorted(lines):
                near = [ln for ln in lines if abs(ln - center) <= ctx]
                keys = set().union(*(lines[ln] for ln in near)) | path_terms[path]
                score = sum(idf.get(k, 0.0) for k in keys) + 0.05 * len(near)
                if best is None or score > best[0]:
                    best = (score, min(near), max(near))
            windows.append((path, *best))
        windows.sort(key=lambda w: -w[1])
        git = git_info(self.root)  # la recherche native lit l'arbre de travail : commit = HEAD (+dirty)
        self._load_records()       # facultatif : sert seulement à retrouver le symbole englobant
        out = []
        for path, score, first, last in windows[:n]:
            file_lines = (self.root / path).read_text(encoding="utf-8", errors="replace").split("\n")
            s, e = max(1, first - ctx), min(len(file_lines), last + ctx)
            center = (first + last) // 2
            chunk = self._enclosing_chunk(path, center)
            commit = git.commit + ("+dirty" if path in git.dirty_files else "")
            rec = {
                "id": f"native:{path}:{s}-{e}", "path": path, "start_line": s, "end_line": e,
                "symbol": chunk["symbol"] if chunk else "", "members": (chunk or {}).get("members"),
                "kind": "grep", "language": chunk["language"] if chunk else "",
                "source_type": source_type_of(path), "text": "\n".join(file_lines[s - 1:e]),
                "commit": commit, "branch": git.branch, "chunk_id": chunk["id"] if chunk else None,
                "live": True,
            }
            out.append((rec, round(score, 4), {}))
        return out

    def _enclosing_chunk(self, path: str, line: int) -> dict | None:
        candidates = [c for c in self._by_path.get(path, []) if c["start_line"] <= line <= c["end_line"]]
        if not candidates:
            return None
        return min(candidates, key=lambda c: (c["kind"] == "class_summary", c["end_line"] - c["start_line"]))

    def _grep(self, patterns: list[str], files: list[str]) -> list[tuple[str, int, str]]:
        """ripgrep si présent, sinon grep -E, sinon Python : (chemin, ligne, texte)."""
        rg = shutil.which("rg")
        if rg:
            cmd = [rg, "--json", "-n", "-i", "--no-config", "--no-ignore"]
            for p in patterns:
                cmd += ["-e", p]
            proc = subprocess.run(cmd + ["--", *files], cwd=self.root, capture_output=True, text=True)
            if proc.returncode in (0, 1):
                hits = []
                for line in proc.stdout.splitlines():
                    evt = json.loads(line)
                    if evt.get("type") == "match":
                        d = evt["data"]
                        hits.append((d["path"]["text"], d["line_number"], d["lines"].get("text", "")))
                self.native_backend = "ripgrep"
                return hits
        grep = shutil.which("grep")
        if grep and sys.platform != "win32":
            cmd = [grep, "-n", "-i", "-E", "-H"]
            for p in patterns:
                cmd += ["-e", p]
            proc = subprocess.run(cmd + ["--", *files], cwd=self.root, capture_output=True, text=True,
                                  env={"LC_ALL": "en_US.UTF-8", "PATH": "/usr/bin:/bin"})
            if proc.returncode in (0, 1):
                hits = []
                for line in proc.stdout.splitlines():
                    parts = line.split(":", 2)
                    if len(parts) == 3 and parts[1].isdigit():
                        hits.append((parts[0], int(parts[1]), parts[2]))
                self.native_backend = "grep"
                return hits
        rx = re.compile("|".join(f"(?:{p})" for p in patterns), re.IGNORECASE)
        hits = []
        for f in files:
            for i, line in enumerate((self.root / f).read_text(encoding="utf-8", errors="replace").split("\n"), 1):
                if rx.search(line):
                    hits.append((f, i, line))
        self.native_backend = "python"
        return hits

    # ------------------------------------------------------------------ #
    # Mise en forme commune
    # ------------------------------------------------------------------ #
    def _finalize(self, ranked, k: int, mode: str) -> list[dict]:
        excluded = set(self.scfg.get("exclude_status") or [])
        allowed = set(self.scfg.get("allowed_acl") or [])
        max_per_file = int(self.scfg.get("max_per_file", 0) or 0)
        per_file = Counter()
        out: list[dict] = []
        for rec, score, ranks in ranked:
            if rec.get("status") and rec["status"] in excluded:
                continue
            if allowed and rec.get("acl", "projet") not in allowed:
                continue
            if max_per_file and per_file[rec["path"]] >= max_per_file:
                continue
            per_file[rec["path"]] += 1
            out.append(self._to_result(rec, score, mode, len(out) + 1, ranks))
            if len(out) >= k:
                break
        return out

    def _to_result(self, rec: dict, score: float, mode: str, rank: int, ranks: dict) -> dict:
        stale = False
        if not rec.get("live"):
            path = self.root / rec["path"]
            try:
                indexed_sha = rec.get("file_sha")
                stale = (not path.exists()) or (indexed_sha is not None and
                                                sha256_text(path.read_text(encoding="utf-8", errors="replace")) != indexed_sha)
            except OSError:
                stale = True
        return {
            "rank": rank, "mode": mode, "score": round(float(score), 6),
            "path": rec["path"], "start_line": rec["start_line"], "end_line": rec["end_line"],
            "symbol": rec.get("symbol") or "", "kind": rec.get("kind", ""), "language": rec.get("language", ""),
            "members": rec.get("members") or "",
            "source_type": rec.get("source_type", "code"), "commit": rec.get("commit", "nogit"),
            "branch": rec.get("branch", ""), "file_commit": rec.get("file_commit", ""), "file_date": rec.get("file_date", ""),
            "status": rec.get("status"), "acl": rec.get("acl"), "stale": stale,
            "chunk_id": rec.get("chunk_id") if rec.get("live") else rec.get("id"),
            "citation": citation(rec["path"], rec["start_line"], rec["end_line"], rec.get("commit", "nogit")),
            "ranks": ranks, "text": rec["text"],
        }


# ---------------------------------------------------------------------- #
# CLI
# ---------------------------------------------------------------------- #

FENCE_LANG = {"java": "java", "typescript": "ts", "tsx": "tsx", "javascript": "js", "yaml": "yaml",
              "sql": "sql", "markdown": "markdown", "xml": "xml", "json": "json"}


def format_markdown(query: str, mode: str, hits: list[dict], info: dict | None, max_lines: int) -> str:
    out = [f"## Recherche « {query} » — mode {mode}, {len(hits)} résultat(s)"]
    if info:
        out.append(f"Index : commit {info['indexed_commit']} · branche {info['branch']} · {info['indexed_at']} · "
                   f"{info['embedding']['provider']}/{info['embedding']['model']} · {info['chunks']} chunks")
        if info.get("index_behind_head"):
            out.append(f"ATTENTION : index construit sur {info['indexed_commit']}, HEAD = {info['head_commit']}. "
                       "Relancer `uv run python indexer.py --incremental` ou vérifier dans le fichier.")
    for h in hits:
        out.append(f"\n### {h['rank']}. {h['citation']}")
        flags = []
        if h["stale"]:
            flags.append("PÉRIMÉ : fichier modifié depuis l'indexation")
        if h.get("status"):
            flags.append(f"statut du document : {h['status']}")
        ranks = ", ".join(f"{k} #{v}" for k, v in h.get("ranks", {}).items() if k != "rrf")
        meta = f"`{h['symbol'] or '-'}` · {h['kind']} · {h['source_type']} · score {h['score']:.4f}"
        out.append(meta + (f" ({ranks})" if ranks else "") + (f" · {' · '.join(flags)}" if flags else ""))
        lines = h["text"].split("\n")
        body = "\n".join(lines[:max_lines])
        fence = "```"
        while fence in body:          # un extrait Markdown peut contenir ses propres blocs de code
            fence += "`"
        out.append(f"{fence}{FENCE_LANG.get(h['language'], '')}\n{body}\n{fence}")
        if len(lines) > max_lines:
            out.append(f"_(extrait tronqué à {max_lines} lignes sur {len(lines)} ; lire {h['path']} "
                       f"lignes {h['start_line']}-{h['end_line']})_")
    if not hits:
        out.append("\nAucun résultat. Reformuler avec un identifiant (classe, méthode) ou changer de mode.")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Recherche dans le code et la documentation NeoFlow.")
    parser.add_argument("query", nargs="*", help="question ou identifiant")
    parser.add_argument("--info", action="store_true", help="état de l'index (commit indexé, HEAD, modèle) sans recherche")
    parser.add_argument("--mode", default=None, choices=MODES)
    parser.add_argument("-k", type=int, default=5)
    parser.add_argument("--type", dest="source_type", choices=["code", "doc"], default=None)
    parser.add_argument("--json", action="store_true", help="sortie JSON (pour scripts et outils)")
    parser.add_argument("--compare", action="store_true", help="comparer les quatre modes sur la question")
    parser.add_argument("--rerank", action="store_true", help="re-ranking cross-encoder (mode hybride)")
    parser.add_argument("--max-lines", type=int, default=30, help="lignes affichées par extrait")
    parser.add_argument("--config", default=None)
    args = parser.parse_args(argv)
    query = " ".join(args.query).strip()
    searcher = Searcher(args.config)
    if args.info:
        try:
            info = searcher.info()
        except FileNotFoundError as exc:
            print(f"Index RAG absent : {exc}")
            return 0
        behind = (f"EN RETARD : index sur {info['indexed_commit']}, HEAD = {info['head_commit']} "
                  "(uv run python indexer.py --incremental)") if info["index_behind_head"] else "à jour avec HEAD"
        print(f"Index RAG '{info['collection']}' : commit {info['indexed_commit']} (branche {info['branch']}), "
              f"{behind} ; indexé le {info['indexed_at']} ; {info['files']} fichiers, {info['chunks']} chunks ; "
              f"embeddings {info['embedding']['provider']}/{info['embedding']['model']} ; Qdrant {info['qdrant']['mode']}.")
        return 0
    if not query:
        parser.error("question manquante")
    mode = args.mode or searcher.scfg.get("default_mode", "hybrid")
    try:
        if args.compare:
            print(f"## Comparaison des modes pour « {query} » (top {args.k})\n")
            print("| Rang | " + " | ".join(MODES) + " |")
            print("|---|" + "---|" * len(MODES))
            columns, timings = {}, {}
            for m in MODES:
                t0 = time.perf_counter()
                columns[m] = searcher.search(query, mode=m, k=args.k, source_type=args.source_type)
                timings[m] = (time.perf_counter() - t0) * 1000
            for i in range(args.k):
                cells = []
                for m in MODES:
                    h = columns[m][i] if i < len(columns[m]) else None
                    cells.append(f"`{h['path'].split('/')[-1]}:{h['start_line']}-{h['end_line']}` {h['symbol'][:40]}" if h else "")
                print(f"| {i + 1} | " + " | ".join(cells) + " |")
            print("| ms | " + " | ".join(f"{timings[m]:.0f}" for m in MODES) + " |")
            return 0
        hits = searcher.search(query, mode=mode, k=args.k, source_type=args.source_type,
                               rerank=True if args.rerank else None)
        if args.json:
            print(json.dumps(hits, ensure_ascii=False, indent=2))
        else:
            info = None
            try:
                info = searcher.info()
            except IndexMissingError:
                pass
            print(format_markdown(query, mode, hits, info, args.max_lines))
    except (IndexMissingError, BackendUnavailableError, RuntimeError) as exc:
        print(f"ERREUR : {exc}", file=sys.stderr)
        return 2
    finally:
        searcher.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
