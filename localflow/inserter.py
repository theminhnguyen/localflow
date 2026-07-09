"""Fügt Text an der Cursor-Position der aktiven App ein.

Standard: Zwischenablage setzen -> ⌘V simulieren -> Zwischenablage wiederherstellen.
Alternative ("type"): Zeichen einzeln tippen (langsamer, lässt Clipboard unberührt).
Hinweis: Nicht-Text-Inhalte (Bilder) in der Zwischenablage gehen beim Wiederherstellen
verloren — Text bleibt erhalten.
"""

import logging
import subprocess
import threading
import time

log = logging.getLogger("localflow.inserter")


def _pbpaste() -> str:
    r = subprocess.run(["pbpaste"], capture_output=True)
    try:
        return r.stdout.decode("utf-8")
    except UnicodeDecodeError:
        return ""


def _pbcopy(text: str) -> None:
    subprocess.run(["pbcopy"], input=text.encode("utf-8"), check=True)


def _press_cmd_v() -> None:
    subprocess.run(
        ["osascript", "-e",
         'tell application "System Events" to keystroke "v" using command down'],
        check=True, capture_output=True,
    )


def insert_text(text: str, mode: str = "paste") -> bool:
    """Fügt text in die aktive App ein. True bei Erfolg."""
    if not text:
        return False
    if mode == "type":
        return _insert_by_typing(text)
    return _insert_by_paste(text)


def _insert_by_paste(text: str) -> bool:
    old = _pbpaste()
    try:
        _pbcopy(text)
        time.sleep(0.05)  # Clipboard-Sync abwarten
        _press_cmd_v()
    except subprocess.CalledProcessError as e:
        log.error("Einfügen fehlgeschlagen (Bedienungshilfen-Berechtigung fehlt?): %s",
                  e.stderr.decode() if e.stderr else e)
        # Text bleibt in der Zwischenablage, damit nichts verloren geht
        return False

    # Zwischenablage erst nach dem Paste wiederherstellen (verzögert, nicht blockierend)
    def restore():
        time.sleep(0.6)
        try:
            _pbcopy(old)
        except Exception:
            pass

    if old:
        threading.Thread(target=restore, daemon=True).start()
    return True


def _insert_by_typing(text: str) -> bool:
    try:
        from pynput.keyboard import Controller

        Controller().type(text)
        return True
    except Exception:
        log.exception("Tippen fehlgeschlagen")
        return False
