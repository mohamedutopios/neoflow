#!/usr/bin/env bash
# verifier-perimetre.sh — vérificateur déterministe du diff d'une branche de fonctionnalité.
#
# Contrôle ce qu'un agent ne doit pas faire, sans LLM :
#   C1  fichiers modifiés hors du périmètre déclaré (fichier .perimetre)      → ÉCHEC
#   C2  tests existant sur la base modifiés, supprimés ou renommés            → ÉCHEC
#   C3  tests désactivés ou focalisés dans les lignes ajoutées                → ÉCHEC
#   C4  fichiers protégés modifiés (legacy, spécification, ADR)               → ÉCHEC
#   C5  taille du diff de production au-delà du seuil                         → ALERTE (ÉCHEC avec --strict)
#   C6  fichiers de dépendances modifiés (pom.xml, package*.json)             → ALERTE
#
# Le diff examiné va de merge-base(base, HEAD) à l'arbre de travail : commits de la
# branche, modifications non commitées et fichiers non suivis.
#
# Usage :
#   scripts/verifier-perimetre.sh [--base main] [--perimetre .perimetre]
#                                 [--max-lignes 600] [--strict]
#                                 [--autoriser-test <chemin>]...
# Codes retour : 0 aucun échec, 1 au moins un échec, 2 erreur d'usage.
# Compatible bash 3.2 (macOS), Linux et Git Bash.

set -u

BASE="main"
PERIMETRE=""
MAX_LIGNES=600
STRICT=0
TESTS_AUTORISES=""

usage() { sed -n '2,22p' "$0" | sed 's/^# \{0,1\}//'; }

while [ $# -gt 0 ]; do
  case "$1" in
    --base) BASE="${2:?}"; shift 2 ;;
    --perimetre) PERIMETRE="${2:?}"; shift 2 ;;
    --max-lignes) MAX_LIGNES="${2:?}"; shift 2 ;;
    --strict) STRICT=1; shift ;;
    --autoriser-test) TESTS_AUTORISES="$TESTS_AUTORISES
${2:?}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Option inconnue : $1" >&2; usage >&2; exit 2 ;;
  esac
done

RACINE=$(git rev-parse --show-toplevel 2>/dev/null) || { echo "Pas dans un dépôt Git." >&2; exit 2; }
cd "$RACINE" || exit 2
git rev-parse --verify --quiet "$BASE^{commit}" >/dev/null || { echo "Référence de base introuvable : $BASE" >&2; exit 2; }
MB=$(git merge-base "$BASE" HEAD) || { echo "Pas d'ancêtre commun entre $BASE et HEAD." >&2; exit 2; }

if [ -z "$PERIMETRE" ] && [ -f .perimetre ]; then PERIMETRE=".perimetre"; fi

ECHECS=0
ALERTES=0
echec()  { ECHECS=$((ECHECS + 1)); echo "  [ÉCHEC]  $*"; }
alerte() { ALERTES=$((ALERTES + 1)); echo "  [ALERTE] $*"; }
ok()     { echo "  [OK]     $*"; }

