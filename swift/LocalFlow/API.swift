import Foundation

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
