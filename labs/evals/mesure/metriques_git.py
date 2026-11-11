#!/usr/bin/env python3
"""Métriques de développement d'une branche : Git, couverture et CI (J10).

Complète la mesure OpenCode (tokens, outils) par ce que voit l'équipe : taille et durée de la
branche, part de code de test, commits correctifs, commits assistés par IA (trailer), couverture
JaCoCo et Vitest, résultats CI exportés par `gh`.

Exemples :
  uv run mesure/metriques_git.py --base main --branche feat/stat-types
  uv run mesure/metriques_git.py --base main --branche feat/stat-types \
      --jacoco backend/target/site/jacoco-it/jacoco.xml \
      --vitest frontend/coverage/coverage-summary.json \
      --ci-json runs.json        # gh run list --branch feat/stat-types --json conclusion,createdAt,name,event > runs.json

Convention de traçabilité (toolbox) : un commit produit avec l'agent porte le trailer
`Assisted-by: OpenCode <modèle>` ; le script le compte, il ne le devine pas.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

MOTIF_TEST = re.compile(r"(^|/)(src/test/|e2e/|__tests__/)|\.(test|spec)\.(ts|tsx|js)$|Test\.java$|IT\.java$")
MOTIF_CORRECTIF = re.compile(r"^(fix|revert|fixup!|squash!|hotfix)\b|^corrige|\bcorrection\b", re.I)
MOTIF_ASSISTE = re.compile(r"^(assisted-by|co-authored-by):.*(opencode|claude|ia\b|ai\b)", re.I | re.M)


def git(repo: Path, *args: str) -> str:
    p = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    if p.returncode:
        raise RuntimeError(f"git {' '.join(args)} : {p.stderr.strip()}")
    return p.stdout


def metriques_branche(repo: Path, base: str, branche: str) -> dict:
    sep = "\x1f"
    log = git(repo, "log", f"{base}..{branche}", "--no-merges", f"--format=%H{sep}%aI{sep}%an{sep}%s{sep}%B\x1e")
    commits = []
    for bloc in log.split("\x1e"):
        bloc = bloc.strip("\n")
        if not bloc:
            continue
        h, date, auteur, sujet, corps = (bloc.split(sep) + [""] * 5)[:5]
        commits.append({"sha": h[:10], "date": date, "auteur": auteur, "sujet": sujet,
                        "correctif": bool(MOTIF_CORRECTIF.search(sujet)), "assiste": bool(MOTIF_ASSISTE.search(corps))})
    numstat = git(repo, "diff", "--numstat", f"{base}...{branche}")
    ajout = supp = ajout_tests = 0
    fichiers = []
    for ligne in numstat.splitlines():
        a, s, f = (ligne.split("\t") + ["", "", ""])[:3]
        if a == "-":  # fichier binaire
            fichiers.append(f)
            continue
        a, s = int(a), int(s)
        ajout, supp = ajout + a, supp + s
        if MOTIF_TEST.search(f):
            ajout_tests += a
        fichiers.append(f)
    dates = sorted(dt.datetime.fromisoformat(c["date"]) for c in commits)
    return {
        "base": base, "branche": branche, "commits": len(commits),
        "premier_commit": dates[0].isoformat() if dates else None,
        "dernier_commit": dates[-1].isoformat() if dates else None,
        "duree_branche_h": round((dates[-1] - dates[0]).total_seconds() / 3600, 2) if len(dates) > 1 else 0.0,
        "auteurs": sorted({c["auteur"] for c in commits}),
        "fichiers_modifies": len(fichiers), "lignes_ajoutees": ajout, "lignes_supprimees": supp,
        "part_lignes_tests": round(ajout_tests / ajout, 3) if ajout else None,
        "commits_correctifs": sum(c["correctif"] for c in commits),
        "commits_assistes_ia": sum(c["assiste"] for c in commits),
        "detail_commits": commits,
    }


def couverture_jacoco(chemin: Path) -> dict:
    racine = ET.parse(chemin).getroot()
    res = {}
    for c in racine.findall("counter"):  # compteurs au niveau du rapport (pas des packages)
        manque, couvert = int(c.get("missed", 0)), int(c.get("covered", 0))
        total = manque + couvert
        res[c.get("type", "?").lower()] = round(100 * couvert / total, 1) if total else None
    return res


def couverture_vitest(chemin: Path) -> dict:
    total = json.loads(chemin.read_text(encoding="utf-8")).get("total", {})
    return {k: v.get("pct") for k, v in total.items() if isinstance(v, dict)}


def resultats_ci(chemin: Path) -> dict:
    runs = json.loads(chemin.read_text(encoding="utf-8"))
    runs = sorted(runs, key=lambda r: r.get("createdAt", ""))
    conclusions = [r.get("conclusion") or r.get("status") for r in runs]
    return {
        "runs": len(runs), "succes": conclusions.count("success"), "echecs": conclusions.count("failure"),
        "taux_succes": round(conclusions.count("success") / len(runs), 3) if runs else None,
        "vert_du_premier_coup": bool(conclusions) and conclusions[0] == "success",
        "echecs_par_workflow": {n: sum(1 for r in runs if r.get("name") == n and r.get("conclusion") == "failure")
                                for n in sorted({r.get("name", "?") for r in runs})},
    }


def markdown(m: dict) -> str:
    g = m["git"]
    part = "-" if g["part_lignes_tests"] is None else f"{100 * g['part_lignes_tests']:.0f} %"
    l = [f"## Métriques Git/CI — `{g['branche']}` (base `{g['base']}`)", "",
         "| Indicateur | Valeur |", "|---|---|",
         f"| Commits (hors merges) | {g['commits']} dont {g['commits_correctifs']} correctif(s), "
         f"{g['commits_assistes_ia']} assisté(s) IA (trailer) |",
         f"| Durée de la branche (1er → dernier commit) | {g['duree_branche_h']} h |",
         f"| Fichiers modifiés | {g['fichiers_modifies']} |",
         f"| Lignes ajoutées / supprimées | +{g['lignes_ajoutees']} / -{g['lignes_supprimees']} |",
         f"| Part des lignes ajoutées dans les tests | {part} |"]
    if m.get("jacoco"):
        l.append(f"| Couverture JaCoCo (lignes / branches) | {m['jacoco'].get('line')} % / {m['jacoco'].get('branch')} % |")
    if m.get("vitest"):
        l.append(f"| Couverture Vitest (lignes / branches) | {m['vitest'].get('lines')} % / {m['vitest'].get('branches')} % |")
    if m.get("ci"):
        c = m["ci"]
        l.append(f"| CI : runs / succès / échecs | {c['runs']} / {c['succes']} / {c['echecs']} "
                 f"(vert du premier coup : {'oui' if c['vert_du_premier_coup'] else 'non'}) |")
    l += ["", "> Une couverture se commente : quelles lignes nouvelles sont couvertes, par quels tests, "
          "avec quelles assertions. Le pourcentage seul ne prouve rien."]
    return "\n".join(l)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0], formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", default=".")
    ap.add_argument("--base", default="main")
    ap.add_argument("--branche", default="HEAD")
    ap.add_argument("--jacoco", help="rapport jacoco.xml après ./mvnw verify (target/site/jacoco/ ou jacoco-it/)")
    ap.add_argument("--vitest", help="coverage-summary.json (vitest --coverage, reporter json-summary)")
    ap.add_argument("--ci-json", help="export `gh run list --json conclusion,createdAt,name,event`")
    ap.add_argument("--format", choices=["md", "json"], default="md")
    args = ap.parse_args(argv)
    try:
        m = {"git": metriques_branche(Path(args.repo), args.base, args.branche)}
    except RuntimeError as exc:
        print(exc, file=sys.stderr)
        return 2
    if args.jacoco:
        m["jacoco"] = couverture_jacoco(Path(args.jacoco))
    if args.vitest:
        m["vitest"] = couverture_vitest(Path(args.vitest))
    if args.ci_json:
        m["ci"] = resultats_ci(Path(args.ci_json))
    print(json.dumps(m, indent=2, ensure_ascii=False) if args.format == "json" else markdown(m))
    return 0


if __name__ == "__main__":
    sys.exit(main())
