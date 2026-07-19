#!/bin/bash
# Baut LocalFlow.app (Swift-Hülle + gebündelte Python-Engine) und packt es in
# eine Drag-and-drop-DMG. Aufruf vom Repo-Wurzelverzeichnis:
#   bash packaging/build_dmg.sh
#
# Seit Phase 3.4: die Swift-App (swift/) ist die Produktions-App, sie startet
# die Python-Engine (packaging/LocalFlow.spec, Ziel "LocalFlow-Engine") als
# gebündelten Kindprozess aus Contents/Resources/engine/ — siehe
# EngineProcess.swift. Die alte, rein-pythonische Menüleisten-App (Ziel
# "LocalFlow" in derselben Spec-Datei) wird hier nicht mehr gebaut; das letzte
# Release vor dieser Umstellung bleibt als DMG unter ~/Downloads/ liegen und
# dient bei Bedarf als manueller Rollback.
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
ENGINE_DIST="dist/LocalFlow-Engine"
APP="swift/build/Build/Products/Release/LocalFlow.app"
DMG="dist/LocalFlow-${VERSION}.dmg"

echo "▸ 1/6  PyInstaller-Engine bauen (Python: $PY)…"
# Etwaige laufende Test-Instanzen beenden (halten sonst Dateien offen)
pkill -9 -f "dist/LocalFlow-Engine" 2>/dev/null || true
pkill -9 -f "LocalFlow.app/Contents/Resources/engine" 2>/dev/null || true
sleep 1
rm -rf build dist
"$PY" -m PyInstaller packaging/LocalFlow.spec --noconfirm --clean \
  --distpath dist --workpath build >/tmp/pyinstaller.log 2>&1 || true
[ -d "$ENGINE_DIST" ] || { echo "✗ Engine-Build fehlgeschlagen — siehe /tmp/pyinstaller.log"; tail -40 /tmp/pyinstaller.log; exit 1; }

echo "▸ 2/6  Swift-App bauen (Release)…"
command -v xcodegen >/dev/null || { echo "✗ xcodegen fehlt (brew install xcodegen)"; exit 1; }
pkill -9 -f "LocalFlow.app/Contents/MacOS/LocalFlow" 2>/dev/null || true
sleep 1
rm -rf swift/build
(cd swift && xcodegen generate)
# xcodegen schreibt mit neuen Xcode-Versionen ein "Projektformat der Zukunft"
# (objectVersion 77, seit Xcode 16 für Ordner-Referenzen) — ältere Xcode-
# Versionen (z.B. auf GitHub-Actions-Runnern) können solche Projekte dann
# nicht mehr öffnen ("cannot be opened because it is in a future Xcode
# project file format"). Das Projekt hier nutzt keine Xcode-16-exklusiven
# Funktionen, darum unbedenklich auf einen breit kompatiblen Wert zurück-
# setzen (bestätigter Fix, siehe github.com/yonaskolb/XcodeGen/issues/1578).
sed -i '' 's/objectVersion = [0-9]*;/objectVersion = 60;/' swift/LocalFlow.xcodeproj/project.pbxproj
xcodebuild -project swift/LocalFlow.xcodeproj -scheme LocalFlow -configuration Release \
  -derivedDataPath swift/build build >/tmp/xcodebuild.log 2>&1 || true
[ -d "$APP" ] || { echo "✗ Swift-Build fehlgeschlagen — siehe /tmp/xcodebuild.log"; tail -80 /tmp/xcodebuild.log; exit 1; }

echo "▸ 3/6  Engine ins Bundle kopieren…"
# EngineProcess.swift sucht die Engine unter Contents/Resources/engine/ per
# Bundle.main.url(forResource:"LocalFlow-Engine", subdirectory:"engine") —
# das PyInstaller-onedir-Layout (Binary + _internal/ als Geschwister) bleibt
# dabei unverändert erhalten, nur an einen anderen Ort kopiert.
rm -rf "$APP/Contents/Resources/engine"
mkdir -p "$APP/Contents/Resources/engine"
cp -R "$ENGINE_DIST"/. "$APP/Contents/Resources/engine/"

# Stabile Signatur bevorzugen: mit ihr überleben die macOS-Berechtigungen jedes
# Update (Designated Requirement = Bundle-ID + Zertifikat, siehe setup_signing.sh).
# --deep signiert dabei auch die frisch hineinkopierten Engine-Binaries neu,
# sodass am Ende alles unter derselben Identität steht. Ist der Signatur-
# Schlüsselbund nicht eingerichtet (z.B. frischer CI-Runner), fällt es sauber
# auf ad-hoc zurück.
SIGN_IDENTITY="LocalFlow Code Signing"
SIGN_KC="$HOME/Library/Keychains/localflow-signing.keychain-db"
SIGN_KC_PASS_FILE="packaging/signing/.keychain_pass"
if [ -f "$SIGN_KC" ] && [ -f "$SIGN_KC_PASS_FILE" ] && security find-identity -p codesigning "$SIGN_KC" 2>/dev/null | grep -q "$SIGN_IDENTITY"; then
  echo "▸ 4/6  Signieren mit stabiler Identität ('$SIGN_IDENTITY')…"
  security unlock-keychain -p "$(cat "$SIGN_KC_PASS_FILE")" "$SIGN_KC" 2>/dev/null || true
  codesign --force --deep --sign "$SIGN_IDENTITY" --keychain "$SIGN_KC" "$APP" >/dev/null 2>&1 \
    || codesign --force --deep --sign - "$APP" >/dev/null 2>&1 || true
else
  echo "▸ 4/6  Ad-hoc-Signierung (stabile Identität nicht eingerichtet)…"
  codesign --force --deep --sign - "$APP" >/dev/null 2>&1 || true
fi

echo "▸ 5/6  DMG-Layout vorbereiten…"
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

echo "▸ 6/6  DMG erstellen…"
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

# Gebaute Zwischenstände entfernen — die fertige App steckt jetzt in der DMG.
#
# WARUM: macOS bindet Bedienungshilfen-/Eingabemonitoring-Rechte bei ad-hoc
# signierten Apps an den DATEIPFAD. Bliebe eine gebaute Kopie liegen, gäbe es
# ZWEI "LocalFlow"-Einträge in den Systemeinstellungen — der Nutzer setzt das
# Häkchen bei der einen, startet aber die andere, und die Rechte "gehen wieder
# aus". Genau dieser Bug wurde am 2026-07-14 gemeldet (damals mit der reinen
# Python-App, gilt aber unverändert für die Swift-Hülle).
# dist/LocalFlow.app: NICHT von diesem Skript gebaut, sondern ein Nebenprodukt
# von Schritt 1 — packaging/LocalFlow.spec definiert in EINER Datei sowohl das
# alte Vollständig-App-Ziel ("LocalFlow", Menüleiste inklusive) als auch das
# hier genutzte Engine-Ziel ("LocalFlow-Engine"); PyInstaller baut beim Lauf
# gegen die Spec-Datei IMMER beide. Muss mit aufgeräumt werden, sonst bleibt
# genau diese alte Kopie als zweiter "LocalFlow"-Treffer liegen (am 2026-07-19
# selbst darüber gestolpert, nachdem sie unbemerkt automatisch gestartet war).
rm -rf swift/build dist/LocalFlow-Engine dist/LocalFlow.app dist/LocalFlow

SIZE="$(du -h "$DMG" | cut -f1)"
echo "✅ Fertig: $DMG  ($SIZE)"
echo "   (Build-Ordner entfernt — verhindert doppelte Berechtigungs-Einträge)"
