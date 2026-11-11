#!/usr/bin/env bash
# worktree-feature.sh — un worktree Git isolé par sous-tâche, avec ports dédiés et
# lancement facultatif de neoagent en arrière-plan (journal de trajectoire dans le worktree).
#
# Usage :
#   scripts/worktree-feature.sh create <nom> [--base <ref>] [--branche <b>]
#                                     [--port-back <n>] [--port-front <n>] [--installer]
#   scripts/worktree-feature.sh run <nom> [--lab <chemin de labs/agent>] -- <options de neoagent>
#       ex. run conges-back -- --ecriture --pattern generator_verifier --tache "Implémentez T04…"
#   scripts/worktree-feature.sh status
#   scripts/worktree-feature.sh remove <nom> [--force] [--supprimer-branche]
#
# Conventions :
#   worktree  ../<depot>-<nom>      (ex. ../neoflow-conges-back)
#   branche   feat/<nom>            (ex. feat/conges-back), créée depuis --base (défaut HEAD)
#   ports     backend 8081, 8082… / Vite 5174, 5175… : premier couple libre parmi les worktrees
#   fichiers  <worktree>/.worktree.env et <worktree>/.worktree-logs/ (exclus de Git)
#
# Le script ne pousse rien, ne fusionne rien et ne supprime une branche que sur demande.
# Compatible bash 3.2 (macOS), Linux et Git Bash.

set -euo pipefail

die() { echo "Erreur : $*" >&2; exit 1; }
info() { echo "› $*"; }
usage() { sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'; }

git rev-parse --git-dir >/dev/null 2>&1 || die "lancez ce script depuis un dépôt Git"
PRINCIPAL=$(git worktree list --porcelain | awk '/^worktree /{ sub(/^worktree /, ""); print; exit }')
DEPOT=$(basename "$PRINCIPAL")
PARENT=$(dirname "$PRINCIPAL")
COMMUN=$(cd "$(git rev-parse --git-common-dir)" && pwd)

chemin_de() { echo "$PARENT/$DEPOT-$1"; }

valider_nom() {
  case "$1" in
    ''|*[!a-z0-9-]*|-*) die "nom invalide « $1 » : minuscules, chiffres et tirets uniquement" ;;
  esac
}

exclure_de_git() {
  local excl="$COMMUN/info/exclude"
  mkdir -p "$COMMUN/info"
  touch "$excl"
  grep -qxF '.worktree.env' "$excl" || echo '.worktree.env' >> "$excl"
  grep -qxF '.worktree-logs/' "$excl" || echo '.worktree-logs/' >> "$excl"
}

ports_utilises() {
  # Affiche les ports déclarés dans les .worktree.env existants (un par ligne).
  git worktree list --porcelain | awk '/^worktree /{ sub(/^worktree /, ""); print }' |
  while IFS= read -r wt; do
    if [ -f "$wt/.worktree.env" ]; then
      grep -E '^(SERVER_PORT|VITE_PORT)=' "$wt/.worktree.env" | cut -d= -f2 || true
    fi
  done
  return 0
}

premier_libre() {
  # premier_libre <depart> : premier port >= depart absent des worktrees et non écouté localement.
  local p="$1" utilises
  utilises=$(ports_utilises)
  while printf '%s\n' "$utilises" | grep -qx "$p" || port_ecoute "$p"; do p=$((p + 1)); done
  echo "$p"
}

port_ecoute() {
  # Connexion TCP locale par /dev/tcp (bash, sans dépendance) : immédiate si personne n'écoute.
  # (lsof peut bloquer longtemps sur certains postes ; il n'est plus utilisé.)
  (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null
}

cmd_create() {
  local nom="${1:-}"; shift || true
  valider_nom "$nom"
  local base="HEAD" branche="feat/$nom" port_back="" port_front="" installer=0
  while [ $# -gt 0 ]; do
    case "$1" in
      --base) base="${2:?}"; shift 2 ;;
      --branche) branche="${2:?}"; shift 2 ;;
      --port-back) port_back="${2:?}"; shift 2 ;;
      --port-front) port_front="${2:?}"; shift 2 ;;
      --installer) installer=1; shift ;;
      *) die "option inconnue pour create : $1" ;;
    esac
  done
  local wt; wt=$(chemin_de "$nom")
  [ -e "$wt" ] && die "$wt existe déjà"
  git rev-parse --verify --quiet "$base^{commit}" >/dev/null || die "base introuvable : $base"

  if git show-ref --verify --quiet "refs/heads/$branche"; then
    info "branche existante $branche : extraction dans $wt"
    git worktree add "$wt" "$branche"
  else
    info "création de $branche depuis $base dans $wt"
    git worktree add -b "$branche" "$wt" "$base"
  fi

  [ -n "$port_back" ] || port_back=$(premier_libre 8081)
  [ -n "$port_front" ] || port_front=$(premier_libre 5174)
  local base_sql; base_sql="neoflow_$(echo "$nom" | tr '-' '_')"

  exclure_de_git
  mkdir -p "$wt/.worktree-logs"
  cat > "$wt/.worktree.env" <<EOF
