#!/bin/bash
# Baut die Swift-Hülle (Phase 3) zum Testen. Aufruf vom Repo-Wurzelverzeichnis
# oder von hier aus:  bash swift/build_swift.sh
#
# Erzeugt/aktualisiert swift/LocalFlow.xcodeproj aus project.yml (xcodegen)
# und baut per xcodebuild. Läuft NUR gegen die Python-Engine aus
# ../dist/LocalFlow-Engine/ (Entwicklungs-Fallback, siehe EngineProcess.swift)
# — dafür vorher einmal "bash packaging/build_dmg.sh" oder direkt
# ".venv/bin/python -m PyInstaller packaging/LocalFlow.spec" laufen lassen.
set -euo pipefail
cd "$(dirname "$0")"

command -v xcodegen >/dev/null || { echo "✗ xcodegen fehlt (brew install xcodegen)"; exit 1; }

echo "▸ Xcode-Projekt aus project.yml erzeugen…"
xcodegen generate

echo "▸ Bauen (Debug)…"
xcodebuild -project LocalFlow.xcodeproj -scheme LocalFlow -configuration Debug \
  -derivedDataPath build build

APP="build/Build/Products/Debug/LocalFlow-Dev.app"
INSTALLED="/Applications/LocalFlow-Dev.app"

# Stabile Signatur bevorzugen (wie bei der Python-App, siehe packaging/build_dmg.sh
# und packaging/setup_signing.sh): sonst brechen Eingabemonitoring-/Mikrofon-
# Berechtigungen bei JEDEM Rebuild wieder, weil sich die ad-hoc-CDHash ändert.
SIGN_IDENTITY="LocalFlow Code Signing"
SIGN_KC="$HOME/Library/Keychains/localflow-signing.keychain-db"
SIGN_KC_PASS_FILE="../packaging/signing/.keychain_pass"
if [ -f "$SIGN_KC" ] && [ -f "$SIGN_KC_PASS_FILE" ] && security find-identity -p codesigning "$SIGN_KC" 2>/dev/null | grep -q "$SIGN_IDENTITY"; then
  echo "▸ Signieren mit stabiler Identität ('$SIGN_IDENTITY')…"
  security unlock-keychain -p "$(cat "$SIGN_KC_PASS_FILE")" "$SIGN_KC" 2>/dev/null || true
  codesign --force --deep --sign "$SIGN_IDENTITY" --keychain "$SIGN_KC" "$APP" >/dev/null 2>&1 \
    || echo "⚠️  Signieren fehlgeschlagen, bleibt bei ad-hoc"
else
  echo "▸ Ad-hoc-Signatur (stabile Identität nicht eingerichtet — siehe packaging/setup_signing.sh)…"
fi

# Nach /Applications installieren statt aus dem Build-Ordner zu starten: die
# Berechtigungen stehen dort unter einem festen Pfad in den Systemeinstellungen,
# und der Build-Ordner soll keine startbare Zweitkopie herumliegen lassen.
echo "▸ Nach $INSTALLED installieren…"
pkill -f "LocalFlow-Dev.app" 2>/dev/null || true
pkill -f "dist/LocalFlow-Engine" 2>/dev/null || true
sleep 1
rm -rf "$INSTALLED"
cp -R "$APP" "$INSTALLED"

echo "✅ Fertig: $INSTALLED"
echo "   Starten:  open -a $INSTALLED --args --hotkey alt_l"
echo "   (--hotkey alt_l: sonst greift die Test-App nach derselben rechten"
echo "    Wahltaste wie die echte LocalFlow-App)"
