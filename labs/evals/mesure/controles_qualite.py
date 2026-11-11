#!/usr/bin/env python3
"""Contrôles automatiques sur le résultat d'un mode (vibe ou structure) : tests, E2E, scans (J10).

On ne juge pas une extension à la démo : on lui applique les mêmes contrôles que la CI du J2, sur
le worktree produit par chaque mode, et on compte ce que le mode a ajouté comme preuves (tests).

Exemples (depuis la racine du worktree à contrôler) :
  uv run --project labs/evals labs/evals/mesure/controles_qualite.py --base main --sortie vibe.controles.json
  uv run --project labs/evals labs/evals/mesure/controles_qualite.py --config labs/evals/mesure/controles.yaml -n

Sortie : JSON {"racine", "base", "date", "controles": [{nom, commande, code, statut, duree_s, extrait}]}
statut : OK (code 0), KO, ABSENT (outil ou fichier absent), MESURE (valeur numérique), IGNORE.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

CONTROLES_DEFAUT = [
    {"nom": "backend verify", "commande": "cd backend && ./mvnw -q verify", "requiert": "backend/mvnw"},
    {"nom": "frontend test", "commande": "npm test --prefix frontend -- --run", "requiert": "frontend/package.json"},
    {"nom": "e2e", "commande": "npx playwright test {e2e}", "requiert_motif": "e2e/tests/{e2e_glob}",
     "note": "application démarrée (make up ou make backend-h2 + make frontend)"},
    {"nom": "semgrep", "commande": "semgrep scan --config p/java --config p/react --error --quiet backend/src frontend/src",
     "outil": "semgrep"},
    {"nom": "gitleaks", "commande": "gitleaks dir . --no-banner --redact", "outil": "gitleaks"},
    {"nom": "tests ajoutés", "type": "mesure",
     "commande": "git diff --name-only --diff-filter=A {base}...HEAD | grep -cE '(Test|IT)\\.java$|\\.test\\.tsx?$|\\.spec\\.ts$' || true"},
    {"nom": "fichiers modifiés", "type": "mesure", "commande": "git diff --name-only {base}...HEAD | wc -l"},
]


def executer(c: dict, racine: Path, valeurs: dict, timeout: int, simulation: bool) -> dict:
    cmd = c["commande"].format(**valeurs)
    res = {"nom": c["nom"], "commande": cmd}
    if c.get("outil") and shutil.which(c["outil"]) is None:
        return res | {"code": None, "statut": "ABSENT", "extrait": f"{c['outil']} non installé"}
    if c.get("requiert") and not (racine / c["requiert"]).exists():
        return res | {"code": None, "statut": "ABSENT", "extrait": f"{c['requiert']} absent"}
    if c.get("requiert_motif"):
        motif = c["requiert_motif"].format(**valeurs)
        if not list(racine.glob(motif)):
            return res | {"code": None, "statut": "ABSENT", "extrait": f"aucun fichier {motif}"}
    if simulation:
        return res | {"code": None, "statut": "IGNORE", "extrait": "simulation (-n)"}
    t0 = time.monotonic()
    try:
        p = subprocess.run(cmd, shell=True, cwd=racine, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return res | {"code": -1, "statut": "KO", "duree_s": timeout, "extrait": f"timeout {timeout}s"}
    sortie = (p.stdout + p.stderr).strip()
    res |= {"code": p.returncode, "duree_s": round(time.monotonic() - t0, 1), "extrait": sortie[-300:]}
    if c.get("type") == "mesure":
        try:
            res |= {"statut": "MESURE", "valeur": int(sortie.splitlines()[-1].strip())}
        except (ValueError, IndexError):
            res |= {"statut": "KO"}
    else:
        res["statut"] = "OK" if p.returncode == 0 else "KO"
    return res


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0], formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--racine", default=".", help="worktree à contrôler")
    ap.add_argument("--base", default="main", help="référence Git pour compter les ajouts")
    ap.add_argument("--e2e", default="", help="spec Playwright à lancer (ex. e2e/tests/calendrier-equipe.spec.ts)")
    ap.add_argument("--config", help="YAML : liste de contrôles {nom, commande, type, outil, requiert}")
    ap.add_argument("--timeout", type=int, default=900)
    ap.add_argument("-n", "--dry-run", action="store_true", help="affiche les contrôles sans les exécuter")
    ap.add_argument("--sortie", help="fichier JSON (ex. X.controles.json à côté du journal X.jsonl)")
    args = ap.parse_args(argv)
    racine = Path(args.racine).resolve()
    controles = CONTROLES_DEFAUT
    if args.config:
        import yaml
        controles = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))["controles"]
    e2e_glob = Path(args.e2e).name if args.e2e else "*.spec.ts"
    valeurs = {"base": args.base, "e2e": args.e2e, "e2e_glob": e2e_glob}
    res = {"racine": str(racine), "base": args.base, "date": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
           "controles": [executer(c, racine, valeurs, args.timeout, args.dry_run) for c in controles]}
    texte = json.dumps(res, indent=2, ensure_ascii=False)
    if args.sortie:
        Path(args.sortie).write_text(texte + "\n", encoding="utf-8")
    for c in res["controles"]:
        print(f"{c['statut']:7} {c['nom']:20} {c.get('valeur', '')}", file=sys.stderr)
    if not args.sortie:
        print(texte)
    return 1 if any(c["statut"] == "KO" for c in res["controles"]) else 0


if __name__ == "__main__":
    sys.exit(main())
