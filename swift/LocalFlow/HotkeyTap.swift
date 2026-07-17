import Cocoa
import Carbon.HIToolbox

/// Unterstützte Hotkeys — Namen wie in localflow/hotkey.py (KEY_NAMES).
enum HotkeyKey: String {
    case altR = "alt_r"
    case altL = "alt_l"
    case cmdR = "cmd_r"
    case ctrlR = "ctrl_r"
    case f13 = "f13"
    case f14 = "f14"

    var keycode: CGKeyCode {
        switch self {
        case .altR: return CGKeyCode(kVK_RightOption)
        case .altL: return CGKeyCode(kVK_Option)
        case .cmdR: return CGKeyCode(kVK_RightCommand)
        case .ctrlR: return CGKeyCode(kVK_RightControl)
        case .f13: return CGKeyCode(kVK_F13)
        case .f14: return CGKeyCode(kVK_F14)
        }
    }

    /// Modifier-Tasten kommen über .flagsChanged, F-Tasten über keyDown/keyUp.
    var isModifier: Bool {
        switch self {
        case .altR, .altL, .cmdR, .ctrlR: return true
        case .f13, .f14: return false
        }
    }

    var modifierFlag: CGEventFlags {
        switch self {
        case .altR, .altL: return .maskAlternate
        case .cmdR: return .maskCommand
        case .ctrlR: return .maskControl
        case .f13, .f14: return []
        }
    }

    /// Welche Taste gilt? Reihenfolge: Start-Parameter `--hotkey <name>`
    /// (zum Testen: `open -a LocalFlow-Dev --args --hotkey alt_l` — muss über
    /// `open` laufen, denn beim Direktstart aus der Shell rechnet macOS die
    /// Berechtigungen dem Terminal statt der App zu), dann
    /// ~/.localflow/config.json (dieselbe Datei wie die Python-Seite — so
    /// bleiben beide Hälften konfigurationsgleich), sonst alt_r.
    static func configured() -> HotkeyKey {
        let args = CommandLine.arguments
        if let idx = args.firstIndex(of: "--hotkey"), idx + 1 < args.count,
           let key = HotkeyKey(rawValue: args[idx + 1]) {
            DevLog.log("Hotkey aus Start-Parameter: \(args[idx + 1])")
            return key
        }
        let path = NSHomeDirectory() + "/.localflow/config.json"
        if let data = FileManager.default.contents(atPath: path),
           let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
           let name = json["hotkey"] as? String {
            if let key = HotkeyKey(rawValue: name) { return key }
            DevLog.log("Unbekannter Hotkey '\(name)' in config.json — nutze alt_r")
        }
        return .altR
    }
}

/// Globaler Hold-to-talk-Hotkey über einen CGEventTap (braucht die
/// Eingabemonitoring-Berechtigung). Entspricht localflow/hotkey.py, das dort
/// über pynput läuft.
final class HotkeyTap {
    private let key: HotkeyKey
    private let onPress: () -> Void
    private let onRelease: () -> Void
    private var eventTap: CFMachPort?
    private var runLoopSource: CFRunLoopSource?
    private var isDown = false
    private var downSince: Date?
    private var watchdogTimer: Timer?

    /// So lange darf „Taste unten ohne Flag" bestehen, bevor der Wächter eingreift.
    /// Ohne diese Schonfrist reißt er die Aufnahme sofort wieder ab: der physische
    /// Tastenzustand steht direkt nach dem Drücken noch nicht zuverlässig an
    /// (entspricht STUCK_GRACE_S in localflow/main.py).
    private static let stuckGrace: TimeInterval = 0.35
    /// Zeit-Deckel gegen ewig laufende Aufnahmen (max_record_seconds in config.py).
    private static let maxHold: TimeInterval = 120

    init(key: HotkeyKey, onPress: @escaping () -> Void, onRelease: @escaping () -> Void) {
        self.key = key
        self.onPress = onPress
        self.onRelease = onRelease
    }

