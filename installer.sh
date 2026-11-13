#!/bin/sh
# Installe ou met à jour Coulisses depuis sa dernière version confirmée (ADR 0085).
#
#   curl -fsSL https://raw.githubusercontent.com/Tibserre/coulisses/main/installer.sh | sh
#
# Pour un Mac où macOS refuse d'ouvrir l'app et ne propose pas « Ouvrir quand même »
# (un profil de gestion qui l'interdit). Un fichier téléchargé par curl n'est pas mis en
# quarantaine : Gatekeeper ne l'examine pas. Ce script remplace donc ce contrôle par le sien,
# avant toute installation :
#   - le DMG fait la taille annoncée par la liste des versions (l'appcast de Sparkle) ;
#   - la signature de l'app est intacte (codesign --verify --deep --strict) ;
#   - elle est signée par le certificat de Coulisses, celui de chaque version publiée
#     (exigence désignée ci-dessous ; scripts/publier.py refuse d'en publier une autre) ;
#   - sa version est celle annoncée.
# L'ancienne Coulisses n'est mise de côté qu'une fois la nouvelle copiée et revérifiée, et
# rien n'est supprimé : elle part à la Corbeille, ou de côté si la Corbeille refuse.
# Pas de sudo. Tout est dans main(), appelée à la dernière ligne : un téléchargement coupé
# en route n'exécute rien.
#
# Pour un essai, sans toucher à Applications : COULISSES_DESTINATION=<dossier> et
# COULISSES_NE_PAS_OUVRIR=1.

set -eu

REPO="Tibserre/coulisses"
APPCAST="https://github.com/${REPO}/releases/latest/download/appcast.xml"
# The designated requirement of every published version (exigence.txt of each publication).
REQUIREMENT='identifier "io.github.tibserre.coulisses" and certificate leaf = H"e354d810d7cc380d2eb60c4eedf28afee292e532"'
NAME="Coulisses.app"
WORK=""
MOUNT=""

say() { printf '%s\n' "$*"; }
fail() { printf 'Échec : %s\n' "$*" >&2; exit 1; }

cleanup() {
  if [ -n "${MOUNT}" ]; then
    if ! hdiutil detach -quiet "${MOUNT}" </dev/null 2>/dev/null &&
      ! hdiutil detach -quiet -force "${MOUNT}" </dev/null 2>/dev/null; then
      printf 'Attention : le DMG est resté monté sur %s ; démontez-le dans le Finder, puis mettez %s à la Corbeille.\n' "${MOUNT}" "${WORK}" >&2
      return
    fi
  fi
  # Only this run's own temporary folder: the downloaded DMG and, after a failed check, the
  # copy that was refused.
  [ -z "${WORK}" ] || rm -rf "${WORK}"
}

# True if a process runs from inside this app (its launcher or its service).
running_from() {
  # Listed first, then searched: the search itself is never in the list.
  processes=$(ps -axo command=)
  printf '%s\n' "${processes}" | grep -F -q -- "$1/Contents/"
}

