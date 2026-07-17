import Cocoa
import AVFoundation

final class AppDelegate: NSObject, NSApplicationDelegate {
    private var statusItem: NSStatusItem!
    private let engine = EngineProcess()
    private let recorder = Recorder()
    private var hotkey: HotkeyTap?
    private var engineReady = false

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.accessory)  // kein Dock-Icon (Menüleisten-App)

        DevLog.log("=== LocalFlow (Swift) gestartet ===")
        logPermissions()

        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.squareLength)
        statusItem.button?.title = "🎙️"

        render(status: "Startet Engine…")
        engine.start { [weak self] state in
            self?.handleEngineState(state)
        }

        requestInputMonitoringIfNeeded()
        requestAccessibilityIfNeeded()

        hotkey = HotkeyTap(key: HotkeyKey.configured(),
                            onPress: { [weak self] in self?.onHotkeyPress() },
                            onRelease: { [weak self] in self?.onHotkeyRelease() })
        hotkey?.start()

        // Explizit anfragen statt auf den ersten Aufnahme-Versuch zu warten —
        // sonst taucht die App erst in den Systemeinstellungen auf, nachdem der
        // Hotkey schon einmal ausgelöst hat.
        AVCaptureDevice.requestAccess(for: .audio) { granted in
            DevLog.log("Mikrofon-Zugriff: \(granted ? "erteilt" : "ABGELEHNT")")
        }
    }

    func applicationWillTerminate(_ notification: Notification) {
        recorder.stop()
        hotkey?.stop()
        engine.stop()
    }

    /// Löst den System-Dialog für Eingabemonitoring aus, wenn die Berechtigung
    /// fehlt (Gegenstück zu hotkey.request_permissions() auf der Python-Seite).
    ///
    /// WICHTIG: Ohne diese Anfrage bleibt der Hotkey stumm, OHNE dass irgendwas
    /// fehlschlägt — CGEvent.tapCreate liefert auch ohne Berechtigung einen
    /// gültigen Tap zurück, der dann einfach nie ein Ereignis bekommt.
    /// Nach dem Erteilen ist ein Neustart der App nötig: CGPreflight*Access()
    /// ist pro Prozess gecacht und der Tap muss neu erstellt werden.
    private func requestInputMonitoringIfNeeded() {
        guard !CGPreflightListenEventAccess() else { return }
        DevLog.log("Eingabemonitoring fehlt — löse System-Dialog aus")
        let granted = CGRequestListenEventAccess()
        DevLog.log("CGRequestListenEventAccess -> \(granted) "
            + "(false ist normal: der Dialog läuft asynchron, danach App neu starten)")
    }

    /// Bedienungshilfen werden fürs simulierte ⌘V gebraucht (siehe Paster).
    private func requestAccessibilityIfNeeded() {
        guard !CGPreflightPostEventAccess() else { return }
        DevLog.log("Bedienungshilfen fehlen — löse System-Dialog aus")
        let granted = CGRequestPostEventAccess()
        DevLog.log("CGRequestPostEventAccess -> \(granted) (danach App neu starten)")
    }

    private func logPermissions() {
        let listen = CGPreflightListenEventAccess()   // Eingabemonitoring
        let post = CGPreflightPostEventAccess()       // Bedienungshilfen
        let mic = AVCaptureDevice.authorizationStatus(for: .audio)
        DevLog.log("Berechtigungen: Eingabemonitoring=\(listen) Bedienungshilfen=\(post) "
            + "Mikrofon=\(mic.rawValue) (0=unbestimmt 1=abgelehnt 2=verweigert 3=erteilt)")
        DevLog.log("Bundle-Pfad: \(Bundle.main.bundlePath)")
        DevLog.log("Bundle-ID: \(Bundle.main.bundleIdentifier ?? "?")")
    }

    // ---- Engine-Status ----

    private func handleEngineState(_ state: EngineProcess.State) {
        switch state {
        case .stopped:
            engineReady = false
            render(status: "Gestoppt")
        case .starting:
            engineReady = false
            render(status: "Startet Engine…")
        case .running:
            engineReady = true
            DevLog.log("Engine bereit")
            render(status: "Bereit")
        case .crashed:
            engineReady = false
            DevLog.log("Engine abgestürzt")
            render(status: "Fehler — siehe ~/.localflow/logs/swift-dev.log")
        }
    }

    // ---- Diktat-Ablauf (Hotkey-Callbacks) ----

    private func onHotkeyPress() {
        DevLog.log("onHotkeyPress (engineReady=\(engineReady) recording=\(recorder.isRecording))")
        guard engineReady, !recorder.isRecording else { return }
        do {
            try recorder.start()
            render(status: "Nimmt auf…")
        } catch {
            DevLog.log("Mikrofon-Start fehlgeschlagen: \(error)")
            render(status: "Mikrofon-Fehler — Berechtigung prüfen")
        }
    }

    private func onHotkeyRelease() {
        DevLog.log("onHotkeyRelease")
        guard let url = recorder.stop() else {
            DevLog.log("stop() lieferte keine Datei (Aufnahme lief nicht)")
            return
        }
        render(status: "Verarbeitet…")
        LocalFlowAPI.shared.transcribe(fileURL: url) { [weak self] result in
            try? FileManager.default.removeItem(at: url)
            switch result {
            case .success(let r):
                DevLog.log("Transkription ok: \"\(r.text)\"")
                guard !r.text.isEmpty else {
                    self?.flash(status: "Bereit")
                    return
                }
                // Paster blockiert (wartet auf losgelassene Modifier) -> nicht auf den
                // Haupt-Thread legen, sonst friert die Menüleiste ein.
                let inserted = Paster.insert(r.text)
                DevLog.log("Einfügen: \(inserted ? "ok" : "fehlgeschlagen")")
                self?.flash(status: inserted ? "Eingefügt ✓" : "In der Zwischenablage (⌘V)")
            case .failure(let error):
                DevLog.log("Transkription fehlgeschlagen: \(error)")
                self?.flash(status: "Fehler beim Diktieren")
            }
        }
    }

    /// Kurze Rückmeldung im Menü, danach zurück auf den Normalstatus.
    private func flash(status: String) {
        DispatchQueue.main.async {
            self.render(status: status)
            DispatchQueue.main.asyncAfter(deadline: .now() + 1.5) {
                self.render(status: self.engineReady ? "Bereit" : "Startet Engine…")
            }
        }
    }

    // ---- Menü ----

    private func render(status: String) {
        let menu = NSMenu()
        menu.addItem(NSMenuItem(title: "LocalFlow — \(status)", action: nil, keyEquivalent: ""))
        menu.addItem(NSMenuItem.separator())
        menu.addItem(withTitle: "Beenden", action: #selector(quit), keyEquivalent: "q", target: self)
        statusItem.menu = menu
    }

    @objc private func quit() {
        NSApp.terminate(nil)
    }
}

private extension NSMenu {
    @discardableResult
    func addItem(withTitle title: String, action: Selector, keyEquivalent: String,
                 target: AnyObject) -> NSMenuItem {
        let item = NSMenuItem(title: title, action: action, keyEquivalent: keyEquivalent)
        item.target = target
        addItem(item)
        return item
    }
}
