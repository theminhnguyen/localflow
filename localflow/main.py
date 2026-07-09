"""LocalFlow-Hauptprogramm: verdrahtet Engine, Hotkey, Aufnahme, Einfügen, Server, Menüleiste.

Start:            .venv/bin/python -m localflow.main
Nur Server:       .venv/bin/python -m localflow.main --serve-only
(--serve-only läuft ohne Menüleiste/Hotkey, z.B. für Tests)
"""

import argparse
import logging
import subprocess
import threading
import time

from . import config
from .audio import Recorder
from .engine import SAMPLE_RATE, Engine

log = logging.getLogger("localflow")

SOUND_START = "/System/Library/Sounds/Tink.aiff"
SOUND_STOP = "/System/Library/Sounds/Pop.aiff"
SOUND_ERROR = "/System/Library/Sounds/Basso.aiff"


class FlowController:
    """Zustands-Maschine: idle -> rec -> busy -> idle. Menüleiste liest .state per Timer."""

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.engine = Engine(cfg.get("model", "turbo"))
        self.recorder = Recorder()
        self.state = "loading"  # loading | idle | rec | busy
        self.history_dirty = False
        self.last_error = ""
        self._hotkey = None

    # ---- Lebenszyklus ----

    def start(self) -> None:
        self.engine.warmup_async()

        threading.Thread(target=self._mark_ready_when_loaded, daemon=True).start()

        from .hotkey import HotkeyListener, request_permissions

        request_permissions()
        self._hotkey = HotkeyListener(
            self.cfg.get("hotkey", "alt_r"), self.on_press, self.on_release
        )
        self._hotkey.start()

    def _mark_ready_when_loaded(self):
        while not self.engine.loaded:
            time.sleep(0.5)
        if self.state == "loading":
            self.state = "idle"

    def shutdown(self) -> None:
        if self._hotkey:
            self._hotkey.stop()

    def set_language(self, code: str) -> None:
        self.cfg["language"] = code
        config.save_config(self.cfg)

    def get_language(self) -> str:
        return self.cfg.get("language", "auto")

    # ---- Diktat-Ablauf ----

    def on_press(self) -> None:
        if self.state in ("rec", "busy"):
            return
        try:
            self.recorder.start()
        except Exception:
            log.exception("Mikrofon-Start fehlgeschlagen (Mikrofon-Berechtigung?)")
            self._sound(SOUND_ERROR)
            return
        self.state = "rec"
        self._sound(SOUND_START)

    def on_release(self) -> None:
        if self.state != "rec":
            return
        audio = self.recorder.stop()
        self._sound(SOUND_STOP)
        min_samples = int(self.cfg.get("min_duration", 0.3) * SAMPLE_RATE)
        if len(audio) < min_samples:
            self.state = "idle"
            return
        self.state = "busy"
        threading.Thread(target=self._process, args=(audio,), daemon=True).start()

    def _process(self, audio) -> None:
        from .audio import is_silent
        from .cleanup import clean
        from .inserter import insert_text

        try:
            if is_silent(audio, self.cfg.get("silence_rms", 0.006)):
                self.state = "idle"  # nur Stille -> nichts einfügen (keine Halluzination)
                return
            dictionary = config.load_dictionary()
            result = self.engine.transcribe(
                audio,
                language=self.get_language(),
                prompt_terms=dictionary.get("terms") or None,
            )
            text = clean(result["text"], result["language"],
                         dictionary, config.load_snippets())
            if not text:
                self.state = "idle"
                return

            ok = insert_text(text, self.cfg.get("insert_mode", "paste"))
            if not ok:
                self.last_error = ("Einfügen fehlgeschlagen — Text liegt in der "
                                   "Zwischenablage (⌘V). Bedienungshilfen-Berechtigung prüfen!")
                self._sound(SOUND_ERROR)

            config.add_history({
                "text": text, "raw": result["text"], "language": result["language"],
                "seconds": result["seconds"], "source": "mac", "time": time.time(),
            })
            self.history_dirty = True
            log.info("Diktat (%ss Audio, %sms): %s",
                     result["seconds"], result["ms"], text[:80])
        except Exception:
            log.exception("Transkription fehlgeschlagen")
            self._sound(SOUND_ERROR)
        finally:
            self.state = "idle"

    def _sound(self, path: str) -> None:
        if self.cfg.get("sounds", True):
            subprocess.Popen(["afplay", path],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main() -> None:
    parser = argparse.ArgumentParser(description="LocalFlow — lokales Diktieren")
    parser.add_argument("--serve-only", action="store_true",
                        help="Nur HTTPS-Server starten (ohne Menüleiste/Hotkey)")
    parser.add_argument("--port", type=int, default=None)
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    config.ensure_files()
    cfg = config.load_config()
    if args.port:
        cfg["server_port"] = args.port

    controller = FlowController(cfg)

    from .server import lan_ip, start_server

    start_server(controller.engine, controller.get_language,
                 cfg.get("server_port", 8790))
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

    from .menubar import MenubarApp

    app = MenubarApp(controller)
    app.run()


if __name__ == "__main__":
    main()
