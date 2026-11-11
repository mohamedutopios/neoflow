"""Indexation de NeoFlow : fichiers -> chunks AST/sections -> embeddings -> Qdrant + index BM25.

Usage (depuis labs/rag) :
    uv run python indexer.py                  # indexation complète
    uv run python indexer.py --incremental    # ne retraite que les fichiers modifiés
    uv run python indexer.py --dry-run        # sélection + chunking, sans embeddings
    uv run python indexer.py --explain backend/src/main/java/com/neosoft/neoflow/legacy/RegleValidationLegacy.java
    uv run python indexer.py --prefetch       # pré-télécharge grammaires/modèles (poste hors ligne)

Rôle de LlamaIndex : modèle de données TextNode (texte + métadonnées, choix des métadonnées
injectées dans l'embedding), IngestionPipeline (embeddings par lots + écriture dans le
QdrantVectorStore). Le chunking AST est fait par rag_chunker (Tree-sitter) en amont.
"""
from __future__ import annotations

import argparse
import sys
import time
import uuid
import warnings
from collections import Counter
from pathlib import Path

from rag_chunker import PARSER_BACKEND, chunk_file
from rag_common import (
    SCHEMA_VERSION, BackendUnavailableError, acl_of, charger_composant, composants_declares,
    embedding_metadata_keys, file_last_commit, git_info,
    load_config, make_embed_model, qdrant_client, read_chunks, read_manifest, redact_secrets,
    resolve_embedding, select_corpus, sha256_text, source_type_of, storage_paths, write_chunks, write_manifest,
)

NAMESPACE = uuid.UUID("6f1c2a52-6b1e-4a53-9d0e-5e0f10a0c0de")


def chunk_corpus(cfg: dict, files: list[str], git, previous: dict | None = None) -> tuple[list[dict], dict]:
    """Découpe les fichiers et construit les enregistrements de chunks (métadonnées complètes)."""
    root = Path(cfg["_repo_root"])
    redact = cfg.get("corpus", {}).get("redact_secrets", True)
    custom_chunker = charger_composant(cfg, "chunker_code")
    records: list[dict] = []
    files_meta: dict[str, dict] = {}
    redactions = 0
    for rel in files:
        path = root / rel
        text = path.read_text(encoding="utf-8", errors="replace")
        file_sha = sha256_text(text)
        if redact:
            text, n = redact_secrets(text)
            redactions += n
        file_commit, file_date = file_last_commit(root, rel) if git.is_repo else ("", "")
        dirty = rel in git.dirty_files
        commit = (git.commit + "+dirty") if dirty else git.commit
        stype = source_type_of(rel)
        acl = acl_of(rel, cfg)
        chunks = chunk_file(rel, text, cfg.get("chunking", {}), custom_chunker)
        for c in chunks:
            key = f"{rel}:{c.start_line}-{c.end_line}:{c.symbol}:{c.kind}:{sha256_text(c.text)[:16]}"
            records.append({
                "id": str(uuid.uuid5(NAMESPACE, key)),
                "path": rel, "start_line": c.start_line, "end_line": c.end_line,
                "symbol": c.symbol, "kind": c.kind, "language": c.language, "source_type": stype,
                "text": c.text, "commit": commit, "branch": git.branch,
                "file_commit": file_commit, "file_date": file_date, "file_sha": file_sha,
                "acl": acl, "status": c.extra.get("status"), "doc_title": c.extra.get("doc_title"),
                "members": c.extra.get("members") or None,
                "part": c.extra.get("part"), "parse_error": bool(c.extra.get("parse_error")),
            })
        files_meta[rel] = {"sha256": file_sha, "chunks": len(chunks), "file_commit": file_commit,
                           "file_date": file_date, "dirty": dirty}
    return records, {"files": files_meta, "redactions": redactions}


def to_nodes(records: list[dict], embed_keys: list[str]):
    """Enregistrements -> TextNode LlamaIndex. Texte embarqué = métadonnées choisies + code."""
    from llama_index.core.schema import TextNode

    nodes = []
    for r in records:
        metadata = {k: v for k, v in r.items() if k not in ("id", "text") and v is not None}
        node = TextNode(id_=r["id"], text=r["text"], metadata=metadata)
        node.excluded_embed_metadata_keys = [k for k in metadata if k not in embed_keys]
        node.excluded_llm_metadata_keys = [k for k in metadata if k not in ("path", "symbol", "start_line", "end_line", "commit")]
        node.metadata_template = "{key}: {value}"
        node.text_template = "{metadata_str}\n\n{content}"
        nodes.append(node)
    return nodes


