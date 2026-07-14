# LocalFlow 🎙️

[![CI](https://github.com/theminhnguyen/localflow/actions/workflows/ci.yml/badge.svg)](https://github.com/theminhnguyen/localflow/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/theminhnguyen/localflow?label=release)](https://github.com/theminhnguyen/localflow/releases/latest)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

*[Read this in English](README.md)*

**Diktier-App wie [Wispr Flow](https://wisprflow.ai) — aber 100 % lokal, kostenlos und offline.**
Deine Stimme wird direkt auf deinem Mac zu Text (Whisper), nichts geht ins Internet,
kein Abo, kein Konto.

- **Am Mac:** Taste halten, sprechen, loslassen → der Text erscheint an der Cursor-Position, in **jeder** App.
- **Am iPhone:** Web-App im Heim-WLAN — Aufnahme-Knopf, Text zum Kopieren **oder direkt an den Mac-Cursor**.

---

## Was es kann

| Feature | LocalFlow |
|---|---|
| Systemweites Diktieren am Mac | ✅ Taste halten & sprechen |
| Freihand-Modus | ✅ Taste doppelt antippen = Aufnahme rastet ein |
| Lokale Spracherkennung | ✅ Whisper (`large-v3-turbo`) auf Apple-Silicon-GPU |
| Deutsch + 90 Sprachen | ✅ automatische Erkennung oder fest wählbar |
| ✨ KI-Feinschliff | ✅ lokales LLM (LM Studio/Ollama): Versprecher raus, Listen formatieren |
| Füllwörter entfernen (ähm, äh…) | ✅ regelbasiert, immer aktiv |
| Persönliches Wörterbuch & Snippets | ✅ |
| iPhone als Fernmikrofon | ✅ „→ Mac": Text landet am Mac-Cursor |
| Audiodateien transkribieren | ✅ Sprachmemo/Meeting → Textdatei |
| Unterwegs diktieren | ✅ automatisch, wenn Tailscale installiert ist |
| Autostart beim Anmelden | ✅ abschaltbar |
| Einrichtungs-Assistent | ✅ führt beim ersten Start durch alle Schritte |
| Web-Einstellungsseite | ✅ auch vom iPhone erreichbar |
| Update-Check | ✅ still, täglich, kein Auto-Download — abschaltbar |
| Diagnose & Log | ✅ Menü „🩺 Diagnose" |
| Kosten / Internet | **0 € / offline** (Wispr Flow: 15 $/Monat + Cloud) |

Alle Funktionen sind unter **⚙️ Einstellungen** (Menü oder [Web-Seite](#einstellungen-anpassen)) einzeln an-/abschaltbar.

## Voraussetzungen

- Mac mit Apple Silicon (M1/M2/M3/M4) — getestet auf **M1 Pro**
- macOS mit Homebrew-Python 3.12 (`/opt/homebrew/bin/python3.12`)
- Für die iPhone-App: Handy im **gleichen WLAN** wie der Mac (oder Tailscale auf beiden)
- Optional für den KI-Feinschliff: ein lokales LLM über **LM Studio** *oder* **Ollama**
  (z. B. ein Gemma-Modell) — LocalFlow erkennt automatisch, was läuft

## Installation

### Einfach: DMG (empfohlen)

1. Neueste Version von der **[Releases-Seite](https://github.com/theminhnguyen/localflow/releases/latest)**
   herunterladen (`LocalFlow-x.y.z.dmg`) — wird bei jedem Versions-Tag automatisch gebaut.
2. DMG öffnen, **LocalFlow** auf den **Programme**-Ordner ziehen.
3. In *Programme* LocalFlow per **Rechtsklick → Öffnen** starten (nur beim ersten
   Mal — die App ist frei/ohne bezahltes Apple-Zertifikat signiert).
4. Ein **Einrichtungs-Assistent** führt dich durch Mikrofon-Zugriff, die beiden
   nötigen Berechtigungen (inkl. automatischem Neustart, sobald sie erteilt sind)
   und lädt das Whisper-Modell mit Fortschrittsanzeige — danach bist du startklar.

Die App bringt Python und alle Bibliotheken selbst mit — keine weitere Installation
nötig. Der Assistent lässt sich jederzeit erneut starten: Menü *🩺 Diagnose →
„Einrichtung erneut starten"*.

**DMG selbst bauen:** `bash packaging/build_dmg.sh` → `dist/LocalFlow-x.y.z.dmg`.

### Für Entwickler: aus dem Quellcode

```bash
cd ~/Downloads/localflow
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m localflow.main
```

### KI-Feinschliff einrichten (optional, empfohlen)

Ein lokales Sprachmodell verbessert jedes Diktat: Selbstkorrekturen
(„um 2 … nein, 3 Uhr") werden aufgelöst, gesprochene Aufzählungen als Liste
formatiert, Grammatik geglättet. LocalFlow erkennt **automatisch** eines von zwei
Backends — ohne LLM läuft alles normal weiter (nur Regel-Cleanup).

**Variante A — LM Studio** (grafisch, einfach):
1. [LM Studio](https://lmstudio.ai) öffnen, ein Chat-Modell laden (z. B. Gemma).
2. Tab *Developer* → *Local Server* → **Start** (läuft auf Port 1234).

**Variante B — Ollama** (Kommandozeile):
```bash
brew install ollama
brew services start ollama
ollama pull gemma3:4b
```

Das Backend lässt sich in `~/.localflow/config.json` festlegen
(`"llm_backend"`: `"auto"` | `"lmstudio"` | `"ollama"`), `"llm_model"` ist ein
Teilstring-Wunsch (z. B. `"gemma"`, leer = erstes geladenes Modell).

### macOS-Berechtigungen (einmalig)

Der Einrichtungs-Assistent stößt das automatisch an. Manuell unter
*Systemeinstellungen → Datenschutz & Sicherheit* braucht **LocalFlow**:

1. **Mikrofon** — Popup erscheint beim ersten Diktat automatisch.
2. **Bedienungshilfen** — damit der Text per ⌘V eingefügt werden kann.
3. **Eingabemonitoring** — damit die Diktier-Taste erkannt wird.

Im Menü *🩺 Diagnose → Berechtigungen prüfen* siehst du den Status.
Nach dem Erteilen LocalFlow **einmal neu starten**.

## Bedienung am Mac

- **Rechte Options-Taste (⌥) gedrückt halten**, sprechen, **loslassen** → Text
  erscheint an der Cursor-Position.
- **Freihand:** ⌥ **doppelt antippen** → Aufnahme rastet ein (Glas-Ton), beliebig
  lange sprechen, einmal antippen → fertig.
- Du kannst sofort das nächste Diktat beginnen, während das vorige noch
  verarbeitet wird — die Texte werden in der richtigen Reihenfolge eingefügt.
- Status in der Menüleiste: 🎙 bereit · 🔴 nimmt auf · ⏳ transkribiert.
- **Audiodatei transkribieren…** im Menü: wandelt Sprachmemos/Meetings in eine
  Textdatei um (liegt danach neben der Originaldatei).

## Einstellungen anpassen

Zwei Wege, alle Schalter zu erreichen:

- **Menü** (🎙 → ⚙️ Einstellungen) — schnell, direkt in der Menüleiste.
- **Web-Seite** (🎙 → ⚙️ Einstellungen → „Einstellungen im Browser öffnen…") —
  übersichtlicher, funktioniert auch **vom iPhone aus** (gleicher Link wie die
  Diktier-App, siehe unten). Änderungen wirken sofort, kein Neustart nötig.

## iPhone einrichten

1. LocalFlow am Mac starten.
2. Menüleiste *🎙 → 📱 Handy koppeln → QR-Code anzeigen*.
3. QR mit der iPhone-Kamera scannen → Safari öffnet `https://<Mac-IP>:8790`.
4. Zertifikat-Warnung: **„Details einblenden → Website besuchen"** (selbstsigniert,
   nötig weil Safari fürs Mikrofon HTTPS verlangt).
5. *Teilen → „Zum Home-Bildschirm"* = wie eine echte App.

**Fernmikrofon:** Chip **„→ Mac"** aktivieren → der diktierte Text erscheint sofort
an der Cursor-Position deines Macs. (Abschaltbar unter ⚙️ Einstellungen.)

**Unterwegs:** Ist [Tailscale](https://tailscale.com) (Gratis-Plan) auf Mac + iPhone
eingerichtet, erscheint im Koppeln-Menü automatisch ein zweiter QR-Code — damit
funktioniert das Handy-Diktat von überall, solange der Mac läuft.

## Anpassen

Alle Nutzerdaten liegen in `~/.localflow/`:

- `config.json` — alle Schalter (auch per ⚙️-Menü/Web-Seite bedienbar)
- `dictionary.json` — `terms` (Erkennungs-Hinweise) & `corrections` (Ersetzungen)
- `snippets.json` — Sprachbefehl → Textbaustein („Snippet Gruß")
- `secret.token` — Kopplungs-Token fürs Handy (chmod 600, siehe „iPhone einrichten")
- `history.json` — die letzten Diktate (Menü *Verlauf*; „Verlauf leeren" löscht alles)
- `onboarded` — Marker, dass der Einrichtungs-Assistent durchgelaufen ist
- `logs/localflow.log` — Diagnose-Log (Menü *🩺 → Log-Datei öffnen*)

## Datenschutz

LocalFlow verarbeitet deine Stimme ausschließlich lokal — Whisper und das
optionale LLM laufen auf deinem Mac, es gibt keine Cloud-Aufrufe.

- **Diktattexte landen standardmäßig NICHT im Log** — nur „[N Zeichen]" ohne
  Inhalt. Zum Debuggen einschaltbar: ⚙️ → „📝 Diktattexte ins Log schreiben".
- **Verlauf** (letzte Diktate, für Menü + Handy) liegt nur lokal in
  `~/.localflow/history.json`. Jederzeit löschbar über *Verlauf → Verlauf
  leeren*, oder ganz abschaltbar mit `"history_keep": 0` in `config.json`.
- **Einzige Netzwerkzugriffe:** der einmalige Whisper-Modell-Download beim
  ersten Diktat und — falls aktiviert — der Update-Check gegen die
  GitHub-Releases-API (⚙️ → „🔄 Auf Updates prüfen", abschaltbar).
- Das **Kopplungs-Token** fürs Handy schützt `/api/*` vor Fremdzugriff im
  selben WLAN (siehe „iPhone einrichten"). Bei Verdacht auf Missbrauch:
  Menü → *📱 Handy koppeln → Kopplung zurücksetzen…*.

## Tests

```bash
.venv/bin/python -m pytest tests/ -q --ignore=tests/test_e2e.py   # schnell
.venv/bin/python -m pytest tests/test_e2e.py -q -s                # mit Modell
```

## Wie es funktioniert

```
Mac:   ⌥ ──► Mikrofon ──► Whisper (mlx) ──► Regel-Cleanup ──► ✨ LLM ──► ⌘V an Cursor
Handy: Knopf ──► HTTPS-Upload ──► (Mac) Whisper ──► Cleanup ──► zurück ODER an Mac-Cursor
```

- **Robustheit:** Aufnehmen und Verarbeiten sind entkoppelt (Warteschlange,
  Reihenfolge bleibt erhalten). Ein Wächter erkennt verlorene Tasten-Ereignisse
  und rettet die Aufnahme — nichts bleibt hängen.
- **Einfügen:** wartet, bis keine Modifier-Taste mehr gedrückt ist, setzt die
  Zwischenablage, ⌘V, stellt die Zwischenablage wieder her.
- **Stille-Schutz:** Zu leise Aufnahmen werden verworfen (Whisper halluziniert sonst).
- **Privatsphäre:** Whisper UND das LLM laufen auf deinem Mac. Es gibt keinerlei
  Cloud-Aufrufe.

## Mitentwickeln

Siehe [CHANGELOG.md](CHANGELOG.md) für die Versionshistorie und
[docs/PLAN-PROFESSIONALISIERUNG.md](docs/PLAN-PROFESSIONALISIERUNG.md) für die
Roadmap. Pull Requests willkommen — `pytest tests/ -q --ignore=tests/test_e2e.py`
muss grün sein.

## Lizenz

MIT — siehe [LICENSE](LICENSE).
