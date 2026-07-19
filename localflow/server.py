"""HTTPS-Server für die iPhone-PWA: Web-App, /api/transcribe, Verlauf, Status.

Neu: Das Handy kann den erkannten Text direkt an der Mac-Cursor-Position
einfügen lassen (Fernmikrofon) und den Diktat-Verlauf des Macs sehen —
beides über Schalter in den Einstellungen abschaltbar.
"""

import hmac
import json
import logging
import socket
import subprocess
import threading
import time
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

from . import autostart, config
from .cleanup import clean
from .engine import MODELS

log = logging.getLogger("localflow.server")

WEB_DIR = Path(__file__).parent / "web"
CERT_DIR = config.CONFIG_DIR / "certs"
_START_TIME = time.time()

# Whitelist für GET/PUT /api/config — bewusst nur die Werte, die eine
# Einstellungs-Seite braucht (kein Token, keine internen Feineinstellungen
# wie silence_rms/llm_timeout). "choices" = Enum, "bool" = Wahrheitswert.
CONFIG_SCHEMA = {
    "language": {"choices": ("auto", "de", "en")},
    "hotkey": {"choices": ("alt_r", "cmd_r", "ctrl_r", "f13")},
    "model": {"choices": tuple(MODELS.keys())},
    "llm_enabled": {"bool": True},
    "llm_smart": {"bool": True},
    "phone_insert": {"bool": True},
    "share_history": {"bool": True},
    "sounds": {"bool": True},
    "update_check": {"bool": True},
    "log_texts": {"bool": True},
}


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


def tailscale_ip():
    """Tailscale-IP des Macs, falls Tailscale installiert und verbunden — sonst None.

    Damit funktioniert das Handy-Diktat auch unterwegs (Mac muss laufen).
    """
    for cli in ("/Applications/Tailscale.app/Contents/MacOS/Tailscale",
                "/opt/homebrew/bin/tailscale", "/usr/local/bin/tailscale"):
        if not Path(cli).exists():
            continue
        try:
            r = subprocess.run([cli, "ip", "-4"], capture_output=True,
                               text=True, timeout=3)
            ip = r.stdout.strip().splitlines()[0].strip() if r.stdout.strip() else ""
            if r.returncode == 0 and ip.startswith("100."):
                return ip
        except (OSError, subprocess.SubprocessError, IndexError):
            pass
    return None


def ensure_cert() -> tuple:
    """Selbstsigniertes Zertifikat; wird neu erzeugt, wenn sich die IPs ändern."""
    CERT_DIR.mkdir(parents=True, exist_ok=True)
    cert, key = CERT_DIR / "cert.pem", CERT_DIR / "key.pem"
    marker = CERT_DIR / "sans.json"

    ips = [ip for ip in (lan_ip(), tailscale_ip()) if ip]
    try:
        old = json.loads(marker.read_text()) if marker.exists() else []
    except (OSError, json.JSONDecodeError):
        old = []

    if not (cert.exists() and key.exists()) or sorted(old) != sorted(ips):
        san = "subjectAltName=DNS:localhost,IP:127.0.0.1" + "".join(
            f",IP:{ip}" for ip in ips)
        subprocess.run(
            ["openssl", "req", "-x509", "-newkey", "rsa:2048", "-sha256",
             "-keyout", str(key), "-out", str(cert), "-days", "3650", "-nodes",
             "-subj", "/CN=LocalFlow", "-addext", san],
            check=True, capture_output=True,
        )
        marker.write_text(json.dumps(ips))
        log.info("Zertifikat erzeugt für %s", ips)
    return str(cert), str(key)