main() {
  [ "$(uname -s)" = Darwin ] || fail "Coulisses ne s'installe que sur un Mac."
  [ "$(uname -m)" = arm64 ] || fail "Coulisses demande un Mac Apple Silicon (M1 ou plus récent)."
  MACOS=$(sw_vers -productVersion)
  case "${MACOS}" in
    1[0-3].*|14.[0-3]|14.[0-3].*) fail "Coulisses demande macOS 14.4 ou plus récent (ce Mac : ${MACOS})." ;;
  esac

  if [ -n "${COULISSES_DESTINATION:-}" ]; then
    DEST=${COULISSES_DESTINATION}
  elif [ -w /Applications ]; then
    DEST=/Applications
  else
    DEST="${HOME}/Applications"
  fi
  mkdir -p "${DEST}"
  TARGET="${DEST}/${NAME}"

  WORK=$(mktemp -d -t coulisses-installation)
  trap cleanup EXIT
  trap 'exit 130' INT TERM

  say "Recherche de la dernière version de Coulisses…"
  curl -fsSL "${APPCAST}" -o "${WORK}/appcast.xml" </dev/null || fail "impossible de lire la dernière version sur GitHub (connexion ?)."
  URL=$(sed -n 's/.*<enclosure url="\([^"]*\)".*/\1/p' "${WORK}/appcast.xml" | head -n 1)
  LENGTH=$(sed -n 's/.*<enclosure [^>]*length="\([0-9]*\)".*/\1/p' "${WORK}/appcast.xml" | head -n 1)
  VERSION=$(sed -n 's/.*<sparkle:shortVersionString>\([^<]*\)<.*/\1/p' "${WORK}/appcast.xml" | head -n 1)
  case "${URL}" in
    *..*|*' '*|*'?'*|*'#'*) fail "adresse du DMG inattendue dans la liste des versions : « ${URL} »." ;;
    "https://github.com/${REPO}/releases/download/"*.dmg) ;;
    *) fail "adresse du DMG inattendue dans la liste des versions : « ${URL} »." ;;
  esac
  [ -n "${LENGTH}" ] || fail "taille du DMG introuvable dans la liste des versions."
  [ -n "${VERSION}" ] || fail "numéro de version introuvable dans la liste des versions."

  say "Téléchargement de Coulisses ${VERSION}…"
  curl -fL --progress-bar "${URL}" -o "${WORK}/Coulisses.dmg" </dev/null || fail "le téléchargement du DMG a échoué."
  SIZE=$(stat -f %z "${WORK}/Coulisses.dmg")
  [ "${SIZE}" = "${LENGTH}" ] || fail "DMG incomplet (${SIZE} octets au lieu de ${LENGTH})."

  mkdir "${WORK}/volume"
  hdiutil attach -quiet -nobrowse -readonly -mountpoint "${WORK}/volume" "${WORK}/Coulisses.dmg" </dev/null ||
    fail "le DMG ne s'ouvre pas."
  MOUNT="${WORK}/volume"
  SOURCE="${MOUNT}/${NAME}"
  [ -d "${SOURCE}" ] || fail "le DMG ne contient pas ${NAME}."

  say "Vérification de la signature…"
  codesign --verify --deep --strict "${SOURCE}" </dev/null 2>"${WORK}/codesign.txt" ||
    fail "la signature de l'app est invalide : $(cat "${WORK}/codesign.txt"). Rien n'est installé."
  codesign --verify -R="${REQUIREMENT}" "${SOURCE}" </dev/null 2>/dev/null ||
    fail "l'app n'est pas signée par le certificat de Coulisses. Rien n'est installé."
  FOUND=$(defaults read "${SOURCE}/Contents/Info" CFBundleShortVersionString 2>/dev/null </dev/null || true)
  [ "${FOUND}" = "${VERSION}" ] || fail "le DMG contient la version « ${FOUND} », pas ${VERSION}. Rien n'est installé."
  say "Signature vérifiée : Coulisses ${VERSION}, signée par le certificat de Coulisses."

  if running_from "${TARGET}"; then
    fail "Coulisses est ouverte. Quittez-la (⌘Q), puis relancez cette commande. Rien n'est installé."
  fi

  # The new copy first, checked, beside the old one: until it passes, nothing is touched.
  PARTIAL="${TARGET}.partiel"
  [ ! -e "${PARTIAL}" ] || fail "une installation interrompue est restée : ${PARTIAL}. Mettez-la à la Corbeille, puis relancez."
  say "Copie dans ${DEST}…"
  if ! ditto "${SOURCE}" "${PARTIAL}" </dev/null; then
    [ ! -e "${PARTIAL}" ] || mv "${PARTIAL}" "${WORK}/refusee.app"
    fail "la copie de l'app a échoué. Rien n'est remplacé."
  fi
  if ! codesign --verify --deep --strict -R="${REQUIREMENT}" "${PARTIAL}" </dev/null 2>/dev/null; then
    mv "${PARTIAL}" "${WORK}/refusee.app"
    fail "la copie ne passe pas la vérification. Rien n'est remplacé."
  fi

  if [ -e "${TARGET}" ]; then
    OLD=$(defaults read "${TARGET}/Contents/Info" CFBundleShortVersionString 2>/dev/null </dev/null || echo "?")
    STAMP=$(date +%Y%m%d-%H%M%S)
    if mv "${TARGET}" "${HOME}/.Trash/Coulisses ${OLD} (${STAMP}).app" 2>/dev/null; then
      say "L'ancienne Coulisses (${OLD}) est dans la Corbeille."
    else
      ASIDE="${HOME}/Coulisses/Anciennes versions"
      mkdir -p "${ASIDE}"
      if ! mv "${TARGET}" "${ASIDE}/Coulisses ${OLD} (${STAMP}).app"; then
        mv "${PARTIAL}" "${WORK}/refusee.app"
        fail "impossible de mettre l'ancienne Coulisses de côté. Rien n'est remplacé."
      fi
      say "L'ancienne Coulisses (${OLD}) est de côté dans ${ASIDE}."
    fi
  fi
  mv "${PARTIAL}" "${TARGET}"

  say "Coulisses ${VERSION} est installée dans ${DEST}."
  if [ "${DEST}" != /Applications ] && [ -z "${COULISSES_DESTINATION:-}" ] && [ -e "/Applications/${NAME}" ]; then
    say "Attention : une autre Coulisses reste dans /Applications, que ce script ne peut pas déplacer sans droits d'administrateur. Ouvrez bien celle de ${DEST}."
  fi
  if [ -z "${COULISSES_NE_PAS_OUVRIR:-}" ]; then
    open "${TARGET}"
  fi
}

main "$@"