est_test() {
  case "$1" in
    */src/test/*|src/test/*|e2e/*) return 0 ;;
    *.test.ts|*.test.tsx|*.test.js|*.test.jsx|*.spec.ts|*.spec.tsx|*.spec.js|*.spec.jsx) return 0 ;;
  esac
  return 1
}

test_autorise() {
  printf '%s\n' "$TESTS_AUTORISES" | grep -Fxq -- "$1"
}

# Liste « statut<TAB>chemin » : diff merge-base → arbre de travail, plus fichiers non suivis.
# Un renommage R est éclaté en D (ancien chemin) + A (nouveau chemin).
CHANGEMENTS=$(
  {
    git diff --name-status -M "$MB" | awk -F'\t' '
      $1 ~ /^R/ { print "D\t" $2; print "A\t" $3; next }
      $1 ~ /^C/ { print "A\t" $3; next }
      { print $1 "\t" $2 }'
    git ls-files --others --exclude-standard | awk '{ print "A\t" $0 }'
  } | grep -v -E $'\t''\.worktree(\.env|-logs/)' | sort -u
)

echo "Vérification du périmètre"
echo "  base : $BASE (merge-base $(git rev-parse --short "$MB")) · branche : $(git branch --show-current 2>/dev/null || echo '?')"
NB=$(printf '%s\n' "$CHANGEMENTS" | grep -c . || true)
echo "  fichiers touchés : $NB"
echo

# --- C1 : périmètre déclaré ------------------------------------------------------
echo "C1  Fichiers hors périmètre"
if [ -z "$PERIMETRE" ]; then
  alerte "aucun fichier de périmètre (.perimetre ou --perimetre) : contrôle C1 non effectué"
elif [ ! -f "$PERIMETRE" ]; then
  echo "Fichier de périmètre introuvable : $PERIMETRE" >&2; exit 2
else
  MOTIFS=$(grep -v -E '^[[:space:]]*(#|$)' "$PERIMETRE" | sed -e 's/[[:space:]]#.*$//' -e 's/[[:space:]]*$//')
  HORS=0
  while IFS=$'\t' read -r statut chemin; do
    [ -z "$chemin" ] && continue
    dedans=1
    while IFS= read -r motif; do
      [ -z "$motif" ] && continue
      # shellcheck disable=SC2053  # motif volontairement non quoté : correspondance glob, * couvre '/'
      if [[ "$chemin" == $motif ]]; then dedans=0; break; fi
    done <<EOF_MOTIFS
$MOTIFS
EOF_MOTIFS
    if [ $dedans -ne 0 ]; then echec "$statut $chemin"; HORS=$((HORS + 1)); fi
  done <<EOF_CHG
$CHANGEMENTS
EOF_CHG
  [ $HORS -eq 0 ] && ok "tous les fichiers sont dans $PERIMETRE"
fi
echo

# --- C2 : tests existants modifiés ou supprimés -----------------------------------
echo "C2  Tests existants modifiés ou supprimés"
C2=0
while IFS=$'\t' read -r statut chemin; do
  [ -z "$chemin" ] && continue
  case "$statut" in M*|D*|T*) ;; *) continue ;; esac
  est_test "$chemin" || continue
  git cat-file -e "$MB:$chemin" 2>/dev/null || continue
  if test_autorise "$chemin"; then
    alerte "$statut $chemin (autorisé explicitement : justifier dans le journal)"
  else
    echec "$statut $chemin existe sur $BASE : un agent ne modifie pas une preuve de référence"
    C2=$((C2 + 1))
  fi
done <<EOF_CHG
$CHANGEMENTS
EOF_CHG
[ $C2 -eq 0 ] && ok "aucun test de la base modifié ou supprimé"
echo

# --- C3 : tests désactivés ou focalisés ------------------------------------------
echo "C3  Tests désactivés ou focalisés"
MOTIF_DESACTIVATION='@Disabled|@Ignore|(^|[^A-Za-z0-9_])(it|test|describe)\.(skip|only|todo)\(|(^|[^A-Za-z0-9_])(xit|xdescribe|fit|fdescribe)\(|assumeTrue\(false\)'
C3=0
while IFS=$'\t' read -r statut chemin; do
  [ -z "$chemin" ] && continue
  case "$statut" in D*) continue ;; esac
  est_test "$chemin" || continue
  [ -f "$chemin" ] || continue
  if git cat-file -e "$MB:$chemin" 2>/dev/null; then
    AJOUTS=$(git diff -U0 "$MB" -- "$chemin" | grep -E '^\+' | grep -v -E '^\+\+\+' || true)
  else
    AJOUTS=$(sed 's/^/+/' "$chemin")
  fi
  TROUVES=$(printf '%s\n' "$AJOUTS" | grep -n -E "$MOTIF_DESACTIVATION" || true)
  if [ -n "$TROUVES" ]; then
    echec "$chemin : $(printf '%s' "$TROUVES" | head -3 | tr '\n' ' ' | cut -c1-160)"
    C3=$((C3 + 1))
  fi
done <<EOF_CHG
$CHANGEMENTS
EOF_CHG
[ $C3 -eq 0 ] && ok "aucun @Disabled, skip, only ajouté"
echo

# --- C4 : fichiers protégés -------------------------------------------------------
echo "C4  Fichiers protégés (legacy, spécification, ADR)"
C4=0
while IFS=$'\t' read -r statut chemin; do
  [ -z "$chemin" ] && continue
  case "$statut" in M*|D*|T*) ;; *) continue ;; esac
  case "$chemin" in
    */MATRICE_TRACABILITE.md|*/JOURNAL_TRACABILITE.md) continue ;;
    backend/src/main/java/com/neosoft/neoflow/legacy/*|frontend/src/legacy/*|docs/specs/*|docs/adr/*)
      echec "$statut $chemin"; C4=$((C4 + 1)) ;;
  esac
done <<EOF_CHG
$CHANGEMENTS
EOF_CHG
[ $C4 -eq 0 ] && ok "legacy, spécification et ADR intacts"
echo

# --- C5 : taille du diff de production --------------------------------------------
echo "C5  Taille du diff"
PROD=0; TESTS=0
while IFS=$'\t' read -r plus moins chemin; do
  [ -z "${chemin:-}" ] && continue
  [ "$plus" = "-" ] && continue
  n=$((plus + moins))
  if est_test "$chemin"; then TESTS=$((TESTS + n)); else PROD=$((PROD + n)); fi
done <<EOF_NUM
$(git diff --numstat "$MB")
EOF_NUM
while IFS= read -r f; do
  [ -z "$f" ] && continue
  [ -f "$f" ] || continue
  n=$(wc -l < "$f" | tr -d ' ')
  if est_test "$f"; then TESTS=$((TESTS + n)); else PROD=$((PROD + n)); fi
done <<EOF_NEW
$(git ls-files --others --exclude-standard)
EOF_NEW
echo "  lignes de production : $PROD · lignes de test : $TESTS · seuil production : $MAX_LIGNES"
if [ "$PROD" -gt "$MAX_LIGNES" ]; then
  if [ $STRICT -eq 1 ]; then echec "diff de production trop gros : découpez (une tâche = un commit)"
  else alerte "diff de production au-delà du seuil : revue par commit (--base HEAD~1) recommandée"; fi
else
  ok "taille relisable"
fi
echo

# --- C6 : dépendances --------------------------------------------------------------
echo "C6  Fichiers de dépendances"
C6=0
while IFS=$'\t' read -r statut chemin; do
  case "${chemin:-}" in
    */pom.xml|pom.xml|*/package.json|package.json|*/package-lock.json|package-lock.json)
      alerte "$statut $chemin : nouvelle dépendance ? ADR exigé (C-03)"; C6=$((C6 + 1)) ;;
  esac
done <<EOF_CHG
$CHANGEMENTS
EOF_CHG
[ $C6 -eq 0 ] && ok "aucun fichier de dépendances modifié"
echo

echo "Bilan : $ECHECS échec(s), $ALERTES alerte(s)"
[ $ECHECS -eq 0 ] || exit 1
exit 0
