#!/usr/bin/env bash
# Initialise le dépôt Git du socle NeoFlow (à lancer une seule fois par le formateur, sur une copie propre).
#   ./scripts/init-depot.sh [nom-organisation/nom-depot]
set -euo pipefail

RACINE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEPOT_DISTANT="${1:-neosoft-formation/neoflow}"
cd "$RACINE"

echo "== Vérifications préalables dans $RACINE"

if [ -d .git ]; then
  echo "Un dépôt Git existe déjà ici : rien n'est fait." >&2
  exit 1
fi

# La toolbox est construite par les stagiaires : elle ne doit pas être dans le socle.
for interdit in AGENTS.md opencode.json opencode.jsonc .opencode ia-toolbox; do
  if [ -e "$interdit" ]; then
    echo "Le socle ne doit pas contenir $interdit (construit par les stagiaires en J1-J2)." >&2
    exit 1
  fi
done

# Aucun artefact de build ni dépendance installée.
residus=$(find . \( -name node_modules -o -name target -o -name dist -o -name test-results \
  -o -name playwright-report -o -name .venv -o -name '*.mv.db' \) -prune -print 2>/dev/null | head -5)
if [ -n "$residus" ]; then
  echo "Artefacts à supprimer avant le premier commit :" >&2
  echo "$residus" >&2
  exit 1
fi

# La régression du J07 ne doit pas être injectée.
if GIT_CEILING_DIRECTORIES="$(dirname "$RACINE")" git apply --reverse --check labs/regressions/j07-regression.patch >/dev/null 2>&1; then
  echo "La régression J07 est injectée : lancez ./scripts/retirer-regression.sh d'abord." >&2
  exit 1
fi

if [ -e .env ]; then
  echo "Attention : .env existe (il est ignoré par Git et ne sera pas commité)."
fi

if ! git config user.email >/dev/null; then
  echo "Configurez votre identité Git (git config --global user.name / user.email) puis relancez." >&2
  exit 1
fi

echo "== Création du dépôt"
git init --quiet
git checkout --quiet -b main 2>/dev/null || git symbolic-ref HEAD refs/heads/main
git add -A
# Bits d'exécution conservés même si le système de fichiers ne les porte pas (Windows).
git update-index --chmod=+x backend/mvnw scripts/*.sh
git commit --quiet -m "chore: socle NeoFlow initial

Backend Spring Boot 3.5 / Java 21, frontend React 18 + TypeScript (Vite),
tests E2E Playwright, docker compose (PostgreSQL, Jaeger ; profil ia : Qdrant, Ollama),
laboratoires IA, tickets des dix variantes, régression injectable du J07."
git log --oneline -1

cat <<CONSEILS

== Dépôt initialisé sur la branche main.

Publication en dépôt modèle (template), par exemple avec la CLI GitHub :
  gh repo create $DEPOT_DISTANT --private --source . --remote origin --push
  gh repo edit $DEPOT_DISTANT --template          # coche « Template repository »

Chaque stagiaire crée ensuite SON dépôt à partir du modèle (historique propre, droits séparés) :
  gh repo create <stagiaire>/neoflow --template $DEPOT_DISTANT --private --clone

Avant d'ouvrir le dépôt aux stagiaires :
  - vérifier que la CI (.github/workflows/ci.yml) passe sur main ;
  - les éléments volontairement non conformes du socle sont décrits dans fil-rouge/NOTES_FORMATEUR.md :
    si la protection des secrets de GitHub signale la clé factice de application.yml, l'autoriser ;
  - ne pas publier fil-rouge/NOTES_FORMATEUR.md ni les solutions dans ce dépôt.
CONSEILS
