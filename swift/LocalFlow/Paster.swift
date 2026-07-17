import Cocoa
import ApplicationServices

/// Fügt Text an der Cursor-Position der aktiven App ein: Zwischenablage sichern
/// -> Text setzen -> ⌘V simulieren -> Zwischenablage wiederherstellen.
/// Logik übernommen aus localflow/inserter.py.
///
/// Warum Swift das selbst macht (statt `insert=1` an die Python-Engine zu
/// schicken): Die Engine läuft als Kindprozess der Swift-App und bekommt vom
/// System keine eigenen Bedienungshilfen-Rechte — ihr Einfügeversuch scheitert
/// dort mit „osascript ist nicht berechtigt, Tastatureingaben zu senden".
/// Die Swift-Hülle besitzt die Rechte und ist ohnehin die richtige Stelle dafür
/// (siehe docs/PLAN-PROFESSIONALISIERUNG.md, Phase 3).
enum Paster {
    /// Muss AUSSERHALB des Haupt-Threads laufen — wartet ggf. sekundenlang auf
    /// losgelassene Modifier-Tasten.
    static func insert(_ text: String) -> Bool {
        guard !text.isEmpty else { return false }

        let payload = needsLeadingSpace(before: text) ? " " + text : text

        let pb = NSPasteboard.general
        let previous = pb.string(forType: .string)

        // NSPasteboard statt pbcopy: Über die Kommandozeilen-Werkzeuge kamen
        // Umlaute in der Ziel-App als Mojibake an (siehe CHANGELOG 0.5.4).
        pb.clearContents()
        pb.setString(payload, forType: .string)
        Thread.sleep(forTimeInterval: 0.05)  // Zwischenablage sicher übernommen

        waitModifiersClear()

        guard postCmdV() else {
            DevLog.log("Paster: ⌘V fehlgeschlagen — Bedienungshilfen-Berechtigung fehlt. "
                + "Text liegt in der Zwischenablage (⌘V von Hand).")
            return false
        }

        // Verzögert wiederherstellen, damit das Einfügen sicher durch ist.
        if let previous = previous {
            DispatchQueue.global().asyncAfter(deadline: .now() + 0.6) {
                let pb = NSPasteboard.general
                pb.clearContents()
                pb.setString(previous, forType: .string)
            }
        }
        return true
    }

    // ---- Leerzeichen zwischen aufeinanderfolgenden Diktaten ----
    //
    // Diktiert man zweimal hintereinander in dieselbe Zeile, klebten die Texte
    // sonst aneinander ("HalloWie geht's"). Statt blind ein Leerzeichen davor
    // zu setzen (das würde am Zeilenanfang eine Einrückung erzeugen), fragen wir
    // die Ziel-App über die Bedienungshilfen-Schnittstelle nach dem Zeichen
    // direkt vor dem Cursor. Antwortet sie nicht (manche Apps geben keine
    // Auskunft), fügen wir nichts hinzu — dann bleibt es beim alten Verhalten.

    private static func needsLeadingSpace(before text: String) -> Bool {
        // Vor Satzzeichen gehört nie ein Leerzeichen ("Hallo" + ", oder?").
        if let first = text.first, ",.!?;:".contains(first) { return false }
        guard let previous = characterBeforeCursor() else { return false }
        return !previous.isWhitespace
    }

    /// Zeichen unmittelbar vor dem Cursor im fokussierten Textfeld — nil, wenn
    /// die App keine Auskunft gibt oder der Cursor am Anfang steht.
    private static func characterBeforeCursor() -> Character? {
        let system = AXUIElementCreateSystemWide()

        var focusedRef: CFTypeRef?
        guard AXUIElementCopyAttributeValue(
                system, kAXFocusedUIElementAttribute as CFString, &focusedRef) == .success,
              let focused = focusedRef else { return nil }
        let element = focused as! AXUIElement

        var rangeRef: CFTypeRef?
        guard AXUIElementCopyAttributeValue(
                element, kAXSelectedTextRangeAttribute as CFString, &rangeRef) == .success,
              let rangeValue = rangeRef else { return nil }

        var cursor = CFRange()
        let gotRange = withUnsafeMutablePointer(to: &cursor) {
            AXValueGetValue(rangeValue as! AXValue, .cfRange, $0)
        }
        guard gotRange, cursor.location > 0 else { return nil }  // Anfang -> kein Leerzeichen

        // Gezielt EIN Zeichen lesen statt den ganzen Feldinhalt (in langen
        // Dokumenten wäre das unnötig teuer).
        var charRange = CFRange(location: cursor.location - 1, length: 1)
        guard let rangeArg = withUnsafePointer(to: &charRange, {
            AXValueCreate(.cfRange, $0)
        }) else { return nil }

        var textRef: CFTypeRef?
        guard AXUIElementCopyParameterizedAttributeValue(
                element, kAXStringForRangeParameterizedAttribute as CFString,
                rangeArg, &textRef) == .success,
              let previous = textRef as? String else { return nil }
        return previous.first
    }

    /// Wartet, bis der Nutzer keine Modifier-Taste mehr hält. Sonst würde aus
    /// dem simulierten ⌘V z.B. ⌘⌥V — in vielen Apps ein anderer Befehl.
    private static func waitModifiersClear(timeout: TimeInterval = 4.0) {
        let combo: CGEventFlags = [.maskCommand, .maskAlternate, .maskControl, .maskShift]
        let deadline = Date().addingTimeInterval(timeout)
        while Date() < deadline {
            if CGEventSource.flagsState(.hidSystemState).intersection(combo).isEmpty { return }
            Thread.sleep(forTimeInterval: 0.05)
        }
        DevLog.log("Paster: Modifier nach \(timeout)s noch gedrückt — füge trotzdem ein")
    }

    private static func postCmdV() -> Bool {
        guard CGPreflightPostEventAccess() else { return false }
        let source = CGEventSource(stateID: .hidSystemState)
        let vKey = CGKeyCode(9)  // kVK_ANSI_V (gleiche Position auf QWERTY und QWERTZ)
        guard let down = CGEvent(keyboardEventSource: source, virtualKey: vKey, keyDown: true),
              let up = CGEvent(keyboardEventSource: source, virtualKey: vKey, keyDown: false)
        else { return false }
        down.flags = .maskCommand
        up.flags = .maskCommand
        down.post(tap: .cghidEventTap)
        up.post(tap: .cghidEventTap)
        return true
    }
}
