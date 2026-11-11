"""Faux `neospec` (J3) : même forme de CLI que `neospec chaine` ; écrit dans --racine, journal d'usage sans « type »."""
import argparse
import json
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("sous_commande", choices=["chaine"])
ap.add_argument("--type", required=True)
ap.add_argument("--reponses", required=True)
ap.add_argument("--racine", required=True)
ap.add_argument("--journal")
ap.add_argument("--max-corrections", type=int, default=2)
ap.add_argument("--offline", action="store_true")
a = ap.parse_args()
racine = Path(a.racine)
(racine / "docs/specs/conges/features").mkdir(parents=True, exist_ok=True)
(racine / "docs/specs/CONGES.md").write_text("# CONGES\nStatut : EN REVUE\n| EF-01 | solde |\n| EF-02 | chevauchement |\n")
(racine / "docs/specs/conges/features/conges_solde.feature").write_text("Fonctionnalité: solde\n")
if a.journal:
    lignes = [{"ts": "2026-11-04T10:00:00+00:00", "etape": e, "modele": "simule:claude-sonnet-5-5" if a.offline else "claude-sonnet-5-5",
               "offline": a.offline, "usage": {"input_tokens": 1000, "output_tokens": 200, "cache_read_input_tokens": 0,
                                               "cache_creation_input_tokens": 500}} for e in ("questions", "generation")]
    Path(a.journal).write_text("\n".join(json.dumps(l) for l in lignes) + "\n")
print("[1/5] 12 question(s)\n[5/5] squelettes de steps Cucumber-JVM\nSpécification écrite au statut EN REVUE")
