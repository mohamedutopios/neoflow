"""Évaluation reproductible du retrieval NeoFlow sur labs/evals/rag_questions.yaml.

Métriques par mode (native, vector, bm25, hybrid) :
  Recall@k     part des fichiers attendus (expected) présents dans le top-k, moyenne sur les questions
  Hit@k        au moins un fichier pertinent (expected + also_relevant) dans le top-k
  MRR          moyenne de 1/rang du premier passage pertinent (0 si absent du top-k)
  Précision@k  part des passages du top-k issus d'un fichier pertinent
  Évidence@k   un passage du top-k contient l'élément de preuve attendu (champ evidence)
  Obsolète@k   un document obsolète connu remonte dans le top-k (champ obsolete)
  Latence      p50 / p95 en ms (après échauffement)

Option --faithfulness N : pour N questions, réponse générée à partir du top-5 hybride, puis
vérification (citations valides, mots-clés attendus, juge affirmation par affirmation).
Fournisseurs (rag_llm.py) : offline par défaut (déterministe, sans réseau), anthropic (Claude,
ANTHROPIC_API_KEY, consomme des tokens), ollama ou neogen (API compatible OpenAI).

Usage :
    uv run python eval.py                               # 4 modes, tableau Markdown sur stdout
    uv run python eval.py -k 5 --out ../../ia-toolbox/evals/rag_resultats.md --json resultats.json
    uv run python eval.py --modes bm25,hybrid --gate hybrid:recall@5:0.70
    uv run python eval.py --faithfulness 5                         # offline : aucun appel réseau
    uv run python eval.py --faithfulness 5 --fournisseur ollama    # génération locale, juge heuristique
"""
from __future__ import annotations

import argparse
import json
import platform
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

import yaml

import rag_metriques
from rag_common import LAB_DIR, charger_composant, composants_declares, percentile, strip_accents
from search import MODES, Searcher

DEFAULT_QUESTIONS = LAB_DIR.parent / "evals" / "rag_questions.yaml"


def norm(text: str) -> str:
    return strip_accents(text).lower()


def load_questions(path: Path) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    for q in data["questions"]:
        q["expected"] = [e if isinstance(e, dict) else {"path": e} for e in q.get("expected", [])]
        q["also_relevant"] = [e if isinstance(e, str) else e["path"] for e in q.get("also_relevant", [])]
        q.setdefault("evidence", [])
        q.setdefault("obsolete", [])
        q.setdefault("categorie", "autre")
    return data


class Metriques:
    """Fonctions de métriques : celles du composant de TP (composants.metriques) si déclaré,
    sinon celles du lab (rag_metriques.py), fonction par fonction."""

    def __init__(self, module=None):
        self.source = {}
        for nom in rag_metriques.NOMS:
            fn = getattr(module, nom, None) if module is not None else None
            setattr(self, nom, fn or getattr(rag_metriques, nom))
            self.source[nom] = "tp" if fn else "lab"


M = Metriques()


def score_question(q: dict, hits: list[dict], k: int, corpus: set[str]) -> dict:
    expected = [e for e in q["expected"] if e["path"] in corpus]
    exp_paths = {e["path"] for e in expected}                       # requis : base du Recall
    relevant = exp_paths | {p for p in q["also_relevant"] if p in corpus}  # pertinents : Hit, MRR, Précision
    top = hits[:k]
    paths = [h["path"] for h in hits]
    first = next((i + 1 for i, p in enumerate(paths[:k]) if p in relevant), None)   # affichage du détail
    symbols = [e for e in expected if e.get("symbol")]
    symbol_hit = None
    if symbols:
        symbol_hit = any(h["path"] == e["path"] and (e["symbol"].split(".")[-1] in (h.get("symbol") or "")
                                                     or e["symbol"].split(".")[-1] in (h.get("members") or "").split(", "))
                         for h in top for e in symbols)
    evidence_hit = None
    if q["evidence"]:
        texts = [norm(h["text"]) for h in top]
        evidence_hit = any(norm(ev) in t for ev in q["evidence"] for t in texts)
    obsolete_rank = next((i + 1 for i, p in enumerate(paths[:k]) if p in set(q["obsolete"])), None)
    return {
        "recall": M.recall_at_k(paths, exp_paths, k),
        "hit": bool(M.hit_at_k(paths, relevant, k)),
        "rr": float(M.reciprocal_rank(paths, relevant, k)),
        "first_rank": first,
        "precision": float(M.precision_at_k(paths, relevant, k)),
        "symbol_hit": symbol_hit,
        "evidence_hit": evidence_hit,
        "obsolete_rank": obsolete_rank,
        "obsolete_before_truth": obsolete_rank is not None and (first is None or obsolete_rank < first),
        "top_paths": paths[:k],
        "top_citations": [h["citation"] for h in top],
    }


