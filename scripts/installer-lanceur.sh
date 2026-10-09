#!/bin/zsh
# Builds Coulisses.app, the app in the Dock (ADR 0034), and puts it in ~/Applications
# (or the folder given). Built on this Mac with Apple's compiler; nothing is downloaded.
#
# Usage: scripts/installer-lanceur.sh [dossier]
#
# The app is signed for this Mac only (ad hoc). macOS ties the permissions (micro, son de
# l'ordinateur) to that signature: built again, the app asks for them again.

set -euo pipefail

ROOT=${0:A:h:h}
SOURCE=$ROOT/native/lanceur
BUILD=$SOURCE/build
DESTINATION=${1:-$HOME/Applications}
APP=$BUILD/Coulisses.app

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
swift $SOURCE/icone.swift $BUILD/Coulisses.iconset
iconutil -c icns $BUILD/Coulisses.iconset -o $APP/Contents/Resources/Coulisses.icns

PLIST=$APP/Contents/Info.plist
cp $SOURCE/Info.plist $PLIST
plutil -replace CoulissesProjet -string $ROOT $PLIST
plutil -replace CoulissesUV -string $UV $PLIST
# The PATH of this shell: ffmpeg, swiftc and the others, as in the Terminal.
plutil -replace CoulissesPATH -string $PATH $PLIST
plutil -replace CFBundleShortVersionString -string $VERSION $PLIST
plutil -replace CFBundleVersion -string $VERSION $PLIST

codesign --force --sign - $APP

mkdir -p $DESTINATION
rm -rf $DESTINATION/Coulisses.app
ditto $APP $DESTINATION/Coulisses.app
print "Coulisses $VERSION est dans $DESTINATION. Glissez-le dans le Dock."
