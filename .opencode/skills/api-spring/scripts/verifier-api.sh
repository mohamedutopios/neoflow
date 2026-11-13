#!/usr/bin/env bash
# Vérification déterministe d'un endpoint NeoFlow (skill api-spring).
# Usage : bash .opencode/skills/api-spring/scripts/verifier-api.sh [ClasseTest[,AutreTest]]
# Sortie 0 si compilation, tests ciblés et règles Semgrep NeoFlow (fichiers modifiés) sont verts ; 1 sinon.
# La sortie est volontairement courte : elle est lue par l'agent.
set -uo pipefail

TESTS="${1:-}"
if [[ -n "$TESTS" && ! "$TESTS" =~ ^[A-Za-z0-9_,#*]+$ ]]; then
  echo "Argument refusé : noms de classes de test uniquement (lettres, chiffres, _ , # *)."
  exit 2
fi

RACINE="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
BACKEND="$RACINE/backend"
[[ -x "$BACKEND/mvnw" ]] || { echo "backend/mvnw introuvable depuis $RACINE"; exit 2; }
JOURNAL="$(mktemp -t verifier-api.XXXXXX)"
echecs=()

etape() { # etape <libellé> <commande...>
  local libelle="$1"; shift
  if "$@" >"$JOURNAL" 2>&1; then
    echo "[OK]    $libelle"
  else
    echo "[ÉCHEC] $libelle"
    grep -E "Tests run:.*Fail|FAILURE!|expected|COMPILATION ERROR|\.java:\[|error:|:(error|warning)\(" "$JOURNAL" \
      | grep -vE "Help 1|Re-run|full stack|See .*reports" | head -n 15
    echecs+=("$libelle")
  fi
}

cd "$BACKEND" || exit 2
etape "Compilation" ./mvnw -q -B -DskipTests compile
# Dans NeoFlow, les *Test passent par ./mvnw test (surefire), les *IT seulement par ./mvnw verify (failsafe).
UNITAIRES=""; INTEGRATION=""
# Garde sur TESTS vide : avec set -u, bash 3.2 (macOS) refuse "${NOMS[@]}" sur un tableau vide.
if [[ -n "$TESTS" ]]; then
  IFS=',' read -r -a NOMS <<< "$TESTS"
  for nom in "${NOMS[@]}"; do
    if [[ "$nom" == *IT ]]; then INTEGRATION+="${INTEGRATION:+,}$nom"; else UNITAIRES+="${UNITAIRES:+,}$nom"; fi
  done
fi
if [[ -z "$TESTS" ]]; then
  etape "Tests unitaires et d'intégration (tous)" ./mvnw -q -B verify
else
  [[ -n "$UNITAIRES" ]] && etape "Tests unitaires ($UNITAIRES)" \
    ./mvnw -q -B test -Dtest="$UNITAIRES" -Dsurefire.failIfNoSpecifiedTests=false
  [[ -n "$INTEGRATION" ]] && etape "Tests d'intégration ($INTEGRATION)" \
    ./mvnw -q -B verify -Dtest=none -Dsurefire.failIfNoSpecifiedTests=false -Dit.test="$INTEGRATION" -Dfailsafe.failIfNoSpecifiedTests=false
fi

cd "$RACINE" || exit 2
# Semgrep sur les seuls fichiers de backend/src/main modifiés par la branche (commités ou non, nouveaux
# compris) : l'agent n'est pas renvoyé vers des défauts préexistants hors de son périmètre (scan complet : CI).
BASE="$(git merge-base main HEAD 2>/dev/null || echo HEAD)"
MODIFIES=()
while IFS= read -r f; do [[ -f "$f" ]] && MODIFIES+=("$f"); done < <(
  { git diff --name-only "$BASE" -- backend/src/main; git ls-files --others --exclude-standard -- backend/src/main; } | sort -u)
if ! command -v semgrep >/dev/null 2>&1 || [[ ! -f .semgrep/neoflow.yml ]]; then
  echo "[--]    Semgrep absent ou règles manquantes : étape jouée en CI"
elif (( ${#MODIFIES[@]} == 0 )); then
  echo "[--]    Semgrep : aucun fichier modifié dans backend/src/main"
else
  # --emacs : une ligne par constat (fichier:ligne:colonne:sévérité(règle):message), lisible par l'agent.
  etape "Semgrep règles NeoFlow (${#MODIFIES[@]} fichier(s) modifié(s))" semgrep scan --config .semgrep/neoflow.yml \
    --metrics=off --quiet --error --emacs "${MODIFIES[@]}"
fi

rm -f "$JOURNAL"
if (( ${#echecs[@]} == 0 )); then
  echo "RÉSULTAT : OK"
  exit 0
fi
echo "RÉSULTAT : ÉCHEC (${echecs[*]})"
exit 1