# Généré par worktree-feature.sh le $(date '+%Y-%m-%d %H:%M') — exclu de Git, ne pas committer.
WORKTREE_NOM=$nom
WORKTREE_BRANCHE=$branche
# Backend : Spring Boot lit SERVER_PORT (équivalent de server.port).
SERVER_PORT=$port_back
# Frontend : npm run dev -- --port \$VITE_PORT --strictPort
VITE_PORT=$port_front
# Cible du proxy /api de Vite (lue par frontend/vite.config.ts) : l'API de CE worktree.
VITE_API_PROXY=http://localhost:$port_back
# Base PostgreSQL dédiée si vous n'utilisez pas le profil H2 (dev-h2 / test) :
# SPRING_DATASOURCE_URL=jdbc:postgresql://localhost:5432/$base_sql
EOF

  if [ $installer -eq 1 ] && [ -f "$wt/frontend/package-lock.json" ]; then
    info "npm ci dans $wt/frontend (node_modules propre au worktree)"
    (cd "$wt/frontend" && npm ci --no-audit --no-fund)
  fi

  echo
  echo "Worktree prêt : $wt"
  echo "  branche  : $branche (depuis $base)"
  echo "  backend  : SERVER_PORT=$port_back   frontend : VITE_PORT=$port_front"
  echo
  echo "Agent au terminal :  uv run --project labs/agent neoagent --repo $wt --ecriture --tache \"…\""
  echo "Agent détaché     :  $0 run $nom -- --ecriture --pattern generator_verifier --tache \"…\""
}

cmd_run() {
  local nom="${1:-}"; shift || true
  valider_nom "$nom"
  local wt; wt=$(chemin_de "$nom")
  [ -d "$wt" ] || die "worktree absent : $wt (lancez d'abord : $0 create $nom)"
  local lab="${NEOAGENT_LAB:-$PRINCIPAL/labs/agent}"
  while [ $# -gt 0 ]; do
    case "$1" in
      --lab) lab="${2:?}"; shift 2 ;;
      --) shift; break ;;
      *) die "option inconnue pour run : $1 (les options de neoagent se placent après --)" ;;
    esac
  done
  [ $# -gt 0 ] || die "options de neoagent manquantes : $0 run $nom -- --tache \"…\" [--ecriture] [--pattern …]"
  [ -f "$lab/pyproject.toml" ] || die "lab neoagent introuvable : $lab (option --lab ou variable NEOAGENT_LAB)"
  command -v uv >/dev/null 2>&1 || die "uv introuvable dans le PATH"
  lab=$(cd "$lab" && pwd)

  mkdir -p "$wt/.worktree-logs"
  local horodatage; horodatage=$(date '+%Y%m%d-%H%M%S')
  local log="$wt/.worktree-logs/run-$horodatage.log"
  local traj="$wt/.worktree-logs/traj-$horodatage.jsonl"
  # --approbation refus d'abord : hors terminal, rien n'est accordé, sauf si l'appelant le décide après --.
  (
    cd "$wt"
    if [ -f .worktree.env ]; then set -a; . ./.worktree.env; set +a; fi
    nohup uv run --project "$lab" neoagent --repo "$wt" --journal "$traj" --approbation refus "$@" \
      > "$log" 2>&1 < /dev/null &
    echo $! > "$wt/.worktree-logs/run-$horodatage.pid"
  )
  local pid; pid=$(cat "$wt/.worktree-logs/run-$horodatage.pid")
  echo "neoagent lancé en arrière-plan (PID $pid) dans $wt"
  echo "  rapport  : $log (JSON final de la CLI)"
  echo "  journal  : $traj"
  echo "  suivre   : tail -f \"$traj\""
  echo "Rappel : sans --approbation accord après --, toute écriture et toute commande sont refusées."
}

