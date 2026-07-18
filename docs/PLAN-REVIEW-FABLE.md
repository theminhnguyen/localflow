# LocalFlow — Kritischer Review & Arbeitsplan (Fable 5 → Sonnet 5)

> **Für die umsetzende Session (Sonnet 5):** Dieses Dokument ist das Ergebnis
> eines kritischen Gesamt-Reviews der App (Stand 2026-07-18, nach v0.6.0 +
> uncommitteten Vorwärm-Änderungen). Es ergänzt `PLAN-PROFESSIONALISIERUNG.md`
> (dessen Phase 3.3/3.4 weiter gilt) um konkrete Befunde mit Priorität.
> Arbeite die Pakete **in Reihenfolge P0 → P1 → P2** ab. Jedes Paket einzeln:
> Tests grün → committen → pushen → bei Nutzer-sichtbaren Änderungen DMG neu
> bauen und deployen (Arbeitsregel 2 im Professionalisierungs-Plan).

---

## Gesamturteil (ehrlich)

Die App ist für ein Ein-Personen-Projekt in bemerkenswert gutem Zustand:
saubere Trennung Engine/UI, echte Tests (163), CI, stabile Signatur,
Privacy-Defaults, durchdachte Fixes (Umlaute via NSPasteboard, TCC-Lektionen,
Leerzeichen via AX-API statt blind). Die Architektur-Entscheidung
„Swift-Hülle + Python-Engine als lokaler Dienst" ist richtig und trägt.

Die kritischen Punkte unten sind keine Design-Fehler, sondern typische
Lücken einer schnell gewachsenen Codebasis: zwei echte Korrektheits-Bugs,
ein Sicherheits-Inkonsistenz-Punkt, fehlende Robustheit an drei Stellen,
und offene Enden aus der laufenden Phase 3. Nichts davon ist dramatisch,
aber P0 sollte VOR neuen Features passieren.

---

## P0 — Korrektheit & Sicherheit (zuerst, in dieser Reihenfolge)

### P0.1 `/api/insert` ignoriert den `phone_insert`-Schalter  🔴 Sicherheit/Konsistenz

**Befund:** `server.py` → `/api/transcribe` mit `insert=1` prüft
`cfg().get("phone_insert", True)` und verweigert das Einfügen, wenn der
Nutzer „Handy darf einfügen" ausgeschaltet hat. Der neuere Endpunkt
`POST /api/insert` (für die Swift-Hülle gebaut) prüft das NICHT — jedes
Gerät im WLAN mit gültigem Token kann Text am Mac-Cursor einfügen, auch
wenn der Schalter aus ist. Der Schalter suggeriert eine Schutzwirkung,
die dieser Endpunkt unterläuft.

