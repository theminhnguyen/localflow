# LocalFlow — Plan

> Nachbau der Kern-Features von **Wispr Flow** als komplett **lokale, kostenlose** App
> für Mac + iPhone. Keine Cloud, kein Abo, keine Daten verlassen den Rechner.

## Was Wispr Flow macht (Recherche-Ergebnis)

- **Systemweites Diktieren am Mac:** Hotkey gedrückt halten (Standard: `fn`),
  sprechen, loslassen → der Text erscheint direkt an der Cursor-Position, in
  jeder App (Mail, Slack, Browser, …).
- **KI-Bereinigung:** Füllwörter („ähm", „äh") werden entfernt, Zeichensetzung
  und Groß-/Kleinschreibung automatisch gesetzt, Listen formatiert.
- **Persönliches Wörterbuch:** Eigennamen und Fachbegriffe werden gelernt und
  korrekt geschrieben.
- **Voice-Snippets:** Kurze Sprachbefehle fügen vordefinierte Textbausteine ein.
- **iPhone:** Eigene App mit Diktier-Screen (kein System-Keyboard nötig).
- **Wichtig:** Wispr Flow braucht Internet — alles läuft über deren Cloud-Server
  (15 $/Monat).

## Unser Ansatz: 100 % lokal & kostenlos

| Wispr Flow | LocalFlow |
|---|---|
| Cloud-Spracherkennung | **Whisper lokal** auf dem M1 Pro (Apple-Silicon-optimiert via MLX) |
| Abo 15 $/Monat | kostenlos, Open Source |
| Internet nötig | läuft offline (Modell wird einmalig geladen) |
| iPhone-App aus dem App Store | **Web-App (PWA)** vom Mac aus im Heim-WLAN — kein Apple-Developer-Account nötig |

## Architektur

Ein Python-Prozess auf dem Mac, drei Bausteine:

```
┌─────────────────────────── LocalFlow (Mac) ───────────────────────────┐
│  Menüleisten-App (🎙️ Status, Einstellungen, Handy-Kopplung)           │
│                                                                        │
│  Hotkey-Listener ── Rechte ⌥-Taste halten = aufnehmen                  │
│        │                                                               │
│  Mikrofon-Aufnahme (16 kHz PCM)                                        │
│        │                                                               │
│  Whisper-Engine (mlx-whisper, large-v3-turbo) ← auch vom Handy genutzt │
│        │                                                               │
│  Cleanup-Pipeline (Füllwörter, Wörterbuch, Snippets)                   │
│        │                                                               │
│  Text-Einfügen: Zwischenablage sichern → Text → ⌘V → wiederherstellen  │
│                                                                        │
│  HTTPS-Server (Flask, Port 8790) ──────────► iPhone-PWA im WLAN        │
└────────────────────────────────────────────────────────────────────────┘
```

### iPhone-Teil (PWA)

- Safari öffnet `https://<Mac-IP>:8790` (QR-Code aus der Menüleiste).
- Großer Push-to-Talk-Button → Aufnahme (MediaRecorder) → Upload an den Mac →
  Whisper transkribiert lokal → Text kommt zurück, mit Kopieren-Button + Verlauf.
- „Zum Home-Bildschirm hinzufügen" = fühlt sich wie eine App an.
- Selbstsigniertes Zertifikat (einmalig in Safari bestätigen), da Mikrofon-Zugriff
  HTTPS verlangt.

## Kern-Features v1

1. ✅ Hold-to-talk am Mac (rechte Option-Taste), Text landet an der Cursor-Position
2. ✅ Lokale Transkription (Deutsch + 90 weitere Sprachen, automatische Erkennung)
3. ✅ Cleanup: Füllwörter raus (ähm/äh/uh/um…), sauberer Satzanfang
4. ✅ Persönliches Wörterbuch (`~/.localflow/dictionary.json`) — korrigiert
   Schreibweisen und hilft Whisper bei Eigennamen
5. ✅ Snippets (`~/.localflow/snippets.json`) — „Snippet Gruß" → ganzer Textbaustein
6. ✅ Menüleisten-App mit Status, Sprache, Verlauf, Handy-Kopplung per QR-Code
7. ✅ iPhone-PWA mit Push-to-talk, Kopieren-Button, Verlauf

### Bewusst NICHT in v1 (später möglich)

- LLM-basierte Umformulierung („mach das förmlicher") → könnte später via Ollama
  lokal ergänzt werden
- Selbstkorrektur-Erkennung („um 2… nein 3 Uhr")
- Echtes iOS-Custom-Keyboard (bräuchte Apple-Developer-Account, 99 $/Jahr)
- Windows-Support

## Technik-Entscheidungen

- **Python 3.12** (Homebrew) in eigenem venv — System-Python 3.9 ist zu alt.
- **mlx-whisper + whisper-large-v3-turbo** (~1,6 GB, einmaliger Download):
  Apple-Silicon-GPU, deutlich schneller als Echtzeit auf dem M1 Pro, sehr gute
  deutsche Qualität. Konfigurierbar auf kleinere Modelle.
- **Audio-Dekodierung** der Handy-Uploads über macOS-eigenes `afconvert`
  (kein ffmpeg nötig); ffmpeg als optionaler Fallback.
- **rumps** für die Menüleiste, **pynput** für den globalen Hotkey,
  **sounddevice** für die Aufnahme, **Flask** für den Server.
- Einfügen per Zwischenablage + simuliertem ⌘V (Zwischenablage wird danach
  wiederhergestellt).

## Einmalige macOS-Berechtigungen (musst du klicken)

Die App läuft im Terminal, daher braucht **Terminal** in
Systemeinstellungen → Datenschutz & Sicherheit:
1. **Mikrofon** (Popup erscheint automatisch beim ersten Diktat)
2. **Bedienungshilfen** + **Eingabemonitoring** (für Hotkey & ⌘V)

## Tests (automatisiert, ohne Mikrofon)

- End-to-End: macOS-Stimme „Anna" synthetisiert deutsche Testsätze → WAV →
  Whisper → Prüfung, ob der Text stimmt.
- Unit-Tests für die Cleanup-Pipeline (Füllwörter, Wörterbuch, Snippets).
- Server-Test: Audio-Upload per HTTP → korrekte Antwort.
- PWA: Seite lädt, kein JS-Fehler.

## Meilensteine

1. Projekt + Umgebung + Modell-Download
2. Engine + Cleanup + Tests grün
3. Server + PWA + Tests grün
4. Hotkey + Einfügen + Menüleiste
5. End-to-End-Prüfung, README, GitHub-Push
