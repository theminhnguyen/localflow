import Foundation

/// Ablauf-Logik des Diktierens — das Gegenstück zu FlowController in
/// localflow/main.py: Taste halten → aufnehmen → transkribieren → einfügen,
/// dazu Freihand-Modus per Doppel-Tipp.
final class FlowController {
    /// Kürzer als das = „Tipp" statt Diktat (TAP_MAX_S in main.py).
    private static let tapMax: TimeInterval = 0.35
    /// Zwei Tipps innerhalb dieser Zeit = Freihand einrasten (DOUBLE_TAP_S).
    private static let doubleTap: TimeInterval = 0.6

    private let recorder = Recorder()
    private var hotkey: HotkeyTap?

    /// EIN Worker, der Diktate der Reihe nach abarbeitet. Ohne ihn könnten zwei
    /// schnell aufeinanderfolgende Diktate gleichzeitig hochladen und in
    /// vertauschter Reihenfolge eingefügt werden — man kann ja sofort weiter-
    /// sprechen, während das vorige noch verarbeitet wird. Entspricht der
    /// Warteschlange plus _work_loop in main.py.
    private let worker = DispatchQueue(label: "studio.minh.localflow.worker")

    private var recordingStarted: Date?
    private var lastTap: Date?
    private var locked = false

    /// Zuletzt eingefügter Text (fürs Menü „Letzten Text kopieren").
    private(set) var lastText: String?

    var engineReady = false
    /// Wird immer auf dem Haupt-Thread gerufen (die Menüleiste malt nur dort).
    var onStatus: ((String) -> Void)?

    func start() {
        let key = HotkeyKey.configured()
        hotkey = HotkeyTap(key: key,
                            onPress: { [weak self] in self?.onPress() },
                            onRelease: { [weak self] in self?.onRelease() })
        hotkey?.start()
    }

    func stop() {
        hotkey?.stop()
        recorder.stop()
    }

    // ---- Hotkey-Rückrufe (schnell und ausnahmesicher halten) ----

    private func onPress() {
        guard engineReady else {
            DevLog.log("Diktat ignoriert — Engine noch nicht bereit")
            return
        }
        guard !recorder.isRecording else { return }  // läuft schon (z.B. Freihand)
        do {
            try recorder.start()
        } catch {
            DevLog.log("Mikrofon-Start fehlgeschlagen: \(error)")
            Sounds.play(.error)
            status("Mikrofon-Fehler — Berechtigung prüfen")
            return
        }
        locked = false
        recordingStarted = Date()
        Sounds.play(.start)
        status("Nimmt auf…")
        // Ausgekühlte Kernel vorwärmen, während aufgenommen wird (siehe
        // engine.prewarm_if_cold / server.py /api/prewarm) — spart den
        // Kalt-Aufschlag des ersten Diktats nach einer Pause.
        LocalFlowAPI.shared.prewarm()
    }

    private func onRelease() {
        guard recorder.isRecording, let started = recordingStarted else { return }
        let now = Date()
        let duration = now.timeIntervalSince(started)

        // Eingerastete Aufnahme: jeder weitere Tastendruck beendet sie.
        if locked {
            finish()
            return
        }

        if duration < Self.tapMax {
            // Nur ein Tipp -> Aufnahme verwerfen …
            if let url = recorder.stop() { try? FileManager.default.removeItem(at: url) }
            // … außer es ist der zweite Tipp -> Freihand einrasten.
            if Config.bool("handsfree", true), let last = lastTap,
               now.timeIntervalSince(last) < Self.doubleTap {
                lastTap = nil
                do {
                    try recorder.start()
                } catch {
                    DevLog.log("Freihand-Start fehlgeschlagen: \(error)")
                    Sounds.play(.error)
                    status("Bereit")
                    return
                }
                locked = true
                recordingStarted = now
                Sounds.play(.lock)
                status("Freihand — Taste tippen zum Beenden")
            } else {
                lastTap = now
                status("Bereit")
            }
            return
        }

        finish()
    }

    /// Aufnahme beenden und einreihen — darf nie blockieren.
    private func finish() {
        guard let url = recorder.stop() else { return }
        locked = false
        recordingStarted = nil
        Sounds.play(.stop)

        guard isLongEnough(url) else {
            DevLog.log("Aufnahme zu kurz — verworfen")
            try? FileManager.default.removeItem(at: url)
            status("Bereit")
            return
        }
        status("Verarbeitet…")
        enqueue(url)
    }

    /// Zu kurze Aufnahmen gar nicht erst hochladen (min_duration in config.py) —
    /// die Engine würde sie ohnehin mit 400 ablehnen.
    private func isLongEnough(_ url: URL) -> Bool {
        let attrs = try? FileManager.default.attributesOfItem(atPath: url.path)
        let bytes = (attrs?[.size] as? Int) ?? 0
        let header = 44  // WAV-Kopf
        let bytesPerSecond = 16000.0 * 2.0  // 16 kHz, 16 bit, mono
        let seconds = Double(max(0, bytes - header)) / bytesPerSecond
        return seconds >= Config.double("min_duration", 0.3)
    }

    private func enqueue(_ url: URL) {
        worker.async { [weak self] in
            guard let self = self else { return }

            // Auf das Ergebnis warten, damit der Worker wirklich seriell bleibt.
            // Blockiert nur diesen einen Thread — Aufnahme und Menü laufen weiter.
            var outcome: Result<TranscribeResult, Error>?
            let done = DispatchSemaphore(value: 0)
            LocalFlowAPI.shared.transcribe(fileURL: url) { result in
                outcome = result
                done.signal()
            }
            done.wait()
            try? FileManager.default.removeItem(at: url)

            switch outcome {
            case .success(let result):
                DevLog.log("Transkription ok: \"\(result.text)\"")
                guard !result.text.isEmpty else {
                    self.flash("Bereit")
                    return
                }
                // Auch das Einfügen läuft hier auf dem Worker: Paster wartet ggf.
                // auf losgelassene Modifier-Tasten und darf niemand anderen aufhalten.
                let inserted = Paster.insert(result.text)
                DevLog.log("Einfügen: \(inserted ? "ok" : "fehlgeschlagen")")
                // Auf dem Haupt-Thread schreiben: AppDelegate.render() liest
                // lastText beim Menü-Aufbau auf dem Haupt-Thread — ohne das wäre
                // dies ein unsynchronisierter Zugriff von zwei Threads auf
                // dieselbe Property (Datenrennen).
                let text = result.text
                DispatchQueue.main.async { self.lastText = text }
                if !inserted { Sounds.play(.error) }
                self.flash(inserted ? "Eingefügt ✓" : "In der Zwischenablage (⌘V)")
            case .failure(let error):
                DevLog.log("Transkription fehlgeschlagen: \(error)")
                Sounds.play(.error)
                self.flash("Fehler beim Diktieren")
            case nil:
                self.flash("Bereit")
            }
        }
    }

    // ---- Status ----

    private func status(_ text: String) {
        DispatchQueue.main.async { self.onStatus?(text) }
    }

    /// Kurze Rückmeldung, danach zurück auf den Normalstatus.
    private func flash(_ text: String) {
        status(text)
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.5) { [weak self] in
            guard let self = self, !self.recorder.isRecording else { return }
            self.onStatus?(self.engineReady ? "Bereit" : "Startet Engine…")
        }
    }
}