**Fix:** Gleiche Prüfung wie im transcribe-Pfad einbauen; bei ausgeschaltetem
Schalter `403 {"error": "…", "code": "insert_disabled"}`. ABER: Die
Swift-Hülle nutzt diesen Endpunkt als Fallback und ist KEIN „Handy" — sie
läuft auf demselben Mac. Sauberste Lösung: Loopback-Anfragen
(`request.remote_addr in ("127.0.0.1", "::1")`) von der Prüfung ausnehmen —
lokale Aufrufer dürfen immer, entfernte nur mit Schalter. Kommentar im Code,
warum (sonst „repariert" das später jemand kaputt).

**Tests:** entfernter Aufruf mit Schalter aus → 403; mit Schalter an → 200;
Loopback mit Schalter aus → 200. (Flask-Test-Client: `environ_base={"REMOTE_ADDR": …}`.)

### P0.2 Zwischenablage-Wiederherstellung überschreibt Folge-Diktate  🐛 Race in BEIDEN Hälften

**Befund:** Beim Paste-Einfügen wird die alte Zwischenablage nach 0,6 s
wiederhergestellt — per Timer/Thread OHNE Abbruch-Möglichkeit
(`inserter.py::_insert_by_paste` restore-Thread; `Paster.swift`
`asyncAfter`). Folgt Diktat 2 innerhalb dieser 0,6 s (Serien-Diktate!),
kann der Restore von Diktat 1 GENAU zwischen „Zwischenablage = Text 2
setzen" und dem simulierten ⌘V feuern → eingefügt wird die ALTE
Zwischenablage statt Text 2. Das ⌘V wartet zusätzlich bis zu 4 s auf
losgelassene Modifier — das Fenster ist real, nicht theoretisch. Mildere
Variante desselben Fehlers: Am Ende steht Text 1 statt des ursprünglichen
Inhalts in der Zwischenablage.

**Fix (beide Seiten gleich):** Ausstehenden Restore beim Start eines neuen
Einfügens abbrechen. Swift: `DispatchWorkItem` statt nacktem `asyncAfter`,
Referenz halten, `cancel()` beim nächsten `insert()`. Python: Restore als
abbrechbares Objekt (z.B. `threading.Timer` statt Thread+sleep, `cancel()`
beim nächsten `insert_text`). Der zuletzt gesicherte „alte" Inhalt des
ERSTEN Diktats soll dabei erhalten bleiben (nicht Text 1 als „alt"
übernehmen — sonst landet nach der Serie Diktattext in der Zwischenablage).

**Tests (Python):** Zwei schnelle `insert_text`-Aufrufe mit gemockten
pb-Funktionen → am Ende ist der VOR Diktat 1 gesicherte Inhalt wieder da,
und zwischen Set(Text 2) und Paste feuert kein Restore.

### P0.3 Engine-Absturz lässt die Swift-Hülle dauerhaft tot zurück  🐛

**Befund:** `EngineProcess.terminationHandler` setzt nur `state = .crashed`.
Der Professionalisierungs-Plan (3.2) verlangt „Neustart bei Crash". Stürzt
die Python-Engine ab (OOM beim Modell-Laden, Port-Kollision, Bug), zeigt
die Menüleiste „Fehler" und nichts geht mehr, bis der Nutzer die App
manuell neu startet.

**Fix:** Automatischer Neustart mit Backoff (z.B. 1 s, 5 s, 15 s; nach 3
Fehlversuchen in kurzer Zeit aufgeben und im Menü „Engine neu starten"
anbieten). Wichtig: `stop()`-Fall (gewolltes Beenden) sauber vom Crash
unterscheiden — der Guard existiert schon (`state != .stopped`).

### P0.4 `lastText`-Datenrennen (klein, aber echt)

**Befund:** `FlowController.lastText` wird auf dem Worker-Thread
geschrieben, `AppDelegate.render()` liest es auf dem Haupt-Thread.

**Fix:** Schreiben in `DispatchQueue.main.async` verlegen (Menü-Update
passiert eh dort) — kein Lock nötig, nur Disziplin.

---

## P1 — Stabilität & offene Enden

### P1.1 Vorwärm-Änderungen abschließen (liegen UNCOMMITTET im Arbeitsverzeichnis!)

Stand: `engine.prewarm_if_cold()` + `_last_use`, `POST /api/prewarm`,
Swift-Aufruf beim Tastendruck, 6 neue Tests — alles fertig, 163 Tests grün,
Swift baut. Es fehlt:
1. **Live-Verifikation** (war durch Classifier-Ausfall blockiert): In-Process
   prüfen, dass bei kalt markierter Engine (`_last_use` zurückdatieren) die
   Log-Zeile „Vorgewärmt (…ms)" kommt und bei heißer Engine NICHT. Dazu:
   übrig gebliebenen Testserver auf Port 8795 killen
   (`pkill -f "localflow.main --serve-only --port 8795"`), `/tmp/lf_prewarm_test.log` löschen.
2. **`COLD_AFTER_S` überdenken:** 120 s ist aggressiv — nach jeder
   2-Minuten-Pause läuft eine Stille-Inferenz, und ein sehr kurzes Diktat
   (<1 s Sprechzeit) wartet dann hinter dem Vorwärmen im Engine-Lock.
   Empfehlung: auf 600 s (10 min) anheben — die Messdaten aus dem Log
   (5202 ms nach 12 h Pause, 1109 ms nach 78 min) geben keine Evidenz, dass
   2 min schon auskühlen. Kommentar mit Messwerten begründen.
3. Version **0.6.1**, CHANGELOG, committen, taggen, DMG bauen, installieren,
   `~/Downloads/LocalFlow-0.6.1.dmg` aktualisieren, alte 0.6.0-DMG entfernen.

### P1.2 Recorder überlebt keinen Gerätewechsel (AirPods!)

**Befund:** `Recorder` nutzt EINE `AVAudioEngine`-Instanz für alle
Aufnahmen; das Eingabeformat wird beim `installTap` fixiert. Wechselt das
Eingabegerät zwischen zwei Diktaten (AirPods verbinden/trennen — beim
Nutzer ein realistischer Alltag), kann das Format nicht mehr stimmen;
AVFoundation wirft dabei teils ObjC-Exceptions, die Swift nicht fangen
kann → Absturz beim nächsten Diktat.

**Fix:** Pro Aufnahme eine frische `AVAudioEngine` erzeugen (billig genug)
und `AVAudioEngineConfigurationChange`-Notification beobachten: läuft
gerade eine Aufnahme, sauber stoppen und Fehler-Klang spielen statt
abstürzen. Manuell testen: Diktat → AirPods verbinden → Diktat.

### P1.3 DevLog wächst unbegrenzt

`~/.localflow/logs/swift-dev.log` hat keine Rotation (Python-Seite hat
RotatingFileHandler, 500 KB × 2). Gleichziehen: beim Start und bei jedem
n-ten Schreiben Größe prüfen, >500 KB → nach `.1` rotieren, eine Generation.

### P1.4 Engine-Subprozess-Log: FileHandle-Leck

`EngineProcess.start()` öffnet ein `FileHandle` fürs Engine-Log und
schließt es bei `stop()`/Neustart nie. Bei P0.3 (Auto-Restart) würde pro
Neustart ein Handle lecken. Beim Fix von P0.3 mit erledigen.

---

## P2 — Parität & Abschluss Phase 3 (nach P0/P1)

### P2.1 Rest von 3.3 (Reihenfolge nach Nutzwert)

1. **Update-Check** in der Swift-Hülle (Engine-`/api/status` liefert
   `version`; GitHub-Check macht die Engine schon — Menüpunkt einblenden).
2. **Autostart** über `SMAppService` + Menü-Toggle.
3. **Koppeln-QR:** kleiner Engine-Endpunkt `/api/qr?variant=lan|ts` (PNG,
   qrcode-Paket ist im Bundle), Swift zeigt ihn in einem Popover/Fenster.
4. **Datei-Transkription:** NSOpenPanel → Upload an `/api/transcribe`.
5. **Onboarding minimal:** KEIN SwiftUI-Großprojekt — die drei
   Berechtigungs-Anfragen + kurze Alerts reichen für v1.0 (die App fordert
   Rechte ja schon aktiv an; es fehlt nur Führung beim Erstlauf).

### P2.2 Phase 3.4 (Umstellung) — Vorsicht, Nutzer-sichtbar

Wie im Professionalisierungs-Plan, plus aus dieser Session gelernt:
- Engine-Ordner ins Bundle (`Contents/Resources/engine/`), `EngineProcess`
  findet ihn schon (Bundle-Pfad hat Vorrang vor dist/-Fallback).
- Bundle-ID/PRODUCT_NAME auf `studio.minh.localflow`/`LocalFlow`, Port auf
  8790 — **erst wenn Parität wirklich reicht**, und mit dem Nutzer
  abgestimmt (seine tägliche App wird ersetzt; TCC-Rechte müssen wegen
  neuer Binary-Struktur einmal neu erteilt werden — stabile Signatur
  minimiert das, aber Bundle-Wechsel Python→Swift ist eine neue Identität
  für Mikrofon-TCC).
- `build_dmg.sh` erweitern (Engine → Swift-App → Bundle → Signatur → DMG);
  die reine Python-App eine Version als Fallback beilegen (Plan 3.4).
- CI: macos-14 baut Swift mit; Release-DMG bleibt ad-hoc signiert, solange
  die **CI-Signatur-Frage offen** ist → als eigenen Punkt mit dem Nutzer
  klären (p12 als GitHub-Secret vs. dokumentiertes „Rechtsklick → Öffnen").

### P2.3 Kleinkram (wenn er im Weg liegt, sonst lassen)

- `test_engine_prewarm.py::test_transcribe_updates_last_use` enthält eine
  halb tote erste Engine-Instanz (`eng` wird gebaut, aber nur `eng2`
  getestet) — beim nächsten Anfassen der Datei säubern.
- `Recorder.stop()`-Größen-Logging nutzt `attributesOfItem` zweifach
  verschachtelt — funktioniert, aber unnötig; egal bis P1.2 eh umbaut.
- `hold_key "alt"` sendet links (58); Selbsttests immer `--hotkey alt_l`.

---

## Arbeitsregeln-Erinnerung (Kurzfassung; Details im Professionalisierungs-Plan + Memory)

1. Deutsch (Kommunikation, Commits, UI). Kostenlos, keine Karte, kein
   Apple-Developer-Account.
2. Nach jedem Paket: Tests → Commit → Push auf `main` → bei sichtbaren
   Änderungen DMG bauen (`bash packaging/build_dmg.sh`), nach
   `/Applications` und `~/Downloads/` deployen, Smoke-Test.
3. **Niemals** `.key`/`.p12`/Passwort-Dateien committen; `git add -A -n`
   vor jedem breiten Add prüfen. Die Suchlisten-/Signatur-Lektionen stehen
   im Memory (`localflow-project`).
4. Swift-Dev-Zyklus: `bash swift/build_swift.sh` (installiert selbst),
   dann `open -a /Applications/LocalFlow-Dev.app --args --hotkey alt_l` —
   NIE das Binary direkt aus der Shell starten (TCC geht ans Terminal).
   Debug ausschließlich über `~/.localflow/logs/swift-dev.log` (NSLog wird
   zensiert). Menüleisten-Apps sind per computer-use nicht klickbar.
5. Selbsttests mit `say` über Lautsprecher sind unzuverlässig (Stille-Gate/
   Halluzination) — Aussagen über Log-Zeitstempel treffen, nicht über den
   erkannten Text. Für alles, was echte Tasten/Mikro braucht: Nutzer bitten.
6. Nach Abschluss jedes Pakets Memory (`localflow-project`) aktualisieren.

## Startbefehl für Sonnet 5

`git -C ~/Downloads/localflow status` prüfen (es LIEGEN uncommittete
Vorwärm-Änderungen vor — die gehören zu P1.1 und werden zusammen mit P0.1–
P0.4 als v0.6.1 gebündelt, NICHT wegwerfen!). Dann P0.1 beginnen.
