#!/usr/bin/env python3
"""Régression des prompts et des comportements de VOS outils IA (J10).

Rejoue des cas fixes (regression_prompts/*.yaml) sur :
  - `neoagent` (J4) : critères sur le journal de trajectoire JSONL, la réponse, le diff, des commandes ;
  - tout outil en ligne de commande (`neospec` du J3, `tests-ia` du J7, RAG J5…) : critères sur le code
    de retour, la sortie ou le fichier produit, les fichiers écrits et le journal d'usage s'il existe.

Trois façons d'exécuter :
  (défaut)   les outils tournent avec --offline (modèle simulé déterministe, aucun appel API) :
             régression de la plomberie, des gabarits de prompts et des formats de sortie ;
  --reel     les outils appellent l'API Claude (ANTHROPIC_API_KEY, consomme des tokens) :
             régression du comportement du modèle avec vos prompts ;
  --rejouer  aucun outil n'est lancé : on réévalue des enregistrements runN.jsonl / runN.sortie.

Exemples :
  uv run run_regression.py --rejouer regression_prompts/exemples_runs/config-A --label config-A
  uv run run_regression.py --rejouer regression_prompts/exemples_runs/config-B --label config-B \
      --reference resultats/config-A.json
  uv run run_regression.py --filtre 'NA0*' --label offline-1.4                # neoagent --offline
  uv run run_regression.py --reel --repetitions 3 --worktree --label reel-1.4 # coûte des tokens
  uv run run_regression.py --rag-questions rag_questions.yaml --filtre 'RAG-Q0*' --reel

Codes de sortie : 0 aucun cas KO (ou aucune régression avec --reference), 1 sinon, 2 erreur d'usage.
"""
from __future__ import annotations

import argparse
import datetime as dt
import fnmatch
import hashlib
import importlib
import json
import math
import os
import re
import shlex
import shutil
import statistics
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    sys.exit("PyYAML manquant : lancez via `uv run` (pyproject.toml) ou `pip install pyyaml`.")

ICI = Path(__file__).resolve().parent
sys.path.insert(0, str(ICI))
from criteres import CRITERES, Contexte, evaluer  # noqa: E402
from trajectoire import JournalIllisible, lire_journal, normaliser_fichiers  # noqa: E402

# CLI du J4 : --ecriture autorise l'écriture (politique générateur) ; hors terminal, --approbation vaut « refus »
# par défaut : le banc passe « accord » (approbations automatiques MAIS journalisées) pour les cas qui écrivent,
# toujours dans un worktree jetable.
NEOAGENT_CMD = ("uv run --project {agent_dir} neoagent --repo {repo} --tache {tache} --pattern {pattern} "
                "--mode {mode} --journal {journal} {offline} {ecriture} {approbation} {outils_externes}")


def lire_rapport(texte: str) -> dict:
    """Dernier objet JSON de la sortie standard : rapport de la CLI neoagent (statut, tours, verdicts…)."""
    for debut in [i for i, c in enumerate(texte) if c == "{"][::-1][:50]:
        try:
            obj = json.loads(texte[debut:])
            return obj if isinstance(obj, dict) else {}
        except json.JSONDecodeError:
            continue
    return {}
DOSSIERS_CONFIG = ["labs/agent/neoagent", "labs/spec", "labs/tests-ia", "labs/rag", "labs/mcp", "AGENTS.md", "ia-toolbox/rules"]


# ------------------------------------------------------------------ cas
def charger_cas(dossier: Path) -> list[dict]:
    cas = []
    for f in sorted(dossier.glob("*.yaml")) + sorted(dossier.glob("*.yml")):
        data = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        if not isinstance(data, dict) or "id" not in data or not (data.get("tache") or data.get("commande")):
            print(f"[ignoré] {f.name} : clés 'id' et 'tache' (neoagent) ou 'commande' obligatoires", file=sys.stderr)
            continue
        data["_fichier"] = f.name
        data.setdefault("outil", "neoagent" if data.get("tache") and not data.get("commande") else "commande")
        cas.append(data)
    return cas


