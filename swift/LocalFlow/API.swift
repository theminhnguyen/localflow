import Foundation

/// Kopplungs-Token — dieselbe Datei, die auch server.py per
/// config.load_or_create_token() schreibt/liest (~/.localflow/secret.token).
enum LocalFlowToken {
    static var current: String? {
        let path = NSHomeDirectory() + "/.localflow/secret.token"
        return try? String(contentsOfFile: path, encoding: .utf8)
            .trimmingCharacters(in: .whitespacesAndNewlines)
    }
}

struct TranscribeResult {
    let text: String
}

enum LocalFlowAPIError: Error {
    case cannotReadAudioFile
    case badResponse
    case httpError(status: Int)
}

/// Spricht mit der lokalen Python-Engine (localflow/server.py) über HTTPS auf
/// 127.0.0.1. Die Engine nutzt ein selbstsigniertes Zertifikat (server.ensure_cert())
/// — wird hier bewusst NUR für 127.0.0.1 akzeptiert, nicht global.
final class LocalFlowAPI: NSObject, URLSessionDelegate {
    static let shared = LocalFlowAPI()

    var port: Int = 8790
    private var baseURL: URL { URL(string: "https://127.0.0.1:\(port)")! }

    private lazy var session: URLSession = {
        URLSession(configuration: .ephemeral, delegate: self, delegateQueue: nil)
    }()

    /// Schnellcheck ohne Auth (analog `/api/ping` in server.py). Liefert erst
    /// dann true, wenn das Whisper-Modell tatsächlich geladen ist (`loaded`) —
    /// NICHT schon, sobald der Flask-Server antwortet. Sonst meldet
    /// EngineProcess "Bereit", bevor die Engine wirklich diktieren kann: ein
    /// Diktat mitten in den ~10-20s Modell-Kaltstart lief dabei live in einen
    /// 30s-Timeout, weil die Antwort erst nach dem clientseitigen Abbruch kam.
    func ping(completion: @escaping (Bool) -> Void) {
        let task = session.dataTask(with: baseURL.appendingPathComponent("api/ping")) { data, response, error in
            guard error == nil, (response as? HTTPURLResponse)?.statusCode == 200,
                  let data = data,
                  let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
            else {
                completion(false)
                return
            }
            completion((json["ok"] as? Bool ?? false) && (json["loaded"] as? Bool ?? false))
        }
        task.resume()
    }

    /// Fire-and-forget beim Tastendruck: bittet die Engine, ausgekühlte
    /// GPU-Kernel im Hintergrund vorzuwärmen, während der Nutzer spricht — so
    /// zahlt die folgende Transkription nicht den Kalt-Aufschlag. Antwort egal.
    func prewarm() {
        var request = URLRequest(url: baseURL.appendingPathComponent("api/prewarm"))
        request.httpMethod = "POST"
        request.timeoutInterval = 5
        if let token = LocalFlowToken.current {
            request.setValue(token, forHTTPHeaderField: "X-LocalFlow-Key")
        }
        session.dataTask(with: request).resume()
    }

    /// Lädt eine WAV-Aufnahme hoch und lässt sie transkribieren (server.py
    /// `/api/transcribe`): Python übernimmt Whisper, Cleanup und LLM-Feinschliff.
    /// Das Einfügen macht die Swift-Seite selbst (siehe Paster) — der
    /// `insert=1`-Weg der Engine funktioniert aus dem Kindprozess heraus nicht.
    /// Die Sprache lässt die Engine über ihren eigenen Sprach-Cache bestimmen.
    func transcribe(fileURL: URL,
                     completion: @escaping (Result<TranscribeResult, Error>) -> Void) {
        guard let audioData = try? Data(contentsOf: fileURL) else {
            completion(.failure(LocalFlowAPIError.cannotReadAudioFile))
            return
        }

        var request = URLRequest(url: baseURL.appendingPathComponent("api/transcribe"))
        request.httpMethod = "POST"
        request.timeoutInterval = 30
        if let token = LocalFlowToken.current {
            request.setValue(token, forHTTPHeaderField: "X-LocalFlow-Key")
        }

        let boundary = "LocalFlowBoundary-\(UUID().uuidString)"
        request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")

        var body = Data()
        body.append("--\(boundary)\r\n".data(using: .utf8)!)
        body.append("Content-Disposition: form-data; name=\"audio\"; filename=\"audio.wav\"\r\n"
            .data(using: .utf8)!)
        body.append("Content-Type: audio/wav\r\n\r\n".data(using: .utf8)!)
        body.append(audioData)
        body.append("\r\n".data(using: .utf8)!)
        body.append("--\(boundary)--\r\n".data(using: .utf8)!)
        request.httpBody = body

        let task = session.dataTask(with: request) { data, response, error in
            if let error = error {
                completion(.failure(error))
                return
            }
            guard let http = response as? HTTPURLResponse, let data = data else {
                completion(.failure(LocalFlowAPIError.badResponse))
                return
            }
            guard http.statusCode == 200 else {
                completion(.failure(LocalFlowAPIError.httpError(status: http.statusCode)))
                return
            }
            guard let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
                completion(.failure(LocalFlowAPIError.badResponse))
                return
            }
            let text = json["text"] as? String ?? ""
            completion(.success(TranscribeResult(text: text)))
        }
        task.resume()
    }

    func urlSession(_ session: URLSession, didReceive challenge: URLAuthenticationChallenge,
                     completionHandler: @escaping (URLSession.AuthChallengeDisposition, URLCredential?) -> Void) {
        guard challenge.protectionSpace.host == "127.0.0.1",
              let trust = challenge.protectionSpace.serverTrust else {
            completionHandler(.performDefaultHandling, nil)
            return
        }
        completionHandler(.useCredential, URLCredential(trust: trust))
    }
}