def mean(values: list) -> float | None:
    vals = [float(v) for v in values if v is not None]
    return sum(vals) / len(vals) if vals else None


def run_eval(searcher: Searcher, data: dict, modes: list[str], k: int, ks: list[int]) -> dict:
    corpus = set(searcher._corpus_files())
    indexed = set(searcher.manifest["files"])
    questions = data["questions"]
    evaluable, skipped = [], []
    for q in questions:
        present = [e["path"] for e in q["expected"] if e["path"] in corpus and e["path"] in indexed]
        (evaluable if present else skipped).append(q)
    kmax = max([k] + ks)
    per_q: dict[str, dict] = defaultdict(dict)
    latencies: dict[str, list[float]] = {m: [] for m in modes}
    for mode in modes:
        searcher.search(questions[0]["question"], mode=mode, k=kmax)  # échauffement (modèle, client)
        for q in evaluable:
            t0 = time.perf_counter()
            hits = searcher.search(q["question"], mode=mode, k=kmax)
            latencies[mode].append((time.perf_counter() - t0) * 1000)
            res = {f"recall@{kk}": score_question(q, hits, kk, corpus)["recall"] for kk in ks}
            res.update(score_question(q, hits, k, corpus))
            per_q[q["id"]][mode] = res
    summary = {}
    for mode in modes:
        rows = [per_q[q["id"]][mode] for q in evaluable]
        summary[mode] = {
            **{f"recall@{kk}": mean([r[f"recall@{kk}"] for r in rows]) for kk in ks},
            "hit": mean([r["hit"] for r in rows]),
            "mrr": M.mrr([r["rr"] for r in rows]),
            "precision": mean([r["precision"] for r in rows]),
            "symbol": mean([r["symbol_hit"] for r in rows]),
            "evidence": mean([r["evidence_hit"] for r in rows]),
            "obsolete": sum(1 for r in rows if r["obsolete_rank"]),
            "obsolete_before_truth": sum(1 for r in rows if r["obsolete_before_truth"]),
            "p50_ms": percentile(latencies[mode], 50),
            "p95_ms": percentile(latencies[mode], 95),
        }
    by_cat: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for q in evaluable:
        for mode in modes:
            by_cat[q["categorie"]][mode].append(per_q[q["id"]][mode]["rr"])
    m = searcher.manifest
    return {
        "k": k, "ks": ks, "modes": modes, "summary": summary, "per_question": per_q,
        "evaluable": [q["id"] for q in evaluable], "skipped": [q["id"] for q in skipped],
        "questions": {q["id"]: q for q in questions},
        "by_category": {c: {mo: mean(v) for mo, v in d.items()} for c, d in by_cat.items()},
        "context": {
            "commit": m["git"]["commit"], "branch": m["git"]["branch"], "indexed_at": m["indexed_at"],
            "embedding": f"{m['embedding']['provider']}/{m['embedding']['model']} ({m['embedding']['dim']} dim)",
            "qdrant": m["qdrant"]["mode"], "chunks": m["chunks"], "files": len(m["files"]),
            "rrf_k": searcher.scfg.get("rrf_k", 60), "candidates": searcher.scfg.get("candidates", 30),
            "max_per_file": searcher.scfg.get("max_per_file", 0),
            "rankers": "+".join(searcher.scfg.get("hybrid_rankers", ["vector", "bm25"])),
            "native_backend": searcher.native_backend or "-",
            "composants": composants_declares(searcher.cfg),
            "metriques": "tp" if "tp" in M.source.values() else "lab",
            "machine": f"{platform.system()} {platform.machine()}, Python {platform.python_version()}",
            "date": time.strftime("%Y-%m-%d %H:%M"),
        },
    }


