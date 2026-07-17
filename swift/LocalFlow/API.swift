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
    let inserted: Bool
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

    /// Schnellcheck ohne Auth (analog `/api/ping` in server.py).
    func ping(completion: @escaping (Bool) -> Void) {
        let task = session.dataTask(with: baseURL.appendingPathComponent("api/ping")) { data, response, error in
            let ok = error == nil && (response as? HTTPURLResponse)?.statusCode == 200
            completion(ok)
        }
        task.resume()
    }

    /// Lädt eine WAV-Aufnahme hoch, lässt sie transkribieren und (falls `insert`)
    /// direkt am Mac-Cursor einfügen — Python übernimmt Cleanup/LLM-Feinschliff/
    /// Einfügen wie bisher (server.py `/api/transcribe`), Swift steuert nur Aufnahme+Hotkey.
    func transcribe(fileURL: URL, insert: Bool, language: String? = nil,
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
        func addField(name: String, value: String) {
            body.append("--\(boundary)\r\n".data(using: .utf8)!)
            body.append("Content-Disposition: form-data; name=\"\(name)\"\r\n\r\n".data(using: .utf8)!)
            body.append("\(value)\r\n".data(using: .utf8)!)
        }
        body.append("--\(boundary)\r\n".data(using: .utf8)!)
        body.append("Content-Disposition: form-data; name=\"audio\"; filename=\"audio.wav\"\r\n"
            .data(using: .utf8)!)
        body.append("Content-Type: audio/wav\r\n\r\n".data(using: .utf8)!)
        body.append(audioData)
        body.append("\r\n".data(using: .utf8)!)
        if insert {
            addField(name: "insert", value: "1")
        }
        if let language = language {
            addField(name: "language", value: language)
        }
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
            let inserted = json["inserted"] as? Bool ?? false
            completion(.success(TranscribeResult(text: text, inserted: inserted)))
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
