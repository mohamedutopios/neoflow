#!/usr/bin/env bash
# Test de bout en bout des permissions et du plugin garde-fous, SANS clé API ni LLM :
# un faux modèle local (mock_llm.py) émet une suite fixe d'appels d'outils dangereux ;
# on vérifie que chacun est bloqué avec la bonne règle, et que les appels légitimes passent.
# Prérequis : OpenCode 2.x, Python 3.10+ (python3, python ou py), curl. Usage, depuis la racine du dépôt :
#   bash .opencode/tests/e2e/verifier-garde-fous.sh
set -uo pipefail
RACINE="$(git rev-parse --show-toplevel)"
ICI="$RACINE/.opencode/tests/e2e"
# Python 3.10+ : python3 (macOS, Linux), python ou py (Windows) ; UTF-8 forcé (scénarios accentués).
export PYTHONUTF8=1
PY="$(for c in python3 python py; do command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(sys.version_info < (3, 10))' >/dev/null 2>&1 && { echo "$c"; break; }; done)"
[[ -n "$PY" ]] || { echo "Python 3.10 ou plus introuvable (python3, python ou py)." >&2; exit 3; }
PORT="${PORT:-$("$PY" -c "import socket;s=socket.socket();s.bind(('127.0.0.1',0));print(s.getsockname()[1])")}"
# Contrôle de version AVANT tout lancement (toolbox écrite pour OpenCode 2.x, voir opencode-isole.sh).
bash "$ICI/opencode-isole.sh" --version > /dev/null || exit 3
TMP="$(mktemp -d)"
SCENARIO="${1:-$ICI/scenario-garde-fous.json}"

CREE_ENV=0
if [[ ! -f "$RACINE/.env" ]]; then  # cible factice pour les tentatives de lecture
  printf 'NEOFLOW_NOTIFICATION_API_KEY=FAUSSE-CLE-DE-TEST\n' > "$RACINE/.env"; CREE_ENV=1
fi

"$PY" "$ICI/mock_llm.py" "$SCENARIO" "$PORT" "$TMP/journal.jsonl" "$RACINE" &
MOCK=$!
nettoyer() {
  kill "$MOCK" 2>/dev/null; wait "$MOCK" 2>/dev/null
  if (( CREE_ENV )); then rm -f "$RACINE/.env"; fi
  rm -rf "$TMP"
}
trap nettoyer EXIT
for _ in $(seq 20); do curl -fs "http://127.0.0.1:$PORT/v1/models" >/dev/null && break; sleep 0.3; done

# Fournisseur factice injecté sans toucher opencode.json ; clé réelle retirée de l'environnement.
# L'agent testé (AGENT) peut fixer son propre modèle dans son frontmatter : on le force aussi sur le faux modèle.
AGENT_JSON=""; [[ -n "${AGENT:-}" ]] && AGENT_JSON=",\"agent\":{\"$AGENT\":{\"model\":\"mock/scripted\"}}"
export OPENCODE_CONFIG_CONTENT="{\"model\":\"mock/scripted\",\"small_model\":\"mock/scripted\"${AGENT_JSON},\"provider\":{\"mock\":{\"npm\":\"@ai-sdk/openai-compatible\",\"name\":\"Mock\",\"options\":{\"baseURL\":\"http://127.0.0.1:$PORT/v1\",\"apiKey\":\"factice\"},\"models\":{\"scripted\":{\"name\":\"Scripted\",\"tool_call\":true}}}}}"
# stdin fermé : sinon `opencode run` attend une entrée sur un stdin non interactif.
mkdir -p "$RACINE/.opencode/journal"
# AGENT=<nom> pour tester un agent précis (ex. AGENT=reviewer), sinon agent par défaut.
# opencode-isole.sh : serveur privé (--standalone), aucun identifiant accessible ; sans le faux modèle, échec.
(cd "$RACINE" && bash "$ICI/opencode-isole.sh" run ${AGENT:+--agent "$AGENT"} --print-logs --format json "Scénario de test des garde-fous" \
  < /dev/null > "$TMP/run.jsonl" 2> "$RACINE/.opencode/journal/e2e-opencode.log")

"$PY" - "$SCENARIO" "$TMP/run.jsonl" "$RACINE" <<'PY'
import json, re, sys
scenario = json.loads(open(sys.argv[1], encoding="utf-8").read().replace("{RACINE}", sys.argv[3]))
resultats = []
for ligne in open(sys.argv[2], encoding="utf-8", errors="replace"):
    try:
        e = json.loads(ligne)
    except ValueError:
        continue
    part = e.get("part") or {}
    if part.get("type") == "tool" and part.get("state", {}).get("status") in ("completed", "error"):
        etat = part["state"]
        resultats.append((part.get("tool"), str(etat.get("output") or etat.get("error") or "")))
ok = 0
for i, etape in enumerate(scenario):
    outil, sortie = resultats[i] if i < len(resultats) else ("absent", "")
    succes = re.search(etape["attendu"], sortie) is not None
    ok += succes
    print(f"{'OK ' if succes else 'KO '} {etape['tool']:8} attendu={etape['attendu']!r:42} obtenu={sortie[:90]!r}")
print(f"\n{ok}/{len(scenario)} vérifications conformes")
sys.exit(0 if ok == len(scenario) else 1)
PY
