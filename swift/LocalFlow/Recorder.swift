import AVFoundation

/// Mikrofon-Aufnahme über AVAudioEngine, als 16 kHz mono 16-bit-PCM-WAV
/// geschrieben — das Format, das die Python-Seite per load_wav() direkt liest
/// (siehe localflow/audio.py), ohne Umweg über afconvert.
final class Recorder {
    enum RecorderError: Error { case alreadyRecording, converterUnavailable }

    private let engine = AVAudioEngine()
    private var outputFile: AVAudioFile?
    private var tempURL: URL?
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

        let input = engine.inputNode
        let inputFormat = input.outputFormat(forBus: 0)

        guard let converter = AVAudioConverter(from: inputFormat, to: convertFormat) else {
            throw RecorderError.converterUnavailable
        }

        let url = FileManager.default.temporaryDirectory
            .appendingPathComponent("localflow-\(UUID().uuidString).wav")
        tempURL = url
        outputFile = try AVAudioFile(forWriting: url, settings: fileSettings)

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

        try engine.start()
        isRecording = true
        DevLog.log("Recorder: Aufnahme läuft (Eingang \(inputFormat.sampleRate) Hz, "
            + "\(inputFormat.channelCount) Kanäle) -> \(url.lastPathComponent)")
    }

    /// Beendet die Aufnahme, liefert die fertige WAV-Datei (nil, falls nichts lief).
    @discardableResult
    func stop() -> URL? {
        guard isRecording else { return nil }
        isRecording = false
        engine.inputNode.removeTap(onBus: 0)
        engine.stop()
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
