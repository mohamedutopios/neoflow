#!/usr/bin/env bash
# Lance OpenCode 2.x SANS accès à aucun identifiant : ni variables *_API_KEY, ni auth.json, ni configuration
# globale (dossiers XDG temporaires), et toujours avec un serveur privé (--standalone).
# Pourquoi : sans --standalone, `opencode run` passe par le service d'arrière-plan, démarré avec VOTRE
# environnement et vos identifiants ; l'injection du faux modèle (OPENCODE_CONFIG_CONTENT) ne l'atteint
# pas et la session part vers le vrai modèle. Ici, si le faux modèle n'est pas pris en compte, l'appel
# échoue (« Model not found ») au lieu de partir.
# Usage : bash .opencode/tests/e2e/opencode-isole.sh run --format json "…" < /dev/null
#         bash .opencode/tests/e2e/opencode-isole.sh debug agents
# Variables : OPENCODE_BIN (défaut « opencode ») ; CLE_FACTICE (valeur FACTICE exposée comme
#             ANTHROPIC_API_KEY, pour la démonstration du hook shell).
set -uo pipefail
OC="${OPENCODE_BIN:-opencode}"
VERSION="$($OC --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)"
if [[ -z "$VERSION" ]]; then echo "OpenCode introuvable ($OC)." >&2; exit 3; fi
if (( ${VERSION%%.*} < 2 )); then
  cat >&2 <<MSG
OpenCode $VERSION détecté : la toolbox J02 est écrite pour OpenCode 2.x (plugins au format
« export default { id, setup } », outils shell / subagent / execute). Installer la 2.x, par exemple :
  brew install anomalyco/tap/opencode-v2
MSG
  exit 3
fi
[[ "${1:-}" == "--version" ]] && { echo "$VERSION"; exit 0; }
ISOLE="$(mktemp -d)"
trap 'rm -rf "$ISOLE"' EXIT
CLES=(-u ANTHROPIC_API_KEY -u OPENAI_API_KEY -u GEMINI_API_KEY -u GOOGLE_GENERATIVE_AI_API_KEY -u OPENROUTER_API_KEY -u OPENCODE_API_KEY)
EXTRA=(); [[ -n "${CLE_FACTICE:-}" ]] && EXTRA=(ANTHROPIC_API_KEY="$CLE_FACTICE")
# Garde-fou : OpenCode doit réellement utiliser les dossiers temporaires (variables XDG). Sinon il lirait
# auth.json et la configuration globale : on refuse de lancer (cas d'un OpenCode qui ignorerait XDG, à
# vérifier notamment sous Windows). `opencode debug paths` affiche les dossiers effectivement utilisés.
MARQUE="$(basename "$ISOLE")"
CHEMINS="$(env "${CLES[@]}" XDG_DATA_HOME="$ISOLE/data" XDG_CONFIG_HOME="$ISOLE/config" XDG_STATE_HOME="$ISOLE/state" \
  $OC debug paths 2>/dev/null | tr '\\' '/')"
for cle in data config; do
  if ! grep -E "^${cle}[[:space:]]" <<< "$CHEMINS" | grep -q "$MARQUE"; then
    echo "Isolement impossible : OpenCode n'utilise pas le dossier temporaire pour « $cle » sur ce poste." >&2
    echo "Lancement refusé (il pourrait lire vos identifiants). Chemins vus : $(grep -E "^${cle}[[:space:]]" <<< "$CHEMINS")" >&2
    exit 4
  fi
done
SOUS_COMMANDE="${1:-}"; shift || true
case "$SOUS_COMMANDE" in
  debug) if [[ "${1:-}" == "paths" ]]; then ARGS=(debug paths); else ARGS=(debug "${1:-}" --standalone "${@:2}"); fi ;;
  *)     ARGS=("$SOUS_COMMANDE" --standalone "$@") ;;
esac
env "${CLES[@]}" XDG_DATA_HOME="$ISOLE/data" XDG_CONFIG_HOME="$ISOLE/config" XDG_STATE_HOME="$ISOLE/state" \
  OPENCODE_DISABLE_EXTERNAL_SKILLS=1 ${EXTRA[@]+"${EXTRA[@]}"} $OC "${ARGS[@]}"
