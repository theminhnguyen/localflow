import AVFoundation

/// Mikrofon-Aufnahme über AVAudioEngine, als 16 kHz mono 16-bit-PCM-WAV
/// geschrieben — das Format, das die Python-Seite per load_wav() direkt liest
/// (siehe localflow/audio.py), ohne Umweg über afconvert.
final class Recorder {
    enum RecorderError: Error { case alreadyRecording, converterUnavailable }

    /// Wird gerufen, wenn eine laufende Aufnahme durch einen Geräte-/Format-
    /// wechsel (z.B. AirPods verbinden/trennen während des Diktierens)
    /// abgebrochen werden musste — der Aufrufer soll dann Status/Sound
    /// zurücksetzen, die Aufnahme selbst ist bereits verworfen.
    var onInterrupted: (() -> Void)?

    private var engine: AVAudioEngine?
    private var outputFile: AVAudioFile?
    private var tempURL: URL?
    private var configObserver: NSObjectProtocol?
    private(set) var isRecording = false

    /// WAV auf der Platte: 16 kHz mono 16-bit PCM.
    private let fileSettings: [String: Any] = [
        AVFormatIDKey: kAudioFormatLinearPCM,
        AVSampleRateKey: 16000.0,
        AVNumberOfChannelsKey: 1,
        AVLinearPCMBitDepthKey: 16,
        AVLinearPCMIsFloatKey: false,
        AVLinearPCMIsBigEndianKey: false,
        AVLinearPCMIsNonInterleaved: false,
    ]

    /// Format, in das der Converter schreibt. MUSS AVAudioFile.processingFormat
    /// entsprechen (float32, deinterleaved) — write(from:) wirft bei Abweichung
    /// eine ObjC-Exception, die in Swift NICHT fangbar ist (try? hilft nicht,
    /// die App stürzt ab). Die Wandlung nach Int16 auf der Platte übernimmt
    /// AVAudioFile selbst anhand von fileSettings.
    private let convertFormat = AVAudioFormat(standardFormatWithSampleRate: 16000, channels: 1)!

    func start() throws {
        guard !isRecording else { throw RecorderError.alreadyRecording }

        // Frische Engine pro Aufnahme statt einer über die Objekt-Lebenszeit
        // wiederverwendeten Instanz: Wechselt das Eingabegerät zwischen zwei
        // Diktaten (z.B. AirPods verbinden), kann eine alte AVAudioEngine
        // einen inkonsistenten internen Graph behalten — installTap/start
        // wirft dann teils ObjC-Exceptions, die Swift NICHT fangen kann
        // (Absturz). Eine neue Instanz ist billig und immer im sauberen
        // Ausgangszustand, unabhängig davon, was seit der letzten Aufnahme
        // am Audiosystem passiert ist.
        let engine = AVAudioEngine()

        let input = engine.inputNode
        let inputFormat = input.outputFormat(forBus: 0)

        guard let converter = AVAudioConverter(from: inputFormat, to: convertFormat) else {
            throw RecorderError.converterUnavailable
        }

        let url = FileManager.default.temporaryDirectory
            .appendingPathComponent("localflow-\(UUID().uuidString).wav")
        let file = try AVAudioFile(forWriting: url, settings: fileSettings)

        input.installTap(onBus: 0, bufferSize: 4096, format: inputFormat) { [weak self] buffer, _ in
            guard let self = self, let file = self.outputFile else { return }
            let ratio = self.convertFormat.sampleRate / inputFormat.sampleRate
            let outCapacity = AVAudioFrameCount(Double(buffer.frameLength) * ratio) + 16
            guard let outBuffer = AVAudioPCMBuffer(pcmFormat: self.convertFormat,
                                                    frameCapacity: outCapacity) else { return }

            var suppliedOnce = false
            let inputBlock: AVAudioConverterInputBlock = { _, outStatus in
                if suppliedOnce {
                    outStatus.pointee = .noDataNow
                    return nil
                }
                suppliedOnce = true
                outStatus.pointee = .haveData
                return buffer
            }
            var convError: NSError?
            converter.convert(to: outBuffer, error: &convError, withInputFrom: inputBlock)
            if let convError = convError {
                DevLog.log("Recorder: Wandlung fehlgeschlagen: \(convError)")
                return
            }
            if outBuffer.frameLength > 0 {
                do {
                    try file.write(from: outBuffer)
                } catch {
                    DevLog.log("Recorder: Schreiben fehlgeschlagen: \(error)")
                }
            }
        }

        // Gerätewechsel während der Aufnahme beobachten (AirPods verbinden/
        // trennen, USB-Mikro ab-/angesteckt, …) — sauber abbrechen statt
        // riskieren, dass der Tap auf ein plötzlich falsches Format trifft.
        // queue: .main, damit der Handler garantiert auf demselben Thread wie
        // start()/stop() läuft (die Benachrichtigung selbst kommt von einem
        // beliebigen AVFoundation-internen Thread).
        let observer = NotificationCenter.default.addObserver(
            forName: .AVAudioEngineConfigurationChange, object: engine, queue: .main
        ) { [weak self] _ in
            self?.handleConfigurationChange()
        }

        do {
            try engine.start()
        } catch {
            NotificationCenter.default.removeObserver(observer)
            throw error
        }

        self.engine = engine
        self.outputFile = file
        self.tempURL = url
        self.configObserver = observer
        isRecording = true
        DevLog.log("Recorder: Aufnahme läuft (Eingang \(inputFormat.sampleRate) Hz, "
            + "\(inputFormat.channelCount) Kanäle) -> \(url.lastPathComponent)")
    }

    private func handleConfigurationChange() {
        guard isRecording else { return }
        DevLog.log("Recorder: Audiogerät während der Aufnahme gewechselt — breche ab")
        let url = stop()
        if let url = url {
            try? FileManager.default.removeItem(at: url)
        }
        onInterrupted?()
    }

    /// Beendet die Aufnahme, liefert die fertige WAV-Datei (nil, falls nichts lief).
    @discardableResult
    func stop() -> URL? {
        guard isRecording else { return nil }
        isRecording = false

        if let observer = configObserver {
            NotificationCenter.default.removeObserver(observer)
            configObserver = nil
        }
        engine?.inputNode.removeTap(onBus: 0)
        engine?.stop()
        engine = nil
        outputFile = nil  // schließt die Datei (AVAudioFile schreibt den Header beim Deinit)

        let url = tempURL
        tempURL = nil
        if let url = url {
            let attrs = try? FileManager.default.attributesOfItem(atPath: url.path)
            let size = (attrs?[.size] as? Int) ?? 0
            DevLog.log("Recorder: gestoppt, \(size) Bytes in \(url.lastPathComponent)")
        }
        return url
    }
}
