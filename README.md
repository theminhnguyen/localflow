# LocalFlow 🎙️

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
| ✨ KI-Feinschliff | ✅ lokales LLM (Ollama): Versprecher raus, Listen formatieren |
| Füllwörter entfernen (ähm, äh…) | ✅ regelbasiert, immer aktiv |
| Persönliches Wörterbuch & Snippets | ✅ |
| iPhone als Fernmikrofon | ✅ „→ Mac": Text landet am Mac-Cursor |
| Audiodateien transkribieren | ✅ Sprachmemo/Meeting → Textdatei |
| Unterwegs diktieren | ✅ automatisch, wenn Tailscale installiert ist |
| Autostart beim Anmelden | ✅ abschaltbar |
| Diagnose & Log | ✅ Menü „🩺 Diagnose" |
| Kosten / Internet | **0 € / offline** (Wispr Flow: 15 $/Monat + Cloud) |

Alle Funktionen sind unter **⚙️ Einstellungen** im Menüleisten-Menü einzeln an-/abschaltbar.

## Voraussetzungen

- Mac mit Apple Silicon (M1/M2/M3/M4) — getestet auf **M1 Pro**
- macOS mit Homebrew-Python 3.12 (`/opt/homebrew/bin/python3.12`)
- Für die iPhone-App: Handy im **gleichen WLAN** wie der Mac (oder Tailscale auf beiden)
- Optional für den KI-Feinschliff: ein lokales LLM über **LM Studio** *oder* **Ollama**
  (z. B. ein Gemma-Modell) — LocalFlow erkennt automatisch, was läuft

## Installation & Start

```bash
cd ~/Downloads/localflow
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m localflow.main
```

Bequemer: **LocalFlow.app** (im Programme-Ordner) — startet ohne Terminal-Fenster,
nur das 🎙 in der Menüleiste. Beim allerersten Start lädt Whisper einmalig das
Modell (~1,6 GB).

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

Unter *Systemeinstellungen → Datenschutz & Sicherheit* braucht **LocalFlow**:

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

Diktier-Taste, Whisper-Modell und alle Feature-Schalter: Menü **⚙️ Einstellungen**.

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

- `config.json` — alle Schalter (auch per ⚙️-Menü bedienbar)
- `dictionary.json` — `terms` (Erkennungs-Hinweise) & `corrections` (Ersetzungen)
- `snippets.json` — Sprachbefehl → Textbaustein („Snippet Gruß")
- `logs/localflow.log` — Diagnose-Log (Menü *🩺 → Log-Datei öffnen*)

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

## Lizenz

MIT — siehe [LICENSE](LICENSE).
