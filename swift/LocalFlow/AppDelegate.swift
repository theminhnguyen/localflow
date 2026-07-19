import Cocoa
import AVFoundation
import UniformTypeIdentifiers

/// Menüleiste und App-Leben. Die Diktier-Logik steckt im FlowController, der
/// Python-Dienst im EngineProcess — analog zur Trennung menubar.py / main.py.
final class AppDelegate: NSObject, NSApplicationDelegate {
    private var statusItem: NSStatusItem!
    private let engine = EngineProcess()
    private let flow = FlowController()
    private var status = "Startet Engine…"
    private var engineState: EngineProcess.State = .starting
    private var updateAvailable: (tag: String, url: String)?
    private var updateTimer: Timer?
    private var qrWindowController: QRWindowController?
    private var historyEntries: [HistoryEntry] = []

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

        // Vor den Berechtigungs-Dialogen zeigen, nicht danach — sonst poppen
        // die System-Dialoge scheinbar aus dem Nichts auf.
        Onboarding.showIfNeeded()

        requestInputMonitoringIfNeeded()
        requestAccessibilityIfNeeded()

        flow.onStatus = { [weak self] text in
            self?.status = text
            self?.render()
        }
        flow.onDictationComplete = { [weak self] in self?.refreshHistory() }
        flow.start()

        // Explizit anfragen statt auf den ersten Aufnahme-Versuch zu warten —
        // sonst taucht die App erst in den Systemeinstellungen auf, nachdem der
        // Hotkey schon einmal ausgelöst hat.
        AVCaptureDevice.requestAccess(for: .audio) { granted in
            DevLog.log("Mikrofon-Zugriff: \(granted ? "erteilt" : "ABGELEHNT")")
        }

