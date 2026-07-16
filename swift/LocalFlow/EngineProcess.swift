import Foundation

/// Startet, überwacht und beendet den Python-Engine-Prozess (LocalFlow-Engine,
/// gebaut aus packaging/LocalFlow.spec — derselbe Code wie server.py, nur ohne
/// Menüleiste/rumps). Die Swift-App übernimmt Menüleiste/Hotkey/Aufnahme/
/// Einfügen selbst; die Engine bleibt ein reiner lokaler HTTP-Dienst.
final class EngineProcess {
    enum State {
        case stopped, starting, running, crashed
    }

    static let defaultPort = 8790

    private(set) var state: State = .stopped
    private var process: Process?
    private let port: Int
    private let engineURL: URL
    private var onStateChange: ((State) -> Void)?
    private var pollTimer: Timer?

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
        guard FileManager.default.fileExists(atPath: engineURL.path) else {
            NSLog("LocalFlow: Engine-Binary fehlt unter %@", engineURL.path)
            setState(.crashed)
            return
        }

        let p = Process()
        p.executableURL = engineURL
        p.arguments = ["--serve-only", "--port", String(port)]
        p.terminationHandler = { [weak self] _ in
            DispatchQueue.main.async {
                guard let self = self, self.state != .stopped else { return }
                self.setState(.crashed)
            }
        }
        do {
            try p.run()
            process = p
            setState(.starting)
            startHealthPolling()
        } catch {
            NSLog("LocalFlow: Engine-Start fehlgeschlagen: %@", String(describing: error))
            setState(.crashed)
        }
    }

    /// Sauberer Shutdown: schickt SIGTERM (main.py fängt das ab, siehe
    /// localflow/main.py) statt SIGKILL, damit der Prozess kontrolliert endet.
    func stop() {
        pollTimer?.invalidate()
        pollTimer = nil
        let wasActive = state != .stopped
        setState(.stopped)
        if wasActive {
            process?.terminate()
        }
        process = nil
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
                }
            }
        }
    }
}
