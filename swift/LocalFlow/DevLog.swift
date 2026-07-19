import Foundation

/// Einfaches Datei-Log nach ~/.localflow/logs/swift-dev.log.
///
/// WARUM eine eigene Datei statt NSLog: macOS zensiert NSLog-Inhalte im
/// System-Protokoll standardmäßig als "<private>", und `log show` ist beim
/// Debuggen entsprechend nutzlos. Die Python-Seite loggt aus demselben Grund
/// ebenfalls in eine eigene Datei (siehe localflow/main.py `_setup_logging`).
enum DevLog {
    static let fileURL: URL = {
        let dir = URL(fileURLWithPath: NSHomeDirectory() + "/.localflow/logs")
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        return dir.appendingPathComponent("swift-dev.log")
    }()

    // Gleiche Werte wie RotatingFileHandler(maxBytes=500_000, backupCount=2)
    // auf der Python-Seite (localflow/main.py _setup_logging) — sonst wächst
    // diese Datei hier unbegrenzt, während das Python-Log längst rotiert.
    private static let maxBytes = 500_000
    private static let backupCount = 2

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
            rotateIfNeeded(nextWriteSize: data.count)
            if let handle = try? FileHandle(forWritingTo: fileURL) {
                handle.seekToEndOfFile()
                handle.write(data)
                try? handle.close()
            } else {
                try? data.write(to: fileURL)
            }
        }
    }

    /// Rotation wie Python `RotatingFileHandler`: swift-dev.log -> .1 -> .2,
    /// die älteste Generation fällt weg. Läuft auf derselben Queue wie log()
    /// selbst — kein zusätzliches Locking gegen gleichzeitige Schreibzugriffe
    /// nötig, die Queue serialisiert das ohnehin.
    private static func rotateIfNeeded(nextWriteSize: Int) {
        let fm = FileManager.default
        let attrs = try? fm.attributesOfItem(atPath: fileURL.path)
        let currentSize = (attrs?[.size] as? Int) ?? 0
        guard currentSize + nextWriteSize > maxBytes else { return }

        let dir = fileURL.deletingLastPathComponent()
        let base = fileURL.lastPathComponent

        let oldest = dir.appendingPathComponent("\(base).\(backupCount)")
        try? fm.removeItem(at: oldest)
        if backupCount > 1 {
            for i in stride(from: backupCount - 1, through: 1, by: -1) {
                let src = dir.appendingPathComponent("\(base).\(i)")
                let dst = dir.appendingPathComponent("\(base).\(i + 1)")
                try? fm.removeItem(at: dst)
                try? fm.moveItem(at: src, to: dst)
            }
        }
        let firstBackup = dir.appendingPathComponent("\(base).1")
        try? fm.removeItem(at: firstBackup)
        try? fm.moveItem(at: fileURL, to: firstBackup)
    }
}
