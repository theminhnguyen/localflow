import Cocoa

/// Minimale Erstlauf-Führung (P2.1e) — bewusst KEIN Assistent mit mehreren
/// Schritten wie localflow/onboarding.py (Modell-Download-Fortschritt entfällt
/// hier: die Engine bringt ihr Modell schon mit/lädt es selbst, sichtbar über
/// die normale "Startet Engine…"-Statuszeile). Die App fordert die drei
/// Berechtigungen ohnehin schon aktiv an (siehe AppDelegate) — es fehlte nur
/// eine kurze Erklärung VOR den System-Dialogen, damit die nicht aus dem
/// Nichts kommen.
enum Onboarding {
    private static let key = "onboardingShown"

    static func showIfNeeded() {
        guard !UserDefaults.standard.bool(forKey: key) else { return }
        let alert = NSAlert()
        alert.messageText = "Willkommen bei LocalFlow"
        alert.informativeText = """
        LocalFlow braucht drei Berechtigungen, um zu funktionieren: Mikrofon, \
        Eingabemonitoring und Bedienungshilfen. macOS fragt dich gleich danach \
        — bitte alle drei erlauben.

        Falls die Diktier-Taste danach noch stumm bleibt: LocalFlow einmal über \
        das Menü beenden und neu starten (Eingabemonitoring wirkt erst nach \
        einem Neustart).
        """
        alert.runModal()
        UserDefaults.standard.set(true, forKey: key)
    }
}
