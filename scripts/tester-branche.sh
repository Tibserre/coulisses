#!/bin/zsh
# Try a branch in « Coulisses (dév) » itself: its service runs from one of the repository's
# worktrees, with that worktree's interface, still on Données-dev and port 8766 (the dev
# service refuses the real data). Without a worktree, back to the repository (main).
#
# 1. « Coulisses (dév) » is quit (it stops the service it started, and asks first while a
#    recording or a processing runs); a dev service it did not start is stopped too, never
#    while it records or processes. Refused: nothing has changed.
# 2. The worktree's interface is built (npm, offline).
# 3. The app opens on the worktree (COULISSES_PROJET, read by the dev launcher only); its
#    window title names the worktree.
#
# Usage: scripts/tester-branche.sh [worktree]
#   worktree: its folder, or its name under .claude/worktrees; none: the repository.

set -euo pipefail

fail() { print -u2 "ÉCHEC : $1"; exit 1; }

ROOT=${0:A:h:h}
COMMON=$(git -C $ROOT rev-parse --path-format=absolute --git-common-dir)
REPO=${COMMON:h}
APP="$HOME/Applications/Coulisses (dév).app"
PLIST="$APP/Contents/Info.plist"
URL=http://127.0.0.1:8766

[[ -d $APP ]] || fail "« Coulisses (dév) » n'est pas installée : scripts/installer-lanceur.sh --dev"
INSTALLED=$(plutil -extract CoulissesProjet raw $PLIST)
[[ ${INSTALLED:A} == ${REPO:A} ]] ||
  fail "« Coulisses (dév) » lance $INSTALLED, pas ce dépôt ($REPO)"
IDENTIFIER=$(plutil -extract CFBundleIdentifier raw $PLIST)

TARGET=$REPO
if [[ -n ${1:-} ]]; then
  if [[ -d $1 ]]; then TARGET=${1:A}; else TARGET=$REPO/.claude/worktrees/$1; fi
  [[ -d $TARGET ]] || fail "worktree introuvable : $1"
  [[ $TARGET == $REPO || ${TARGET:h} == $REPO/.claude/worktrees ]] ||
    fail "$TARGET n'est ni le dépôt ni l'un de ses worktrees (.claude/worktrees)"
fi
BRANCH=$(git -C $TARGET branch --show-current)
BRANCH=${BRANCH:-détachée}

print "1. « Coulisses (dév) » et son service s'arrêtent…"
running() { [[ $(osascript -e "application id \"$IDENTIFIER\" is running") == true ]]; }
if running; then
  osascript -e "tell application id \"$IDENTIFIER\" to quit" >/dev/null || true
  for _ in {1..60}; do running || break; sleep 0.5; done
  running &&
    fail "« Coulisses (dév) » est restée ouverte (un enregistrement ou un traitement ?) : rien n'a changé"
fi
# A dev service the app did not start (run from a worktree by hand) still answers: stopped,
# unless it records or processes.
if STATE=$(curl -sf -m 2 $URL/api/etat); then
  python3 -c '
import json, sys, unicodedata
from pathlib import Path
def same(p): return unicodedata.normalize("NFC", str(Path(p).resolve()))
served = json.loads(sys.argv[1])["data_dir"]
sys.exit(0 if same(served) == same(Path.home() / "Coulisses" / "Données-dev") else 1)' \
    "$STATE" || fail "ce qui répond sur le port 8766 ne sert pas Données-dev : rien n'a changé"
  ACTIVITY=$(curl -sf -m 2 $URL/api/activite) || fail "le service de dév ne dit pas ce qu'il fait"
  python3 -c '
import json, sys
a = json.loads(sys.argv[1])
sys.exit(1 if a.get("recording") or a.get("processing") or a.get("downloading") else 0)' \
    "$ACTIVITY" || fail "le service de dév enregistre, traite ou télécharge : rien n'a changé"
  PID=$(python3 -c 'import json, sys; print(json.loads(sys.argv[1])["pid"])' "$STATE")
  kill -INT $PID
  for _ in {1..60}; do curl -s -m 1 $URL/api/etat >/dev/null || break; sleep 0.5; done
  curl -s -m 1 $URL/api/etat >/dev/null && fail "le service de dév (pid $PID) ne s'arrête pas"
fi

print "2. L'interface de ${TARGET:t} (branche $BRANCH)…"
cd $TARGET/web
if [[ ! -d node_modules ]]; then
  npm ci --offline --no-audit --no-fund --ignore-scripts >/dev/null ||
    fail "dépendances de l'interface introuvables dans le cache de npm"
fi
npm run build >/dev/null || fail "l'interface ne se construit pas"

print "3. « Coulisses (dév) » s'ouvre sur ${TARGET:t} (branche $BRANCH), données de dév…"
if [[ $TARGET == $REPO ]]; then
  open "$APP"
else
  open -n --env COULISSES_PROJET=$TARGET "$APP"
fi
print "   Pour revenir sur main : scripts/tester-branche.sh"
