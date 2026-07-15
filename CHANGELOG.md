# Changelog

Alle nennenswerten Änderungen an LocalFlow. Format angelehnt an
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), Versionierung an
[Semantic Versioning](https://semver.org/). Die automatisch generierten Notes
jedes [GitHub-Release](https://github.com/theminhnguyen/localflow/releases)
sind die technische Rohfassung — hier die kuratierte Sicht.

## [0.5.3] — 2026-07-15

### Fixed
- **Berechtigungen überlebten Updates nicht — jetzt schon.** Auch nach den
  Fixes in 0.5.2 gingen Bedienungshilfen-/Eingabemonitoring-Rechte nach dem
  nächsten Bau wieder verloren, obwohl das Häkchen aktiv aussah. Ursache: ohne
  bezahltes Apple-Zertifikat wird ad-hoc signiert, und macOS bindet diese
  Rechte dabei an die PRÜFSUMME der Programmdatei — die sich bei jedem Build
  ändert. Ab jetzt signiert LocalFlow mit einem eigenen, kostenlosen
  Code-Signing-Zertifikat (`packaging/setup_signing.sh`, einmalig lokal
  auszuführen). Damit bleibt die Signatur über Builds hinweg stabil, die
  Rechte überstehen künftige Updates. Fällt auf ad-hoc zurück, falls das
  Zertifikat nicht eingerichtet ist (z. B. auf frischen CI-Runnern).

## [0.5.2] — 2026-07-14

### Fixed
- **Einrichtungs-Assistent lief in einer Endlosschleife.** Nach dem Erteilen der
  Berechtigungen startete die App neu, begann den Assistenten aber von vorn —
  und die Häkchen schienen sich „von selbst auszuschalten". Drei Ursachen:
  1. `CGPreflight*Access()` meldet bei ad-hoc signierten Apps (ohne bezahltes
     Apple-Zertifikat) auch nach dem Setzen der Häkchen weiterhin `False` — der
     Wert ist pro Prozess gecacht. Der Assistent wartete darum endlos. Jetzt
     bricht er nach 45 s aus der Warteschleife aus und startet neu.
  2. Der „schon eingerichtet"-Marker wurde erst ganz am Ende geschrieben. Der
     Neustart-Schritt setzt ihn jetzt VOR dem Neustart — die frisch gestartete
     Instanz weiß dadurch Bescheid und beginnt nicht von vorn.
  3. Nach jedem DMG-Bau blieb eine zweite `LocalFlow.app` in `dist/` liegen.
     macOS bindet diese Rechte an den DATEIPFAD, listete beide Kopien getrennt
     auf — Häkchen bei der einen gesetzt, gestartet wurde die andere.
     `build_dmg.sh` räumt die Build-Kopie jetzt selbst weg.

### Added
- 🩺 Diagnose → „Berechtigungen prüfen" zeigt jetzt den Pfad der laufenden App
  und warnt explizit, wenn weitere LocalFlow-Kopien auf dem Mac gefunden werden.

## [0.5.1] — 2026-07-14

### Added
- Gestaltetes DMG-Hintergrundbild (Wortmarke, Pfeil zum Programme-Ordner) —
  vorher ein leeres Finder-Fenster, jetzt ein geführtes Installations-Layout
  im LocalFlow-Design. Erzeugt von `scripts/make_dmg_background.py`,
  automatisch per Finder-AppleScript in `packaging/build_dmg.sh` platziert.

## [0.5.0] — 2026-07-14

### Added
- Einrichtungs-Assistent beim allerersten Start (Mikrofon, Berechtigungen inkl.
  automatischem Neustart, Modell-Download mit Fortschrittsanzeige).
- Web-Einstellungsseite (`/settings`), auch vom iPhone erreichbar — Änderungen
  wirken sofort, kein Neustart nötig.
- Englisches README als Hauptsprache (`README.de.md` für die deutsche Fassung).

## [0.4.0] — 2026-07-14

### Added
- **Kopplungs-Token** für alle `/api/*`-Endpunkte — schließt die Sicherheitslücke,
  durch die jedes Gerät im selben WLAN unautorisiert Text am Mac einfügen konnte.
  Token steckt als URL-Fragment im QR-Code/Link, landet nie in Server-Logs.
- CI-Pipeline (GitHub Actions, macOS/arm64): Tests bei jedem Push.
- Release-Automatik: ein Versions-Tag baut automatisch die DMG und veröffentlicht
  sie als GitHub-Release.
- Stiller, täglicher Update-Check gegen die GitHub-Releases-API (abschaltbar,
  kein Auto-Download).
- Zentrale Versionsnummer (`localflow/__init__.py`) statt an drei Stellen hartcodiert.

### Changed
- Diktattexte landen standardmäßig **nicht mehr** im Log (nur Zeichenzahl) —
  einschaltbar zum Debuggen.
- Verlaufslänge konfigurierbar (`history_keep`), Verlauf/Log jederzeit über
  das Menü leerbar.

### Security
- Siehe „Kopplungs-Token" oben — die wichtigste Änderung dieser Version.

## [0.3.0] — 2026-07-13

### Added
- Eigenständiges PyInstaller-Bundle (`LocalFlow.app`) inkl. Drag-and-drop-DMG
  (`packaging/build_dmg.sh`) — bringt Python und alle Bibliotheken selbst mit,
  kein Homebrew/venv auf dem Zielrechner nötig.
- Menüleisten-Prozess heißt jetzt „LocalFlow" statt „Python" im App-Umschalter.

### Changed
- Kaltstart ~3× schneller: `turbo-q4`-Modell als Standard (identische Qualität,
  kleinerer Download), GPU-Kernel werden beim Start vorgewärmt.
- Wächter-Takt beschleunigt (80 ms) — das rote „Aufnahme läuft"-Icon blitzt bei
  einem verschluckten Tasten-Ereignis kaum noch auf.

### Fixed
- `multiprocessing`-Kindprozesse (numba/mlx) stürzten im gebündelten Build mit
  „unrecognized arguments" ab — behoben über `multiprocessing.freeze_support()`.

## [0.2.0] — 2026-07-11

### Added
- ✨ KI-Feinschliff über ein lokales LLM (LM Studio *oder* Ollama, automatisch
  erkannt): löst Selbstkorrekturen auf, formatiert gesprochene Aufzählungen.
- 🚀 Schnell-Modus: das LLM läuft nur, wenn der Text es braucht — spart bei
  kurzen, sauberen Diktaten spürbar Zeit.
- iPhone als Fernmikrofon („→ Mac"): diktierter Text landet direkt am Mac-Cursor.
- Audiodatei-Transkription (Sprachmemo/Meeting → Textdatei) aus dem Menü.
- Freihand-Modus (Taste doppelt antippen = Aufnahme rastet ein).
- Autostart beim Anmelden, Tailscale-Erkennung für Diktat unterwegs, geteilter
  Verlauf zwischen Mac und Handy, Diagnose-Menü mit Log-Zugriff.

### Fixed
- Serien-Diktate (schnell hintereinander) ließen die App gelegentlich mit
  dauerhaft rotem Icon hängen bleiben — Aufnehmen und Verarbeiten sind jetzt
  über eine Warteschlange entkoppelt, ein Wächter rettet verschluckte
  Tasten-Ereignisse.
- Whisper echote bei ruhigen Aufnahmen Teile des internen Erkennungs-Hinweises
  wörtlich in den Text (`initial_prompt`-Leck).

## [0.1.0] — 2026-07-09

### Added
- Erste Version: lokales Diktieren am Mac (Whisper via `mlx-whisper`, Taste
  halten & sprechen, Einfügen per ⌘V an der Cursor-Position).
- iPhone-Web-App (PWA) im Heim-WLAN als zweite Diktier-Oberfläche.
- Regelbasierte Textbereinigung (Füllwörter, Wörterbuch-Korrekturen, Snippets).
- Menüleisten-App mit Status, Sprachwahl, Verlauf, QR-Kopplung.
