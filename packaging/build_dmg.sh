#!/bin/bash
# Baut LocalFlow.app (PyInstaller) und packt es in eine Drag-and-drop-DMG.
# Aufruf vom Repo-Wurzelverzeichnis:  bash packaging/build_dmg.sh
set -euo pipefail

cd "$(dirname "$0")/.."

# Python-Interpreter: lokal der Projekt-venv, in CI (kein .venv) das System-/
# Runner-Python mit den via requirements.txt installierten Paketen.
if [ -x ".venv/bin/python" ]; then
  PY=".venv/bin/python"
else
  PY="python3"
fi

# Zentrale Versionsquelle: localflow/__init__.py (NICHT hier hardcoden)
VERSION="$("$PY" -c 'from localflow import __version__; print(__version__)')"
APP="dist/LocalFlow.app"
DMG="dist/LocalFlow-${VERSION}.dmg"

echo "▸ 1/4  PyInstaller-Build (Python: $PY)…"
# Etwaige laufende Test-Instanz beenden (hält sonst Dateien im dist/ offen)
pkill -9 -f "dist/LocalFlow" 2>/dev/null || true
sleep 1
rm -rf build dist
# "-m PyInstaller" statt des "pyinstaller"-Kommandos: funktioniert unabhängig
# davon, ob PyInstaller in einem venv/bin oder systemweit installiert ist.
"$PY" -m PyInstaller packaging/LocalFlow.spec --noconfirm --clean \
  --distpath dist --workpath build >/tmp/pyinstaller.log 2>&1
[ -d "$APP" ] || { echo "✗ Build fehlgeschlagen — siehe /tmp/pyinstaller.log"; tail -40 /tmp/pyinstaller.log; exit 1; }

# Stabile Signatur bevorzugen: mit ihr überleben die macOS-Berechtigungen jedes
# Update (Designated Requirement = Bundle-ID + Zertifikat, siehe setup_signing.sh).
# Ist der Signatur-Schlüsselbund nicht eingerichtet (z.B. frischer CI-Runner),
# fällt es sauber auf ad-hoc zurück.
SIGN_IDENTITY="LocalFlow Code Signing"
SIGN_KC="$HOME/Library/Keychains/localflow-signing.keychain-db"
if [ -f "$SIGN_KC" ] && security find-identity -p codesigning "$SIGN_KC" 2>/dev/null | grep -q "$SIGN_IDENTITY"; then
  echo "▸ 2/4  Signieren mit stabiler Identität ('$SIGN_IDENTITY')…"
  security unlock-keychain -p "localflow-build" "$SIGN_KC" 2>/dev/null || true
  codesign --force --deep --sign "$SIGN_IDENTITY" --keychain "$SIGN_KC" "$APP" >/dev/null 2>&1 \
    || codesign --force --deep --sign - "$APP" >/dev/null 2>&1 || true
else
  echo "▸ 2/4  Ad-hoc-Signierung (stabile Identität nicht eingerichtet)…"
  codesign --force --deep --sign - "$APP" >/dev/null 2>&1 || true
fi

echo "▸ 3/4  DMG-Layout vorbereiten…"
STAGE="$(mktemp -d)"
cp -R "$APP" "$STAGE/LocalFlow.app"
ln -s /Applications "$STAGE/Applications"       # Ziel für Drag-and-drop
# Kurz-Anleitung mit ins Image legen
cat > "$STAGE/ANLEITUNG.txt" <<'TXT'
LocalFlow installieren:

1. LocalFlow-Symbol auf den "Programme"-Ordner ziehen.
2. In "Programme" LocalFlow per RECHTSKLICK -> "Öffnen" starten
   (nur beim allerersten Mal; danach normal per Doppelklick/Spotlight).
3. Ein Assistent führt durch Mikrofon, Berechtigungen und den
   einmaligen Modell-Download.

Diktieren: rechte Wahltaste (Option) halten, sprechen, loslassen.
TXT

