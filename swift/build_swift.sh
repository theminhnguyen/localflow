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

APP="build/Build/Products/Debug/LocalFlow.app"
echo "✅ Fertig: swift/$APP"
echo "   Starten:  open swift/$APP"
