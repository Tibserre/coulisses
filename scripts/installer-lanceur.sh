#!/bin/zsh
# Builds Coulisses.app, the app in the Dock (ADR 0034), and puts it in ~/Applications
# (or the folder given). Built on this Mac with Apple's compiler; nothing is downloaded.
#
# --dev builds « Coulisses (dév) » instead (ADR 0040): another name, identifier, icon,
# port (8766) and log, on ~/Coulisses/Données-dev; its service refuses the real data. The
# two apps live side by side and share neither service, data nor permissions.
#
# Usage: scripts/installer-lanceur.sh [--dev] [dossier]
#
# The app is signed for this Mac only (ad hoc). macOS ties the permissions (micro, son de
# l'ordinateur) to that signature: built again, the app asks for them again.

set -euo pipefail

ROOT=${0:A:h:h}
SOURCE=$ROOT/native/lanceur

VARIANT=""
NAME="Coulisses"
IDENTIFIER="local.coulisses.app"
DESTINATION=""
# Anything not understood stops here: a misplaced --dev would replace the everyday app.
for argument in "$@"; do
  case $argument in
    --dev)
      VARIANT=dev
      NAME="Coulisses (dév)"
      IDENTIFIER="local.coulisses.app.dev"
      ;;
    -*)
      print -u2 "Option inconnue : $argument. Usage : scripts/installer-lanceur.sh [--dev] [dossier]"
      exit 2
      ;;
    *)
      [[ -z $DESTINATION ]] || {
        print -u2 "Un seul dossier de destination. Usage : scripts/installer-lanceur.sh [--dev] [dossier]"
        exit 2
      }
      DESTINATION=$argument
      ;;
  esac
done
DESTINATION=${DESTINATION:-$HOME/Applications}
BUILD=$SOURCE/build${VARIANT:+-$VARIANT}
APP="$BUILD/$NAME.app"

UV=$(command -v uv) || { print -u2 "uv est introuvable : installez-le, puis relancez."; exit 1 }
command -v swiftc >/dev/null || {
  print -u2 "Les outils de développement d'Apple manquent : xcode-select --install"
  exit 1
}
VERSION=$(sed -n 's/^version = "\(.*\)"/\1/p' $ROOT/pyproject.toml | head -1)

rm -rf $BUILD
mkdir -p $APP/Contents/MacOS $APP/Contents/Resources

print "Compilation…"
swiftc -O -swift-version 5 -target arm64-apple-macosx14.4 \
  $SOURCE/main.swift -o $APP/Contents/MacOS/Coulisses

print "Icône…"
swift $SOURCE/icone.swift $BUILD/Coulisses.iconset $VARIANT
iconutil -c icns $BUILD/Coulisses.iconset -o $APP/Contents/Resources/Coulisses.icns

PLIST=$APP/Contents/Info.plist
cp $SOURCE/Info.plist $PLIST
plutil -replace CoulissesProjet -string $ROOT $PLIST
plutil -replace CoulissesUV -string $UV $PLIST
# The PATH of this shell: ffmpeg, swiftc and the others, as in the Terminal.
plutil -replace CoulissesPATH -string $PATH $PLIST
plutil -replace CFBundleShortVersionString -string $VERSION $PLIST
plutil -replace CFBundleName -string $NAME $PLIST
plutil -replace CFBundleDisplayName -string $NAME $PLIST
plutil -replace CFBundleIdentifier -string $IDENTIFIER $PLIST
plutil -replace CoulissesVariante -string "$VARIANT" $PLIST
plutil -replace CFBundleVersion -string $VERSION $PLIST

codesign --force --sign - $APP

mkdir -p $DESTINATION
rm -rf "$DESTINATION/$NAME.app"
ditto $APP "$DESTINATION/$NAME.app"
print "$NAME $VERSION est dans $DESTINATION. Glissez-le dans le Dock."