CLES_QUESTION = ("question", "q", "texte")
CLES_ATTENDUS = ("expected", "fichiers_attendus", "expected_files", "attendus", "sources")


def charger_questions_rag(chemin: Path) -> list[dict]:
    """Jeu du J05 (labs/evals/rag_questions.yaml), lecture tolérante des noms de clés."""
    data = yaml.safe_load(chemin.read_text(encoding="utf-8")) or []
    items = data.get("questions", []) if isinstance(data, dict) else data
    res = []
    for i, it in enumerate(items or [], 1):
        if not isinstance(it, dict):
            continue
        q = next((it[k] for k in CLES_QUESTION if it.get(k)), None)
        att = next((it[k] for k in CLES_ATTENDUS if it.get(k)), [])
        att = [att] if isinstance(att, str) else att
        att = [a if isinstance(a, str) else str(a.get("path") or a.get("fichier") or "") for a in att]
        if q and att:
            res.append({"id": str(it.get("id") or f"Q{i:02d}"), "question": q, "attendus": [a for a in att if a],
                        "mots_cles": [str(m) for m in it.get("answer_keywords") or []], "categorie": it.get("categorie", "")})
    return res


def cas_depuis_rag(questions: list[dict], outil_regex: str, outils_externes: list[str]) -> list[dict]:
    cas = []
    for q in questions:
        crit = [{"id": "C1", "type": "outil_appele", "outil": outil_regex},
                {"id": "C2", "type": "cite_fichiers", "fichiers": q["attendus"], "min_ratio": 0.5},
                {"id": "C3", "type": "aucune_ecriture"}]
        if q["mots_cles"]:
            crit.append({"id": "C4", "type": "sortie_contient", "motifs": [re.escape(m) for m in q["mots_cles"]]})
        cas.append({"id": f"RAG-{q['id']}", "titre": f"Jeu J05 : {q['question'][:60]}", "outil": "neoagent",
                    "cible": f"rag ({q['categorie']})" if q["categorie"] else "rag", "pattern": "react", "mode": "structure",
                    "outils_externes": outils_externes, "repetitions": 1, "seuil": 1.0, "_fichier": "rag_questions",
                    "tache": (f"Question sur le dépôt NeoFlow : {q['question']}\nRépondez en 8 lignes maximum, en citant "
                              "chaque source sous la forme chemin:lignes. Ne modifiez aucun fichier."),
                    "criteres": crit, "budget": {"max_appels_outils": 20}})
    return cas


# ------------------------------------------------------------------ statistiques et comparaison
def lire_seuil(v) -> float:
    if isinstance(v, str) and "/" in v:
        a, b = v.split("/", 1)
        return int(a) / int(b)
    return float(v if v is not None else 1.0)


def wilson_bas(k: int, n: int, z: float = 1.96) -> float:
    if n == 0:
        return 0.0
    p = k / n
    centre = p + z * z / (2 * n)
    marge = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return round((centre - marge) / (1 + z * z / n), 3)


def agreger(cas: dict, runs: list[dict]) -> dict:
    n, k = len(runs), sum(1 for r in runs if r["statut"] == "OK")
    seuil = lire_seuil(cas.get("seuil"))
    par_critere = {}
    for r in runs:
        for c in r["criteres"]:
            e = par_critere.setdefault(c["id"], {"type": c["type"], "ok": 0, "evalues": 0})
            if c["ok"] is not None:
                e["evalues"] += 1
                e["ok"] += int(bool(c["ok"]))

    def med(cle):
        vals = [r[cle] for r in runs if r.get(cle) is not None]
        return statistics.median(vals) if vals else None

    return {"id": cas["id"], "titre": cas.get("titre", ""), "cible": cas.get("cible", ""), "outil": cas["outil"],
            "fichier": cas.get("_fichier"), "n": n, "reussis": k, "taux": round(k / n, 3) if n else 0.0, "seuil": seuil,
            "verdict": "OK" if n and k / n >= seuil - 1e-9 else "KO", "instable": 0 < k < n, "wilson_bas": wilson_bas(k, n),
            "mediane_tokens": med("tokens_total"), "mediane_appels": med("appels_outils"), "mediane_duree_s": med("duree_s"),
            "par_critere": par_critere, "runs": runs}