        scheduleUpdateChecks()
    }

    func applicationWillTerminate(_ notification: Notification) {
        updateTimer?.invalidate()
        flow.stop()
        engine.stop()
    }

    // ---- Update-Check (still im Hintergrund, nie blockierend) ----
    //
    // Dieselbe Zeitplanung wie main.py _update_check_loop: App-Start bleibt
    // schlank (Netzwerk erst nach 60s), danach alle 24h. Prüft die eigentliche
    // GitHub-Logik über den Engine-Endpunkt /api/update-check (server.py) —
    // kein Grund, das ein zweites Mal in Swift nachzubauen.

    private func scheduleUpdateChecks() {
        DispatchQueue.main.asyncAfter(deadline: .now() + 60) { [weak self] in
            self?.performAutomaticUpdateCheck()
            let timer = Timer(timeInterval: 24 * 3600, repeats: true) { [weak self] _ in
                self?.performAutomaticUpdateCheck()
            }
            RunLoop.main.add(timer, forMode: .common)
            self?.updateTimer = timer
        }
    }

    /// Automatischer 24h-Check: respektiert den `update_check`-Schalter aus
    /// der Konfiguration und bleibt bei "kein Update" still (kein Alert).
    private func performAutomaticUpdateCheck() {
        guard Config.bool("update_check", true) else { return }
        LocalFlowAPI.shared.checkForUpdate { [weak self] result in
            guard let result = result else { return }
            DispatchQueue.main.async {
                guard let self = self else { return }
                DevLog.log("Update verfügbar: \(result.tag)")
                self.updateAvailable = result
                self.render()
            }
        }
    }

    /// Manueller Check über das Menü — meldet IMMER zurück (auch "kein
    /// Update"), unabhängig vom Schalter (main.py: manual=True-Verhalten).
    @objc private func checkForUpdateNow() {
        LocalFlowAPI.shared.checkForUpdate { [weak self] result in
            DispatchQueue.main.async {
                guard let self = self else { return }
                let alert = NSAlert()
                if let result = result {
                    self.updateAvailable = result
                    self.render()
                    alert.messageText = "Update verfügbar: \(result.tag)"
                    alert.informativeText = result.url
                } else {
                    alert.messageText = "Du nutzt bereits die neueste Version."
                }
                alert.runModal()
            }
        }
    }

    @objc private func openUpdate() {
        guard let update = updateAvailable, let url = URL(string: update.url) else { return }
        NSWorkspace.shared.open(url)
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
        engineState = state
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
            refreshHistory()
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
        if let update = updateAvailable {
            menu.addItem(withTitle: "⬆️ Update \(update.tag) verfügbar…",
                         action: #selector(openUpdate), target: self)
        }
        menu.addItem(NSMenuItem.separator())
        menu.addItem(withTitle: "⚙️ Einstellungen im Browser öffnen…",
                     action: #selector(openSettings), target: self)
        let autoItem = menu.addItem(withTitle: "🚀 Beim Anmelden starten",
                                     action: #selector(toggleAutostart), target: self)
        autoItem.state = Autostart.enabled ? .on : .off
        menu.addItem(withTitle: "📱 Handy koppeln", submenu: pairingSubmenu())
        menu.addItem(withTitle: "📄 Datei transkribieren…",
                     action: #selector(transcribeFile), target: self)
        menu.addItem(withTitle: "🌐 Sprache", submenu: languageSubmenu())
        menu.addItem(withTitle: "🕘 Verlauf", submenu: historySubmenu())
        let copyItem = menu.addItem(withTitle: "📋 Letzten Text kopieren",
                                     action: #selector(copyLastText), target: self)
        copyItem.isEnabled = flow.lastText != nil
        menu.addItem(NSMenuItem.separator())
        // Nur sichtbar, wenn die automatischen Neustart-Versuche aufgegeben haben
        // (EngineProcess.restartDelays ausgeschöpft) — sonst versucht die Engine
        // es ohnehin gerade selbst im Hintergrund erneut.
        if engineState == .crashed {
            menu.addItem(withTitle: "🔄 Engine neu starten", action: #selector(restartEngine),
                        target: self)
        }
        menu.addItem(withTitle: "📊 Status anzeigen", action: #selector(showStatus), target: self)
        menu.addItem(withTitle: "🩺 Log öffnen", action: #selector(openLog), target: self)
        menu.addItem(withTitle: "🔄 Jetzt nach Updates suchen",
                     action: #selector(checkForUpdateNow), target: self)
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

    @objc private func toggleAutostart() {
        Autostart.setEnabled(!Autostart.enabled)
        render()
    }

    // ---- Sprache ----

    private static let languages = [("Automatisch", "auto"), ("Deutsch", "de"), ("Englisch", "en")]

    /// Ließt den aktuellen Wert direkt aus config.json (Config.swift, kein
    /// Netzwerk nötig) — geschrieben wird über PUT /api/config, das server.py
    /// synchron persistiert, bevor die Antwort zurückkommt (main.py.set_language).
    private func languageSubmenu() -> NSMenu {
        let submenu = NSMenu()
        let current = Config.string("language") ?? "auto"
        for (label, code) in Self.languages {
            let item = submenu.addItem(withTitle: label, action: #selector(setLanguage(_:)),
                                        target: self)
            item.state = current == code ? .on : .off
            item.representedObject = code
        }
        return submenu
    }

    @objc private func setLanguage(_ sender: NSMenuItem) {
        guard let code = sender.representedObject as? String else { return }
        LocalFlowAPI.shared.setConfig("language", code) { [weak self] _ in
            DispatchQueue.main.async { self?.render() }
        }
    }

    // ---- Verlauf ----

    private func refreshHistory() {
        LocalFlowAPI.shared.fetchHistory { [weak self] entries in
            DispatchQueue.main.async {
                self?.historyEntries = entries
                self?.render()
            }
        }
    }

    /// Analog zu menubar._refresh_history(): bis zu 8 Einträge, auf 60 Zeichen
    /// gekürzt, 📱-Präfix für Handy-Diktate, Klick kopiert den vollen Text.
    private func historySubmenu() -> NSMenu {
        let submenu = NSMenu()
        if historyEntries.isEmpty {
            let empty = NSMenuItem(title: "(leer)", action: nil, keyEquivalent: "")
            empty.isEnabled = false
            submenu.addItem(empty)
        } else {
            for entry in historyEntries.prefix(8) {
                let icon = entry.source == "phone" ? "📱 " : ""
                let truncated = entry.text.count > 60
                    ? String(entry.text.prefix(60)) + "…" : entry.text
                let item = submenu.addItem(withTitle: icon + truncated,
                                            action: #selector(copyHistoryEntry(_:)), target: self)
                item.representedObject = entry.text
            }
        }
        submenu.addItem(NSMenuItem.separator())
        submenu.addItem(withTitle: "Verlauf leeren", action: #selector(clearHistoryMenu),
                        target: self)
        return submenu
    }

    @objc private func copyHistoryEntry(_ sender: NSMenuItem) {
        guard let text = sender.representedObject as? String else { return }
        let pasteboard = NSPasteboard.general
        pasteboard.clearContents()
        pasteboard.setString(text, forType: .string)
    }

    @objc private func clearHistoryMenu() {
        LocalFlowAPI.shared.clearHistory { [weak self] _ in
            DispatchQueue.main.async { self?.refreshHistory() }
        }
    }

    // ---- Diagnose ----

    /// Formatiert /api/status + lokal geprüfte Berechtigungen zu demselben
    /// Text wie main.py.status_report() — ohne eigenen Formatierungs-
    /// Endpunkt, die JSON-Rohdaten reichen.
    @objc private func showStatus() {
        LocalFlowAPI.shared.fetchStatus { json in
            DispatchQueue.main.async {
                let alert = NSAlert()
                alert.messageText = "LocalFlow — Status"
                alert.informativeText = Self.formatStatus(json)
                alert.runModal()
            }
        }
    }

    private static func formatStatus(_ json: [String: Any]?) -> String {
        guard let json = json else { return "Status konnte nicht geladen werden." }
        let version = json["version"] as? String ?? "?"
        let model = json["model"] as? String ?? "?"
        let loaded = json["loaded"] as? Bool ?? false
        let uptimeS = json["uptime_s"] as? Int ?? 0
        let stats = json["stats"] as? [String: Any] ?? [:]
        let count = stats["count"] as? Int ?? 0
        let audioS = (stats["audio_s"] as? NSNumber)?.doubleValue ?? 0
        let engineMs = stats["engine_ms"] as? Int ?? 0
        let avgMs = count > 0 ? engineMs / count : 0
        let llmUsed = stats["llm_used"] as? Int ?? 0
        let llm = json["llm"] as? [String: Any] ?? [:]
        let llmEnabled = llm["enabled"] as? Bool ?? false
        let llmLine: String
        if llm["ready"] as? Bool == true {
            let backend = llm["backend"] as? String ?? "?"
            let llmModel = llm["model"] as? String ?? "?"
            llmLine = "\(backend): \(llmModel) bereit"
        } else {
            let hint = llm["hint"] as? String ?? "?"
            llmLine = "kein LLM aktiv (\(hint))"
        }
        let lanIP = json["lan_ip"] as? String ?? "?"
        let port = json["port"] as? Int ?? 0
        func ok(_ v: Bool) -> String { v ? "✅" : "❌" }

        return """
        LocalFlow v\(version)
        Läuft seit: \(uptimeS / 3600)h \((uptimeS % 3600) / 60)min
        Modell: \(model) (\(loaded ? "geladen" : "lädt…"))
        Diktate: \(count)  ·  Audio: \(Int(audioS))s  ·  Ø Engine: \(avgMs)ms
        KI-Feinschliff: \(llmEnabled ? "an" : "aus") (\(llmLine))  ·  genutzt: \(llmUsed)×
        Eingabemonitoring: \(ok(CGPreflightListenEventAccess()))   \
        Bedienungshilfen: \(ok(CGPreflightPostEventAccess()))
        Server: https://\(lanIP):\(port)
        """
    }

    /// Untermenü mit beiden QR-Varianten (server.py: variant=lan|ts) — analog
    /// zu menubar._build_menu()s "📱 Handy koppeln". Die Tailscale-Option wird,
    /// anders als im Python-Menü, IMMER angezeigt (das Menü hier wird ohne
    /// Live-Status synchron aufgebaut); ist Tailscale nicht aktiv, meldet das
    /// der Endpunkt per 404 und ein Alert erklärt das statt eines leeren Bilds.
    private func pairingSubmenu() -> NSMenu {
        let submenu = NSMenu()
        submenu.addItem(withTitle: "QR-Code anzeigen (Heim-WLAN)",
                        action: #selector(showQRLan), target: self)
        submenu.addItem(withTitle: "QR-Code anzeigen (unterwegs/Tailscale)",
                        action: #selector(showQRTailscale), target: self)
        return submenu
    }

    @objc private func showQRLan() {
        showQR(variant: "lan", title: "LocalFlow — Handy koppeln (Heim-WLAN)")
    }

    @objc private func showQRTailscale() {
        showQR(variant: "ts", title: "LocalFlow — Handy koppeln (unterwegs)")
    }

    private func showQR(variant: String, title: String) {
        LocalFlowAPI.shared.fetchQR(variant: variant) { [weak self] data in
            DispatchQueue.main.async {
                guard let self = self else { return }
                guard let data = data, let image = NSImage(data: data) else {
                    let alert = NSAlert()
                    alert.messageText = variant == "ts"
                        ? "Tailscale ist nicht aktiv."
                        : "QR-Code konnte nicht geladen werden."
                    alert.runModal()
                    return
                }
                self.qrWindowController = QRWindowController(image: image, title: title)
                self.qrWindowController?.showWindow(nil)
                NSApp.activate(ignoringOtherApps: true)
                self.qrWindowController?.window?.makeKeyAndOrderFront(nil)
            }
        }
    }

    /// Beliebige Audio-/Videodatei transkribieren (Gegenstück zu
    /// menubar._transcribe_file()): läuft über denselben /api/transcribe-
    /// Endpunkt wie das Diktat, server.py.decode_upload() erkennt das Format
    /// an der Dateiendung. Ergebnis landet wie in Python als "<Datei>.txt"
    /// neben dem Original und wird mit der Standard-App dafür geöffnet.
    @objc private func transcribeFile() {
        let panel = NSOpenPanel()
        panel.title = "Audio- oder Videodatei transkribieren"
        panel.canChooseFiles = true
        panel.canChooseDirectories = false
        panel.allowsMultipleSelection = false
        panel.allowedContentTypes = [.audio, .movie]
        panel.begin { [weak self] response in
            guard response == .OK, let url = panel.url else { return }
            self?.runFileTranscription(url)
        }
    }

    private func runFileTranscription(_ url: URL) {
        LocalFlowAPI.shared.transcribe(fileURL: url, filename: url.lastPathComponent,
                                        timeout: 300) { result in
            DispatchQueue.main.async {
                switch result {
                case .success(let transcribed):
                    let outURL = URL(fileURLWithPath: url.path + ".txt")
                    do {
                        try transcribed.text.appending("\n").write(
                            to: outURL, atomically: true, encoding: .utf8)
                        NSWorkspace.shared.open(outURL)
                        DevLog.log("Datei transkribiert: \(url.lastPathComponent) -> \(outURL.lastPathComponent)")
                    } catch {
                        DevLog.log("Textdatei konnte nicht geschrieben werden: \(error)")
                    }
                case .failure(let error):
                    DevLog.log("Datei-Transkription fehlgeschlagen: \(error)")
                    let alert = NSAlert()
                    alert.messageText = "Datei-Transkription fehlgeschlagen (Format nicht lesbar?)"
                    alert.runModal()
                }
            }
        }
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

    @objc private func restartEngine() {
        DevLog.log("Manueller Engine-Neustart über das Menü")
        status = "Startet Engine…"
        render()
        engine.restart()
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

    @discardableResult
    func addItem(withTitle title: String, submenu: NSMenu) -> NSMenuItem {
        let item = NSMenuItem(title: title, action: nil, keyEquivalent: "")
        item.submenu = submenu
        addItem(item)
        return item
    }
}
