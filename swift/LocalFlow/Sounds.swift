import AppKit

/// Akustische Rückmeldung beim Diktieren — dieselben System-Klänge wie in
/// localflow/main.py (SOUND_START/STOP/LOCK/ERROR), abschaltbar über den
/// `sounds`-Schalter in ~/.localflow/config.json.
enum Sound: String {
    case start = "/System/Library/Sounds/Tink.aiff"
    case stop = "/System/Library/Sounds/Pop.aiff"
    case lock = "/System/Library/Sounds/Glass.aiff"
    case error = "/System/Library/Sounds/Basso.aiff"
}

enum Sounds {
    /// NSSound spielt nur, solange es jemand festhält — eine lokale Variable
    /// wäre sofort wieder weg und der Klang bliebe stumm. Darum halten wir die
    /// laufenden Klänge hier, bis sie durch sind.
    private static var playing: [NSSound] = []

    static func play(_ sound: Sound) {
        guard Config.bool("sounds", true) else { return }
        DispatchQueue.main.async {
            guard let nsSound = NSSound(contentsOfFile: sound.rawValue, byReference: true)
            else { return }
            playing.append(nsSound)
            nsSound.play()
            DispatchQueue.main.asyncAfter(deadline: .now() + 3) {
                playing.removeAll { $0 === nsSound }
            }
        }
    }
}
