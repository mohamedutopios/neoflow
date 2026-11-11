"""Faux lanceur `tests-ia generer` (J7) : écrit rapport et tests acceptés dans --sortie, journal au format du contrat."""
import argparse
import json
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("sous_commande", choices=["generer"])
for opt in ("--projet", "--classe", "--spec", "--sortie", "--journal", "--tours"):
    ap.add_argument(opt)
ap.add_argument("--sans-mutation", action="store_true")
ap.add_argument("--offline", action="store_true")
a = ap.parse_args()
sortie = Path(a.sortie)
(sortie / "acceptes/com/neosoft").mkdir(parents=True, exist_ok=True)
(sortie / "acceptes/com/neosoft/XIaTest.java").write_text("class XIaTest {}\n")
(sortie / "rapport-generation.md").write_text(f"# Génération — {a.classe}\n| 1 | XIaTest | ACCEPTE | CV-01 | 1 test(s) vert(s) |\n")
ev = [{"ts": "2026-11-04T10:00:00Z", "session": "t", "etape": 1, "type": "llm", "modele": "simule:claude-sonnet-5-5",
       "usage": {"input_tokens": 2225, "output_tokens": 0, "cache_read_input_tokens": 0}},
      {"ts": "2026-11-04T10:00:01Z", "session": "t", "etape": 1, "type": "tool_call", "outil": "commande", "entree": "./mvnw -q test-compile"},
      {"ts": "2026-11-04T10:00:09Z", "session": "t", "etape": 2, "type": "tool_result", "outil": "commande", "sortie_extrait": "code=0"}]
Path(a.journal).write_text("\n".join(json.dumps(e) for e in ev) + "\n")
print("rapport écrit")
