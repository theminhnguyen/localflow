# Changelog

Alle nennenswerten Änderungen an LocalFlow. Format angelehnt an
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), Versionierung an
[Semantic Versioning](https://semver.org/). Die automatisch generierten Notes
jedes [GitHub-Release](https://github.com/theminhnguyen/localflow/releases)
sind die technische Rohfassung — hier die kuratierte Sicht.

## [1.0.0] — 2026-07-19

### Changed
- **Native Swift-App löst die reine Python-Menüleisten-App ab.** LocalFlow
  läuft jetzt als echte, kleine Swift-App (Menüleiste, Hotkey, Aufnahme,
  Einfügen), die Whisper/Cleanup/KI-Feinschliff weiterhin über eine
  gebündelte, gleich mitgelieferte Python-Engine erledigt — für dich als
  Nutzer:in ändert sich an der Bedienung nichts (gleiche Bundle-Identität,
  gleicher Port, gleiche Systemrechte). Grund: spürbar schnellerer Start,
  robusteres Hotkey-Handling, natives macOS-Verhalten (z. B. Autostart über
  die offizielle Login-Item-API statt eines selbstgebauten LaunchAgents).
- Menü um Sprache-, Verlauf- und Diagnose-Status-Untermenüs ergänzt (volle
  Parität zur bisherigen Python-Menüleiste), dazu QR-Kopplung, Datei-
  Transkription und Update-Check nativ in der neuen App.

## [0.6.1] — 2026-07-19

### Added
- **Vorwärmen gegen langsame Diktate nach einer Pause.** Nach längerem Nicht-
  Diktieren (z. B. der Mac schlief zwischenzeitlich) dauerte das erste Diktat
  3-5x so lange wie gewohnt (gemessen: 5202ms statt 1008ms) — die GPU-Kernel
  kühlen aus. LocalFlow wärmt sie jetzt beim Drücken der Diktier-Taste im
  Hintergrund vor, während man spricht, sodass die eigentliche Transkription
  beim Loslassen schon heiße Kernel vorfindet. Neuer Endpunkt `/api/prewarm`
  für die Swift-Hülle, die den Hotkey selbst abfängt.

### Fixed
- **Sicherheit:** `/api/insert` (Fallback-Einfügeweg für die Swift-Hülle)
  respektiert jetzt den „Handy darf einfügen"-Schalter — vorher konnte ihn
  jedes Gerät im WLAN mit gültigem Kopplungs-Token umgehen. Aufrufe vom Mac
  selbst (die Swift-Hülle) sind davon unabhängig weiter erlaubt.
- **Zwischenablage-Wiederherstellung bei Serien-Diktaten:** Der verzögerte
  Restore nach dem Einfügen (0,6s) konnte bei zwei schnell aufeinander-
  folgenden Diktaten genau zwischen „Zwischenablage = Text 2" und dem
  simulierten ⌘V feuern — eingefügt wurde dann die alte Zwischenablage statt
  des zweiten Diktats. Der Restore ist jetzt abbrechbar (Python + Swift).
- **Swift-Hülle:** Stürzt die Engine ab, startet sie jetzt automatisch neu
  (Backoff 1s/5s/15s statt dauerhaft "Fehler" in der Menüleiste); ein
  Datenrennen beim zuletzt eingefügten Text (fürs Menü) behoben.

## [0.6.0] — 2026-07-17

### Added
- **Leerzeichen zwischen aufeinanderfolgenden Diktaten.** Diktierte man zweimal
  hintereinander in dieselbe Zeile, klebten die Texte aneinander
  („HalloWie geht's"). LocalFlow fragt jetzt über die Bedienungshilfen-
  Schnittstelle das Zeichen direkt vor dem Cursor ab und setzt nur dann ein
  Leerzeichen, wenn dort wirklich Text steht — am Zeilenanfang und nach einem
  Absatz bleibt es aus, vor Satzzeichen („, oder?") ebenfalls. Gibt die Ziel-App
  keine Auskunft, bleibt es beim bisherigen Verhalten. Gilt auch fürs
  iPhone-Diktat, das denselben Einfügeweg nutzt.

## [0.5.4] — 2026-07-15

### Fixed
- **Umlaute wurden beim Einfügen manchmal zu Kauderwelsch.** Diktierter Text mit
  ä/ö/ü/ß kam bei einer per synthetischem ⌘V ausgelösten Einfüge-Aktion in der
  Ziel-App manchmal als Mojibake an ("√Ñ" statt "Ä"), obwohl die Zwischenablage
  selbst beim direkten Auslesen (`pbpaste`) korrekt war — die Ziel-App las
  offenbar eine andere, vom System automatisch mit-erzeugte Zwischenablage-
  Variante als LocalFlows synthetisches ⌘V. Behoben, indem die Zwischenablage
  jetzt direkt über die native `NSPasteboard`-API (statt über die
  `pbcopy`/`pbpaste`-Kommandozeilen-Werkzeuge) gesetzt und gelesen wird — der
  Weg, den auch echte Mac-Apps selbst nutzen. Betraf sowohl das Diktat-
  Einfügen als auch "Verlauf kopieren" und "Letztes Diktat kopieren" im Menü.

### Added (Vorarbeit Phase 3 — native Swift-Hülle)
- `--serve-only`-Engine-Modus reagiert jetzt sauber auf SIGTERM (nötig, damit
  eine künftige Swift-App den Python-Dienst kontrolliert beenden kann).
- Neuer Endpunkt `POST /api/insert` (Token-geschützt): fügt gelieferten Text
  über den bewährten Weg ein — Fallback, falls natives Einfügen mal nicht greift.

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
