"""LocalFlow-Hauptprogramm: verdrahtet Engine, Hotkey, Aufnahme, Einfügen, Server, Menüleiste.

Start:            .venv/bin/python -m localflow.main
Nur Server:       .venv/bin/python -m localflow.main --serve-only
(--serve-only läuft ohne Menüleiste/Hotkey, z.B. für Tests)

Ablauf-Architektur (Fix für den „roter Kreis hängt"-Bug):
- Aufnehmen und Verarbeiten sind entkoppelt: fertige Aufnahmen wandern in eine
  Warteschlange und werden von EINEM Worker der Reihe nach transkribiert und
  eingefügt. Man kann also sofort das nächste Diktat starten.
- Ein Wächter-Thread prüft laufend: Ist die Hotkey-Taste physisch längst los-
  gelassen, obwohl kein Loslassen-Ereignis kam (verschlucktes Event)? Dann wird
  die Aufnahme gerettet statt ewig zu hängen. Zusätzlich ein Zeit-Deckel.
"""

import argparse
import logging
import queue
import subprocess
import threading
import time
from collections import deque
from logging.handlers import RotatingFileHandler
from pathlib import Path

from . import config
from .audio import Recorder
from .engine import SAMPLE_RATE, Engine

log = logging.getLogger("localflow")

SOUND_START = "/System/Library/Sounds/Tink.aiff"
SOUND_STOP = "/System/Library/Sounds/Pop.aiff"
SOUND_LOCK = "/System/Library/Sounds/Glass.aiff"
SOUND_ERROR = "/System/Library/Sounds/Basso.aiff"

# Tipp-Erkennung für den Freihand-Modus
TAP_MAX_S = 0.35       # kürzer als das = "Tipp" statt Diktat
DOUBLE_TAP_S = 0.6     # zwei Tipps innerhalb dieser Zeit = Freihand-Start
STUCK_GRACE_S = 0.35   # so lange darf "Taste unten ohne Flag" bestehen, bevor gerettet wird