    func start() {
        let eventMask: CGEventMask =
            (1 << CGEventType.flagsChanged.rawValue)
            | (1 << CGEventType.keyDown.rawValue)
            | (1 << CGEventType.keyUp.rawValue)

        let selfPtr = Unmanaged.passUnretained(self).toOpaque()
        guard let tap = CGEvent.tapCreate(
            tap: .cgSessionEventTap,
            place: .headInsertEventTap,
            options: .listenOnly,   // nur mitlesen, nichts blockieren
            eventsOfInterest: eventMask,
            callback: { _, type, event, refcon in
                if let refcon = refcon {
                    let tapSelf = Unmanaged<HotkeyTap>.fromOpaque(refcon).takeUnretainedValue()
                    tapSelf.handle(type: type, event: event)
                }
                return Unmanaged.passUnretained(event)
            },
            userInfo: selfPtr
        ) else {
            DevLog.log("HotkeyTap: ✗ tapCreate fehlgeschlagen — Eingabemonitoring-Berechtigung fehlt")
            return
        }
        eventTap = tap
        let source = CFMachPortCreateRunLoopSource(kCFAllocatorDefault, tap, 0)
        runLoopSource = source
        CFRunLoopAddSource(CFRunLoopGetMain(), source, .commonModes)
        CGEvent.tapEnable(tap: tap, enable: true)
        DevLog.log("HotkeyTap: ✓ Tap aktiv, lauscht auf \(key.rawValue) (keycode \(key.keycode))")
        // Die Falle: tapCreate klappt AUCH ohne Berechtigung — der Tap bekommt
        // dann nur nie ein Ereignis. Ohne diese Warnung sieht alles gesund aus,
        // während der Hotkey in Wahrheit tot ist.
        if !CGPreflightListenEventAccess() {
            DevLog.log("HotkeyTap: ⚠️ Eingabemonitoring NICHT erteilt — es kommen KEINE "
                + "Tastenereignisse an (Berechtigung erteilen, dann App neu starten)")
        }

        startWatchdog()
    }

    func stop() {
        watchdogTimer?.invalidate()
        watchdogTimer = nil
        if let tap = eventTap {
            CGEvent.tapEnable(tap: tap, enable: false)
        }
        if let source = runLoopSource {
            CFRunLoopRemoveSource(CFRunLoopGetMain(), source, .commonModes)
        }
        eventTap = nil
        runLoopSource = nil
        isDown = false
    }

    private func handle(type: CGEventType, event: CGEvent) {
        if type == .tapDisabledByTimeout || type == .tapDisabledByUserInput {
            // Das System kann den Tap unter Last deaktivieren — ohne dieses
            // Re-Enable würde der Hotkey danach stumm bleiben.
            DevLog.log("HotkeyTap: Tap wurde vom System deaktiviert — reaktiviere")
            if let tap = eventTap {
                CGEvent.tapEnable(tap: tap, enable: true)
            }
            return
        }

        let keycode = CGKeyCode(event.getIntegerValueField(.keyboardEventKeycode))
        if type == .flagsChanged {
            DevLog.log("HotkeyTap: flagsChanged keycode=\(keycode) (erwartet \(key.keycode)) flags=\(event.flags.rawValue)")
        }
        guard keycode == key.keycode else { return }

        if key.isModifier {
            guard type == .flagsChanged else { return }
            setDown(event.flags.contains(key.modifierFlag))
        } else {
            guard type == .keyDown || type == .keyUp else { return }
            setDown(type == .keyDown)
        }
    }

    // ---- Wächter: rettet verlorene Loslassen-Ereignisse (analog
    // main.py._watchdog_step) ----
    //
    // Rechte Modifier-Tasten "verschlucken" ihr Loslassen-Ereignis gelegentlich
    // (bekanntes macOS-Verhalten, betraf auch die Python-Version über pynput).
    // Ohne Wächter bliebe eine Aufnahme dann für immer aktiv. Prüft den
    // PHYSISCHEN Tastenzustand, unabhängig vom Event-Strom.

    private func startWatchdog() {
        watchdogTimer?.invalidate()
        guard key.isModifier else { return }  // F-Tasten haben kein Flag zum Nachprüfen
        let timer = Timer(timeInterval: 0.08, repeats: true) { [weak self] _ in
            self?.checkPhysicalState()
        }
        RunLoop.main.add(timer, forMode: .common)
        watchdogTimer = timer
    }

    private func checkPhysicalState() {
        guard isDown else { return }
        let flags = CGEventSource.flagsState(.hidSystemState)
        if !flags.contains(key.modifierFlag) {
            DevLog.log("HotkeyTap: Wächter — Loslassen-Ereignis verloren, Aufnahme gerettet")
            setDown(false)
        }
    }

    private func setDown(_ down: Bool) {
        if down && !isDown {
            isDown = true
            DevLog.log("HotkeyTap: ▼ gedrückt")
            DispatchQueue.main.async { self.onPress() }
        } else if !down && isDown {
            isDown = false
            DevLog.log("HotkeyTap: ▲ losgelassen")
            DispatchQueue.main.async { self.onRelease() }
        }
    }
}
