"""HTTPS-Server für die iPhone-PWA: liefert die Web-App und /api/transcribe."""

import logging
import socket
import subprocess
import threading
import time
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

from . import config
from .cleanup import clean

log = logging.getLogger("localflow.server")

WEB_DIR = Path(__file__).parent / "web"
CERT_DIR = config.CONFIG_DIR / "certs"


def lan_ip() -> str:
    """Ermittelt die WLAN-IP im Heimnetz.

    Bevorzugt die echte LAN-Adresse (192.168.x / 10.x / 172.16-31.x) über
    macOS-Interfaces en0/en1. VPN-Interfaces wie Tailscale (100.64.x/CGNAT)
    werden übersprungen, damit der Handy-Link im Heim-WLAN funktioniert.
    """
    import ipaddress

    def is_lan(ip: str) -> bool:
        try:
            addr = ipaddress.ip_address(ip)
        except ValueError:
            return False
        # CGNAT 100.64.0.0/10 (Tailscale u.ä.) ausschließen
        if addr in ipaddress.ip_network("100.64.0.0/10"):
            return False
        return addr.is_private and not addr.is_loopback and not addr.is_link_local

    # 1) macOS: klassische WLAN/Ethernet-Interfaces direkt abfragen
    for iface in ("en0", "en1", "en2"):
        try:
            out = subprocess.run(["ipconfig", "getifaddr", iface],
                                 capture_output=True, text=True, timeout=2)
            ip = out.stdout.strip()
            if ip and is_lan(ip):
                return ip
        except (OSError, subprocess.SubprocessError):
            pass

    # 2) Fallback: Socket-Trick (nimmt die Default-Route)
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("192.168.255.255", 1))  # kein echtes Senden nötig
        ip = s.getsockname()[0]
        if is_lan(ip):
            return ip
    except OSError:
        pass
    finally:
        s.close()
    return "127.0.0.1"


def ensure_cert() -> tuple:
    """Erzeugt einmalig ein selbstsigniertes Zertifikat (openssl ist bei macOS dabei)."""
    CERT_DIR.mkdir(parents=True, exist_ok=True)
    cert, key = CERT_DIR / "cert.pem", CERT_DIR / "key.pem"
    if not (cert.exists() and key.exists()):
        ip = lan_ip()
        subprocess.run(
            ["openssl", "req", "-x509", "-newkey", "rsa:2048", "-sha256",
             "-keyout", str(key), "-out", str(cert), "-days", "3650", "-nodes",
             "-subj", "/CN=LocalFlow",
             "-addext", f"subjectAltName=DNS:localhost,IP:127.0.0.1,IP:{ip}"],
            check=True, capture_output=True,
        )
        log.info("Selbstsigniertes Zertifikat erzeugt: %s", cert)
    return str(cert), str(key)


def create_app(engine, get_language) -> Flask:
    """engine: Engine-Instanz. get_language: Callable -> aktuelle Sprach-Einstellung."""
    app = Flask(__name__, static_folder=None)

    @app.get("/")
    def index():
        return send_from_directory(WEB_DIR, "index.html")

    @app.get("/<path:name>")
    def static_file(name):
        return send_from_directory(WEB_DIR, name)

    @app.get("/api/ping")
    def ping():
        return jsonify(ok=True, model=engine.repo, loaded=engine.loaded)

    @app.post("/api/transcribe")
    def transcribe():
        from .audio import decode_upload

        f = request.files.get("audio")
        if f is None:
            return jsonify(error="Feld 'audio' fehlt"), 400
        blob = f.read()
        if len(blob) < 100:
            return jsonify(error="Audio leer"), 400

        language = request.form.get("language") or get_language()
        try:
            audio = decode_upload(blob, f.filename or "audio.m4a")
        except ValueError as e:
            return jsonify(error=str(e)), 415

        if len(audio) < 1600:  # < 0,1 s
            return jsonify(error="Aufnahme zu kurz"), 400

        from .audio import is_silent

        if is_silent(audio, config.load_config().get("silence_rms", 0.006)):
            return jsonify(text="", raw="", language="", seconds=0, ms=0,
                           note="Stille erkannt — nichts transkribiert")

        dictionary = config.load_dictionary()
        result = engine.transcribe(
            audio, language=language, prompt_terms=dictionary.get("terms") or None
        )
        text = clean(result["text"], result["language"],
                     dictionary, config.load_snippets())
        config.add_history({
            "text": text, "raw": result["text"], "language": result["language"],
            "seconds": result["seconds"], "source": "phone", "time": time.time(),
        })
        log.info("Handy-Diktat (%ss Audio, %sms): %s",
                 result["seconds"], result["ms"], text[:80])
        return jsonify(
            text=text, raw=result["text"], language=result["language"],
            seconds=result["seconds"], ms=result["ms"],
        )

    return app


def start_server(engine, get_language, port: int) -> threading.Thread:
    """Startet den HTTPS-Server in einem Daemon-Thread."""
    app = create_app(engine, get_language)
    cert, key = ensure_cert()

    def run():
        app.run(host="0.0.0.0", port=port, ssl_context=(cert, key),
                threaded=True, debug=False, use_reloader=False)

    t = threading.Thread(target=run, daemon=True, name="localflow-server")
    t.start()
    log.info("Server läuft: https://%s:%s", lan_ip(), port)
    return t
