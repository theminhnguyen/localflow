# LocalFlow — Professionalisierungs-Plan (v0.4 → v1.0)

> **Für die umsetzende Session (z. B. Sonnet 5):** Dieses Dokument ist die einzige
> Quelle, die du brauchst. Lies zuerst „Kontext & Ist-Zustand" und „Arbeitsregeln",
> dann setze die Phasen **in Reihenfolge** um. Jedes Arbeitspaket hat Design,
> betroffene Dateien, Tests und Abnahmekriterien. Erst wenn alle Kriterien eines
> Pakets erfüllt sind, geht es weiter.

---

## Kontext & Ist-Zustand (Stand v0.3.0, 2026-07-13)

**Produkt:** LocalFlow = lokale Diktier-App (Wispr-Flow-Ersatz). Taste halten →
Whisper (mlx, Apple-GPU) transkribiert lokal → Regel-Cleanup → optional LLM-Feinschliff
(LM Studio/Ollama, auto-erkannt) → Text landet per ⌘V an der Cursor-Position.
iPhone-PWA im WLAN als Fernmikrofon. Alles offline, keine Cloud.

**Orte:**
- Repo: `~/Downloads/localflow` (= GitHub `theminhnguyen/localflow`, public, Branch `main`)
- Installierte App: `/Applications/LocalFlow.app` — eigenständiges **PyInstaller-Bundle**
  (Binary „LocalFlow", Bundle-ID `studio.minh.localflow`, `LSUIElement=true`)
- Nutzerdaten: `~/.localflow/` (config.json, dictionary.json, snippets.json,
  history.json, logs/, certs/)
- DMG: `bash packaging/build_dmg.sh` → `dist/LocalFlow-<ver>.dmg` (~171 MB)

**Code-Landkarte (`localflow/`):**
| Datei | Zweck |
|---|---|
| `main.py` | `FlowController` (Zustands-Maschine: Aufnahme→Queue-Worker→Einfügen), Wächter-Thread (rettet verschluckte ⌥-Loslassen-Events via Quartz-Tastenstatus), Sprach-Cache, Stats, `main()` |
| `engine.py` | Whisper-Wrapper (mlx-whisper, Standard `turbo-q4`), Warmup wärmt GPU-Kernel (3 Läufe) |
| `llm.py` | Zwei-Backend-Feinschliff: LM Studio (`:1234/v1`, OpenAI-API) + Ollama (`:11434`), `resolve()`/`status()`, 🚀-Schnell-Modus (`needs_polish`: LLM nur bei Korrektur-/Listen-Triggern oder ≥14 Wörtern) |
| `server.py` | Flask-HTTPS (Port 8790, selbstsigniertes Zert mit LAN+Tailscale-SANs): `/api/ping`, `/api/transcribe` (auch `insert=1` → Einfügen am Mac!), `/api/history`, `/api/status`, statische PWA |
| `hotkey.py` | pynput-Listener + `physically_down()`/`any_modifier_down()` (Quartz `CGEventSourceFlagsState`) |
| `inserter.py` | Clipboard sichern → ⌘V (Quartz-CGEvent, Fallback osascript) → Clipboard zurück; wartet bis keine Modifier-Taste gedrückt |
| `menubar.py` | rumps-Menü: Status, ⚙️ Einstellungen (Toggles/Hotkey/Modell), 📱 Koppeln (QR), 🩺 Diagnose, Datei-Transkription. UI-Updates NUR über `rumps.Timer`-Tick (Haupt-Thread) |
| `audio.py` | Aufnahme (sounddevice 16 kHz), Upload-Dekodierung (afconvert→ffmpeg-Fallback), Stille-Gate (RMS) |
| `config.py` | Defaults + Laden/Speichern `~/.localflow/` |
| `autostart.py` | LaunchAgent `studio.minh.localflow.plist` (aktiv beim Nutzer) |
| `web/index.html` | PWA: Tap-to-talk, Sprach-Chips, „→ Mac"-Chip (insert), Verlauf |

**Packaging:** `packaging/LocalFlow.spec` (PyInstaller; torch/numba-tests/llvmlite-tests
ausgeschlossen — torch wird NUR vom nie genutzten Gewichts-Konverter gebraucht; scipy+numba
sind Pflicht für `mlx_whisper.timing`), `packaging/launcher.py` (ruft
`multiprocessing.freeze_support()` — ohne das crashen mlx/numba-Kindprozesse in argparse),
`packaging/build_dmg.sh` (Build → ad-hoc-Signatur → DMG mit Programme-Symlink).

**Tests:** `tests/` — 56 schnelle (pytest, ohne Modell) + `test_e2e.py` (synthetisiert
Sätze mit macOS-Stimme „Anna" → echtes Whisper). Laufen mit
`~/Downloads/localflow/.venv/bin/python -m pytest tests/ -q --ignore=tests/test_e2e.py`.

**Bekannte Stolperfallen (aus schmerzhafter Erfahrung):**
1. **Whisper-`initial_prompt` niemals mit Einleitungswörtern** („Glossar:") — wird bei
   leisen Aufnahmen wörtlich in die Ausgabe geechot. Nur nackte Wortliste, leer = None.
2. **App-Neustart:** erst `pkill -f "LocalFlow.app"` UND `pkill -f "localflow.main"`,
   sonst hält der alte Prozess Port 8790 / Dateien in `dist/` offen und
   `open -a LocalFlow` startet nichts Neues.
3. **`rm -rf dist` scheitert („Directory not empty")**, solange eine Test-Instanz aus
   `dist/` läuft → vorher killen (macht `build_dmg.sh` inzwischen selbst).
4. **venv niemals verschieben** (absolute Shebangs) — am Zielort neu anlegen.
5. **macOS-TCC:** Der Downloads-Ordner kann für Tools mitten in der Session gesperrt
   werden („Operation not permitted"). Workaround: Klon im Session-Scratchpad bearbeiten,
   via GitHub pushen, in `~/Downloads/localflow` pullen.
6. **Nur EIN `ollama pull` gleichzeitig** — parallele Pulls blockieren sich.
7. **Erste 2–3 Inferenzen nach Modell-Load sind 3–5× langsamer** (Metal-Kernel) —
   deckt `Engine.warmup()` ab; bei Engine-Änderungen beibehalten.
8. LLM-Live-Tests brauchen laufendes LM Studio (`~/.lmstudio/bin/lms server start`,
   Modell `gemma-4-e2b-it`); ohne LLM fällt alles lautlos auf Regel-Cleanup zurück (so gewollt).

---

## Arbeitsregeln für die umsetzende Session

1. **Sprache:** Kommunikation, Commits, UI-Texte auf Deutsch.
2. **Nach jedem Arbeitspaket:** Tests grün → committen → auf `main` pushen →
   `git -C ~/Downloads/localflow pull` → **DMG neu bauen** (`bash packaging/build_dmg.sh`)
   → neue App nach `/Applications` kopieren (alte vorher killen/löschen) → App starten →
   Live-Smoke-Test (`curl -sk https://127.0.0.1:8790/api/status`). Die DMG **immer**
   zusätzlich nach `~/Downloads/LocalFlow-<ver>.dmg` kopieren (Nutzer-Wunsch: stets aktuell).
3. **Version zentral pflegen** (wird in Paket 2 eingeführt): `localflow/_version.py`.
   Spürbare Änderung ⇒ Minor-Bump.
4. **Keine Kosten, keine Kreditkarte.** GitHub-Free-Tier, keine bezahlten Dienste.
   Apple-Developer-ID (99 €/Jahr) ist explizit NICHT Teil dieses Plans.
5. **Nichts committen, was groß oder geheim ist:** `dist/`, `build/`, `*.dmg` sind in
   `.gitignore`; das neue `~/.localflow/secret.token` bleibt außerhalb des Repos.
6. **Repo-öffentlich-Denken:** Keine privaten Pfade/Daten in README/Code-Kommentare.
7. Bei Feature-Änderungen mit Außenwirkung: README mitziehen; bei neuen Kern-Features
   auch Portfolio-Karte (`theminhnguyen.github.io`, `js/data.js`) aktuell halten.

---

# PHASE 1 — Sicherheit & Infrastruktur (Ziel: Tag `v0.4.0`)

## Paket 1.1 — Kopplungs-Token für den Server 🔴 (zuerst!)

**Problem:** `/api/transcribe` akzeptiert von JEDEM im WLAN Audio und fügt mit
`insert=1` Text am Mac-Cursor ein. Das ist eine echte Sicherheitslücke.

**Design:**
- Beim Start: existiert `~/.localflow/secret.token` nicht → `secrets.token_urlsafe(24)`
  erzeugen, Datei mit `chmod 0600`.
- Kopplung: Die QR-/Link-URL bekommt das Token als **Fragment**:
  `https://<ip>:8790/#k=<token>` (Fragmente verlassen den Browser nicht → tauchen in
  keinem Server-Log auf). PWA liest `location.hash`, speichert Token in `localStorage`
  (`lf_key`), entfernt das Fragment via `history.replaceState`, sendet es fortan als
  Header `X-LocalFlow-Key` bei allen `/api/*`-Aufrufen.
- Server (`server.py`): `@app.before_request`-Guard für Pfade, die mit `/api/` beginnen,
  **außer** `/api/ping` (bleibt offen für den Status-Punkt der PWA; enthält nichts
  Sensibles). Vergleich ausschließlich mit `hmac.compare_digest`. Fehlend/falsch →
  `401 {"error": "nicht gekoppelt", "code": "unauthorized"}`.
- Config-Schalter `require_auth` (Default **true**). Toggle NICHT ins Menü — Sicherheit
  soll man nicht versehentlich ausschalten; wer es braucht, editiert config.json.
- Menü „📱 Handy koppeln": QR/Link enthalten das Token automatisch. Neuer Unterpunkt
  „Kopplung zurücksetzen…" → rumps-Bestätigung → Token-Datei neu erzeugen →
  Hinweis „Alle Handys müssen den QR neu scannen".
- PWA: bei HTTP 401 eine gut sichtbare Karte „🔑 Nicht gekoppelt — scanne den QR-Code
  am Mac neu (Menüleiste → Handy koppeln)". Kein Retry-Loop.
- Der Mac-eigene Diktatpfad (Hotkey) läuft NICHT über HTTP → unberührt.

**Dateien:** `server.py` (Guard + Token-Laden), `config.py` (Default `require_auth`),
`menubar.py` (URL-Bau `_url()` + Reset-Menüpunkt), `web/index.html` (Hash-Import,
Header, 401-UI), neu: Token-Helfer in `server.py` oder `config.py` (`load_or_create_token()`).

**Tests (neu in `tests/test_server_extra.py` oder eigener Datei):**
- ohne Header → 401 für `/api/transcribe`, `/api/history`, `/api/status`
- mit korrektem Header → 200; mit falschem → 401
- `/api/ping` und `/` (PWA) bleiben ohne Token erreichbar
- `require_auth=false` → alles offen (Abwärtskompatibilität)
- Token-Datei wird erzeugt, hat Modus 0600, bleibt über Neustarts stabil
- Reset erzeugt neues Token (altes wird ungültig)

**Abnahme:** Frisches Gerät ohne Token kann weder transkribieren noch einfügen;
nach QR-Scan funktioniert die PWA unverändert (inkl. „→ Mac"); alle Tests grün.

**Stolperfalle:** iOS-PWA „Zum Home-Bildschirm": `localStorage` bleibt erhalten, aber
teste den Fluss QR → Safari → Home-Bildschirm-App (Token muss in beiden Kontexten
ankommen — deshalb Fragment + localStorage statt Query-Param + Cookie).

## Paket 1.2 — Version zentralisieren + CI (GitHub Actions)

**Design Version:** Neue Datei `localflow/_version.py` mit `__version__ = "0.4.0"`.
Verwenden in: `menubar` (Diagnose-Status), `/api/status` (`"version"`),
`packaging/LocalFlow.spec` (importieren statt Hardcode), `packaging/build_dmg.sh`
(per `python -c "from localflow._version import __version__; print(__version__)"`).

**Design CI (`.github/workflows/ci.yml`):**
```yaml
name: CI
on: [push, pull_request]
jobs:
  tests:
    runs-on: macos-14        # arm64, kostenlos für public Repos
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12", cache: pip }
      - run: python -m pip install -r requirements.txt
      - run: python -m pytest tests/ -q --ignore=tests/test_e2e.py
```
- E2E-Tests bewusst NICHT in CI (600-MB-Modell-Download je Lauf). 
- Prüfe vorab lokal, dass die Suite ohne Mikrofon/GUI durchläuft (tut sie heute).
- `requirements.txt` enthält pytest bereits; PyInstaller wird in CI-Tests NICHT gebraucht.
- CI-Badge oben ins README.

**Abnahme:** Push auf `main` → Action grün auf github.com/theminhnguyen/localflow/actions.

## Paket 1.3 — Release-Automatik (Tag → DMG → GitHub Release)

**Design (`.github/workflows/release.yml`):**
- Trigger: `push: tags: ["v*"]`.
- Schritte: checkout → setup-python 3.12 → `pip install -r requirements.txt pyinstaller`
  → Konsistenz-Check `[ "v$(python -c 'from localflow._version import __version__; print(__version__)')" = "$GITHUB_REF_NAME" ]`
  → `bash packaging/build_dmg.sh` → `gh release create "$GITHUB_REF_NAME" dist/LocalFlow-*.dmg --generate-notes`
  (Token: eingebautes `GITHUB_TOKEN`, braucht `permissions: contents: write`).
- `build_dmg.sh` muss dafür CI-fest sein: kein interaktives Zeug (ist es), Version aus
  `_version.py` (Paket 1.2), `pkill`-Aufrufe mit `|| true` (bereits so).
- README: Abschnitt „Installation" auf die Releases-Seite verlinken
  (`https://github.com/theminhnguyen/localflow/releases/latest`).

**Abnahme:** `git tag v0.4.0 && git push origin v0.4.0` erzeugt automatisch ein
GitHub-Release mit angehängter DMG; DMG von dort herunterladen, mounten, App startet.

**Hinweis:** Die CI-gebaute DMG ist ad-hoc-signiert wie die lokale — Nutzerhinweis
„Rechtsklick → Öffnen" bleibt (bewusst, kostenlos).

## Paket 1.4 — Privacy-Logging + Verlaufs-Hygiene

**Problem:** Diktattexte landen wörtlich im Log (`~/.localflow/logs/`) — widerspricht
dem Datenschutz-USP.

**Design:**
- Config `log_texts` (Default **false**). Helfer in `main.py`:
  `def _loggable(self, text): return text[:80] if self.cfg.get("log_texts") else f"[{len(text)} Zeichen]"`
  — an ALLEN Stellen nutzen, die Diktat-/Handy-Texte loggen (`main._process`,
  `server./api/transcribe`, Datei-Transkription).
- Verlauf bleibt Feature (bewusst lokal), aber: Menüpunkt „Verlauf leeren" (unter
  „Verlauf") + Config `history_keep` (Default 50; `0` = Verlauf ganz aus, dann speichert
  `add_history` nichts und die Menü-/API-Verläufe zeigen leer).
- 🩺 Diagnose: neuer Punkt „Log leeren" (Dateien in `logs/` truncaten).
- README: Datenschutz-Absatz ergänzen (was wird wo gespeichert, wie löscht man es;
  einzige Netzzugriffe: HF-Modelldownload einmalig + optionaler Update-Check aus 1.5).

**Tests:** `caplog`-basiert: bei Default landet ein markanter Diktattext NICHT im Log,
mit `log_texts=true` schon; `history_keep=0` ⇒ `load_history()` bleibt leer.

**Abnahme:** Frisch diktieren → `grep <text> ~/.localflow/logs/*` liefert nichts.

## Paket 1.5 — Update-Check

**Design (neu `localflow/updater.py`):**
- `fetch_latest(timeout=4)` → GET `https://api.github.com/repos/theminhnguyen/localflow/releases/latest`
  (urllib, ohne Auth; 60 Anfragen/h reichen). Liefert `{"tag": "v0.5.0", "url": html_url}`
  oder `None` bei jedem Fehler (fail-silent, loggen nur auf DEBUG).
- `is_newer(tag, current)` — nackter Tupel-Vergleich `(0,5,0) > (0,4,0)`;
  eigene 6-Zeilen-Implementierung, KEINE neue Abhängigkeit.
- Config `update_check` (Default true, Toggle im ⚙️-Menü: „🔄 Auf Updates prüfen") —
  das ist der einzige „Telefon-nach-Hause"-Call der App, also abschaltbar + im README.
- Ablauf: Hintergrund-Thread prüft 1× beim Start (nach 60 s Verzögerung, damit der
  Start schlank bleibt) und dann alle 24 h. Bei Fund: `controller.update_available =
  {"tag":…, "url":…}` → Menü-Tick (Haupt-Thread!) blendet oben einen Menüpunkt ein
  „⬆️ Update v0.5.0 verfügbar…" → Klick öffnet die Release-Seite (`open <url>`).
  KEIN automatischer Download/Selbstaustausch (bewusst: ad-hoc-Signatur macht
  In-App-Replacement fehleranfällig).
- Zusätzlich manuell: 🩺 Diagnose → „Jetzt nach Updates suchen".

**Tests:** `is_newer` (inkl. gleiche Version, v-Präfix, zweistellige Zahlen);
`fetch_latest` gemockt (Erfolg/Netzfehler/Ratelimit → None); Menü-Logik: Flag am
Controller ⇒ Tick erzeugt Menüpunkt (analog bestehender `_tick`-Tests-Muster,
notfalls Logik in testbare Funktion ziehen).

**Abnahme:** Mit lokal gefaktem `fetch_latest` (Monkeypatch/kleiner Testhook) erscheint
der Menüpunkt und öffnet die richtige URL; echter Lauf gegen GitHub liefert die
aktuelle Release ohne Fehler.

### Phase-1-Abschluss
- Alle Tests grün (Ziel: >70), README aktualisiert, Memory-Notiz ergänzen.
- `_version.py` → `0.4.0`, committen, `git tag v0.4.0`, Push von Branch UND Tag.
- CI-Release abwarten und verifizieren; parallel lokal DMG bauen, installieren,
  Live-Smoke-Test; DMG nach `~/Downloads/` kopieren.

---

# PHASE 2 — Erlebnis (Ziel: Tag `v0.5.0`)

## Paket 2.1 — Onboarding beim ersten Start

**Design (pragmatisch mit rumps, kein AppKit-Eigenbau):**
- Marker `~/.localflow/onboarded` (enthält Version). Fehlt er → Onboarding-Sequenz
  VOR dem normalen Betrieb (aber Server/Warmup dürfen parallel schon starten).
- Zustands-Logik als eigene, testbare Klasse `localflow/onboarding.py`
  (`next_step(perms, model_ready) -> Step`), UI-Ausführung in `menubar.py`.
- Schritte (jeweils `rumps.alert` mit klarem Titel „Schritt X von 4"):
  1. **Willkommen** — was die App tut, was gleich passiert.
  2. **Mikrofon** — kurze Proberaufnahme öffnen/schließen (löst macOS-Prompt aus),
     danach weiter (Erfolg nicht zuverlässig abfragbar → nicht blockieren).
  3. **Bedienungshilfen + Eingabemonitoring** — beide Panes öffnen
     (`x-apple.systempreferences:…Privacy_Accessibility` / `…Privacy_ListenEvent`),
     dann Poll-Schleife (rumps.Timer, 1 s) auf `permissions_status()`; Status-Zeile im
     Menü zeigt live „⏳ warte auf Häkchen…" → beide true ⇒ nächster Schritt.
     Wichtig: Nach Erteilen ist ein **App-Neustart nötig**, damit der Event-Tap greift →
     Alert „Neu starten" → `subprocess.Popen(["open","-a","LocalFlow"])` geht NICHT
     (Instanz läuft) — stattdessen sauber: Helper-Skript-Variante oder
     `os.execv(sys.executable, [sys.executable])` (PyInstaller-Binary re-exec; testen!).
     Fallback, falls re-exec im Bundle zickt: Alert „Bitte LocalFlow beenden und neu
     öffnen" + `rumps.quit_application()`.
  4. **Modell-Download mit Fortschritt** — statt stillem Erstdiktat-Download:
     `huggingface_hub.snapshot_download(repo)` in Thread; Fortschritt über
     `tqdm`-Klasse abfangen (eigene `tqdm`-Subklasse, die `controller.download_pct`
     setzt) → Status-Zeile „Lädt Whisper… 43 %". Danach `engine.warmup()` →
     „🎉 Fertig! Halte ⌥ und sprich."
- Nach Durchlauf: Marker schreiben. Menüpunkt 🩺 → „Einrichtung erneut starten".

**Tests:** `onboarding.next_step`-Matrix (alle Kombinationen), Marker-Logik,
tqdm-Hook-Klasse (setzt Prozentwerte). UI-Alerts selbst: manueller Testdurchlauf mit
gelöschtem Marker + frischem `~/.localflow`-Backup (danach zurückspielen!).

**Abnahme:** `mv ~/.localflow ~/.localflow.bak` → App-Start führt komplett durch bis
zum ersten erfolgreichen Diktat; danach Backup zurück.

## Paket 2.2 — Einstellungs-Seite (Web) statt Menü-Gefrickel

**Entscheidung:** KEIN AppKit/pyobjc-Fenster (hoher Pflegeaufwand, hässlich in rumps);
stattdessen nutzt LocalFlow den vorhandenen Server: eine hübsche lokale Settings-Seite,
die auch vom iPhone funktioniert. Das native SwiftUI-Fenster kommt in Phase 3.

**Design:**
- `GET /api/config` → gefilterte Config (Whitelist, ohne Token/Interna);
  `PUT /api/config` → validiert (Schlüssel-Whitelist + Typ/Enum je Feld:
  `language ∈ {auto,de,en}`, `hotkey ∈ {alt_r,cmd_r,ctrl_r,f13}`,
  `model ∈ MODELS.keys()`, bools, Zahlen mit Grenzen) → wendet über die vorhandenen
  Setter an (`set_language`, `set_hotkey`, `set_model`, `set_toggle`) — dadurch
  greifen Änderungen sofort ohne Neustart. Beide Endpunkte Token-geschützt (Paket 1.1).
- Neue Seite `web/settings.html` (gleiche Design-Sprache wie `index.html`, dunkel):
  Gruppen „Diktat" (Sprache, Taste, Modell), „KI-Feinschliff" (an/aus, Schnell-Modus,
  Backend-Anzeige nur lesend aus `/api/status`), „Handy" (Einfügen erlauben, Verlauf
  teilen), „System" (Töne, Autostart, Update-Check, Texte loggen). Speichern per PUT,
  Toast „Gespeichert ✓".
- Menü: „⚙️ Einstellungen öffnen…" → `open https://127.0.0.1:8790/settings#k=<token>`
  (ersetzt die Toggle-Liste im Menü NICHT sofort — beide parallel lassen, Menü bleibt
  Schnellzugriff; Untermenüs Hotkey/Modell dürfen zugunsten der Seite entfallen).
- Autostart-Toggle braucht Server-Zugriff auf `autostart.enable/disable` — über den
  Controller reichen (`controller.set_autostart(bool)` neu, dünner Wrapper).

**Tests:** PUT-Validierung (gute/böse Werte, unbekannte Schlüssel → 400), GET filtert
Token heraus, Setter werden aufgerufen (FakeController), Seite wird ausgeliefert (200).

**Abnahme:** Einstellung auf der Seite ändern (z. B. Sprache) → wirkt sofort beim
nächsten Diktat; vom iPhone aus erreichbar und benutzbar.

## Paket 2.3 — README englisch + Demo-GIF + Feinschliff

- `README.md` → Englisch als Hauptsprache, kompakter; `README.de.md` mit heutigem
  Inhalt, gegenseitig verlinkt. Badges: CI, Release, License.
- Demo-GIF (Screen-Aufnahme geht nicht headless — stattdessen: kurze animierte
  SVG/GIF aus der Portfolio-Mockup-Idee bauen oder mit `ffmpeg`+Screenshots des
  PWA-Flows; pragmatisch: 2–3 Screenshots (Menü, PWA, Diktat-Ergebnis) + das
  Portfolio-Mockup-GIF). Keine Fremd-Assets.
- `CHANGELOG.md` (Keep-a-Changelog-Format) rückwirkend ab 0.1.0 kurz befüllen,
  ab jetzt pro Release pflegen (Release-Workflow nutzt weiterhin `--generate-notes`,
  CHANGELOG ist die kuratierte Sicht).
- Portfolio-Karte (`theminhnguyen.github.io/js/data.js`): Beschreibung um „DMG-Download"
  ergänzen, `live`-Link auf die Releases-Seite prüfen/aktualisieren.

### Phase-2-Abschluss: `_version.py` → `0.5.0`, Tag, CI-Release, DMG lokal + `~/Downloads/`.

---

# PHASE 3 — Native Swift-Hülle + echtes Settings-Fenster (Ziel: `v1.0.0`)

**Nur beginnen, wenn Phase 1+2 abgeschlossen und stabil sind.** Vorher mit dem Nutzer
kurz bestätigen, dass er den Umbau jetzt will (größerer Eingriff, ~1 Session).

## Architektur-Entscheidung (bereits getroffen, so umsetzen)

**Hybrid „Swift-Shell + Python-Engine":** Die Swift-App übernimmt ALLES Interaktive
(Menüleiste, Hotkey, Aufnahme, Einfügen, Settings, Onboarding) und behandelt die
bestehende Python-Engine als lokalen Dienst — exakt wie das iPhone heute:

```
LocalFlow.app (Swift, NSStatusItem)
 ├─ startet/überwacht: Contents/Resources/engine/LocalFlow-Engine  (PyInstaller-CLI,
 │     --serve-only --port 8790; unser heutiges Binary ohne rumps-Teil)
 ├─ Hotkey:   CGEventTap (flagsChanged für ⌥ rechts; Tap-Timeout-Re-Enable!)
 ├─ Aufnahme: AVAudioEngine → AVAudioConverter → 16 kHz mono Float32 → WAV in RAM
 ├─ Diktat:   POST /api/transcribe (Header X-LocalFlow-Key aus ~/.localflow/secret.token)
 ├─ Einfügen: NSPasteboard sichern → CGEvent ⌘V → zurück  (Logik 1:1 aus inserter.py)
 └─ Settings: SwiftUI-Fenster, liest/schreibt via GET/PUT /api/config (Paket 2.2!)
```

**Warum so:** Alle schwierigen Teile (Whisper, LLM, Cleanup, PWA, Token, Config-API)
bleiben unverändert in Python; Swift ersetzt genau die Schicht, die heute fragil ist
(pynput-Eventverlust, rumps-UI, „Python"-Prozessname, 9-s-Start). Die Engine kann
später unabhängig weiterentwickelt werden.

## Pakete

**3.1 Engine-Modus härten (Python):**
- `--serve-only` wird zu vollwertigem Engine-Modus: kein rumps-Import, sauberes
  SIGTERM-Handling, `/api/health` (schnell, ohne Modell), `/api/insert` (POST Text →
  `inserter.insert_text`; Token-geschützt) — damit Swift das Einfügen wahlweise an
  Python delegieren kann (Fallback), primär macht Swift es selbst.
- PyInstaller-Zweitziel „LocalFlow-Engine" (`console=True`-Variante ohne App-Bundle,
  nur `COLLECT`-Ordner) in `LocalFlow.spec` ergänzen.

**3.2 Swift-Projekt aufsetzen (`swift/` im Repo):**
- Kein Xcode-GUI-Zwang: Build über `swiftc` + Bundle-Skript (analog PyInstaller-Weg)
  ODER `xcodegen` + `xcodebuild`, je nachdem was auf der Maschine vorhanden ist
  (`xcode-select -p` prüfen; ohne volles Xcode: swiftc-Weg).
- Dateien: `AppDelegate.swift` (NSStatusItem, Menü), `EngineProcess.swift`
  (Prozess-Lifecycle, Health-Poll, Neustart bei Crash), `HotkeyTap.swift`
  (CGEventTap inkl. `kCGEventTapDisabledByTimeout`-Re-Enable — DAS behebt das
  Event-Verlust-Problem endgültig), `Recorder.swift` (AVAudioEngine, 16 kHz),
  `Paster.swift`, `API.swift` (URLSession, selbstsigniertes Zert der Engine via
  Delegate für 127.0.0.1 akzeptieren), `SettingsView.swift` (SwiftUI, Formular wie
  Web-Settings), `OnboardingView.swift`.
- Info.plist: `LSUIElement`, Bundle-ID `studio.minh.localflow` beibehalten
  (TCC-Rechte-Kontinuität best effort), NSMicrophoneUsageDescription.

**3.3 Feature-Parität + Umschalt-Test:**
Checkliste gegen heutige App: Hold-to-talk, Doppel-Tipp-Freihand, Serien-Diktate
(Queue in Swift oder sequenziell via Engine), Sounds, Menü (Sprache/Verlauf/Koppeln-QR
— QR rendert die Engine als PNG-Endpoint `/api/qr?variant=lan|ts`, neu, klein),
Diagnose, Datei-Transkription (NSOpenPanel → Upload), Autostart (SMAppService),
Update-Check (Swift liest `/api/status` + GitHub wie 1.5 oder ruft Engine-Endpoint).

**3.4 Packaging v1.0:** `build_dmg.sh` baut erst Engine (PyInstaller), dann Swift-App,
kopiert Engine ins Bundle, signiert ad-hoc, DMG. CI-Release-Workflow anpassen
(macos-14 hat Xcode CLT). Erst wenn die Checkliste 3.3 komplett grün ist, ersetzt die
Swift-App die rumps-App in `/Applications`; die reine Python-App bleibt als
`--legacy`-Fallback eine Version lang lauffähig.

**Risiken, ehrlich:** AVAudioConverter-Formatdetails, CGEventTap-Berechtigungs-Flow,
selbstsigniertes Zert in URLSession, PyInstaller-Engine-Startzeit im Bundle. Deshalb:
3.1 zuerst, jeder Swift-Baustein einzeln gegen die laufende Engine testen.

---

## Prioritäten-Übersicht (TL;DR für die Session)

| # | Paket | Wert | Aufwand |
|---|---|---|---|
| 1.1 | Kopplungs-Token | 🔴 Sicherheit | S |
| 1.2 | Version + CI | Profi-Fundament | S |
| 1.3 | Tag→Release-DMG | Verteilung | S |
| 1.4 | Privacy-Log | Vertrauen/USP | S |
| 1.5 | Update-Check | Produktgefühl | S |
| 2.1 | Onboarding | Erster Eindruck | M |
| 2.2 | Web-Settings | Bedienbarkeit | M |
| 2.3 | README-EN/GIF/Changelog | Außenwirkung | S |
| 3.x | Swift-Hülle | Endgültige Robustheit | L (eigene Session) |

**Startbefehl für die umsetzende Session:** Lies dieses Dokument vollständig, prüfe
`git -C ~/Downloads/localflow status` (sauber?), starte mit Paket 1.1, arbeite die
Phasen der Reihe nach ab, halte dich strikt an die Arbeitsregeln (v. a. Regel 2:
Tests → Push → Pull → **DMG neu bauen** → deployen → Smoke-Test).
