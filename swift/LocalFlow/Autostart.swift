import ServiceManagement

/// Autostart bei der Anmeldung — Gegenstück zu localflow/autostart.py, dort
/// über einen LaunchAgent-Plist gelöst. Hier reicht SMAppService.mainApp
/// (macOS 13+, siehe LSMinimumSystemVersion): registriert/entfernt die App
/// selbst als Login-Item, ganz ohne eigene Plist-Verwaltung.
enum Autostart {
    static var enabled: Bool {
        SMAppService.mainApp.status == .enabled
    }

    @discardableResult
    static func setEnabled(_ value: Bool) -> Bool {
        do {
            if value {
                try SMAppService.mainApp.register()
            } else {
                try SMAppService.mainApp.unregister()
            }
            DevLog.log("Autostart \(value ? "aktiviert" : "deaktiviert")")
            return true
        } catch {
            DevLog.log("Autostart-Änderung fehlgeschlagen: \(error)")
            return false
        }
    }
}
