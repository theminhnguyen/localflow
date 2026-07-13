#!/bin/bash
# Baut LocalFlow.app (PyInstaller) und packt es in eine Drag-and-drop-DMG.
# Aufruf vom Repo-Wurzelverzeichnis:  bash packaging/build_dmg.sh
set -euo pipefail

cd "$(dirname "$0")/.."
VENV=".venv/bin"
VERSION="0.3.0"
APP="dist/LocalFlow.app"
DMG="dist/LocalFlow-${VERSION}.dmg"

echo "▸ 1/4  PyInstaller-Build…"
# Etwaige laufende Test-Instanz beenden (hält sonst Dateien im dist/ offen)
pkill -9 -f "dist/LocalFlow" 2>/dev/null || true
sleep 1
rm -rf build dist
"$VENV/pyinstaller" packaging/LocalFlow.spec --noconfirm --clean \
  --distpath dist --workpath build >/tmp/pyinstaller.log 2>&1
[ -d "$APP" ] || { echo "✗ Build fehlgeschlagen — siehe /tmp/pyinstaller.log"; exit 1; }

echo "▸ 2/4  Ad-hoc-Signierung (nötig auf Apple Silicon)…"
codesign --force --deep --sign - "$APP" >/dev/null 2>&1 || true

echo "▸ 3/4  DMG-Layout vorbereiten…"
STAGE="$(mktemp -d)"
cp -R "$APP" "$STAGE/LocalFlow.app"
ln -s /Applications "$STAGE/Applications"       # Ziel für Drag-and-drop
# Kurz-Anleitung mit ins Image legen
cat > "$STAGE/ANLEITUNG.txt" <<'TXT'
LocalFlow installieren:

1. LocalFlow-Symbol auf den "Programme"-Ordner (rechts) ziehen.
2. In "Programme" LocalFlow per RECHTSKLICK -> "Öffnen" starten
   (nur beim allerersten Mal; danach normal per Doppelklick/Spotlight).
3. macOS fragt nach Mikrofon, Bedienungshilfen und Eingabemonitoring
   -> alle erlauben und LocalFlow einmal neu starten.

Diktieren: rechte Wahltaste (Option) halten, sprechen, loslassen.
TXT

echo "▸ 4/4  DMG erstellen…"
rm -f "$DMG"
hdiutil create -volname "LocalFlow" -srcfolder "$STAGE" \
  -ov -format UDZO "$DMG" >/dev/null
rm -rf "$STAGE"

SIZE="$(du -h "$DMG" | cut -f1)"
echo "✅ Fertig: $DMG  ($SIZE)"
