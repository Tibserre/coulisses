#!/bin/zsh
# The test of the built app (ADR 0040, 0041; plan step 11c). Coulisses.app's own service is
# started as its launcher starts it: its Python, its tools, nothing of Homebrew on the PATH,
# the network cut (a macOS sandbox lets it reach 127.0.0.1 only), a throwaway data folder.
# It checks that:
#   - the signature is valid, before and after;
#   - the .app's tools need nothing of this Mac, and ffmpeg is LGPL, without network, and
#     reads every format of ADR 0041;
#   - a recording imported in the app is processed to the end by the engine (real models,
#     read from ~/Coulisses/Modèles);
#   - nothing was written into the .app.
# Voices made by `say`; the sample files are made by Homebrew's ffmpeg (test tooling only).
# Nothing is written in ~/Coulisses/Données.
#
# Usage: scripts/essai-paquet.sh [--publication] [chemin/Coulisses.app]
# --publication: an app signed ad hoc fails (scripts/publier.py, ADR 0040).

set -euo pipefail

ROOT=${0:A:h:h}
PUBLICATION=""
if [[ ${1:-} == --publication ]]; then PUBLICATION=1; shift; fi
APP=${1:-$ROOT/dist/Coulisses.app}
APP=${APP:A}
RES=$APP/Contents/Resources
WORK=$(mktemp -d -t coulisses-paquet)
PORT=8798
URL=http://127.0.0.1:$PORT
SERVICE=""

finish() {
  # The app launched at step 5 first: it must not write after its preferences are back.
  if [[ -n $LAUNCHER ]] && kill -0 $LAUNCHER 2>/dev/null; then
    kill -TERM $LAUNCHER 2>/dev/null || true
    wait_end $LAUNCHER 30 || print -u2 "ATTENTION : l'app d'essai ($LAUNCHER) tourne encore."
  fi
  restore_preferences
  if [[ -n $SERVICE ]]; then
    kill -INT $SERVICE 2>/dev/null || true
    wait $SERVICE 2>/dev/null || true
  fi
  print "Journal du service : $WORK/service.log"
}
trap finish EXIT

fail() { print -u2 "ÉCHEC : $*"; exit 1 }
# Step 5 sets aside the published app's preferences (same identifier as an installed
# Coulisses) and puts them back, even when the test fails.
SAVED_PREFERENCES=""
LAUNCHER=""
# Waits for a process to end, at most `seconds`; false if it does not.
wait_end() {
  local pid=$1 seconds=$2
  for _ in $(seq 1 $((seconds * 2))); do
    kill -0 $pid 2>/dev/null || return 0
    sleep 0.5
  done
  return 1
}
# `defaults import` adds to a domain without removing what was written meanwhile: the
# domain is deleted first, then given back what it held, and compared.
restore_preferences() {
  [[ -n $SAVED_PREFERENCES ]] || return 0
  defaults delete $BUNDLE_ID 2>/dev/null || true
  defaults import $BUNDLE_ID $SAVED_PREFERENCES
  defaults export $BUNDLE_ID $WORK/preferences-apres.plist
  SAVED_PREFERENCES=""
  plutil -convert xml1 -o $WORK/avant.xml $WORK/preferences.plist
  plutil -convert xml1 -o $WORK/apres.xml $WORK/preferences-apres.plist
  diff -q $WORK/avant.xml $WORK/apres.xml >/dev/null ||
    { print -u2 "ÉCHEC : les préférences de $BUNDLE_ID n'ont pas pu être remises telles quelles (sauvegarde : $WORK/preferences.plist)"; exit 1 }
}
snapshot() { find $APP -print0 | xargs -0 stat -f '%m %z %p %N' | sort }

[[ -x $RES/python/bin/python3 ]] || fail "$APP n'est pas une Coulisses.app construite"
VERSION=$(plutil -extract CFBundleShortVersionString raw $APP/Contents/Info.plist)
print "Essai de $APP ($VERSION)"

print "1. Signature et contenu…"
codesign --verify --deep --strict $APP || fail "signature invalide"
# Signed by the certificate of construction.toml, the .app and what it runs (ADR 0040).
EXPECTED=$($RES/python/bin/python3 -I -B -c 'import sys, tomllib; print(tomllib.load(open(sys.argv[1], "rb"))["signature"]["identity"])' $ROOT/scripts/construction.toml)
# Read whole before parsing: an early exit would close the pipe (SIGPIPE, then pipefail).
signer() {
  local shown=$(codesign -dvv $1 2>&1)
  print -r -- $shown | awk -F= '/^Authority=/{print $2; exit} /^Signature=adhoc/{print "ad hoc"; exit}'
}
SIGNER=$(signer $APP)
if [[ $SIGNER == "ad hoc" ]]; then
  [[ -z $PUBLICATION ]] || fail "signature ad hoc : une telle app ne se publie pas"
  print "   signature ad hoc : essai seulement, jamais publiée"
