#!/usr/bin/env bash
# Injecte la régression du TP J07 (labs/regressions/j07-regression.patch).
# Fonctionne dans un dépôt Git comme dans une simple copie (git apply, ou patch -p1 en repli).
set -euo pipefail

RACINE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PATCH="$RACINE/labs/regressions/j07-regression.patch"
cd "$RACINE"

[ -f "$PATCH" ] || { echo "Patch introuvable : $PATCH" >&2; exit 1; }

# Empêche git de remonter dans un éventuel dépôt parent : les chemins du patch sont relatifs à neoflow/.
export GIT_CEILING_DIRECTORIES="$(dirname "$RACINE")"

if command -v git >/dev/null 2>&1; then
  if git apply --reverse --check "$PATCH" >/dev/null 2>&1; then
    echo "La régression J07 est déjà injectée."
    exit 0
  fi
  git apply --check "$PATCH"
  git apply "$PATCH"
elif command -v patch >/dev/null 2>&1; then
  if patch -p1 --dry-run --reverse --force --silent < "$PATCH" >/dev/null 2>&1; then
    echo "La régression J07 est déjà injectée."
    exit 0
  fi
  patch -p1 --forward --silent < "$PATCH"
else
  echo "Ni git ni patch ne sont disponibles." >&2
  exit 1
fi

echo "Régression J07 injectée."
echo "Redémarrez le backend : make backend (ou make backend-h2), ou docker compose up -d --build backend."