def comparer(actuel: dict, reference: dict) -> list[dict]:
    ref = {c["id"]: c for c in reference.get("cas", [])}
    lignes = []
    for c in actuel["cas"]:
        r = ref.get(c["id"])
        if r is None:
            lignes.append({"id": c["id"], "ecart": "NOUVEAU", "avant": "-", "apres": f"{c['reussis']}/{c['n']}"})
            continue
        if r["verdict"] == "OK" and c["verdict"] == "KO":
            ecart = "REGRESSION"
        elif r["verdict"] == "KO" and c["verdict"] == "OK":
            ecart = "AMELIORATION"
        elif c["verdict"] == "OK" and c["taux"] < r["taux"]:
            ecart = "BAISSE"
        else:
            ecart = "STABLE_OK" if c["verdict"] == "OK" else "KO_PERSISTANT"

        def delta(cle):
            a, b = r.get(cle), c.get(cle)
            return None if not a or b is None else round(100 * (b - a) / a, 1)

        modifies = []
        for cid, e in c["par_critere"].items():
            e0 = r.get("par_critere", {}).get(cid)
            if e0 and e0["evalues"] and e["evalues"] and e0["ok"] / e0["evalues"] != e["ok"] / e["evalues"]:
                modifies.append(f"{cid} ({e['type']}) {e0['ok']}/{e0['evalues']} → {e['ok']}/{e['evalues']}")
        lignes.append({"id": c["id"], "ecart": ecart, "avant": f"{r['reussis']}/{r['n']}", "apres": f"{c['reussis']}/{c['n']}",
                       "delta_tokens_pct": delta("mediane_tokens"), "delta_appels_pct": delta("mediane_appels"),
                       "criteres_modifies": modifies})
    for cid in set(ref) - {c["id"] for c in actuel["cas"]}:
        lignes.append({"id": cid, "ecart": "SUPPRIME", "avant": f"{ref[cid]['reussis']}/{ref[cid]['n']}", "apres": "-"})
    return lignes


# ------------------------------------------------------------------ évaluation d'un run
def evaluer_run(cas: dict, journal: Path | None, sortie: str, checks: dict, registre: dict, rapport: dict | None = None) -> dict:
    traj, detail_journal = None, ""
    try:
        traj = lire_journal(journal) if journal and journal.exists() and journal.stat().st_size else None
    except JournalIllisible as exc:
        detail_journal = str(exc)
    if cas["outil"] == "neoagent":
        if traj is None:
            return {"statut": "ERREUR", "criteres": [], "detail": detail_journal or "journal absent",
                    "tokens_total": 0, "appels_outils": 0, "duree_s": None, "fichier": str(journal)}
    fichiers = normaliser_fichiers(set(checks.get("fichiers_git", [])) | (traj.fichiers_modifies() if traj else set()),
                                   checks.get("racine"))
    texte = (traj.reponse if cas["outil"] == "neoagent" and traj and traj.reponse else "") or sortie
    ctx = Contexte(trajectoire=traj, fichiers=fichiers, controles=checks.get("controles", {}), sortie=texte,
                   code_retour=checks.get("code_retour"), rapport=rapport or {})
    res = evaluer(cas, ctx, registre)
    evalues = [r for r in res if r["ok"] is not None]
    statut = "OK" if evalues and all(r["ok"] for r in evalues) else "KO"
    return {"statut": statut, "criteres": res, "tokens_total": traj.tokens_total if traj else None,
            "appels_outils": len(traj.appels) if traj else None,
            "duree_s": round(traj.duree_s, 1) if traj and traj.duree_s is not None else None,
            "session": traj.sessions[0] if traj and traj.sessions else "",
            "avertissements": traj.avertissements if traj else [], "fichier": str(journal or "")}