def fmt(v) -> str:
    if v is None:
        return "—"
    return f"{v:.2f}"


def render(res: dict) -> str:
    k, ks, modes = res["k"], res["ks"], res["modes"]
    c = res["context"]
    out = ["# Évaluation du retrieval NeoFlow", ""]
    out.append(f"Dépôt au commit `{c['commit']}` (branche `{c['branch']}`), indexé le {c['indexed_at']} ; "
               f"{c['files']} fichiers, {c['chunks']} chunks ; embeddings {c['embedding']} ; Qdrant {c['qdrant']}.")
    out.append(f"Hybride = RRF({c['rankers']}, k={c['rrf_k']}, {c['candidates']} candidats par liste) ; "
               f"max {c['max_per_file']} passage(s) par fichier ; natif via {c['native_backend']}. "
               f"Mesuré le {c['date']} sur {c['machine']}.")
    if c.get("composants"):
        out.append(f"Composants de TP actifs : {', '.join(f'{k} = `{v}`' for k, v in c['composants'].items())}.")
    out.append(f"Questions évaluées : {len(res['evaluable'])} / {len(res['questions'])}.")
    out.append("")
    head = ["Mode"] + [f"Recall@{kk}" for kk in ks] + [f"Hit@{k}", "MRR", f"Précision@{k}", f"Symbole@{k}",
                                                       f"Évidence@{k}", f"Obsolète@{k}", "p50 ms", "p95 ms"]
    out.append("| " + " | ".join(head) + " |")
    out.append("|" + "---|" * len(head))
    for mode in modes:
        s = res["summary"][mode]
        row = [f"**{mode}**"] + [fmt(s[f"recall@{kk}"]) for kk in ks] + [
            fmt(s["hit"]), fmt(s["mrr"]), fmt(s["precision"]), fmt(s["symbol"]), fmt(s["evidence"]),
            f"{s['obsolete']} ({s['obsolete_before_truth']} avant la vérité)",
            f"{s['p50_ms']:.0f}", f"{s['p95_ms']:.0f}"]
        out.append("| " + " | ".join(row) + " |")
    out += ["", f"## Détail par question (rang du premier fichier attendu, — = absent du top-{k})", ""]
    out.append("| Id | Catégorie | Question | " + " | ".join(modes) + " | Meilleur |")
    out.append("|---|---|---|" + "---|" * len(modes) + "---|")
    for qid in res["evaluable"]:
        q = res["questions"][qid]
        cells, best = [], []
        rrs = {m: res["per_question"][qid][m]["rr"] for m in modes}
        top = max(rrs.values())
        for m in modes:
            r = res["per_question"][qid][m]
            cell = str(r["first_rank"]) if r["first_rank"] else "—"
            if r["recall"] is not None and r["recall"] < 1 and r["first_rank"]:
                cell += f" ({r['recall']:.0%})"
            if r["obsolete_rank"]:
                cell += f" obs.{r['obsolete_rank']}"
            cells.append(cell)
            if top > 0 and rrs[m] == top:
                best.append(m)
        question = q["question"] if len(q["question"]) <= 70 else q["question"][:67] + "…"
        out.append(f"| {qid} | {q['categorie']} | {question} | " + " | ".join(cells) + f" | {', '.join(best) or 'aucun'} |")
    out += ["", "Légende : `2 (50%)` = premier fichier attendu au rang 2, la moitié des fichiers attendus trouvés ; "
            "`obs.3` = document obsolète au rang 3.", "", "## MRR par type de requête", ""]
    out.append("| Catégorie | " + " | ".join(modes) + " |")
    out.append("|---|" + "---|" * len(modes))
    for cat, vals in sorted(res["by_category"].items()):
        out.append(f"| {cat} | " + " | ".join(fmt(vals.get(m)) for m in modes) + " |")
    if res["skipped"]:
        out += ["", "## Questions non évaluables", "",
                "Aucun fichier attendu n'est présent dans le corpus indexé (socle incomplet ou liste blanche) : "
                + ", ".join(res["skipped"]) + "."]
    if res.get("faithfulness"):
        f = res["faithfulness"]
        out += ["", "## Fidélité des réponses générées (top-5 hybride)", "",
                f"Génération : `{f['answer_model']}` ; juge : `{f['judge_model']}` ; tokens entrée/sortie : "
                f"{f['tokens_in']} / {f['tokens_out']}."
                + (" En mode offline, la réponse est extractive : le score valide la chaîne de mesure, "
                   "pas un modèle." if f['answer_model'].startswith("offline") else ""), "",
                "| Id | Citations valides | Mots-clés attendus | Fidélité (juge) | Contradiction signalée |",
                "|---|---|---|---|---|"]
        for row in f["rows"]:
            out.append(f"| {row['id']} | {fmt(row['citations_valid'])} | {fmt(row['keywords'])} | "
                       f"{fmt(row['faithfulness'])} | {row['contradiction']} |")
        out.append(f"| **moyenne** | {fmt(mean([r['citations_valid'] for r in f['rows']]))} | "
                   f"{fmt(mean([r['keywords'] for r in f['rows']]))} | {fmt(mean([r['faithfulness'] for r in f['rows']]))} | |")
    return "\n".join(out) + "\n"