else
  [[ $SIGNER == $EXPECTED ]] || fail "signée par « $SIGNER », pas par « $EXPECTED »"
fi
LIBRARIES=(${(f)"$(find $RES/python -name '*.so')"})
(( ${#LIBRARIES} )) || fail "aucune bibliothèque .so dans $RES/python"
for inside in $RES/bin/ffmpeg $RES/bin/uv $RES/python/bin/python3.12 ${LIBRARIES[1,3]}; do
  [[ $(signer $inside) == $SIGNER ]] || fail "${inside#$RES/} n'est pas signé comme l'app ($(signer $inside))"
done
# Sparkle (ADR 0040): signed like the app, never downloading nor installing on its own.
SPARKLE=$APP/Contents/Frameworks/Sparkle.framework
[[ -d $SPARKLE ]] || fail "Sparkle manque dans l'app"
[[ ! -e $SPARKLE/Versions/B/XPCServices ]] || fail "Sparkle garde ses services XPC (inutiles hors bac à sable)"
for part in $SPARKLE $SPARKLE/Versions/B/Autoupdate $SPARKLE/Versions/B/Updater.app; do
  [[ $(signer $part) == $SIGNER ]] || fail "${part#$APP/} n'est pas signé comme l'app"
done
PLIST=$APP/Contents/Info.plist
for key in SUEnableSystemProfiling SUAllowsAutomaticUpdates SUAutomaticallyUpdate; do
  [[ $(plutil -extract $key raw $PLIST 2>/dev/null) == false ]] || fail "$key n'est pas à « non » dans Info.plist"
done
[[ $(plutil -extract SURequireSignedFeed raw $PLIST 2>/dev/null) == true ]] || fail "l'app accepterait un appcast non signé"
FEED=$(plutil -extract SUFeedURL raw $PLIST 2>/dev/null || true)
if [[ -n $FEED ]]; then
  [[ $FEED == https://github.com/* ]] || fail "flux des mises à jour inattendu : $FEED"
  plutil -extract SUPublicEDKey raw $PLIST >/dev/null 2>&1 || fail "un flux sans clé des mises à jour"
  print "   mises à jour : $FEED, sur accord ou sur demande, jamais installées seules"
else
  [[ -z $PUBLICATION ]] || fail "sans flux ni clé de mises à jour, une app ne se publie pas"
  print "   sans clé des mises à jour : cette app ne cherche pas les siennes (essai seulement)"
fi
snapshot > $WORK/avant.txt
for tool in ffmpeg ffprobe uv coulisses-son-ordinateur; do
  [[ -x $RES/bin/$tool ]] || fail "outil absent : $tool"
  foreign=$(otool -L $RES/bin/$tool | tail -n +2 | awk '{print $1}' | grep -vE '^(/usr/lib/|/System/Library/)' || true)
  [[ -z $foreign ]] || fail "$tool dépend de ce Mac : $foreign"
done
BUILT_WITH=$($RES/bin/ffmpeg -version)
[[ $BUILT_WITH == *--disable-network* ]] || fail "ffmpeg n'est pas construit sans réseau"
[[ $BUILT_WITH == *--enable-gpl* || $BUILT_WITH == *--enable-nonfree* ]] && fail "ffmpeg n'est pas sous LGPL"
PROTOCOLS=$($RES/bin/ffmpeg -hide_banner -protocols | awk '/Input:/{on=1; next} /Output:/{on=0} on {print $1}' | sort -u | tr '\n' ' ')
[[ $PROTOCOLS == "file pipe " ]] || fail "protocoles en entrée de ffmpeg : $PROTOCOLS"
print "   signature valide ($SIGNER) ; outils autonomes ; ffmpeg LGPL, sans réseau, protocoles : $PROTOCOLS"

print "2. Le ffmpeg de l'app lit chaque format…"
say -v Thomas -o $WORK/voix.aiff "Bonjour à tous. On reprend la scène du marché, avec plus d'énergie au début."
typeset -A SAMPLES=(
  wav "-c:a pcm_s16le" aiff "-c:a pcm_s16be" caf "-c:a pcm_s24le" m4a "-c:a aac"
  mov "-c:a aac" mp3 "-c:a libmp3lame" flac "-c:a flac" ogg "-c:a libopus"
  opus "-c:a libopus" webm "-c:a libopus" aac "-c:a aac"
)
for ext in ${(k)SAMPLES}; do
  ffmpeg -loglevel error -y -i $WORK/voix.aiff -ar 48000 ${=SAMPLES[$ext]} $WORK/essai.$ext
  bytes=$($RES/bin/ffmpeg -v error -i $WORK/essai.$ext -ac 1 -ar 16000 -f f32le - | wc -c | tr -d ' ')
  (( bytes > 100000 )) || fail "$ext : le ffmpeg de l'app n'en tire rien ($bytes octets)"
  # Read whole before testing: grep -q would close the pipe early (SIGPIPE, then pipefail).
  probed=$($RES/bin/ffprobe -v error -show_streams -of json $WORK/essai.$ext) || fail "$ext : ffprobe a échoué"
  [[ $probed == *'"codec_type": "audio"'* ]] || fail "$ext : ffprobe n'y voit pas d'audio"
done
# mlx-audio hands raw bytes through a pipe, and reads s16le back.
piped=$(cat $WORK/essai.wav | $RES/bin/ffmpeg -v error -i pipe:0 -ac 1 -ar 16000 -f s16le pipe:1 | wc -c | tr -d ' ')
(( piped > 50000 )) || fail "lecture par un tube : $piped octets"
# And by the app's own import (media.probe), as when a file is chosen: not processed.
for ext in ${(k)SAMPLES}; do
  env -i HOME=$HOME COULISSES_RESSOURCES=$RES PYTHONDONTWRITEBYTECODE=1 \
    PATH=$RES/bin:/usr/bin:/bin:/usr/sbin:/sbin $RES/python/bin/python3 -I -B -c \
    "import sys; from pathlib import Path; from coulisses_app.media import probe; probe(Path(sys.argv[1]))" \
    $WORK/essai.$ext || fail "$ext : refusé par l'import de l'app"
done
print "   lus : ${(ok)SAMPLES} ; par un tube ; et par l'import de l'app"

cat > $WORK/reseau.sb <<'PROFILE'
(version 1)
(allow default)
(deny network-outbound)
(allow network-outbound (remote ip "localhost:*"))
(allow network-outbound (remote unix-socket))
PROFILE
if sandbox-exec -f $WORK/reseau.sb curl -s -m 5 -o /dev/null https://www.apple.com; then
  fail "internet répond depuis le bac à sable"
fi

print "3. Le service de l'app démarre, réseau coupé, sans Homebrew…"
# As the launcher starts it (main.swift); env -i: nothing of this shell (PATH, PYTHON…).
(cd $HOME && exec env -i HOME=$HOME TMPDIR=$TMPDIR USER=$USER LANG=fr_FR.UTF-8 \
  PATH=/usr/bin:/bin:/usr/sbin:/sbin COULISSES_RESSOURCES=$RES \
  PYTHONDONTWRITEBYTECODE=1 PYTHONNOUSERSITE=1 COULISSES_DATA_DIR=$WORK/donnees \
  sandbox-exec -f $WORK/reseau.sb \
  $RES/python/bin/python3 -I -B -u -m coulisses_app.cli --sans-navigateur --port $PORT \
  > $WORK/service.log 2>&1) &
SERVICE=$!
for _ in {1..120}; do curl -s -m 1 -o /dev/null $URL/api/etat && break; sleep 1; done
ETAT=$(curl -s -m 2 $URL/api/etat) || fail "le service ne répond pas (voir le journal)"
print $ETAT | python3 -c "
import json, sys
s = json.load(sys.stdin)
assert s['app_version'] == '$VERSION', s['app_version']
assert s['data_dir'] == '$WORK/donnees', s['data_dir']
print('   version', s['app_version'], '; moteur', s['engine_version'], '; données temporaires')" ||
  fail "le service ne dit pas ce qu'il faut : $ETAT"

print "4. Import (m4a, comme d'un téléphone) et traitement par le moteur…"
ID=$(curl -s -F fichier=@$WORK/essai.m4a -F non_nommes=1 $URL/api/seances |
  python3 -c 'import json, sys; print(json.load(sys.stdin)["id"])') || fail "import refusé"
STATE=""
for _ in {1..900}; do
  STATE=$(curl -s $URL/api/seances/$ID | python3 -c \
    'import json, sys; s = json.load(sys.stdin)["session"]; print(s["job_state"], s["job_error"] or "")')
  [[ $STATE == done* || $STATE == failed* ]] && break
  sleep 2
done
[[ $STATE == done* ]] || fail "traitement : $STATE"
curl -s $URL/api/seances/$ID/transcript | python3 -c '
import json, sys
view = json.load(sys.stdin)
turns = view["turns"]
assert turns, "aucun tour"
print("   traitée :", len(turns), "tours")' || fail "transcription vide"

kill -INT $SERVICE; wait $SERVICE 2>/dev/null || true; SERVICE=""

print "5. L'app elle-même, lancée sans accord : rien ne sort du Mac…"
# ADR 0040: Sparkle looks for updates only after consent. The app is launched for real (its
# window opens), on a throwaway data folder, as a friend's app that was never asked: no
# answer to Sparkle's question, which it asks on this second launch. Its connections are
# read for 30 s. The preferences of this identifier are set aside before, put back after.
BUNDLE_ID=$(plutil -extract CFBundleIdentifier raw $PLIST)
# An installed Coulisses of the same identifier, open now, would share these preferences.
for pid in ${(f)"$(pgrep -f '\.app/Contents/MacOS/' || true)"}; do
  running=$(ps -o comm= -p $pid 2>/dev/null || true)
  bundle=${running%/Contents/MacOS/*}
  [[ -n $running && $bundle != $APP ]] || continue
  if [[ $(plutil -extract CFBundleIdentifier raw "$bundle/Contents/Info.plist" 2>/dev/null) == $BUNDLE_ID ]]; then
    fail "une Coulisses de même identifiant est ouverte ($bundle) : quittez-la, puis relancez l'essai"
  fi
done
defaults export $BUNDLE_ID $WORK/preferences.plist
SAVED_PREFERENCES=$WORK/preferences.plist
defaults delete $BUNDLE_ID 2>/dev/null || true
defaults write $BUNDLE_ID SUHasLaunchedBefore -bool true
{
  open -n --env COULISSES_DATA_DIR=$WORK/donnees-app $APP
  : > $WORK/connexions.txt
  for _ in {1..30}; do
    PIDS=(${(f)"$(pgrep -f "$APP/Contents/" || true)"})
    if (( ${#PIDS} )); then
      lsof -nP -a -i -p ${(j:,:)PIDS} 2>/dev/null | awk 'NR > 1 {print $9}' >> $WORK/connexions.txt || true
    fi
    sleep 1
  done
  LAUNCHER=$(pgrep -f "$APP/Contents/MacOS/" || true)
  [[ -n $LAUNCHER ]] || fail "l'app ne s'est pas lancée"
  # Stopped by hand: AppleScript would also quit an installed Coulisses of the same identifier.
  APP_SERVICE=$(pgrep -P $LAUNCHER -f coulisses_app.cli || true)
  kill -TERM $LAUNCHER
  if [[ -n $APP_SERVICE ]]; then
    kill -INT $APP_SERVICE
    wait_end $APP_SERVICE 60 || fail "le service de l'app d'essai ne s'arrête pas ($APP_SERVICE)"
  fi
  # Nothing written after the put back.
  wait_end $LAUNCHER 30 || fail "l'app d'essai ne s'arrête pas ($LAUNCHER)"
  LAUNCHER=""
  OUTSIDE=$(awk -F'->' 'NF > 1 {sub(/:[0-9]+$/, "", $2); print $2}' $WORK/connexions.txt |
    grep -vE '^(127\.0\.0\.1|\[::1\]|localhost)$' | sort -u || true)
  [[ -z $OUTSIDE ]] || fail "l'app s'est connectée hors du Mac sans accord : $OUTSIDE"
}
restore_preferences
print "   aucune connexion hors de 127.0.0.1 en 30 s, sans réponse à Sparkle ; préférences de l'app remises telles quelles"

print "6. Rien d'écrit dans l'app…"
snapshot > $WORK/apres.txt
diff $WORK/avant.txt $WORK/apres.txt > $WORK/ecrit.txt || fail "l'app a changé pendant l'essai : $(head -5 $WORK/ecrit.txt)"
codesign --verify --deep --strict $APP || fail "signature invalide après l'essai"
if grep -iE "ConnectionError|Name or service not known|nodename nor servname|Errno 1\]" $WORK/service.log; then
  fail "le service a tenté de sortir (voir le journal)"
fi
print "RÉUSSI : $APP lit, traite, sans réseau ni Homebrew, et reste telle quelle."
