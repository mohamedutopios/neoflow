#!/usr/bin/env bash
# Lance les tests des laboratoires de labs/. Un lab absent, ou sans test, est ignoré.
#
#   scripts/labs.sh test       tests de chaque lab présent (make labs-test)
#   scripts/labs.sh offline    mêmes tests sans clé API (ANTHROPIC_API_KEY retirée, NEOFLOW_OFFLINE=1),
#                              puis exécution de fumée de neoagent en --offline (make labs-offline)
#
#   LABS="rag mcp" scripts/labs.sh test     limite l'exécution à certains labs
#
# Lab Python : pyproject.toml + fichiers test_*.py  ->  uv run --all-extras --with pytest pytest -q
# Lab Java   : pom.xml                              ->  ./mvnw -B -q test (wrapper du lab, sinon backend/mvnw -f)
set -uo pipefail

RACINE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODE="${1:-test}"
LABS="${LABS:-spec agent rag mcp tests-ia legacy-ia workflow evals}"
MVNW_SOCLE="$RACINE/backend/mvnw"

case "$MODE" in
  test) ;;
  offline)
    # Garantit qu'aucun test ne consomme la clé : un appel réel échouera au lieu de facturer.
    unset ANTHROPIC_API_KEY
    export NEOFLOW_OFFLINE=1
    ;;
  *) echo "Usage : $0 test|offline" >&2; exit 2 ;;
esac

reussis=()
echecs=()
ignores=()

a_des_tests_python() {
  [ -n "$(find "$1" \( -name .venv -o -name node_modules -o -name target \) -prune -o \
    \( -name 'test_*.py' -o -name '*_test.py' \) -print -quit 2>/dev/null)" ]
}

lancer() {
  local nom="$1"; shift
  echo
  echo "== $nom : $*"
  if "$@"; then reussis+=("$nom"); else echecs+=("$nom"); fi
}

tests_python() {
  (cd "$1" && uv run --all-extras --with pytest pytest -q)
}

tests_java() {
  if [ -x "$1/mvnw" ]; then
    (cd "$1" && ./mvnw -B -q test)
  else
    "$MVNW_SOCLE" -B -q -f "$1/pom.xml" test
  fi
}

fumee_neoagent() {
  local journal
  journal="$(mktemp "${TMPDIR:-/tmp}/neoagent-offline.XXXXXX")"
  (cd "$RACINE/labs/agent" && uv run neoagent --repo "$RACINE" \
      --tache "Liste les fichiers du dossier docs/ sans rien modifier" \
      --offline --journal "$journal" </dev/null) && [ -s "$journal" ]
  local statut=$?
  rm -f "$journal"
  return $statut
}

for lab in $LABS; do
  dossier="$RACINE/labs/$lab"
  if [ ! -d "$dossier" ]; then
    ignores+=("$lab (absent)")
    continue
  fi
  trouve=0
  if [ -f "$dossier/pyproject.toml" ]; then
    trouve=1
    if ! command -v uv >/dev/null 2>&1; then
      echecs+=("$lab (uv introuvable)")
    elif a_des_tests_python "$dossier"; then
      lancer "$lab (Python)" tests_python "$dossier"
    else
      ignores+=("$lab (Python, aucun test)")
    fi
  fi
  if [ -f "$dossier/pom.xml" ]; then
    trouve=1
    lancer "$lab (Java)" tests_java "$dossier"
  fi
  [ "$trouve" -eq 1 ] || ignores+=("$lab (ni pyproject.toml ni pom.xml)")
done

if [ "$MODE" = offline ] && [ -d "$RACINE/labs/agent/neoagent" ] && command -v uv >/dev/null 2>&1; then
  case " $LABS " in
    *" agent "*) lancer "agent (neoagent --offline)" fumee_neoagent ;;
  esac
fi

echo
echo "== Bilan ($MODE)"
[ ${#reussis[@]} -eq 0 ] || printf '  réussi  : %s\n' "${reussis[@]}"
[ ${#ignores[@]} -eq 0 ] || printf '  ignoré  : %s\n' "${ignores[@]}"
[ ${#echecs[@]} -eq 0 ] || printf '  ÉCHEC   : %s\n' "${echecs[@]}"
[ ${#echecs[@]} -eq 0 ]