# --------------------------------------------------------------------------- #
# Fidélité : réponse générée à partir du top-5 hybride, puis jugement affirmation par affirmation
# --------------------------------------------------------------------------- #


def faithfulness(searcher: Searcher, data: dict, ids: list[str], fournisseur: str, juge: str) -> dict:
    """fournisseur / juge : offline (défaut, déterministe), anthropic, ou un fournisseur compatible OpenAI."""
    from rag_llm import juger, repondre

    cfg = searcher.cfg
    questions = {q["id"]: q for q in data["questions"]}
    rows, t_in, t_out = [], 0, 0
    for qid in ids:
        q = questions[qid]
        hits = searcher.search(q["question"], mode="hybrid", k=5)
        try:
            gen = repondre(q["question"], hits, fournisseur, cfg)
            verdict, gen_juge = juger(gen.texte, hits, juge, cfg)
        except Exception as exc:  # fournisseur injoignable, clé ou quota : on arrête proprement
            body = getattr(exc, "body", None)
            detail = body.get("error", {}).get("message") if isinstance(body, dict) else str(exc)
            rows.append({"id": qid, "citations_valid": None, "keywords": None, "faithfulness": None,
                         "contradiction": f"erreur : {type(exc).__name__}: {detail}"[:120], "answer": ""})
            break
        t_in += gen.input_tokens + (gen_juge.input_tokens if gen_juge else 0)
        t_out += gen.output_tokens + (gen_juge.output_tokens if gen_juge else 0)
        answer = gen.texte
        cited = [int(n) for n in re.findall(r"\[P(\d+)\]", answer)]
        valid = sum(1 for n in cited if 1 <= n <= len(hits)) / len(cited) if cited else 0.0
        kws = q.get("answer_keywords") or []
        kw = sum(1 for kword in kws if norm(kword) in norm(answer)) / len(kws) if kws else None
        claims = verdict.get("claims", [])
        faith = sum(1 for c in claims if c["supported"]) / len(claims) if claims else None
        rows.append({"id": qid, "citations_valid": valid, "keywords": kw, "faithfulness": faith,
                     "contradiction": "oui" if verdict.get("contradiction_signalee") else "non",
                     "answer": answer, "claims": claims})
    modele = lambda nom: "extractif (offline)" if nom == "offline" else (
        cfg["llm"][nom].get("answer_model") or cfg["llm"][nom].get("modele", "?"))
    juge_desc = "heuristique (offline)" if juge == "offline" else (
        cfg["llm"][juge].get("judge_model") or cfg["llm"][juge].get("modele", "?"))
    return {"answer_model": f"{fournisseur} / {modele(fournisseur)}", "judge_model": f"{juge} / {juge_desc}",
            "rows": rows, "tokens_in": t_in, "tokens_out": t_out}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Évalue les stratégies de recherche sur le jeu de référence.")
    parser.add_argument("--questions", default=str(DEFAULT_QUESTIONS))
    parser.add_argument("--modes", default=",".join(MODES))
    parser.add_argument("-k", type=int, default=5, help="k des métriques Hit/MRR/Précision/Évidence")
    parser.add_argument("--recall-k", default="1,3,5,10", help="valeurs de k pour Recall@k")
    parser.add_argument("--out", help="écrire le rapport Markdown dans ce fichier")
    parser.add_argument("--json", dest="json_out", help="écrire les résultats détaillés en JSON")
    parser.add_argument("--gate", action="append", default=[],
                        help="seuil bloquant MODE:METRIQUE:SEUIL, ex. hybrid:recall@5:0.7 (code retour 1 si non atteint) ; "
                             "métriques : recall@K, hit, mrr, precision, symbol, evidence")
    parser.add_argument("--faithfulness", type=int, default=0, metavar="N",
                        help="fidélité des réponses générées sur N questions (fournisseur : --fournisseur)")
    parser.add_argument("--fournisseur", help="génération : offline | anthropic | ollama | neogen (défaut : llm.fournisseur)")
    parser.add_argument("--juge", help="juge de fidélité : offline | anthropic | ollama | neogen (défaut : llm.juge)")
    parser.add_argument("--config", default=None)
    args = parser.parse_args(argv)

    data = load_questions(Path(args.questions))
    modes = [m.strip() for m in args.modes.split(",") if m.strip()]
    ks = [int(x) for x in args.recall_k.split(",")]
    global M
    with Searcher(args.config) as searcher:
        M = Metriques(charger_composant(searcher.cfg, "metriques"))
        try:
            res = run_eval(searcher, data, modes, args.k, ks)
        except (FileNotFoundError, ConnectionError) as exc:
            print(f"ERREUR : {exc}", file=sys.stderr)
            return 2
        if args.faithfulness:
            with_kw = [qid for qid in res["evaluable"] if res["questions"][qid].get("answer_keywords")]
            ids = (with_kw or res["evaluable"])[: args.faithfulness]
            llm = searcher.cfg.get("llm", {})
            res["faithfulness"] = faithfulness(searcher, data, ids, args.fournisseur or llm.get("fournisseur", "offline"),
                                               args.juge or llm.get("juge", "offline"))
    report = render(res)
    print(report)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(report, encoding="utf-8")
    if args.json_out:
        res_json = {k: v for k, v in res.items() if k != "questions"}
        Path(args.json_out).write_text(json.dumps(res_json, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    failed = []
    for gate in args.gate:
        mode, metric, threshold = gate.split(":")
        value = res["summary"].get(mode, {}).get(metric)
        if value is None or value < float(threshold):
            failed.append(f"{mode} {metric} = {fmt(value)} < {threshold}")
    if failed:
        print("SEUIL NON ATTEINT : " + " ; ".join(failed), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
