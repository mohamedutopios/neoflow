#!/usr/bin/env python3
"""Langfuse pour les laboratoires Python de NeoFlow (J10).

Sous-commandes :
  verifier   contrôle les variables LANGFUSE_* et la santé de l'instance (/api/public/health)
  journal    pousse des journaux de trajectoire neoagent (J4) en OpenTelemetry (OTLP) : une trace par
             session, une `generation` par appel LLM (modèle, usage, coût par formule si --tarifs),
             un `tool` par appel d'outil, les approbations et les erreurs ; --dry-run sans réseau
  rag        rejoue le jeu de référence du J05 sur le Searcher de labs/rag et trace chaque recherche
             (observation `retriever` : latence, passages) avec deux scores par trace :
             recall_at_k (part des fichiers attendus trouvés) et rr (rang réciproque du 1er attendu)

Exemples (depuis labs/evals/) :
  uv run --extra langfuse mesure/langfuse_labs.py verifier
  uv run --extra langfuse mesure/langfuse_labs.py journal mesure/exemples/*.jsonl --tag J10 \
      --tarifs mesure/exemples/tarifs_fictifs.yaml [--dry-run]
  # « rag » importe le Searcher du J05 : il s'exécute dans l'environnement de labs/rag (Qdrant,
  # LlamaIndex, BM25), complété par le SDK Langfuse
  uv run --project ../rag --with "langfuse>=3" python mesure/langfuse_labs.py rag \
      --questions rag_questions.yaml --modes hybrid,bm25 -k 5 --label chunking-ast
  uv run --project ../rag python mesure/langfuse_labs.py rag --hors-ligne        # sans Langfuse

Les métriques de référence du J05 restent celles de labs/rag (Recall@k, MRR) : ce script ajoute la
vue Langfuse (distribution des latences, comparaison de deux configurations par tag, traces
inspectables). Pour le workflow LangGraph du J09, voir README.md (CallbackHandler, une ligne).
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import statistics
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ICI = Path(__file__).resolve().parent
sys.path.insert(0, str(ICI.parent))
from run_regression import charger_questions_rag  # noqa: E402  (lecture tolérante du jeu J05)


def verifier() -> int:
    host = os.environ.get("LANGFUSE_HOST") or os.environ.get("LANGFUSE_BASE_URL") or "http://localhost:3000"
    ok = True
    for var in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY"):
        present = bool(os.environ.get(var))
        ok &= present
        print(f"{var:22} {'définie' if present else 'ABSENTE'}")
    try:
        with urllib.request.urlopen(host.rstrip("/") + "/api/public/health", timeout=3) as r:
            print(f"{'Santé':22} {host} → HTTP {r.status}")
            ok &= r.status == 200
    except urllib.error.HTTPError as exc:
        print(f"{'Santé':22} {host} répond HTTP {exc.code} : est-ce bien Langfuse (port 3000 déjà pris) ?")
        ok = False
    except (urllib.error.URLError, OSError) as exc:
        print(f"{'Santé':22} {host} injoignable ({exc})")
        ok = False
    return 0 if ok else 1


def poster_score(trace_id: str, nom: str, valeur: float, commentaire: str = "") -> bool:
    """POST /api/public/scores, un objet par appel.

    Constaté le 2026-11-04 : le SDK Python 5.x envoie les scores en lot (tableau), format refusé par un
    serveur Langfuse 3.x (ZodError « expected object, received array »). L'API publique unitaire
    fonctionne avec les deux générations de serveur.
    """
    host = os.environ.get("LANGFUSE_HOST") or os.environ.get("LANGFUSE_BASE_URL") or "http://localhost:3000"
    jeton = base64.b64encode(f"{os.environ['LANGFUSE_PUBLIC_KEY']}:{os.environ['LANGFUSE_SECRET_KEY']}".encode()).decode()
    corps = json.dumps({"traceId": trace_id, "name": nom, "value": valeur, "dataType": "NUMERIC",
                        "comment": commentaire or None}).encode()
    req = urllib.request.Request(host.rstrip("/") + "/api/public/scores", data=corps, method="POST",
                                 headers={"Authorization": f"Basic {jeton}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return 200 <= r.status < 300
    except (urllib.error.URLError, OSError) as exc:
        print(f"[score non envoyé] {nom} : {exc}", file=sys.stderr)
        return False


def score_question(chemins: list[str], attendus: list[str]) -> tuple[float, float]:
    def trouve(attendu: str, chemin: str) -> bool:
        return chemin == attendu or chemin.endswith("/" + attendu) or attendu.endswith("/" + chemin)

    rappel = sum(1 for a in attendus if any(trouve(a, c) for c in chemins)) / len(attendus)
    rang = next((i for i, c in enumerate(chemins, 1) if any(trouve(a, c) for a in attendus)), None)
    return rappel, (1 / rang if rang else 0.0)


def rag(args) -> int:
    questions = charger_questions_rag(Path(args.questions))
    if not questions:
        print("Aucune question exploitable (clés question + fichiers attendus).", file=sys.stderr)
        return 2
    sys.path.insert(0, str(Path(args.rag_dir).resolve()))
    try:
        from search import Searcher  # API stable du lab J05
    except ImportError as exc:
        print(f"Lab RAG introuvable dans {args.rag_dir} : {exc}", file=sys.stderr)
        return 2
    lf = propager = None
    if not args.hors_ligne:
        from langfuse import get_client, propagate_attributes
        lf, propager = get_client(), propagate_attributes
    modes = [m.strip() for m in args.modes.split(",") if m.strip()]
    lignes = {m: [] for m in modes}
    with Searcher(args.config) if args.config else Searcher() as s:
        for q in questions:
            for mode in modes:
                t0 = time.perf_counter()
                if lf:
                    with propager(trace_name=f"rag {q['id']} {mode}", session_id=args.label,
                                  tags=["rag-j05", mode, args.label]):
                        with lf.start_as_current_observation(name=f"search {mode}", as_type="retriever",
                                                             input={"question": q["question"], "mode": mode, "k": args.k}) as obs:
                            hits = s.search(q["question"], mode=mode, k=args.k)
                            ms = (time.perf_counter() - t0) * 1000
                            obs.update(output=[{"path": h["path"], "lignes": f"{h.get('start_line')}-{h.get('end_line')}",
                                                "score": h.get("score")} for h in hits],
                                       metadata={"latence_ms": round(ms, 1), "attendus": q["attendus"]})
                            trace_id = lf.get_current_trace_id()
                else:
                    hits = s.search(q["question"], mode=mode, k=args.k)
                    ms = (time.perf_counter() - t0) * 1000
                rappel, rr = score_question([h["path"] for h in hits], q["attendus"])
                if lf:
                    poster_score(trace_id, f"recall_at_{args.k}", rappel, f"attendus : {', '.join(q['attendus'])}")
                    poster_score(trace_id, "rr", rr)
                lignes[mode].append((q["id"], rappel, rr, ms))
    if lf:
        lf.flush()
    print(f"| Mode | Questions | Recall@{args.k} | MRR | Latence p50 (ms) | Latence max (ms) |")
    print("|---|---|---|---|---|---|")
    for mode, l in lignes.items():
        lat = [x[3] for x in l]
        print(f"| {mode} | {len(l)} | {statistics.mean(x[1] for x in l):.2f} | {statistics.mean(x[2] for x in l):.2f} | "
              f"{statistics.median(lat):.0f} | {max(lat):.0f} |")
    if lf:
        print(f"\nTraces envoyées (session Langfuse « {args.label} »). Comparez deux labels par les tags.", file=sys.stderr)
    return 0


# ------------------------------------------------------------------ journaux neoagent → Langfuse (OTLP)
A_TYPE, A_INPUT, A_OUTPUT = "langfuse.observation.type", "langfuse.observation.input", "langfuse.observation.output"
A_MODELE, A_USAGE, A_COUT = "langfuse.observation.model.name", "langfuse.observation.usage_details", "langfuse.observation.cost_details"
A_NIVEAU, A_META = "langfuse.observation.level", "langfuse.observation.metadata"
A_TRACE_NOM, A_TAGS, A_SESSION, A_ENV = "langfuse.trace.name", "langfuse.trace.tags", "session.id", "langfuse.environment"


def _ns(t) -> int:
    return int(t.timestamp() * 1_000_000_000)


def _tronquer(v, n=2000) -> str:
    t = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False, default=str)
    return t if len(t) <= n else t[:n] + "…"


def pousser_journaux(args) -> int:
    """Rejoue chaque journal en spans OpenTelemetry avec ses horodatages d'origine (attributs Langfuse)."""
    from opentelemetry import trace as ot
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
    from couts import charger_tarifs, cout
    from trajectoire import JournalIllisible, lire_journal

    tarifs = charger_tarifs(args.tarifs)
    provider = TracerProvider(resource=Resource.create({"service.name": "neoagent"}))
    if args.dry_run:
        memoire = InMemorySpanExporter()
        provider.add_span_processor(SimpleSpanProcessor(memoire))
    else:
        if verifier() != 0:
            print("Langfuse non prêt : voir ci-dessus (ou --dry-run).", file=sys.stderr)
            return 1
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        host = os.environ.get("LANGFUSE_HOST") or os.environ.get("LANGFUSE_BASE_URL") or "http://localhost:3000"
        jeton = base64.b64encode(f"{os.environ['LANGFUSE_PUBLIC_KEY']}:{os.environ['LANGFUSE_SECRET_KEY']}".encode()).decode()
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(
            endpoint=host.rstrip("/") + "/api/public/otel/v1/traces", headers={"Authorization": f"Basic {jeton}"})))
    tracer = provider.get_tracer("neoflow.labs.evals")
    for f in args.fichiers:
        try:
            t = lire_journal(f)
        except JournalIllisible as exc:
            print(f"[ignoré] {exc}", file=sys.stderr)
            continue
        if not t.debut_ts:
            print(f"[ignoré] {f} : aucun horodatage", file=sys.stderr)
            continue
        racine = tracer.start_span(f"neoagent {Path(f).stem}", start_time=_ns(t.debut_ts), attributes={
            A_TYPE: "agent", A_TRACE_NOM: f"neoagent {Path(f).stem}", A_TAGS: ["neoagent"] + list(args.tag),
            A_SESSION: args.session_langfuse or (t.sessions[0] if t.sessions else Path(f).stem), A_ENV: "formation",
            A_OUTPUT: _tronquer(t.reponse), A_META: json.dumps({"statut": t.statut_fin, "etapes": t.etape_max})})
        ctx = ot.set_span_in_context(racine)
        instants = sorted([a.fin for a in t.appels if a.fin] + [a["ts"] for a in t.approbations if a["ts"]]
                          + [a["ts"] for a in t.appels_llm if a["ts"]])
        for a in t.appels_llm:
            if not a["ts"]:
                continue
            debut = max([x for x in instants if x < a["ts"]], default=t.debut_ts)
            attrs = {A_TYPE: "generation", A_MODELE: a["modele"] or "inconnu", A_META: json.dumps({"etape": a["etape"]}),
                     A_USAGE: json.dumps({"input": a["usage"]["input_tokens"], "output": a["usage"]["output_tokens"],
                                          "cache_read_input_tokens": a["usage"]["cache_read_input_tokens"],
                                          "cache_creation_input_tokens": a["usage"]["cache_creation_input_tokens"]})}
            if tarifs:
                total, _, manquants = cout({a["modele"]: a["usage"]}, tarifs)
                if total is not None:
                    attrs[A_COUT] = json.dumps({"total": total})
            s = tracer.start_span(f"llm étape {a['etape']}", context=ctx, start_time=_ns(debut), attributes=attrs)
            s.end(end_time=_ns(a["ts"]))
        for a in t.appels:
            attrs = {A_TYPE: "tool", A_META: json.dumps({"famille": a.famille, "statut": a.statut, "etape": a.etape})}
            if not args.sans_contenu:
                attrs |= {A_INPUT: _tronquer(a.entree), A_OUTPUT: _tronquer(a.sortie)}
            if a.statut in ("erreur", "refuse"):
                attrs[A_NIVEAU] = "ERROR" if a.statut == "erreur" else "WARNING"
            s = tracer.start_span(f"outil {a.outil}", context=ctx, start_time=_ns(a.debut or t.debut_ts), attributes=attrs)
            s.end(end_time=_ns(a.fin or a.debut or t.debut_ts))
        for a in t.approbations:
            if a["ts"]:
                s = tracer.start_span(f"approbation {a['cible']}", context=ctx, start_time=_ns(a["ts"]), attributes={
                    A_TYPE: "event", A_META: json.dumps({"accepte": a["accepte"], "action": a["action"]})})
                s.end(end_time=_ns(a["ts"]))
        racine.end(end_time=_ns(t.fin_ts or t.debut_ts))
        print(f"{Path(f).name} : {len(t.appels_llm)} appel(s) LLM, {len(t.appels)} outil(s)", file=sys.stderr)
    provider.force_flush()
    if args.dry_run:
        spans = memoire.get_finished_spans()
        from collections import Counter
        print(json.dumps({"traces": len({s.context.trace_id for s in spans}), "observations": len(spans),
                          "par_type": dict(Counter(s.attributes.get(A_TYPE) for s in spans))}, indent=2, ensure_ascii=False))
    provider.shutdown()
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0], formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="commande", required=True)
    sub.add_parser("verifier")
    j = sub.add_parser("journal")
    j.add_argument("fichiers", nargs="+", help="journaux neoagent .jsonl (ou dossiers)")
    j.add_argument("--tag", action="append", default=[])
    j.add_argument("--session-langfuse", help="regroupe les traces dans une session Langfuse")
    j.add_argument("--tarifs", help="calcule le coût de chaque appel LLM (couts.py)")
    j.add_argument("--sans-contenu", action="store_true", help="n'envoie que les métriques")
    j.add_argument("--dry-run", action="store_true")
    r = sub.add_parser("rag")
    r.add_argument("--questions", default=str(ICI.parent / "rag_questions.yaml"))
    r.add_argument("--rag-dir", default=str(ICI.parent.parent / "rag"))
    r.add_argument("--config", help="config.yaml du lab RAG (défaut : celle du lab)")
    r.add_argument("--modes", default="hybrid,bm25")
    r.add_argument("-k", type=int, default=5)
    r.add_argument("--label", default="rag-j05", help="nom de la configuration évaluée (session et tag Langfuse)")
    r.add_argument("--hors-ligne", action="store_true", help="calcule sans envoyer à Langfuse")
    args = ap.parse_args(argv)
    if args.commande == "journal":
        return pousser_journaux(args)
    return verifier() if args.commande == "verifier" else rag(args)


if __name__ == "__main__":
    sys.exit(main())
