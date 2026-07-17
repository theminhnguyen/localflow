import Foundation

/// Liest ~/.localflow/config.json — dieselbe Datei, die auch die Python-Seite
/// nutzt (localflow/config.py). Bewusst bei jedem Zugriff frisch gelesen, statt
/// beim Start einmal zwischenzuspeichern: Änderungen über die Web-Einstellungs-
/// seite (/settings) greifen so ohne Neustart, genau wie bei der Python-App.
/// Die Datei ist wenige Kilobyte groß, Diktate liegen Sekunden auseinander —
/// die Lesekosten fallen nicht ins Gewicht.
enum Config {
    static func all() -> [String: Any] {
        let path = NSHomeDirectory() + "/.localflow/config.json"
        guard let data = FileManager.default.contents(atPath: path),
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
        else { return [:] }
        return json
    }

    static func bool(_ key: String, _ fallback: Bool) -> Bool {
        all()[key] as? Bool ?? fallback
    }

    static func string(_ key: String) -> String? {
        all()[key] as? String
    }

    static func double(_ key: String, _ fallback: Double) -> Double {
        if let n = all()[key] as? NSNumber { return n.doubleValue }
        return fallback
    }

    static func int(_ key: String, _ fallback: Int) -> Int {
        if let n = all()[key] as? NSNumber { return n.intValue }
        return fallback
    }
}