class FlowController:
    """Zustands-Logik. Menüleiste liest .state per Timer (nur Haupt-Thread malt UI)."""

    def __init__(self, cfg: dict, recorder=None, engine=None):
        self.cfg = cfg
        self.engine = engine or Engine(cfg.get("model", "turbo"))
        self.recorder = recorder or Recorder()
        self.recording = False
        self.rec_started = 0.0
        self.locked = False          # Freihand-Aufnahme eingerastet
        self._last_tap = 0.0
        self._busy = 0
        self._busy_lock = threading.Lock()
        self._queue = queue.Queue()
        self._stop = False
        self.history_dirty = False
        self.last_error = ""
        self.started_at = time.time()
        self.stats = {"count": 0, "audio_s": 0.0, "engine_ms": 0, "llm_used": 0}
        self.errors = deque(maxlen=5)
        self._hotkey = None
        # Austauschbar für Tests:
        from .inserter import insert_text

        self._insert = insert_text
        self._phys_down = None  # wird in start() gesetzt
        # Sprach-Cache für "auto": erkannte Sprache wiederverwenden (~0,7s schneller)
        self._lang_cache = None
        self._lang_count = 0
        self._warned_loading = False  # "Modell lädt noch"-Hinweis nur einmal

    # ---- Zustand für die Menüleiste ----

    @property
    def state(self) -> str:
        if self.recording:
            return "rec"
        if self._busy:
            return "busy"
        return "idle" if self.engine.loaded else "loading"

    # ---- Lebenszyklus ----

    def start(self) -> None:
        self.engine.warmup_async()

        from .hotkey import HotkeyListener, physically_down, request_permissions

        request_permissions()
        if self._phys_down is None:
            self._phys_down = lambda: physically_down(self.cfg.get("hotkey", "alt_r"))
        self._hotkey = HotkeyListener(
            self.cfg.get("hotkey", "alt_r"), self.on_press, self.on_release
        )
        self._hotkey.start()
        threading.Thread(target=self._work_loop, daemon=True,
                         name="localflow-worker").start()
        threading.Thread(target=self._watchdog_loop, daemon=True,
                         name="localflow-watchdog").start()

    def shutdown(self) -> None:
        self._stop = True
        if self._hotkey:
            self._hotkey.stop()
        self._queue.put(None)

    # ---- Einstellungen (aus dem Menü) ----

    def set_language(self, code: str) -> None:
        self.cfg["language"] = code
        config.save_config(self.cfg)
        self._lang_cache = None  # Cache verwerfen, Nutzer hat umgestellt

    def get_language(self) -> str:
        return self.cfg.get("language", "auto")

    def effective_language(self):
        """Sprache für die Engine: fest gewählte direkt; bei "auto" die zuletzt
        erkannte (spart die teure Erkennung), mit periodischer Neu-Erkennung."""
        lang = self.get_language()
        if lang != "auto":
            return lang
        every = max(1, int(self.cfg.get("language_redetect_every", 8)))
        if self._lang_cache and self._lang_count % every != 0:
            return self._lang_cache
        return None  # echte Auto-Erkennung

    def note_detected_language(self, language: str, text: str) -> None:
        """Nach jeder Transkription: Cache pflegen."""
        self._lang_count += 1
        if text and language:
            self._lang_cache = language
        elif not text:
            self._lang_cache = None  # leeres Ergebnis -> nächstes Mal neu erkennen

    def set_toggle(self, key: str, value: bool) -> None:
        self.cfg[key] = value
        config.save_config(self.cfg)

    def set_hotkey(self, key_name: str) -> None:
        from .hotkey import HotkeyListener, physically_down

        self.cfg["hotkey"] = key_name
        config.save_config(self.cfg)
        if self._hotkey:
            self._hotkey.stop()
        self._phys_down = lambda: physically_down(key_name)
        self._hotkey = HotkeyListener(key_name, self.on_press, self.on_release)
        self._hotkey.start()

    def set_model(self, short: str) -> None:
        self.cfg["model"] = short
        config.save_config(self.cfg)
        self.engine = Engine(short)
        self.engine.warmup_async()

    # ---- Diktat-Ablauf (Hotkey-Callbacks: schnell & ausnahmesicher) ----

    def on_press(self) -> None:
        if self.recording:
            return  # läuft schon (z.B. Freihand) — Stopp passiert beim Loslassen
        try:
            self.recorder.start()
        except Exception:
            log.exception("Mikrofon-Start fehlgeschlagen (Mikrofon-Berechtigung?)")
            self._remember_error("Mikrofon-Start fehlgeschlagen — Berechtigung prüfen")
            self._sound(SOUND_ERROR)
            return
        self.recording = True
        self.locked = False
        self.rec_started = time.monotonic()
        self._sound(SOUND_START)

    def on_release(self) -> None:
        if not self.recording:
            return
        now = time.monotonic()
        dur = now - self.rec_started

        if self.locked:
            # Eingerastete Aufnahme: jeder weitere Tastendruck beendet sie
            self._finish()
            return

        if dur < TAP_MAX_S:
            # Nur ein Tipp: Aufnahme verwerfen ...
            self.recorder.stop()
            self.recording = False
            # ... außer es ist der zweite Tipp -> Freihand-Aufnahme einrasten
            if self.cfg.get("handsfree", True) and (now - self._last_tap) < DOUBLE_TAP_S:
                self._last_tap = 0.0
                try:
                    self.recorder.start()
                except Exception:
                    log.exception("Freihand-Start fehlgeschlagen")
                    self._sound(SOUND_ERROR)
                    return
                self.recording = True
                self.locked = True
                self.rec_started = now
                self._sound(SOUND_LOCK)
            else:
                self._last_tap = now
            return

        self._finish()

    def _finish(self) -> None:
        """Aufnahme beenden und zur Verarbeitung einreihen (niemals blockieren)."""
        try:
            audio = self.recorder.stop()
        except Exception:
            log.exception("Aufnahme-Stopp fehlgeschlagen")
            audio = None
        self.recording = False
        self.locked = False
        self._sound(SOUND_STOP)
        if audio is None or len(audio) < int(self.cfg.get("min_duration", 0.3) * SAMPLE_RATE):
            return
        with self._busy_lock:
            self._busy += 1
        self._queue.put(audio)

    # ---- Wächter: rettet verlorene Loslassen-Ereignisse ----

    def _watchdog_step(self) -> bool:
        """Eine Prüfung; True = eingegriffen. (Separat für Tests.)"""
        if not self.recording:
            return False
        dur = time.monotonic() - self.rec_started
        if dur > float(self.cfg.get("max_record_seconds", 120)):
            log.warning("Wächter: Aufnahme nach %.0fs automatisch beendet", dur)
            if self._hotkey:
                self._hotkey.reset()
            self._finish()
            return True
        if (not self.locked and dur > STUCK_GRACE_S
                and self._phys_down is not None and not self._phys_down()):
            log.warning("Wächter: Loslassen-Ereignis verloren — Aufnahme gerettet")
            if self._hotkey:
                self._hotkey.reset()
            self._finish()
            return True
        return False

    def _watchdog_loop(self) -> None:
        # Häufig pollen: pynput verschluckt bei rechten Modifier-Tasten oft das
        # Loslassen-Ereignis. Der Wächter erkennt die physisch losgelassene Taste
        # dann in ~80ms und beendet die Aufnahme, bevor das rote Icon auffällt.
        while not self._stop:
            time.sleep(0.08)
            try:
                self._watchdog_step()
            except Exception:
                log.exception("Wächter-Fehler")

    # ---- Verarbeitung (ein Worker, hält die Reihenfolge ein) ----

    def _work_loop(self) -> None:
        while True:
            audio = self._queue.get()
            if audio is None:
                return
            try:
                self._process(audio)
            except Exception:
                log.exception("Transkription fehlgeschlagen")
                self._remember_error("Transkription fehlgeschlagen (siehe Log)")
                self._sound(SOUND_ERROR)
            finally:
                with self._busy_lock:
                    self._busy -= 1

    def _process(self, audio) -> None:
        from . import llm
        from .audio import is_silent
        from .cleanup import clean

        if is_silent(audio, self.cfg.get("silence_rms", 0.006)):
            return  # nur Stille -> nichts einfügen (keine Halluzination)
        if not self.engine.loaded and not self._warned_loading:
            # Diktat kam mitten in den Kaltstart -> ehrlich Bescheid geben
            self._warned_loading = True
            self.last_error = ("Whisper lädt noch (einmalig nach dem Start) — "
                               "dein Diktat wird gleich verarbeitet…")
        dictionary = config.load_dictionary()
        result = self.engine.transcribe(
            audio,
            language=self.effective_language(),
            prompt_terms=dictionary.get("terms") or None,
        )
        text = clean(result["text"], result["language"],
                     dictionary, config.load_snippets())
        self.note_detected_language(result["language"], text)
        if not text:
            return
        t_llm = time.monotonic()
        text, llm_used = llm.maybe_polish(text, self.cfg)
        llm_ms = int((time.monotonic() - t_llm) * 1000)

        ok = self._insert(text, self.cfg.get("insert_mode", "paste"))
        if not ok:
            self._remember_error(
                "Einfügen fehlgeschlagen — Text liegt in der Zwischenablage (⌘V). "
                "Bedienungshilfen-Berechtigung prüfen!")
            self._sound(SOUND_ERROR)

        self.stats["count"] += 1
        self.stats["audio_s"] += result["seconds"]
        self.stats["engine_ms"] += result["ms"]
        if llm_used:
            self.stats["llm_used"] += 1
        config.add_history({
            "text": text, "raw": result["text"], "language": result["language"],
            "seconds": result["seconds"], "source": "mac", "time": time.time(),
        })
        self.history_dirty = True
        log.info("Diktat (%ss Audio | Whisper %sms | LLM %s): %s",
                 result["seconds"], result["ms"],
                 f"{llm_ms}ms" if llm_used else "übersprungen 🚀", text[:80])

    # ---- Datei-Transkription ----

    def transcribe_file(self, path: str) -> str:
        """Transkribiert eine Audio-/Videodatei; liefert den Pfad der Textdatei."""
        from . import llm
        from .audio import decode_upload
        from .cleanup import clean

        src = Path(path)
        audio = decode_upload(src.read_bytes(), src.name)
        result = self.engine.transcribe(audio, language=self.get_language())
        text = clean(result["text"], result["language"],
                     config.load_dictionary(), {})
        text, _ = llm.maybe_polish(text, self.cfg)
        out = src.with_suffix(src.suffix + ".txt")
        out.write_text(text + "\n", encoding="utf-8")
        log.info("Datei transkribiert: %s (%ss Audio) -> %s",
                 src.name, result["seconds"], out.name)
        return str(out)

    # ---- Diagnose ----

    def status_report(self) -> str:
        from . import llm
        from .hotkey import permissions_status
        from .server import lan_ip

        perms = permissions_status()
        ok = lambda v: "✅" if v else "❌"
        uptime = int(time.time() - self.started_at)
        s = self.stats
        avg = (s["engine_ms"] // s["count"]) if s["count"] else 0
        lines = [
            f"Läuft seit: {uptime // 3600}h {(uptime % 3600) // 60}min",
            f"Modell: {self.engine.repo} ({'geladen' if self.engine.loaded else 'lädt…'})",
            f"Diktate: {s['count']}  ·  Audio: {s['audio_s']:.0f}s  ·  Ø Engine: {avg}ms",
            f"KI-Feinschliff: {'an' if self.cfg.get('llm_enabled') else 'aus'}"
            f" ({self._llm_status()})  ·  genutzt: {s['llm_used']}×",
            f"Eingabemonitoring: {ok(perms['input_monitoring'])}   "
            f"Bedienungshilfen: {ok(perms['accessibility'])}",
            f"Server: https://{lan_ip()}:{self.cfg.get('server_port', 8790)}",
        ]
        if self.errors:
            lines.append("Letzte Fehler:")
            lines += [f"  • {e}" for e in list(self.errors)[-3:]]
        return "\n".join(lines)

    def _llm_status(self) -> str:
        from . import llm

        st = llm.status(self.cfg)
        if st["ready"]:
            return f"{st['backend']}: {st['model']} bereit"
        return f"kein LLM aktiv ({st['hint']})"

    def _remember_error(self, msg: str) -> None:
        self.errors.append(f"{time.strftime('%H:%M')} {msg}")
        self.last_error = msg

    def _sound(self, path: str) -> None:
        if self.cfg.get("sounds", True):
            try:
                subprocess.Popen(["afplay", path],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except OSError:
                pass


def _brand_process() -> None:
    """Kein 'Python' im Dock/App-Umschalter: Menüleisten-App ohne Dock-Symbol,
    Prozessname 'LocalFlow'."""
    try:
        from AppKit import NSApplication, NSApplicationActivationPolicyAccessory

        NSApplication.sharedApplication().setActivationPolicy_(
            NSApplicationActivationPolicyAccessory)
    except Exception:
        log.debug("Dock-Ausblendung nicht möglich", exc_info=True)
    try:
        from Foundation import NSProcessInfo

        NSProcessInfo.processInfo().setProcessName_("LocalFlow")
    except Exception:
        pass


def _setup_logging() -> None:
    config.ensure_files()
    handlers = [logging.StreamHandler()]
    try:
        handlers.append(RotatingFileHandler(
            config.LOG_DIR / "localflow.log", maxBytes=500_000, backupCount=2,
            encoding="utf-8"))
    except OSError:
        pass
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
        handlers=handlers,
    )
    logging.getLogger("werkzeug").setLevel(logging.WARNING)


def main() -> None:
    parser = argparse.ArgumentParser(description="LocalFlow — lokales Diktieren")
    parser.add_argument("--serve-only", action="store_true",
                        help="Nur HTTPS-Server starten (ohne Menüleiste/Hotkey)")
    parser.add_argument("--port", type=int, default=None)
    args = parser.parse_args()

    _setup_logging()
    cfg = config.load_config()
    if args.port:
        cfg["server_port"] = args.port

    controller = FlowController(cfg)

    from .server import lan_ip, start_server

    start_server(controller.engine, controller.get_language,
                 cfg.get("server_port", 8790), controller=controller)
    print(f"📱 Handy-Link: https://{lan_ip()}:{cfg.get('server_port', 8790)}")

    if args.serve_only:
        controller.engine.warmup_async()
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            pass
        return

    controller.start()

    _brand_process()  # "LocalFlow" statt "Python" im App-Umschalter, kein Dock-Symbol

    from .menubar import MenubarApp

    app = MenubarApp(controller)
    app.run()


if __name__ == "__main__":
    main()
