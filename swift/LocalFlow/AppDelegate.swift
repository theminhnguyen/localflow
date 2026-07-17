import Cocoa
import AVFoundation

/// Menüleiste und App-Leben. Die Diktier-Logik steckt im FlowController, der
/// Python-Dienst im EngineProcess — analog zur Trennung menubar.py / main.py.
final class AppDelegate: NSObject, NSApplicationDelegate {
    private var statusItem: NSStatusItem!
    private let engine = EngineProcess()
    private let flow = FlowController()
    private var status = "Startet Engine…"

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.accessory)  // kein Dock-Icon (Menüleisten-App)

        DevLog.log("=== LocalFlow (Swift) gestartet ===")
        logPermissions()

        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.squareLength)
        statusItem.button?.title = "🎙️"
        render()

        engine.start { [weak self] state in
            self?.handleEngineState(state)
        }

        requestInputMonitoringIfNeeded()
        requestAccessibilityIfNeeded()

        flow.onStatus = { [weak self] text in
            self?.status = text
            self?.render()
        }
        flow.start()

        // Explizit anfragen statt auf den ersten Aufnahme-Versuch zu warten —
        // sonst taucht die App erst in den Systemeinstellungen auf, nachdem der
        // Hotkey schon einmal ausgelöst hat.
        AVCaptureDevice.requestAccess(for: .audio) { granted in
            DevLog.log("Mikrofon-Zugriff: \(granted ? "erteilt" : "ABGELEHNT")")
        }
    }

    func applicationWillTerminate(_ notification: Notification) {
        flow.stop()
        engine.stop()
    }

    // ---- Berechtigungen ----

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
            flow.engineReady = false
            status = "Gestoppt"
        case .starting:
            flow.engineReady = false
            status = "Startet Engine…"
        case .running:
            flow.engineReady = true
            DevLog.log("Engine bereit")
            status = "Bereit"
        case .crashed:
            flow.engineReady = false
            DevLog.log("Engine abgestürzt")
            status = "Fehler — siehe Log"
        }
        render()
    }

    // ---- Menü ----

    private func render() {
        let menu = NSMenu()
        menu.addItem(NSMenuItem(title: "LocalFlow — \(status)", action: nil, keyEquivalent: ""))
        menu.addItem(NSMenuItem.separator())
        menu.addItem(withTitle: "⚙️ Einstellungen im Browser öffnen…",
                     action: #selector(openSettings), target: self)
        let copyItem = menu.addItem(withTitle: "📋 Letzten Text kopieren",
                                     action: #selector(copyLastText), target: self)
        copyItem.isEnabled = flow.lastText != nil
        menu.addItem(NSMenuItem.separator())
        menu.addItem(withTitle: "🩺 Log öffnen", action: #selector(openLog), target: self)
        menu.addItem(withTitle: "Beenden", action: #selector(quit),
                     keyEquivalent: "q", target: self)
        statusItem.menu = menu
    }

    /// Die vorhandene Web-Einstellungsseite der Engine (Paket 2.2) — 127.0.0.1,
    /// weil deren Zertifikat diese Adresse immer abdeckt. Token als Fragment
    /// ("#k="), damit es in keinem Zugriffs-Log landet (siehe menubar._url()).
    @objc private func openSettings() {
        guard let token = LocalFlowToken.current else {
            DevLog.log("Kein Kopplungs-Token gefunden — Einstellungen nicht erreichbar")
            return
        }
        let url = "https://127.0.0.1:\(EngineProcess.defaultPort)/settings#k=\(token)"
        NSWorkspace.shared.open(URL(string: url)!)
    }

    @objc private func copyLastText() {
        guard let text = flow.lastText else { return }
        let pasteboard = NSPasteboard.general
        pasteboard.clearContents()
        pasteboard.setString(text, forType: .string)
    }

    @objc private func openLog() {
        NSWorkspace.shared.open(DevLog.fileURL)
    }

    @objc private func quit() {
        NSApp.terminate(nil)
    }
}

private extension NSMenu {
    @discardableResult
    func addItem(withTitle title: String, action: Selector, keyEquivalent: String = "",
                 target: AnyObject) -> NSMenuItem {
        let item = NSMenuItem(title: title, action: action, keyEquivalent: keyEquivalent)
        item.target = target
        addItem(item)
        return item
    }
}
