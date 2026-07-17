import Foundation

/// Einfaches Datei-Log nach ~/.localflow/logs/swift-dev.log.
///
/// WARUM eine eigene Datei statt NSLog: macOS zensiert NSLog-Inhalte im
/// System-Protokoll standardmäßig als "<private>", und `log show` ist beim
/// Debuggen entsprechend nutzlos. Die Python-Seite loggt aus demselben Grund
/// ebenfalls in eine eigene Datei (siehe localflow/main.py `_setup_logging`).
enum DevLog {
    private static let url: URL = {
        let dir = URL(fileURLWithPath: NSHomeDirectory() + "/.localflow/logs")
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        return dir.appendingPathComponent("swift-dev.log")
    }()

    private static let queue = DispatchQueue(label: "studio.minh.localflow.devlog")

    private static let formatter: DateFormatter = {
        let f = DateFormatter()
        f.dateFormat = "HH:mm:ss.SSS"
        return f
    }()

    static func log(_ message: String) {
        let line = "\(formatter.string(from: Date())) \(message)\n"
        queue.async {
            guard let data = line.data(using: .utf8) else { return }
            if let handle = try? FileHandle(forWritingTo: url) {
                handle.seekToEndOfFile()
                handle.write(data)
                try? handle.close()
            } else {
                try? data.write(to: url)
            }
        }
    }
}