# Hintergrundbild (unsichtbarer Ordner, wie bei DMGs üblich)
BG_SRC="packaging/dmg_background.png"
HAVE_BG=0
if [ -f "$BG_SRC" ]; then
  mkdir -p "$STAGE/.background"
  cp "$BG_SRC" "$STAGE/.background/background.png"
  HAVE_BG=1
fi

echo "▸ 4/4  DMG erstellen…"
rm -f "$DMG"

if [ "$HAVE_BG" = "1" ] && [ "$(uname)" = "Darwin" ]; then
  # Zwischen-DMG beschreibbar erzeugen, damit Finder Icon-Layout/Hintergrund
  # setzen kann; danach komprimiert & schreibgeschützt final konvertieren.
  RW_DMG="$(mktemp -u).dmg"
  hdiutil create -volname "LocalFlow" -srcfolder "$STAGE" \
    -fs HFS+ -format UDRW -size 900m "$RW_DMG" >/dev/null
  MOUNT_OUT="$(hdiutil attach -readwrite -noverify -noautoopen "$RW_DMG")"
  # grep -o statt sed: hdiutil-Ausgabe hat mehrere "/dev/..."-Zeilen, nur EINE
  # enthält "/Volumes/..." (die Partitionszeile) -> gezielt NUR den Pfad ziehen.
  MOUNT_POINT="$(echo "$MOUNT_OUT" | grep -o '/Volumes/[^	]*' | head -1)"
  [ -n "$MOUNT_POINT" ] || { echo "✗ Mount-Punkt nicht gefunden:"; echo "$MOUNT_OUT"; exit 1; }

  osascript <<APPLESCRIPT || echo "⚠️  Finder-Layout fehlgeschlagen, DMG bleibt trotzdem nutzbar"
tell application "Finder"
  tell disk "LocalFlow"
    open
    set current view of container window to icon view
    set toolbar visible of container window to false
    set statusbar visible of container window to false
    set the bounds of container window to {400, 120, 1720, 920}
    set viewOptions to the icon view options of container window
    set arrangement of viewOptions to not arranged
    set icon size of viewOptions to 128
    set text size of viewOptions to 13
    set background picture of viewOptions to file ".background:background.png"
    set position of item "LocalFlow.app" to {360, 430}
    set position of item "Applications" to {960, 430}
    set position of item "ANLEITUNG.txt" to {1230, 690}
    close
    open
    update without registering applications
    delay 2
    close
  end tell
end tell
APPLESCRIPT

  if ! hdiutil detach "$MOUNT_POINT" >/tmp/lf_detach.log 2>&1; then
    sleep 1
    hdiutil detach "$MOUNT_POINT" -force >/tmp/lf_detach.log 2>&1 \
      || { echo "✗ Aushängen fehlgeschlagen:"; cat /tmp/lf_detach.log; exit 1; }
  fi
  hdiutil convert "$RW_DMG" -format UDZO -ov -o "$DMG" >/dev/null
  rm -f "$RW_DMG"
else
  hdiutil create -volname "LocalFlow" -srcfolder "$STAGE" \
    -ov -format UDZO "$DMG" >/dev/null
fi
rm -rf "$STAGE"

# Gebaute .app aus dist/ entfernen — sie steckt jetzt in der DMG.
#
# WARUM: macOS bindet Bedienungshilfen-/Eingabemonitoring-Rechte bei ad-hoc
# signierten Apps an den DATEIPFAD. Bliebe dist/LocalFlow.app liegen, gäbe es
# ZWEI "LocalFlow"-Einträge in den Systemeinstellungen — der Nutzer setzt das
# Häkchen bei der einen, startet aber die andere, und die Rechte "gehen wieder
# aus". Genau dieser Bug wurde am 2026-07-14 gemeldet.
rm -rf "$APP" dist/LocalFlow

SIZE="$(du -h "$DMG" | cut -f1)"
echo "✅ Fertig: $DMG  ($SIZE)"
echo "   (dist/LocalFlow.app entfernt — verhindert doppelte Berechtigungs-Einträge)"