def run_index(cfg: dict, incremental: bool = False, dry_run: bool = False, quiet: bool = False) -> dict:
    log = (lambda *a: None) if quiet else (lambda *a: print(*a, flush=True))
    t0 = time.perf_counter()
    root = Path(cfg["_repo_root"])
    git = git_info(root)
    selection = select_corpus(cfg)
    log(f"Dépôt : {root}")
    log(f"Git   : commit {git.commit}, branche {git.branch}" + (f", {len(git.dirty_files)} fichier(s) modifié(s)" if git.dirty_files else ""))
    if composants_declares(cfg):
        log(f"Composants de TP : {composants_declares(cfg)}")
    log(f"Corpus: {len(selection.files)} fichiers retenus ({selection.source}) ; écartés : "
        + ", ".join(f"{k}={len(v)}" for k, v in selection.skipped.items() if v))

    previous = read_manifest(cfg) if incremental else None
    if incremental and previous is None:
        log("Pas d'index existant : indexation complète.")
        incremental = False
    if previous and previous.get("schema") != SCHEMA_VERSION:
        log("Schéma d'index différent : indexation complète.")
        incremental, previous = False, None

    to_process = selection.files
    removed: list[str] = []
    kept_records: list[dict] = []
    if incremental and previous:
        old_files = previous.get("files", {})
        to_process = [f for f in selection.files
                      if f not in old_files or old_files[f]["sha256"] != sha256_text((root / f).read_text(encoding="utf-8", errors="replace"))]
        removed = [f for f in old_files if f not in selection.files]
        changed = set(to_process) | set(removed)
        kept_records = [r for r in read_chunks(cfg) if r["path"] not in changed]
        log(f"Incrémental : {len(to_process)} fichier(s) à (ré)indexer, {len(removed)} supprimé(s), "
            f"{len(kept_records)} chunk(s) conservé(s).")

    t1 = time.perf_counter()
    new_records, meta = chunk_corpus(cfg, to_process, git)
    t_chunk = time.perf_counter() - t1
    all_records = kept_records + new_records
    kinds = Counter(r["kind"] for r in all_records)
    langs = Counter(r["language"] for r in all_records)
    log(f"Chunks: {len(all_records)} ({len(new_records)} nouveaux) en {t_chunk:.2f}s ; "
        f"par type : {dict(kinds.most_common())} ; par langage : {dict(langs.most_common())}")
    if PARSER_BACKEND:
        log(f"Tree-sitter : {PARSER_BACKEND}")
    if meta["redactions"]:
        log(f"Secrets masqués avant indexation : {meta['redactions']}")
    if dry_run:
        return {"chunks": len(all_records), "files": len(selection.files), "dry_run": True}

    spec = resolve_embedding(cfg, forced=(previous or {}).get("embedding") if incremental else None)
    embed_model = make_embed_model(spec)
    client, qmode = qdrant_client(cfg, forced_mode=(previous or {}).get("qdrant") if incremental else None)
    collection = cfg["collection"]
    log(f"Embeddings : {spec['provider']} / {spec['model']} ; Qdrant : {qmode['mode']} "
        f"({qmode.get('url') or qmode.get('path')}) ; collection '{collection}'")

    from llama_index.core.ingestion import IngestionPipeline
    from llama_index.vector_stores.qdrant import QdrantVectorStore
    from qdrant_client import models

    warnings.filterwarnings("ignore", message="Payload indexes have no effect")

    if not incremental and client.collection_exists(collection):
        client.delete_collection(collection)
    if incremental:
        for rel in sorted(set(to_process) | set(removed)):
            if client.collection_exists(collection):
                client.delete(collection, points_selector=models.FilterSelector(filter=models.Filter(
                    must=[models.FieldCondition(key="path", match=models.MatchValue(value=rel))])))

    vector_store = QdrantVectorStore(client=client, collection_name=collection)
    pipeline = IngestionPipeline(transformations=[embed_model], vector_store=vector_store)
    t2 = time.perf_counter()
    embed_keys = embedding_metadata_keys(cfg)
    nodes = to_nodes(new_records, embed_keys)
    if nodes:
        pipeline.run(nodes=nodes, show_progress=not quiet)
    t_embed = time.perf_counter() - t2
    dim = len(embed_model.get_query_embedding("dimension"))
    if qmode["mode"] == "server":
        for field in ("path", "source_type", "language", "kind", "branch", "acl"):
            client.create_payload_index(collection, field, models.PayloadSchemaType.KEYWORD)
    count = client.count(collection).count if client.collection_exists(collection) else 0
    client.close()

    files_meta = dict((previous or {}).get("files", {})) if incremental else {}
    for rel in removed:
        files_meta.pop(rel, None)
    files_meta.update(meta["files"])
    write_chunks(cfg, all_records)
    manifest = {
        "schema": SCHEMA_VERSION,
        "collection": collection,
        "indexed_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "repo_root": str(root),
        "git": git.to_dict(),
        "embedding": {"provider": spec["provider"], "model": spec["model"], "dim": dim, "metadata_keys": embed_keys},
        "qdrant": qmode,
        "chunks": len(all_records),
        "points": count,
        "files": files_meta,
        "stats": {"kinds": dict(kinds), "languages": dict(langs), "skipped": {k: len(v) for k, v in selection.skipped.items()},
                  "redactions": meta["redactions"], "tree_sitter": dict(PARSER_BACKEND),
                  "composants": composants_declares(cfg),
                  "seconds": {"chunking": round(t_chunk, 2), "embedding_upsert": round(t_embed, 2),
                              "total": round(time.perf_counter() - t0, 2)}},
    }
    write_manifest(cfg, manifest)
    log(f"Index : {count} points dans Qdrant, {len(all_records)} chunks BM25 ; "
        f"embeddings+upsert {t_embed:.1f}s ; total {time.perf_counter() - t0:.1f}s")
    log(f"Stockage : {storage_paths(cfg)['dir']}")
    return manifest