def rejouer_run(cas: dict, base: Path, registre: dict) -> dict:
    stem = base.with_suffix("")
    sortie_f = stem.with_suffix(".sortie")
    checks_f = stem.with_suffix(".checks.json")
    checks = json.loads(checks_f.read_text(encoding="utf-8")) if checks_f.exists() else {}
    sortie = sortie_f.read_text(encoding="utf-8") if sortie_f.exists() else ""
    journal = stem.with_suffix(".jsonl")
    stdout_f = stem.parent / (stem.name + ".stdout.txt")
    rapport = lire_rapport(stdout_f.read_text(encoding="utf-8")) if stdout_f.exists() and cas["outil"] == "neoagent" else {}
    res = evaluer_run(cas, journal if journal.exists() else None, sortie, checks, registre, rapport)
    res["fichier"] = res.get("fichier") or str(stem.with_suffix(".sortie"))
    return res


# ------------------------------------------------------------------ exécution
def git(*args: str, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)


def fichiers_git(cwd: Path) -> set[str]:
    return {l[3:].strip() for l in git("status", "--porcelain", "--untracked-files=all", cwd=cwd).stdout.splitlines() if len(l) > 3}


def empreinte(racine: Path) -> str:
    h = hashlib.sha256()
    vus = 0
    for d in DOSSIERS_CONFIG:
        p = racine / d
        fichiers = [p] if p.is_file() else sorted(x for x in p.rglob("*") if x.is_file() and x.suffix in
                                                  (".py", ".md", ".txt", ".yaml", ".yml", ".java", ".json", ".j2", ".tmpl")
                                                  and not {".venv", "__pycache__", "target", "node_modules"} & set(x.parts)) if p.exists() else []
        for f in fichiers:
            h.update(str(f.relative_to(racine)).encode())
            h.update(f.read_bytes())
            vus += 1
    return h.hexdigest()[:12] if vus else "aucune-config"


def developper(valeur: str) -> str:
    """${VAR:-défaut} et ${VAR} depuis l'environnement."""
    return re.sub(r"\$\{(\w+)(?::-([^}]*))?\}", lambda m: os.environ.get(m.group(1), m.group(2) or ""), valeur)


def construire_commande(modele: str, valeurs: dict[str, str], listes: dict[str, list[str]]) -> list[str]:
    """Découpe le gabarit PUIS substitue : une tâche avec espaces ou retours à la ligne reste un seul argument."""
    argv = []
    for jeton in shlex.split(developper(modele)):
        if jeton.startswith("{") and jeton.endswith("}") and jeton[1:-1] in listes:
            argv += listes[jeton[1:-1]]
        else:
            argv.append(jeton.format(**valeurs) if "{" in jeton else jeton)
    return argv


def executer_controles(cas: dict, cwd: Path, timeout: int, valeurs: dict | None = None) -> dict:
    res = {}
    for crit in cas.get("criteres") or []:
        if crit.get("type") != "commande":
            continue
        cmd = crit["cmd"]
        for cle in ("dossier", "repo", "journal", "sortie"):   # marqueurs connus seulement (les {…} d'awk restent intacts)
            cmd = cmd.replace("{" + cle + "}", str((valeurs or {}).get(cle, "")))
        try:
            p = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True, timeout=timeout)
            res[crit["id"]] = {"cmd": crit["cmd"], "code": p.returncode, "extrait": (p.stdout + p.stderr)[-400:]}
        except subprocess.TimeoutExpired:
            res[crit["id"]] = {"cmd": crit["cmd"], "code": -1, "extrait": f"timeout {timeout}s"}
    return res


