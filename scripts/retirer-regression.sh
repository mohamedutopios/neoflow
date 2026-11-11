#!/usr/bin/env bash
# Retire la régression du TP J07 : le code revient exactement à l'état du socle.
set -euo pipefail

RACINE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PATCH="$RACINE/labs/regressions/j07-regression.patch"
cd "$RACINE"

[ -f "$PATCH" ] || { echo "Patch introuvable : $PATCH" >&2; exit 1; }

export GIT_CEILING_DIRECTORIES="$(dirname "$RACINE")"

if command -v git >/dev/null 2>&1; then
  if ! git apply --reverse --check "$PATCH" >/dev/null 2>&1; then
    if git apply --check "$PATCH" >/dev/null 2>&1; then
      echo "La régression J07 n'est pas injectée : rien à retirer."
      exit 0
    fi
    echo "Les fichiers ciblés ont été modifiés depuis l'injection : retrait automatique impossible." >&2
    echo "Corrigez à la main ou restaurez-les (git checkout -- <fichier>)." >&2
    exit 1
  fi
  git apply --reverse "$PATCH"
elif command -v patch >/dev/null 2>&1; then
  if ! patch -p1 --dry-run --reverse --force --silent < "$PATCH" >/dev/null 2>&1; then
    echo "La régression J07 n'est pas injectée, ou les fichiers ont été modifiés depuis : rien n'est retiré." >&2
    exit 1
  fi
  patch -p1 --reverse --silent < "$PATCH"
else
  echo "Ni git ni patch ne sont disponibles." >&2
  exit 1
fi

echo "Régression J07 retirée. Redémarrez le backend."
