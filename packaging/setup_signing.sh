#!/bin/bash
# Richtet die STABILE Code-Signatur für LocalFlow ein (einmalig auszuführen):
#
#   bash packaging/setup_signing.sh
#
# WARUM: Ohne bezahltes Apple-Zertifikat wird die App "ad-hoc" signiert. macOS
# merkt sich Bedienungshilfen-/Eingabemonitoring-Rechte dann an der PRÜFSUMME der
# Programmdatei, die sich bei jedem Build ändert -> nach jedem Update sind die
# Berechtigungen kaputt (Häkchen an, aber wirkungslos).
#
# Mit einem eigenen (selbst-signierten, kostenlosen) Zertifikat ist die
# "Designated Requirement" der App stabil:
#     identifier "studio.minh.localflow" and certificate root = H"<fix>"
# -> macOS erkennt die App über Zertifikat + Bundle-ID wieder, die Rechte
# überleben Updates.
#
# Alles läuft in einem EIGENEN Schlüsselbund mit zufällig erzeugtem, nur lokal
# gespeichertem Passwort — der Anmelde-Schlüsselbund und das Login-Passwort
# werden NICHT angefasst, es erscheint keine Passwort-Abfrage.
set -euo pipefail

cd "$(dirname "$0")/.."
SIGN_DIR="packaging/signing"
CRT="$SIGN_DIR/localflow-codesign.crt"
KEY="$SIGN_DIR/localflow-codesign.key"
P12="$SIGN_DIR/localflow-codesign.p12"
IDENTITY="LocalFlow Code Signing"
KC="$HOME/Library/Keychains/localflow-signing.keychain-db"

# Passwörter werden zufällig erzeugt und NUR lokal abgelegt (gitignored) —
# nie als Klartext in ein Skript schreiben, das ins öffentliche Repo geht.
P12_PASS_FILE="$SIGN_DIR/.p12_pass"
KC_PASS_FILE="$SIGN_DIR/.keychain_pass"
[ -f "$P12_PASS_FILE" ] || { umask 077; openssl rand -hex 24 > "$P12_PASS_FILE"; }
[ -f "$KC_PASS_FILE" ] || { umask 077; openssl rand -hex 24 > "$KC_PASS_FILE"; }
P12_PASS="$(cat "$P12_PASS_FILE")"
KC_PASS="$(cat "$KC_PASS_FILE")"

# p12 bei Bedarf aus crt+key erzeugen (nur das öffentliche crt liegt im Repo;
# key/p12 sind gitignored und werden lokal (neu) erstellt).
if [ ! -f "$P12" ]; then
  [ -f "$CRT" ] && [ -f "$KEY" ] || { echo "✗ Zertifikat/Schlüssel fehlen in $SIGN_DIR"; exit 1; }
  openssl pkcs12 -export -inkey "$KEY" -in "$CRT" -out "$P12" \
    -name "$IDENTITY" -passout pass:"$P12_PASS" -legacy
fi

echo "▸ Eigenen Signatur-Schlüsselbund anlegen…"
security delete-keychain "$KC" 2>/dev/null || true
security create-keychain -p "$KC_PASS" "$KC"
security set-keychain-settings "$KC"            # kein Auto-Lock
security unlock-keychain -p "$KC_PASS" "$KC"

echo "▸ Zertifikat importieren…"
security import "$P12" -k "$KC" -P "$P12_PASS" -T /usr/bin/codesign -A

echo "▸ codesign-Zugriff freischalten (kein interaktiver Dialog)…"
security set-key-partition-list -S apple-tool:,apple:,codesign: \
  -s -k "$KC_PASS" "$KC" >/dev/null 2>&1 || true

echo "▸ Schlüsselbund in die Suchliste aufnehmen…"
EXISTING="$(security list-keychains -d user | sed 's/[\" ]//g' | tr '\n' ' ')"
# shellcheck disable=SC2086
security list-keychains -d user -s "$KC" $EXISTING

# Praxistest: lässt sich damit wirklich signieren?
TMP="$(mktemp)"; cp /bin/echo "$TMP"
if codesign --force --sign "$IDENTITY" --keychain "$KC" -i studio.minh.localflow "$TMP" 2>/dev/null \
   && codesign -dvv "$TMP" 2>&1 | grep -q "Authority=$IDENTITY"; then
  echo "✅ Signatur-Identität '$IDENTITY' ist einsatzbereit."
  echo "   build_dmg.sh signiert die App ab jetzt automatisch damit."
  echo "   -> Berechtigungen einmal neu erteilen, danach überstehen sie Updates."
else
  echo "⚠️  Signieren mit der Identität fehlgeschlagen — build_dmg.sh nutzt weiter ad-hoc."
  rm -f "$TMP"; exit 1
fi
rm -f "$TMP"
