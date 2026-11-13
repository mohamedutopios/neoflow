#!/usr/bin/env bash
# Affiche ce qu'un agent présente réellement au modèle, SANS LLM (faux modèle, OpenCode isolé) :
# outils offerts, skills (<available_skills> du prompt système) et subagents délégables.
# Remplace en OpenCode 2.x les commandes `opencode debug skill` et `opencode debug agent <nom>` de la 1.x.
# Usage, depuis la racine du dépôt : bash .opencode/tests/e2e/ce-que-voit-le-modele.sh [agent]
# Les règles de permission résolues, elles, se lisent avec :
#   bash .opencode/tests/e2e/opencode-isole.sh debug agents | python3 .opencode/tests/resume_agents.py <agent>
#   (sous Windows : python à la place de python3)
set -uo pipefail
RACINE="$(git rev-parse --show-toplevel)"
ICI="$RACINE/.opencode/tests/e2e"
# Python 3.10+ : python3 (macOS, Linux), python ou py (Windows) ; UTF-8 forcé (scénarios accentués).
export PYTHONUTF8=1
PY="$(for c in python3 python py; do command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(sys.version_info < (3, 10))' >/dev/null 2>&1 && { echo "$c"; break; }; done)"
[[ -n "$PY" ]] || { echo "Python 3.10 ou plus introuvable (python3, python ou py)." >&2; exit 3; }
AGENT="${1:-build}"
bash "$ICI/opencode-isole.sh" --version > /dev/null || exit 3
TMP="$(mktemp -d)"
PORT="${PORT:-$("$PY" -c "import socket;s=socket.socket();s.bind(('127.0.0.1',0));print(s.getsockname()[1])")}"
echo '[]' > "$TMP/scenario.json"
MOCK_CONTEXTE=1 "$PY" "$ICI/mock_llm.py" "$TMP/scenario.json" "$PORT" "$TMP/journal.jsonl" "$RACINE" &
MOCK=$!
trap 'kill "$MOCK" 2>/dev/null; wait "$MOCK" 2>/dev/null; rm -rf "$TMP"' EXIT
for _ in $(seq 20); do curl -fs "http://127.0.0.1:$PORT/v1/models" >/dev/null && break; sleep 0.3; done
export OPENCODE_CONFIG_CONTENT="{\"model\":\"mock/scripted\",\"small_model\":\"mock/scripted\",\"agent\":{\"$AGENT\":{\"model\":\"mock/scripted\"}},\"provider\":{\"mock\":{\"npm\":\"@ai-sdk/openai-compatible\",\"name\":\"Mock\",\"options\":{\"baseURL\":\"http://127.0.0.1:$PORT/v1\",\"apiKey\":\"factice\"},\"models\":{\"scripted\":{\"name\":\"Scripted\",\"tool_call\":true}}}}}"
(cd "$RACINE" && bash "$ICI/opencode-isole.sh" run --agent "$AGENT" "Liste" < /dev/null > "$TMP/run.txt" 2>&1)
grep -m1 -E 'Falling back|not a primary|unknown agent' "$TMP/run.txt" >&2

"$PY" - "$TMP/journal.jsonl" "$AGENT" <<'PY'
import json, re, sys
lignes = [json.loads(l) for l in open(sys.argv[1], encoding="utf-8") if l.strip()]
requete = next((l for l in lignes if l.get("outils")), None)
if requete is None:
    sys.exit("Aucune requête reçue par le faux modèle : voir la configuration (opencode-isole.sh debug config).")
print(f"# Agent {sys.argv[2]} : ce que reçoit le modèle")
print("Outils offerts :", ", ".join(sorted(requete["outils"])))
skills = re.findall(r"<skill>\s*<id>(.*?)</id>\s*<name>(.*?)</name>.*?<description>(.*?)</description>", requete["systeme"], re.S)
print("Skills proposées :" if skills else "Skills proposées : aucune")
for ident, nom, description in skills:
    alias = f" (name: {nom})" if nom != ident else ""
    print(f"  - {ident}{alias} : {description[:90]}")
bloc = requete["outils"].get("subagent", "")
subagents = re.findall(r"^- ([a-z0-9-]+):", bloc.split("Available subagents:")[-1], re.M) if bloc else []
print("Subagents délégables :", ", ".join(subagents) if subagents else "aucun (outil subagent absent)")
PY