def executer_run(cas: dict, k: int, args, racine: Path, dossier_runs: Path, registre: dict) -> dict:
    d = dossier_runs / str(cas["id"])
    d.mkdir(parents=True, exist_ok=True)
    journal, sortie_f = d / f"run{k}.jsonl", d / f"run{k}.sortie"
    cwd, worktree = racine, None
    if args.worktree and cas.get("worktree", False):
        worktree = Path(tempfile.mkdtemp(prefix=f"rr-{cas['id']}-")) / "wt"
        p = git("worktree", "add", "--detach", str(worktree), "HEAD", cwd=racine)
        if p.returncode:
            raise RuntimeError(f"git worktree add : {p.stderr.strip()}")
        cwd = worktree
    avant = fichiers_git(cwd)
    dossier = d / f"run{k}.out"
    valeurs = {"agent_dir": str(Path(args.agent_dir).resolve()), "repo": str(cwd), "tache": str(cas.get("tache", "")).strip(),
               "pattern": cas.get("pattern", "react"), "mode": cas.get("mode", "structure"), "journal": str(journal),
               "sortie": str(sortie_f), "dossier": str(dossier),
               "entree": str((racine / cas["entree"]).resolve()) if cas.get("entree") else ""}
    ecrit = bool(cas.get("ecriture", cas.get("worktree", False)))
    listes = {"offline": [] if args.reel else ["--offline"],
              "ecriture": ["--ecriture"] if ecrit else [],
              "approbation": ["--approbation", str(cas.get("approbation", "accord" if ecrit else "refus"))],
              "outils_externes": [x for o in cas.get("outils_externes") or [] for x in ("--outils-externes", o)]}
    gabarit = args.neoagent_cmd if cas["outil"] == "neoagent" else cas["commande"]
    argv = construire_commande(gabarit, valeurs, listes)
    code, sortie = None, ""
    with open(d / f"run{k}.stdout.txt", "w", encoding="utf-8") as out, open(d / f"run{k}.stderr.log", "w") as err:
        try:
            code = subprocess.run(argv, cwd=cwd, stdout=out, stderr=err, timeout=args.timeout).returncode
        except subprocess.TimeoutExpired:
            code = -1
        except FileNotFoundError as exc:
            err.write(str(exc))
            code = 127
    stdout = (d / f"run{k}.stdout.txt").read_text(encoding="utf-8", errors="replace")
    produit = dossier / cas["fichier_sortie"] if cas.get("fichier_sortie") else None   # ex. rapport-generation.md
    if produit and produit.exists():
        sortie_f.write_text(produit.read_text(encoding="utf-8", errors="replace"), encoding="utf-8")
    sortie = sortie_f.read_text(encoding="utf-8", errors="replace") if sortie_f.exists() else stdout
    if not sortie_f.exists():
        sortie_f.write_text(sortie, encoding="utf-8")
    checks = {"racine": str(cwd), "fichiers_git": sorted(fichiers_git(cwd) - avant), "code_retour": code,
              "controles": executer_controles(cas, cwd, args.timeout_controle, valeurs), "commande": argv[:6] + ["…"]}
    (d / f"run{k}.checks.json").write_text(json.dumps(checks, indent=2, ensure_ascii=False), encoding="utf-8")
    if worktree and not args.garder_worktrees:
        git("worktree", "remove", "--force", str(worktree), cwd=racine)
        shutil.rmtree(worktree.parent, ignore_errors=True)
    rapport = lire_rapport(stdout) if cas["outil"] == "neoagent" else {}
    res = evaluer_run(cas, journal if journal.exists() else None, sortie, checks, registre, rapport)
    if code == -1:
        res["statut"] = "TIMEOUT"
    return res