def explain(cfg: dict, rel: str) -> None:
    """Affiche le découpage d'un fichier (démo AST) sans rien indexer."""
    root = Path(cfg["_repo_root"])
    text = (root / rel).read_text(encoding="utf-8", errors="replace")
    chunks = chunk_file(rel, text, cfg.get("chunking", {}), charger_composant(cfg, "chunker_code"))
    print(f"{rel} : {len(text.splitlines())} lignes -> {len(chunks)} chunks (Tree-sitter : {PARSER_BACKEND or 'non utilisé'})\n")
    print(f"{'lignes':>11}  {'type':<14} symbole")
    for c in chunks:
        part = f"  (partie {c.extra['part']})" if c.extra.get("part") else ""
        print(f"{c.start_line:>5}-{c.end_line:<5}  {c.kind:<14} {c.symbol}{part}")
    summary = next((c for c in chunks if c.kind == "class_summary"), None)
    if summary:
        print("\nRésumé de type (texte embarqué pour le chunk class_summary) :\n")
        print("\n".join(summary.text.splitlines()[:25]))


def prefetch(cfg: dict) -> None:
    """Pré-télécharge ce qui peut l'être (poste de formation sans réseau ensuite)."""
    from rag_chunker import get_parser

    for lang in ("java", "typescript", "tsx", "javascript"):
        print(f"Tree-sitter {lang}: {'ok' if get_parser(lang) is not None else 'INDISPONIBLE'} ({PARSER_BACKEND.get(lang, '-')})")
    spec = resolve_embedding(cfg)
    model = make_embed_model(spec)
    print(f"Embeddings {spec['provider']} / {spec['model']} : dimension {len(model.get_query_embedding('test'))}")
    rerank = cfg.get("search", {}).get("rerank", {})
    if rerank.get("enabled"):
        from fastembed.rerank.cross_encoder import TextCrossEncoder

        TextCrossEncoder(model_name=rerank["model"])
        print(f"Re-ranker {rerank['model']} : ok")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Indexe NeoFlow (code + docs) dans Qdrant et BM25.")
    parser.add_argument("--config", help="chemin de config.yaml (défaut : à côté de ce script)")
    parser.add_argument("--incremental", action="store_true", help="ne retraiter que les fichiers modifiés/supprimés")
    parser.add_argument("--dry-run", action="store_true", help="sélection + chunking uniquement")
    parser.add_argument("--explain", metavar="FICHIER", help="afficher le découpage d'un fichier (chemin relatif au dépôt)")
    parser.add_argument("--list-files", action="store_true", help="lister les fichiers retenus et écartés")
    parser.add_argument("--prefetch", action="store_true", help="pré-télécharger grammaires et modèles")
    args = parser.parse_args(argv)
    cfg = load_config(args.config)
    if args.explain:
        explain(cfg, args.explain)
        return 0
    if args.prefetch:
        prefetch(cfg)
        return 0
    if args.list_files:
        sel = select_corpus(cfg)
        print("\n".join(f"  + {f}" for f in sel.files))
        for reason, files in sel.skipped.items():
            for f in files[:15]:
                print(f"  - [{reason}] {f}")
            if len(files) > 15:
                print(f"  - [{reason}] ... {len(files) - 15} autres")
        return 0
    try:
        run_index(cfg, incremental=args.incremental, dry_run=args.dry_run)
    except (BackendUnavailableError, RuntimeError) as exc:
        print(f"ERREUR : {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
