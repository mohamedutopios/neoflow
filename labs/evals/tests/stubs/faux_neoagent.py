"""Faux neoagent respectant la CLI et le journal du contrat neoagent (tests du banc, aucun appel API)."""
import argparse
import datetime as dt
import json
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--repo", required=True)
ap.add_argument("--tache", required=True)
ap.add_argument("--pattern", default="react")
ap.add_argument("--mode", default="structure")
ap.add_argument("--journal", required=True)
ap.add_argument("--offline", action="store_true")
ap.add_argument("--outils-externes", action="append", default=[])
ap.add_argument("--ecriture", action="store_true")
ap.add_argument("--approbation", choices=("interactif", "refus", "accord"), default="refus")
a = ap.parse_args()
t = dt.datetime(2026, 11, 4, 9, 0, tzinfo=dt.timezone.utc)


def ts(s):
    return (t + dt.timedelta(seconds=s)).isoformat()


cible = "backend/src/main/java/Exemple.java"
Path(a.repo, cible).parent.mkdir(parents=True, exist_ok=True)
ev = [
    {"ts": ts(1), "session": "faux-1", "etape": 1, "type": "llm", "usage": {"input_tokens": 1000, "output_tokens": 100, "cache_read_input_tokens": 0}, "modele": "claude-sonnet-5-5"},
    {"ts": ts(2), "session": "faux-1", "etape": 1, "type": "tool_call", "outil": "editer_fichier", "entree": {"chemin": cible, "nouveau": "x"}},
    {"ts": ts(3), "session": "faux-1", "etape": 1, "type": "approbation", "outil": "editer_fichier",
     "entree": {"accordee": a.approbation == "accord"}, "sortie_extrait": "accord automatique" if a.approbation == "accord" else "refus"},
    {"ts": ts(4), "session": "faux-1", "etape": 1, "type": "tool_result", "outil": "editer_fichier", "entree": {"is_error": not a.ecriture},
     "sortie_extrait": "OK" if a.ecriture else "REFUS GARDE-FOU : écriture non autorisée (--ecriture absent)"},
    {"ts": ts(5), "session": "faux-1", "etape": 2, "type": "llm", "usage": {"input_tokens": 200, "output_tokens": 50, "cache_read_input_tokens": 1100}, "modele": "claude-sonnet-5-5"},
    {"ts": ts(6), "session": "faux-1", "etape": 2, "type": "tool_call", "outil": "executer_commande", "entree": {"commande": "./mvnw -q verify", "repertoire": "backend"}},
    {"ts": ts(9), "session": "faux-1", "etape": 2, "type": "tool_result", "outil": "executer_commande", "entree": {"is_error": False}, "sortie_extrait": "code de sortie 0\nBUILD SUCCESS"},
    {"ts": ts(10), "session": "faux-1", "etape": 3, "type": "fin", "entree": {"statut": "termine"},
     "usage": {"input_tokens": 1200, "output_tokens": 150, "cache_read_input_tokens": 1100}, "modele": "claude-sonnet-5-5",
     "sortie_extrait": f"offline={a.offline} mode={a.mode} pattern={a.pattern} externes={','.join(a.outils_externes)} tache={a.tache[:30]}"},
]
if a.ecriture:
    Path(a.repo, cible).write_text("class Exemple {}\n")
Path(a.journal).write_text("\n".join(json.dumps(e, ensure_ascii=False) for e in ev) + "\n")
print(json.dumps({"pattern": a.pattern, "mode": a.mode, "offline": a.offline, "statut": "verifie", "tours": 1,
                  "verdicts": [{"ok": True, "commande": "./mvnw -q verify", "duree_s": 1.0}]}))