cmd_status() {
  printf '%-34s %-22s %-6s %-6s %-8s %s\n' "WORKTREE" "BRANCHE" "BACK" "FRONT" "MODIFS" "DERNIER RUN"
  git worktree list --porcelain | awk '
    /^worktree /{ sub(/^worktree /, ""); wt=$0 }
    /^branch /{ sub(/^branch refs\/heads\//, ""); br=$0 }
    /^detached/{ br="(détachée)" }
    /^$/{ if (wt != "") print wt "\t" br; wt=""; br="" }
    END{ if (wt != "") print wt "\t" br }' |
  while IFS=$'\t' read -r wt br; do
    local back="-" front="-" modifs etat="-"
    if [ -f "$wt/.worktree.env" ]; then
      back=$(grep -E '^SERVER_PORT=' "$wt/.worktree.env" | cut -d= -f2 || true)
      front=$(grep -E '^VITE_PORT=' "$wt/.worktree.env" | cut -d= -f2 || true)
    fi
    modifs=$(git -C "$wt" status --porcelain 2>/dev/null | grep -c . || true)
    local dernier_pid
    dernier_pid=$(ls -t "$wt"/.worktree-logs/*.pid 2>/dev/null | head -1 || true)
    if [ -n "$dernier_pid" ]; then
      local pid; pid=$(cat "$dernier_pid")
      if kill -0 "$pid" 2>/dev/null; then etat="en cours (PID $pid)"; else etat="terminé ($(basename "$dernier_pid" .pid))"; fi
    fi
    printf '%-34s %-22s %-6s %-6s %-8s %s\n' "$(basename "$wt")" "${br:--}" "$back" "$front" "$modifs" "$etat"
  done
}

cmd_remove() {
  local nom="${1:-}"; shift || true
  valider_nom "$nom"
  local force=0 suppr_branche=0
  while [ $# -gt 0 ]; do
    case "$1" in
      --force) force=1; shift ;;
      --supprimer-branche) suppr_branche=1; shift ;;
      *) die "option inconnue pour remove : $1" ;;
    esac
  done
  local wt; wt=$(chemin_de "$nom")
  [ -d "$wt" ] || die "worktree absent : $wt"
  local branche; branche=$(git -C "$wt" branch --show-current)

  local pidf
  for pidf in "$wt"/.worktree-logs/*.pid; do
    [ -f "$pidf" ] || continue
    if kill -0 "$(cat "$pidf")" 2>/dev/null; then
      [ $force -eq 1 ] || die "un neoagent tourne encore (PID $(cat "$pidf")) : attendez ou utilisez --force"
      info "arrêt du PID $(cat "$pidf")"; kill "$(cat "$pidf")" 2>/dev/null || true
    fi
  done

  if [ -n "$(git -C "$wt" status --porcelain)" ] && [ $force -eq 0 ]; then
    die "modifications non commitées dans $wt : commitez, ou relancez avec --force (perte des modifications)"
  fi
  # Journaux archivés dans le dépôt principal (traçabilité), puis fichiers du script retirés.
  if [ -d "$wt/.worktree-logs" ] && [ -n "$(ls -A "$wt/.worktree-logs" 2>/dev/null)" ]; then
    local archive; archive="$PRINCIPAL/.worktree-logs/$nom-$(date '+%Y%m%d-%H%M%S')"
    mkdir -p "$archive" && cp -R "$wt/.worktree-logs/." "$archive/" && info "journaux archivés dans $archive"
  fi
  rm -f "$wt/.worktree.env"; rm -rf "$wt/.worktree-logs"
  if [ $force -eq 1 ]; then git worktree remove --force "$wt"; else git worktree remove "$wt"; fi
  git worktree prune
  info "worktree supprimé : $wt"

  if [ $suppr_branche -eq 1 ] && [ -n "$branche" ]; then
    if [ $force -eq 1 ]; then git branch -D "$branche"; else git branch -d "$branche" || die "branche $branche non fusionnée : fusionnez-la ou utilisez --force"; fi
    info "branche supprimée : $branche"
  elif [ -n "$branche" ]; then
    info "branche conservée : $branche"
  fi
}

sous_commande="${1:-}"; shift || true
case "$sous_commande" in
  create) cmd_create "$@" ;;
  run) cmd_run "$@" ;;
  status) cmd_status ;;
  remove) cmd_remove "$@" ;;
  -h|--help|help|'') usage ;;
  *) usage >&2; exit 2 ;;
esac
