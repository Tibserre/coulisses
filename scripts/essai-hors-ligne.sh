#!/bin/zsh
# The whole path with the network cut (spec §2 P1, plan step 10): import, processing by the
# engine, summary by Ollama, with nothing allowed out of the Mac. A macOS sandbox lets the
# service reach 127.0.0.1 only (itself, Ollama); every other connection is refused. Voices
# made by `say`, a throwaway data folder: no real data, nothing written in ~/Coulisses/Données.
#
# Usage: scripts/essai-hors-ligne.sh [modèle Ollama]
# Ollama must be running (it is outside the sandbox, on 127.0.0.1).

set -euo pipefail

ROOT=${0:A:h:h}
WORK=$(mktemp -d -t coulisses-hors-ligne)
PORT=8799
URL=http://127.0.0.1:$PORT
MODEL=${1:-$(curl -s -m 5 127.0.0.1:11434/api/tags | python3 -c \
  'import json, sys; print(json.load(sys.stdin)["models"][0]["name"])')}
SERVICE=""

finish() {
  if [[ -n $SERVICE ]]; then
    kill -INT $SERVICE 2>/dev/null || true
    wait $SERVICE 2>/dev/null || true
  fi
  if pgrep -f "coulisses-app --sans-navigateur --port $PORT" >/dev/null; then
    print -u2 "ATTENTION : le service d'essai tourne encore (port $PORT)."
  fi
  print "Journal du service : $WORK/service.log"
}
trap finish EXIT

fail() { print -u2 "ÉCHEC : $*"; exit 1 }

cat > $WORK/reseau.sb <<'PROFILE'
(version 1)
(allow default)
(deny network-outbound)
(allow network-outbound (remote ip "localhost:*"))
(allow network-outbound (remote unix-socket))
PROFILE
cut() { sandbox-exec -f $WORK/reseau.sb "$@" }

print "1. Le réseau est coupé dans le bac à sable…"
if cut curl -s -m 5 -o /dev/null https://www.apple.com; then fail "internet répond depuis le bac à sable"; fi
cut curl -s -m 5 -o /dev/null 127.0.0.1:11434/api/tags || fail "Ollama ne répond pas sur 127.0.0.1"
print "   internet : refusé ; 127.0.0.1 : accessible."

print "2. Deux voix de synthèse…"
say -v Thomas -o $WORK/a.aiff "Bonjour à tous. On reprend la scène du marché, avec plus d'énergie au début."
say -v Amélie -o $WORK/b.aiff "D'accord. Je propose que la marchande arrive par la gauche, et qu'on garde le silence plus longtemps."
say -v Thomas -o $WORK/c.aiff "Très bien. On la joue tout de suite, puis on en reparle."
ffmpeg -loglevel error -i $WORK/a.aiff -i $WORK/b.aiff -i $WORK/c.aiff \
  -filter_complex "[0][1][2]concat=n=3:v=0:a=1" -ar 48000 -ac 1 $WORK/seance.wav

print "3. Le service démarre, réseau coupé…"
# exec: $! is uv itself (sandbox-exec runs it in its place), which passes ⌃C on.
(cd $ROOT && COULISSES_DATA_DIR=$WORK/donnees exec sandbox-exec -f $WORK/reseau.sb \
  uv run --offline coulisses-app --sans-navigateur --port $PORT > $WORK/service.log 2>&1) &
SERVICE=$!
for _ in {1..120}; do curl -s -m 1 -o /dev/null $URL/api/etat && break; sleep 1; done
curl -s -m 1 -o /dev/null $URL/api/etat || fail "le service ne répond pas"

print "4. Import et traitement par le moteur…"
ID=$(curl -s -F fichier=@$WORK/seance.wav -F non_nommes=2 $URL/api/seances |
  python3 -c 'import json, sys; print(json.load(sys.stdin)["id"])')
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
turns = view.get("turns") or view.get("tours") or []
print("   transcription :", len(turns), "tours")'

print "5. Résumé court par Ollama ($MODEL)…"
curl -s -o /dev/null -H 'content-type: application/json' \
  -d "{\"action_ref\": \"resume-court\", \"model\": \"$MODEL\"}" $URL/api/seances/$ID/resumes
for _ in {1..600}; do
  SUMMARY=$(curl -s $URL/api/seances/$ID/resumes | python3 -c '
import json, sys
g = json.load(sys.stdin)
done = [x for x in g["generations"] if x["action_ref"] == "resume-court"]
failed = [x for x in g["pending"] if x["action_ref"] == "resume-court" and x["state"] == "failed"]
print("ok " + (done[0]["output"] or "")[:300].replace("\n", " ") if done else "failed " + (failed[0]["error"] or "") if failed else "")')
  [[ -n $SUMMARY ]] && break
  sleep 2
done
[[ $SUMMARY == ok* ]] || fail "résumé : ${SUMMARY:-pas fini à temps}"
print "   ${SUMMARY#ok }"

print "6. Aucune connexion refusée dans le journal ?"
if grep -iE "ConnectionError|Name or service not known|nodename nor servname|Errno 1\]" $WORK/service.log; then
  fail "le service a tenté de sortir (voir le journal)"
fi
print "RÉUSSI : import, traitement et résumé, sans réseau."
