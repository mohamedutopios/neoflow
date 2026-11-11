#!/usr/bin/env python3
"""Fiche de mesure d'une tâche et comparaison avant / après (J10).

Entrées acceptées (une mesure par argument) :
  - un journal de trajectoire neoagent `X.jsonl`, ou un dossier de journaux (workers d'un orchestrateur) ;
  - une fiche déjà normalisée `X.fiche.json` (par exemple la baseline J1 mesurée sur OpenCode avec
    `solutions/annexe-opencode/mesure/analyse_session.py --format fiche`).
Fichiers associés, cherchés à côté de l'entrée : `X.reprises.yaml` (journal humain : début, fin,
reprises, défauts, couverture) et `X.controles.json` (sortie de controles_qualite.py).

Coût : calculé depuis les champs `usage` de l'API, par modèle, avec la formule de couts.py et un
fichier de tarifs (--tarifs). Aucun prix n'est codé dans le lab.

Exemples :
  uv run mesure/mesurer.py mesure/exemples/j01_baseline_opencode.fiche.json \
      mesure/exemples/j10_structure_stat_types.jsonl --label J1 --label J10 --tarifs mesure/exemples/tarifs_fictifs.yaml
  uv run mesure/mesurer.py mesure/exemples/extension_vibe.jsonl mesure/exemples/extension_structure.jsonl \
      --label vibe --label structure --tarifs mesure/tarifs.yaml --format json --sortie comparaison.json
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import json
import sys
from pathlib import Path

ICI = Path(__file__).resolve().parent
sys.path.insert(0, str(ICI.parent))
from couts import charger_tarifs, cout, formule_texte  # noqa: E402
from trajectoire import CLES_USAGE, JournalIllisible, lire_journal  # noqa: E402

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None


def _yaml(chemin: Path) -> dict:
    if not chemin.exists() or yaml is None:
        return {}
    return yaml.safe_load(chemin.read_text(encoding="utf-8")) or {}


def _associe(entree: Path, suffixe: str) -> Path:
    nom = entree.name
    for ext in (".fiche.json", ".jsonl", ".json"):
        if nom.endswith(ext):
            return entree.with_name(nom[: -len(ext)] + suffixe)
    return entree.with_name(nom + suffixe)


def _instant(v) -> dt.datetime | None:
    if isinstance(v, dt.datetime):
        return v
    return dt.datetime.fromisoformat(str(v)) if v else None


def fiche_depuis_journal(chemin: Path) -> dict:
    t = lire_journal(chemin)
    r = t.resume()
    return {
        "source": "neoagent", "fichier": str(chemin), "tache": "", "sessions": t.sessions,
        "statut_fin": t.statut_fin, "duree_session_min": round(t.duree_s / 60, 1) if t.duree_s is not None else None,
        "etapes": t.etape_max, "appels_llm": len(t.appels_llm), "usage": t.usage, "usage_par_modele": t.usage_par_modele(),
        "appels_outils": len(t.appels), "familles": r["familles"], "outils": r["outils"],
        "executions_tests": len(t.executions_tests()), "ecritures": len(t.ecritures()), "refus": len(t.refus()),
        "approbations": r["approbations"], "relances": 0, "fichiers_modifies": r["fichiers_modifies"],
        "erreurs": t.erreurs, "avertissements": list(t.avertissements),
    }


def mesurer(entree: Path, label: str, tarifs: dict) -> dict:
    if entree.name.endswith(".fiche.json"):
        fiche = json.loads(entree.read_text(encoding="utf-8"))
        fiche.setdefault("avertissements", [])
    else:
        fiche = fiche_depuis_journal(entree)
    fiche["label"] = label
    journal = _yaml(_associe(entree, ".reprises.yaml"))
    reprises, defauts = journal.get("reprises") or [], journal.get("defauts") or []
    debut, fin = _instant(journal.get("debut")), _instant(journal.get("fin"))
    if debut and fin:
        fiche["delai_bout_en_bout_min"], fiche["source_delai"] = round((fin - debut).total_seconds() / 60, 1), "journal humain"
    else:
        fiche["delai_bout_en_bout_min"] = fiche.get("delai_bout_en_bout_min") or fiche.get("duree_session_min")
        fiche["source_delai"] = fiche.get("source_delai") or "durée de session (approximation)"
        if not journal and "reprises" not in fiche:
            fiche["avertissements"].append("aucun journal de reprises : délai approximatif, reprises et défauts non mesurés")
    par_type: dict = {}
    for r in reprises:
        e = par_type.setdefault(str(r.get("type", "autre")), {"nombre": 0, "minutes": 0.0})
        e["nombre"] += 1
        e["minutes"] += float(r.get("duree_min") or 0)
    if reprises or "reprises" not in fiche:
        fiche["reprises"] = {"nombre": len(reprises), "minutes": round(sum(e["minutes"] for e in par_type.values()), 1),
                             "par_type": par_type}
    if defauts or "defauts" not in fiche:
        fiche["defauts"] = {"total": len(defauts),
                            "avant_pr": sum(1 for d in defauts if d.get("phase", "avant_pr") == "avant_pr"),
                            "apres_pr": sum(1 for d in defauts if d.get("phase") == "apres_pr"), "detail": defauts}
    fiche["tache"] = journal.get("tache") or fiche.get("tache", "")
    fiche["configuration"] = journal.get("configuration") or fiche.get("configuration", "")
    fiche["couverture"] = journal.get("couverture") or fiche.get("couverture")
    rapport_f = _associe(entree, ".rapport.json")      # sortie JSON de la CLI neoagent (verdicts du vérificateur)
    if rapport_f.exists():
        rapport = json.loads(rapport_f.read_text(encoding="utf-8"))
        verdicts = rapport.get("verdicts") or []
        fiche["verifications"] = len(verdicts)
        fiche["verifications_ko"] = sum(1 for v in verdicts if not v.get("ok"))
        fiche["statut_pattern"] = rapport.get("statut")
    controles = _associe(entree, ".controles.json")
    if controles.exists():
        c = json.loads(controles.read_text(encoding="utf-8"))
        fiche["controles"] = {x["nom"]: (x.get("valeur") if x["statut"] == "MESURE" else x["statut"]) for x in c.get("controles", [])}
    fiche["tokens_total"] = sum(int(fiche.get("usage", {}).get(k, 0)) for k in CLES_USAGE)
    total, detail, manquants = cout(fiche.get("usage_par_modele") or {}, tarifs) if tarifs else (None, {}, [])
    fiche["cout_formule"], fiche["cout_par_modele"] = total, detail
    if tarifs and manquants:
        fiche["avertissements"].append("coût non calculé, prix manquants : " + ", ".join(manquants[:4]))
    return fiche


LIGNES = [
    ("Délai bout en bout (min)", "delai_bout_en_bout_min"), ("Temps de reprise manuelle (min)", "reprises.minutes"),
    ("Reprises humaines", "reprises.nombre"), ("Relances de prompt", "relances"),
    ("Défauts avant PR", "defauts.avant_pr"), ("Défauts après PR", "defauts.apres_pr"),
    ("Durée de session (min)", "duree_session_min"), ("Étapes de l'agent", "etapes"), ("Appels LLM", "appels_llm"),
    ("Appels d'outils", "appels_outils"), ("Exécutions de tests", "executions_tests"),
    ("Vérifications (verdicts)", "verifications"), ("dont rouges", "verifications_ko"), ("Écritures", "ecritures"),
    ("Approbations humaines", "approbations.total"), ("Refus (politique)", "refus"),
    ("input_tokens", "usage.input_tokens"), ("output_tokens", "usage.output_tokens"),
    ("cache_read_input_tokens", "usage.cache_read_input_tokens"), ("cache_creation_input_tokens", "usage.cache_creation_input_tokens"),
    ("Tokens total", "tokens_total"), ("Coût (formule)", "cout_formule"),
]


def valeur(m: dict, chemin: str):
    for p in chemin.split("."):
        m = m.get(p) if isinstance(m, dict) else None
    return m


def fmt(v, cle="") -> str:
    if v is None:
        return "-"
    if isinstance(v, float):
        return f"{v:.4f}" if cle.startswith("cout") else f"{v:,.1f}".replace(",", " ")
    if isinstance(v, int):
        return f"{v:,}".replace(",", " ")
    return str(v)


def markdown(mesures: list[dict], tarifs: dict) -> str:
    out = []
    if len(mesures) > 1:
        out += ["## Comparaison", "", "| Indicateur | " + " | ".join(m["label"] for m in mesures) + " | Écart (dernier / premier) |",
                "|---" * (len(mesures) + 2) + "|"]
        for nom, cle in LIGNES:
            vals = [valeur(m, cle) for m in mesures]
            a, b = vals[0], vals[-1]
            ecart = f"{100 * (b - a) / a:+.0f} %" if isinstance(a, (int, float)) and isinstance(b, (int, float)) and a else "-"
            out.append(f"| {nom} | " + " | ".join(fmt(v, cle) for v in vals) + f" | {ecart} |")
        controles = sorted({k for m in mesures for k in (m.get("controles") or {})})
        for k in controles:
            out.append(f"| Contrôle : {k} | " + " | ".join(str((m.get("controles") or {}).get(k, "-")) for m in mesures) + " | |")
        out.append("")
    for m in mesures:
        out += [f"## {m['label']}", "", f"- Tâche : {m.get('tache') or '-'}",
                f"- Source : {m.get('source')} · configuration : {m.get('configuration') or '-'}",
                f"- Délai : {fmt(m.get('delai_bout_en_bout_min'))} min ({m.get('source_delai')})",
                f"- Reprises : {m['reprises']['nombre']} ({fmt(m['reprises']['minutes'])} min) — "
                + (", ".join(f"{k} {v['nombre']}×/{v['minutes']:.0f} min" for k, v in m["reprises"]["par_type"].items()) or "aucune"),
                f"- Défauts : {m['defauts']['total']} (avant PR {m['defauts']['avant_pr']}, après PR {m['defauts']['apres_pr']})",
                "- Tokens par modèle : " + (", ".join(f"{k} {sum(v.values()):,}".replace(",", " ")
                                                     for k, v in (m.get("usage_par_modele") or {}).items()) or "-"),
                f"- Coût par modèle : {m.get('cout_par_modele') or '-'}"]
        if m.get("couverture"):
            out.append(f"- Couverture (déclarée) : {m['couverture']}")
        out += [f"- **Attention** : {a}" for a in m.get("avertissements", [])]
        out.append("")
    if tarifs:
        out.append(f"> {formule_texte(tarifs)}")
    return "\n".join(out)


def en_csv(mesures: list[dict]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["label"] + [cle for _, cle in LIGNES])
    for m in mesures:
        w.writerow([m["label"]] + [valeur(m, cle) for _, cle in LIGNES])
    return buf.getvalue()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0], formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("entrees", nargs="+", help="journal .jsonl, dossier de journaux ou fiche .fiche.json")
    ap.add_argument("--label", action="append", default=[])
    ap.add_argument("--tarifs", help="YAML des prix par modèle (mesure/tarifs.example.yaml)")
    ap.add_argument("--format", choices=["md", "json", "csv"], default="md")
    ap.add_argument("--sortie", help="fichier de sortie (sinon stdout)")
    args = ap.parse_args(argv)
    tarifs = charger_tarifs(args.tarifs)
    mesures = []
    for i, e in enumerate(args.entrees):
        p = Path(e)
        label = args.label[i] if i < len(args.label) and args.label[i] else p.name.split(".")[0]
        try:
            mesures.append(mesurer(p, label, tarifs))
        except (JournalIllisible, OSError, json.JSONDecodeError) as exc:
            print(f"[erreur] {p} : {exc}", file=sys.stderr)
            return 1
    texte = {"md": lambda m: markdown(m, tarifs), "csv": en_csv,
             "json": lambda m: json.dumps(m if len(m) > 1 else m[0], indent=2, ensure_ascii=False, default=str)}[args.format](mesures)
    if args.sortie:
        Path(args.sortie).write_text(texte + "\n", encoding="utf-8")
    else:
        print(texte)
    return 0


if __name__ == "__main__":
    sys.exit(main())