# ------------------------------------------------------------------ rapport
def rapport_markdown(res: dict) -> str:
    l = [f"# Régression des outils IA — {res['label']}", "",
         f"- Mode : {res['mode']} · date : {res['date']} · empreinte : `{res['empreinte']}`",
         f"- Cas : {len(res['cas'])} · runs : {sum(c['n'] for c in res['cas'])}", "",
         "| Cas | Outil | Cible | Réussite | Seuil | Wilson bas | Verdict | Tokens (méd.) | Outils (méd.) |",
         "|---|---|---|---|---|---|---|---|---|"]
    for c in res["cas"]:
        f = lambda v: "-" if v is None else v  # noqa: E731
        l.append(f"| {c['id']} | {c['outil']} | {c['cible']} | {c['reussis']}/{c['n']} | {c['seuil']:.0%} | "
                 f"{c['wilson_bas']:.2f} | {c['verdict']}{' (instable)' if c['instable'] else ''} | "
                 f"{f(c['mediane_tokens'])} | {f(c['mediane_appels'])} |")
    echecs = [(c, r) for c in res["cas"] for r in c["runs"] if r["statut"] != "OK"]
    if echecs:
        l += ["", "## Critères en échec", ""]
        for c, r in echecs:
            ko = [f"{x['id']} {x['type']} : {' '.join(str(x['detail']).split())}" for x in r["criteres"] if x["ok"] is False]
            l.append(f"- **{c['id']}** {Path(r.get('fichier') or '').name} ({r['statut']}) : " + ("; ".join(ko) or r.get("detail", "")))
    if res.get("comparaison"):
        l += ["", f"## Écarts par rapport à `{res['reference']}`", "",
              "| Cas | Écart | Avant | Après | Δ tokens | Δ appels | Critères modifiés |", "|---|---|---|---|---|---|---|"]
        for e in res["comparaison"]:
            fmt = lambda v: "-" if v is None else f"{v:+.1f} %"  # noqa: E731
            l.append(f"| {e['id']} | **{e['ecart']}** | {e['avant']} | {e['apres']} | {fmt(e.get('delta_tokens_pct'))} | "
                     f"{fmt(e.get('delta_appels_pct'))} | {'; '.join(e.get('criteres_modifies', [])) or '-'} |")
    l += ["", "> Borne basse de Wilson (95 %) : taux de réussite minimal compatible avec les runs observés. "
          "3 réussites sur 3 ne garantissent que 0,44."]
    return "\n".join(l)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0], formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cas", default=str(ICI / "regression_prompts"))
    ap.add_argument("--filtre", help="motif sur l'identifiant, ex. 'NA0[1-3]*'")
    ap.add_argument("--label", default="courant")
    ap.add_argument("--repetitions", type=int)
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--reel", action="store_true", help="les outils appellent l'API Claude (consomme des tokens)")
    mode.add_argument("--rejouer", metavar="DOSSIER", help="réévalue des enregistrements <cas>/runN.* sans rien lancer")
    ap.add_argument("--agent-dir", default=os.environ.get("NEOAGENT_DIR", str(ICI.parent / "agent")))
    ap.add_argument("--neoagent-cmd", default=os.environ.get("NEOAGENT_CMD", NEOAGENT_CMD), help="gabarit de commande")
    ap.add_argument("--worktree", action="store_true", help="les cas « worktree: true » s'exécutent dans un worktree jetable")
    ap.add_argument("--garder-worktrees", action="store_true")
    ap.add_argument("--timeout", type=int, default=900)
    ap.add_argument("--timeout-controle", type=int, default=900)
    ap.add_argument("--reference", help="résultats JSON d'une configuration de référence")
    ap.add_argument("--criteres-externes", action="append", default=[], help="module Python exposant CRITERES")
    ap.add_argument("--rag-questions", help="jeu du J05 transformé en cas neoagent (RAG-*)")
    ap.add_argument("--rag-outil", default=r"rag\w*|rechercher\w*", help="regex de l'outil RAG attendu")
    ap.add_argument("--rag-outils-externes", default="rag.agent_tool:rag_tool", help="--outils-externes passé à neoagent")
    ap.add_argument("--sortie", default=str(ICI / "resultats"))
    args = ap.parse_args(argv)

    registre = dict(CRITERES)
    for nom in args.criteres_externes:
        sys.path.insert(0, str(Path.cwd()))
        registre.update(getattr(importlib.import_module(nom), "CRITERES"))
    if args.reel and not os.environ.get("ANTHROPIC_API_KEY"):
        print("--reel exige ANTHROPIC_API_KEY (clé fournie par Neosoft, jamais dans le dépôt).", file=sys.stderr)
        return 2

    cas = charger_cas(Path(args.cas))
    if args.rag_questions:
        cas += cas_depuis_rag(charger_questions_rag(Path(args.rag_questions)), args.rag_outil, [args.rag_outils_externes])
    if args.filtre:
        cas = [c for c in cas if fnmatch.fnmatch(str(c["id"]), args.filtre)]
    if not cas:
        print("Aucun cas à exécuter.", file=sys.stderr)
        return 2

    sortie = Path(args.sortie)
    sortie.mkdir(parents=True, exist_ok=True)
    res = {"label": args.label, "date": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
           "mode": "rejeu" if args.rejouer else ("reel" if args.reel else "offline"), "cas": []}
    if args.rejouer:
        base = Path(args.rejouer)
        meta = yaml.safe_load((base / "meta.yaml").read_text(encoding="utf-8")) if (base / "meta.yaml").exists() else {}
        res.update({"empreinte": meta.get("empreinte", "enregistrement"), "description": meta.get("description", "")})
        for c in cas:
            noms = sorted({p.name.split(".")[0] for p in (base / str(c["id"])).glob("run*.*")
                           if re.fullmatch(r"run\d+", p.name.split(".")[0])}, key=lambda x: int(x[3:]))
            runs = [base / str(c["id"]) / nom for nom in noms][: args.repetitions or None]
            if not runs:
                print(f"[rejeu] {c['id']} : aucun enregistrement, cas ignoré", file=sys.stderr)
                continue
            res["cas"].append(agreger(c, [rejouer_run(c, r, registre) for r in runs]))
    else:
        p = git("rev-parse", "--show-toplevel", cwd=Path.cwd())
        racine = Path(p.stdout.strip()) if p.returncode == 0 else Path.cwd()
        res.update({"empreinte": empreinte(racine), "commit": git("rev-parse", "--short", "HEAD", cwd=racine).stdout.strip()})
        dossier_runs = sortie / "runs" / f"{args.label}-{dt.datetime.now():%Y%m%d-%H%M%S}"
        for c in cas:
            n = args.repetitions or int(c.get("repetitions", 1))
            runs = []
            for k in range(1, n + 1):
                print(f"[{c['id']}] run {k}/{n} ({res['mode']})…", file=sys.stderr)
                runs.append(executer_run(c, k, args, racine, dossier_runs, registre))
            res["cas"].append(agreger(c, runs))
    if args.reference:
        res["reference"] = args.reference
        res["comparaison"] = comparer(res, json.loads(Path(args.reference).read_text(encoding="utf-8")))
    (sortie / f"{args.label}.json").write_text(json.dumps(res, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    md = rapport_markdown(res)
    (sortie / f"{args.label}.md").write_text(md + "\n", encoding="utf-8")
    print(md)
    print(f"\nRésultats : {sortie / (args.label + '.json')}", file=sys.stderr)
    if res.get("comparaison"):
        return 1 if any(e["ecart"] == "REGRESSION" for e in res["comparaison"]) else 0
    return 1 if any(c["verdict"] == "KO" for c in res["cas"]) else 0


if __name__ == "__main__":
    sys.exit(main())
