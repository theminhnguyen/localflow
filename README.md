# LocalFlow 🎙️

**Diktier-App wie [Wispr Flow](https://wisprflow.ai) — aber 100 % lokal, kostenlos und offline.**
Deine Stimme wird direkt auf deinem Mac zu Text (Whisper), nichts geht ins Internet,
kein Abo, kein Konto.

- **Am Mac:** Taste halten, sprechen, loslassen → der Text erscheint an der Cursor-Position, in **jeder** App.
- **Am iPhone:** Web-App im Heim-WLAN — großer Aufnahme-Knopf, Text zum Kopieren.

---

## Was es kann

| Feature | LocalFlow |
|---|---|
| Systemweites Diktieren am Mac | ✅ Taste halten & sprechen |
| Lokale Spracherkennung | ✅ Whisper (`large-v3-turbo`) auf Apple-Silicon-GPU |
| Deutsch + 90 Sprachen | ✅ automatische Erkennung oder fest wählbar |
| Füllwörter entfernen (ähm, äh…) | ✅ |
| Persönliches Wörterbuch | ✅ Eigennamen/Korrekturen |
| Text-Snippets per Sprache | ✅ „Snippet Gruß" → ganzer Baustein |
| iPhone-App | ✅ als Web-App (PWA), kein App Store nötig |
| Kosten / Internet | **0 € / offline** (Wispr Flow: 15 $/Monat + Cloud) |

## Voraussetzungen

- Mac mit Apple Silicon (M1/M2/M3/M4) — getestet auf **M1 Pro**
- macOS mit Homebrew-Python 3.12 (`/opt/homebrew/bin/python3.12`)
- Für die iPhone-App: Handy im **gleichen WLAN** wie der Mac

## Installation & Start

```bash
cd ~/Downloads/localflow
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m localflow.main
```

Oder einfach **`start.command` im Finder doppelklicken**.

Beim allerersten Start lädt Whisper einmalig das Modell (~1,6 GB) herunter.

### macOS-Berechtigungen (einmalig)

LocalFlow läuft im Terminal, darum braucht **Terminal** (bzw. dein Terminal-Programm)
unter *Systemeinstellungen → Datenschutz & Sicherheit*:

1. **Mikrofon** — Popup erscheint beim ersten Diktat automatisch.
2. **Bedienungshilfen** — damit der Text per ⌘V eingefügt werden kann.
3. **Eingabemonitoring** — damit die Diktier-Taste erkannt wird.

Im Menü *🎙 → Berechtigungen prüfen* siehst du den Status und kannst die Dialoge auslösen.
Nach dem Erteilen LocalFlow **einmal neu starten**.

## Bedienung am Mac

- **Rechte Options-Taste (⌥) gedrückt halten**, sprechen, **loslassen**.
- Der erkannte Text wird an der aktuellen Cursor-Position eingefügt.
- Status in der Menüleiste: 🎙 bereit · 🔴 nimmt auf · ⏳ transkribiert.

Die Taste lässt sich in `~/.localflow/config.json` ändern
(`"hotkey": "alt_r"` → z. B. `"cmd_r"`, `"ctrl_r"`, `"f13"`).

## iPhone-App einrichten

1. LocalFlow am Mac starten.
2. Menüleiste *🎙 → 📱 Handy koppeln → QR-Code anzeigen*.
3. QR mit der iPhone-Kamera scannen → Safari öffnet `https://<Mac-IP>:8790`.
4. Beim selbstsignierten Zertifikat auf **„Erweitert → Trotzdem fortfahren"** tippen
   (nötig, weil Safari für Mikrofon-Zugriff HTTPS verlangt).
5. In Safari über *Teilen → „Zum Home-Bildschirm"* als App ablegen.
6. Großen Knopf tippen, sprechen, erneut tippen → Text kommt zurück, „Kopieren".

Die Transkription läuft dabei **auf dem Mac**, nicht auf dem Handy.

## Anpassen

Alle Nutzerdaten liegen in `~/.localflow/`:

- `config.json` — Modell, Sprache, Hotkey, Einfüge-Modus, Stille-Schwelle.
- `dictionary.json` — `terms` (Erkennungs-Hinweise) & `corrections` (Ersetzungen).
- `snippets.json` — Sprachbefehl → Textbaustein.

Im Menü direkt über *Wörterbuch bearbeiten* / *Snippets bearbeiten* erreichbar.

## Tests

```bash
.venv/bin/python -m pytest tests/test_cleanup.py tests/test_audio.py -q   # schnell
.venv/bin/python -m pytest tests/test_e2e.py -q -s                        # mit Modell
```

Der E2E-Test spricht Sätze über die macOS-Stimme „Anna" ein und prüft die Erkennung.

## Wie es funktioniert

```
Mac:   ⌥-Taste ──► Mikrofon (16 kHz) ──► Whisper (mlx) ──► Cleanup ──► ⌘V an Cursor
Handy: Knopf ──► Aufnahme ──► HTTPS-Upload ──► (Mac) Whisper ──► Cleanup ──► Text zurück
```

- **Engine:** `mlx-whisper` nutzt die GPU des Apple-Chips → schneller als Echtzeit.
- **Einfügen:** Zwischenablage sichern → Text setzen → ⌘V → Zwischenablage zurück.
- **Stille-Schutz:** Zu leise Aufnahmen werden verworfen (Whisper halluziniert sonst Text).
- **Server:** Flask über HTTPS (selbstsigniert) nur im lokalen Netz.

## Grenzen (bewusst nicht in v1)

- Keine LLM-Umformulierung („mach das förmlicher") — ließe sich später via lokalem
  Ollama ergänzen.
- Kein echtes iOS-Keyboard (bräuchte Apple-Developer-Account) — daher die PWA.
- Nur macOS (Apple Silicon), kein Windows.

## Lizenz

MIT — siehe [LICENSE](LICENSE).
