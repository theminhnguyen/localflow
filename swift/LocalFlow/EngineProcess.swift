import Foundation

/// Startet, überwacht und beendet den Python-Engine-Prozess (LocalFlow-Engine,
/// gebaut aus packaging/LocalFlow.spec — derselbe Code wie server.py, nur ohne
/// Menüleiste/rumps). Die Swift-App übernimmt Menüleiste/Hotkey/Aufnahme/
/// Einfügen selbst; die Engine bleibt ein reiner lokaler HTTP-Dienst.
final class EngineProcess {
    enum State {
        case stopped, starting, running, crashed
    }

    // Derselbe Port, den vorher die Python-App belegte — die Swift-Hülle ist
    // jetzt die Produktions-App (Phase 3.4), kein Grund mehr für einen
    // eigenen Entwicklungs-Port.
    static let defaultPort = 8790

    /// Backoff zwischen automatischen Neustart-Versuchen nach einem Absturz.
    /// Nach so vielen erfolglosen Versuchen IN FOLGE geben wir auf — das Menü
    /// bietet dann "Engine neu starten" als manuelle Aktion an, statt endlos
    /// im Hintergrund weiterzuversuchen.
    private static let restartDelays: [TimeInterval] = [1, 5, 15]

    private(set) var state: State = .stopped
    private var process: Process?
    private let port: Int
    private let engineURL: URL
    private var onStateChange: ((State) -> Void)?
    private var pollTimer: Timer?
    private var logHandle: FileHandle?
    private var restartAttempts = 0
    /// false nach explizitem stop() — unterscheidet "gewollt beendet" von
    /// "abgestürzt" zuverlässiger als ein reiner State-Vergleich.
    private var wantsRunning = false

    init(port: Int = EngineProcess.defaultPort) {
        self.port = port
        if let bundled = Bundle.main.url(forResource: "LocalFlow-Engine", withExtension: nil,
                                          subdirectory: "engine") {
            engineURL = bundled
        } else {
            // Entwicklungs-Fallback: PyInstaller-Output direkt aus dist/ nutzen,
            // ohne es erst ins App-Bundle zu kopieren (siehe packaging/LocalFlow.spec).
            engineURL = URL(fileURLWithPath: NSHomeDirectory()
                + "/Downloads/localflow/dist/LocalFlow-Engine/LocalFlow-Engine")
        }
    }

    func start(onStateChange: @escaping (State) -> Void) {
        self.onStateChange = onStateChange
        wantsRunning = true
        restartAttempts = 0
        launch()
    }

    /// Manueller Neustart — z.B. Menüpunkt "Engine neu starten", nachdem die
    /// automatischen Versuche aufgegeben haben. Setzt den Versuchszähler zurück.
    func restart() {
        wantsRunning = true
        restartAttempts = 0
        process?.terminate()
        launch()
    }

    /// Sauberer Shutdown: schickt SIGTERM (main.py fängt das ab, siehe
    /// localflow/main.py) statt SIGKILL, damit der Prozess kontrolliert endet.
    func stop() {
        wantsRunning = false
        pollTimer?.invalidate()
        pollTimer = nil
        let wasActive = state != .stopped
        setState(.stopped)
        if wasActive {
            process?.terminate()
        }
        process = nil
        logHandle?.closeFile()
        logHandle = nil
    }

    private func launch() {
        guard FileManager.default.fileExists(atPath: engineURL.path) else {
            DevLog.log("EngineProcess: ✗ Engine-Binary fehlt unter \(engineURL.path)")
            setState(.crashed)
            return
        }

        let p = Process()
        p.executableURL = engineURL
        p.arguments = ["--serve-only", "--port", String(port)]

        // Engine-Log mitschreiben statt ins Leere laufen zu lassen — sonst sind
        // Startfehler (z.B. Port belegt) von außen unsichtbar. Altes Handle vor
        // dem Ersetzen explizit schließen statt auf ARC-Aufräumen zu vertrauen.
        logHandle?.closeFile()
        logHandle = openLogHandle()
        p.standardOutput = logHandle
        p.standardError = logHandle

        // Identität statt reinem State-Flag prüfen: bei einem manuellen restart()
        // wird der alte Prozess beendet und SOFORT ein neuer gestartet — dessen
        // terminationHandler feuert aber erst asynchron danach. Ohne diesen
        // Vergleich würde der veraltete Handler fälschlich einen ZWEITEN
        // Neustart obendrauf auslösen.
        p.terminationHandler = { [weak self] finishedProcess in
            DispatchQueue.main.async {
                guard let self = self, self.process === finishedProcess else { return }
                self.handleTermination()
            }
        }
        do {
            try p.run()
            process = p
            setState(.starting)
            startHealthPolling()
        } catch {
            DevLog.log("EngineProcess: ✗ Start fehlgeschlagen: \(error)")
            process = p  // damit der folgende Identitätsvergleich in handleTermination greift
            handleTermination()
        }
    }

    private func openLogHandle() -> FileHandle? {
        let logURL = FileManager.default.temporaryDirectory.appendingPathComponent("localflow-engine.log")
        FileManager.default.createFile(atPath: logURL.path, contents: nil)
        let handle = try? FileHandle(forWritingTo: logURL)
        DevLog.log("EngineProcess: Engine-Log unter \(logURL.path)")
        return handle
    }

    /// Reagiert auf einen beendeten Prozess — ob Absturz oder gescheiterter Start.
    private func handleTermination() {
        guard wantsRunning else { return }  // stop() war absichtlich, nichts zu tun
        pollTimer?.invalidate()
        pollTimer = nil
        setState(.crashed)

        guard restartAttempts < Self.restartDelays.count else {
            DevLog.log("EngineProcess: ✗ \(restartAttempts) Neustart-Versuche erfolglos — "
                + "gebe auf. Manueller Neustart über das Menü nötig.")
            return
        }
        let delay = Self.restartDelays[restartAttempts]
        restartAttempts += 1
        DevLog.log("EngineProcess: Absturz erkannt — Neustart-Versuch "
            + "\(restartAttempts)/\(Self.restartDelays.count) in \(delay)s")
        DispatchQueue.main.asyncAfter(deadline: .now() + delay) { [weak self] in
            guard let self = self, self.wantsRunning else { return }
            self.launch()
        }
    }

    private func setState(_ newState: State) {
        state = newState
        onStateChange?(newState)
    }

    private func startHealthPolling() {
        pollTimer?.invalidate()
        let timer = Timer(timeInterval: 1.0, repeats: true) { [weak self] _ in
            self?.checkHealth()
        }
        RunLoop.main.add(timer, forMode: .common)
        pollTimer = timer
    }

    private func checkHealth() {
        LocalFlowAPI.shared.port = port
        LocalFlowAPI.shared.ping { [weak self] ok in
            DispatchQueue.main.async {
                guard let self = self else { return }
                if ok, self.state == .starting {
                    self.setState(.running)
                    // Wieder gesund erreicht -> voller Neustart-Kredit für einen
                    // künftigen, unabhängigen Absturz (kein "verbrauchtes" Budget
                    // von einem Vorfall vor Tagen).
                    self.restartAttempts = 0
                }
            }
        }
    }
}