def create_app(engine, get_language, controller=None) -> Flask:
    """engine: Engine. get_language: Callable. controller: FlowController (optional)."""
    app = Flask(__name__, static_folder=None)
    config.load_or_create_token()  # Token früh anlegen, damit die erste Kopplung sofort klappt

    def cfg() -> dict:
        return controller.cfg if controller is not None else config.load_config()

    @app.before_request
    def _check_auth():
        # Statische PWA-Dateien (inkl. "/") bleiben immer frei — die Seite muss
        # laden können, bevor ihr JS überhaupt ein Token aus dem Link lesen kann.
        # /api/ping bleibt frei (reiner Status-Check, keine sensiblen Daten).
        if not request.path.startswith("/api/") or request.path == "/api/ping":
            return None
        if not cfg().get("require_auth", True):
            return None
        supplied = request.headers.get("X-LocalFlow-Key", "")
        current = config.load_or_create_token()
        if not supplied or not hmac.compare_digest(supplied, current):
            return jsonify(error="nicht gekoppelt", code="unauthorized"), 401
        return None

    @app.get("/")
    def index():
        return send_from_directory(WEB_DIR, "index.html")

    @app.get("/settings")
    def settings_page():
        return send_from_directory(WEB_DIR, "settings.html")

    @app.get("/<path:name>")
    def static_file(name):
        return send_from_directory(WEB_DIR, name)

    @app.get("/api/ping")
    def ping():
        c = cfg()
        return jsonify(ok=True, model=engine.repo, loaded=engine.loaded,
                       insert_allowed=bool(c.get("phone_insert", True)),
                       history_allowed=bool(c.get("share_history", True)))

    @app.post("/api/prewarm")
    def prewarm():
        # Wird von der Swift-Hülle beim Tastendruck gefeuert (fire-and-forget):
        # wärmt ausgekühlte GPU-Kernel im Hintergrund vor, während der Nutzer
        # spricht, damit die folgende Transkription nicht den Kalt-Aufschlag
        # zahlt. No-op, wenn die Engine noch heiß ist (siehe engine.prewarm_if_cold).
        engine.prewarm_if_cold()
        return jsonify(ok=True)

    @app.get("/api/history")
    def history():
        if not cfg().get("share_history", True):
            return jsonify(enabled=False, entries=[])
        entries = [
            {"text": e.get("text", ""), "source": e.get("source", "?"),
             "seconds": e.get("seconds", 0), "time": e.get("time", 0),
             "language": e.get("language", "")}
            for e in config.load_history()[:30]
        ]
        return jsonify(enabled=True, entries=entries)

    @app.get("/api/status")
    def status():
        from . import llm

        from . import __version__

        c = cfg()
        body = {
            "version": __version__,
            "model": engine.repo, "loaded": engine.loaded,
            "uptime_s": int(time.time() - _START_TIME),
            "llm": {"enabled": bool(c.get("llm_enabled")), **llm.status(c)},
            "lan_ip": lan_ip(), "tailscale_ip": tailscale_ip(),
            "port": c.get("server_port", 8790),
        }
        if controller is not None:
            body["stats"] = dict(controller.stats)
            body["state"] = controller.state
        return jsonify(**body)

    @app.get("/api/update-check")
    def update_check():
        # Für die Swift-Hülle (Phase 3): dieselbe Prüf-Logik wie main.py
        # FlowController.check_for_update_now(), nur als Endpunkt statt über
        # einen rumps-Menü-Tick — kein Grund, GitHub-Abfrage + Versions-
        # vergleich ein zweites Mal in Swift nachzubauen.
        from . import __version__, updater

        try:
            found = updater.check_for_update(__version__)
        except Exception:
            log.debug("Update-Check fehlgeschlagen", exc_info=True)
            found = None
        if found:
            return jsonify(available=True, tag=found["tag"], url=found["url"])
        return jsonify(available=False)

    @app.get("/api/config")
    def get_config():
        c = cfg()
        body = {k: c.get(k) for k in CONFIG_SCHEMA}
        body["autostart"] = autostart.enabled()
        return jsonify(**body)

    @app.put("/api/config")
    def put_config():
        if controller is None:
            return jsonify(error="im --serve-only-Modus nicht verfügbar"), 400
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify(error="ungültiger Body (JSON-Objekt erwartet)"), 400
        unknown = [k for k in data if k not in CONFIG_SCHEMA and k != "autostart"]
        if unknown:
            return jsonify(error=f"unbekannte Schlüssel: {', '.join(unknown)}"), 400

        applied = {}
        for key, value in data.items():
            if key == "autostart":
                if not isinstance(value, bool):
                    return jsonify(error="autostart: muss ein Wahrheitswert sein"), 400
                applied["autostart"] = controller.set_autostart(value)
                continue
            rule = CONFIG_SCHEMA[key]
            if "choices" in rule and value not in rule["choices"]:
                return jsonify(error=f"{key}: ungültiger Wert {value!r}"), 400
            if rule.get("bool") and not isinstance(value, bool):
                return jsonify(error=f"{key}: muss ein Wahrheitswert sein"), 400
            # Über die vorhandenen Setter anwenden -> greift sofort, kein Neustart nötig
            if key == "language":
                controller.set_language(value)
            elif key == "hotkey":
                controller.set_hotkey(value)
            elif key == "model":
                controller.set_model(value)
            else:
                controller.set_toggle(key, value)
            applied[key] = value
        return jsonify(ok=True, applied=applied)

    @app.post("/api/insert")
    def insert():
        # Für die Swift-Hülle (Phase 3): Fallback, falls das native Einfügen dort
        # mal nicht greift — Python macht es dann über den bewährten Weg.
        #
        # Der phone_insert-Schalter ("Handy darf einfügen") gilt hier genauso
        # wie im /api/transcribe-Pfad — SONST kann ihn jedes Gerät im WLAN mit
        # gültigem Token umgehen, obwohl der Nutzer ihn bewusst ausgeschaltet
        # hat. Ausnahme: Aufrufe von diesem Mac selbst (127.0.0.1/::1) — das
        # ist die Swift-Hülle, kein "Handy", und soll immer einfügen dürfen.
        c = cfg()
        is_local = request.remote_addr in ("127.0.0.1", "::1")
        if not is_local and not c.get("phone_insert", True):
            return jsonify(error="Einfügen vom Handy ist ausgeschaltet",
                           code="insert_disabled"), 403

        data = request.get_json(silent=True) or {}
        text = data.get("text", "")
        if not isinstance(text, str) or not text.strip():
            return jsonify(error="Feld 'text' fehlt oder ist leer"), 400
        from .inserter import insert_text

        inserted = insert_text(text, c.get("insert_mode", "paste"))
        return jsonify(ok=True, inserted=inserted)

    @app.post("/api/transcribe")
    def transcribe():
        from . import llm
        from .audio import decode_upload, is_silent

        c = cfg()
        f = request.files.get("audio")
        if f is None:
            return jsonify(error="Feld 'audio' fehlt"), 400
        blob = f.read()
        if len(blob) < 100:
            return jsonify(error="Audio leer"), 400

        language = request.form.get("language")
        if not language:
            # Sprach-Cache des Controllers nutzen (spart die teure Auto-Erkennung)
            if controller is not None:
                language = controller.effective_language()
            else:
                language = get_language()
        try:
            audio = decode_upload(blob, f.filename or "audio.m4a")
        except ValueError as e:
            return jsonify(error=str(e)), 415

        if len(audio) < 1600:  # < 0,1 s
            return jsonify(error="Aufnahme zu kurz"), 400
        if is_silent(audio, c.get("silence_rms", 0.006)):
            return jsonify(text="", raw="", language="", seconds=0, ms=0,
                           note="Stille erkannt — nichts transkribiert")

        dictionary = config.load_dictionary()
        result = engine.transcribe(
            audio, language=language, prompt_terms=dictionary.get("terms") or None
        )
        text = clean(result["text"], result["language"],
                     dictionary, config.load_snippets())
        if controller is not None and not request.form.get("language"):
            controller.note_detected_language(result["language"], text)
        t_llm = time.time()
        text, llm_used = llm.maybe_polish(text, c)
        llm_ms = int((time.time() - t_llm) * 1000) if llm_used else 0

        inserted = False
        if request.form.get("insert") == "1" and text:
            if c.get("phone_insert", True):
                from .inserter import insert_text

                inserted = insert_text(text, c.get("insert_mode", "paste"))
            else:
                log.info("Handy-Einfügen angefragt, aber in den Einstellungen aus")

        if text:
            config.add_history({
                "text": text, "raw": result["text"], "language": result["language"],
                "seconds": result["seconds"], "source": "phone", "time": time.time(),
            }, keep=int(c.get("history_keep", 50)))
            if controller is not None:
                controller.history_dirty = True
                controller.stats["count"] += 1
                controller.stats["audio_s"] += result["seconds"]
                controller.stats["engine_ms"] += result["ms"]
                if llm_used:
                    controller.stats["llm_used"] += 1
        log.info("Handy-Diktat (%ss Audio, %sms%s%s): %s",
                 result["seconds"], result["ms"],
                 ", LLM" if llm_used else "",
                 ", eingefügt" if inserted else "", config.loggable_text(text, c))
        return jsonify(
            text=text, raw=result["text"], language=result["language"],
            seconds=result["seconds"], ms=result["ms"], llm_ms=llm_ms,
            inserted=inserted,
        )

    return app


def start_server(engine, get_language, port: int, controller=None) -> threading.Thread:
    """Startet den HTTPS-Server in einem Daemon-Thread."""
    app = create_app(engine, get_language, controller=controller)
    cert, key = ensure_cert()

    def run():
        app.run(host="0.0.0.0", port=port, ssl_context=(cert, key),
                threaded=True, debug=False, use_reloader=False)

    t = threading.Thread(target=run, daemon=True, name="localflow-server")
    t.start()
    log.info("Server läuft: https://%s:%s", lan_ip(), port)
    return t
