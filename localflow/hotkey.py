"""Globaler Hold-to-talk-Hotkey über pynput (braucht Eingabemonitoring-Berechtigung).

Zusätzlich: direkte Abfrage des physischen Tastenzustands über Quartz.
Damit kann ein Wächter erkennen, dass die Taste längst losgelassen wurde,
auch wenn das Loslassen-Ereignis verloren ging (z.B. weil das simulierte ⌘V
des vorigen Diktats dazwischenfunkte) — der Fix für den „roter Kreis hängt"-Bug.
"""

import logging

log = logging.getLogger("localflow.hotkey")

KEY_NAMES = {
    "alt_r": "rechte Option-Taste (⌥)",
    "cmd_r": "rechte Command-Taste (⌘)",
    "ctrl_r": "rechte Control-Taste (⌃)",
    "f13": "F13",
    "f14": "F14",
}


class HotkeyListener:
    """Ruft on_press beim Drücken und on_release beim Loslassen der Hotkey-Taste auf."""

    def __init__(self, key_name: str, on_press, on_release):
        from pynput import keyboard

        self._keyboard = keyboard
        try:
            self._key = getattr(keyboard.Key, key_name)
        except AttributeError:
            log.warning("Unbekannter Hotkey '%s', nutze alt_r", key_name)
            self._key = keyboard.Key.alt_r
        self._on_press = on_press
        self._on_release = on_release
        self._down = False
        self._listener = None

    def start(self) -> None:
        kb = self._keyboard

        def press(key):
            if key == self._key and not self._down:
                self._down = True
                try:
                    self._on_press()
                except Exception:
                    log.exception("Fehler beim Aufnahme-Start")

        def release(key):
            if key == self._key and self._down:
                self._down = False
                try:
                    self._on_release()
                except Exception:
                    log.exception("Fehler beim Aufnahme-Stopp")

        self._listener = kb.Listener(on_press=press, on_release=release)
        self._listener.daemon = True
        self._listener.start()

    def reset(self) -> None:
        """Interne Druck-Markierung zurücksetzen (nach Wächter-Rettung)."""
        self._down = False

    def stop(self) -> None:
        if self._listener:
            self._listener.stop()
            self._listener = None


# ---- Physischer Tastenzustand (Quartz) ----

def _flags():
    import Quartz

    return Quartz.CGEventSourceFlagsState(Quartz.kCGEventSourceStateHIDSystemState)


def physically_down(key_name: str) -> bool:
    """Ist die Hotkey-Taste gerade wirklich gedrückt?

    Für F-Tasten gibt es kein Modifier-Flag -> True (Wächter bleibt dann neutral
    und greift nur über den Zeit-Deckel ein).
    """
    try:
        import Quartz

        masks = {
            "alt_r": Quartz.kCGEventFlagMaskAlternate,
            "cmd_r": Quartz.kCGEventFlagMaskCommand,
            "ctrl_r": Quartz.kCGEventFlagMaskControl,
        }
        mask = masks.get(key_name)
        if mask is None:
            return True
        return bool(_flags() & mask)
    except Exception:
        return True  # im Zweifel nicht eingreifen


def any_modifier_down() -> bool:
    """Hält der Nutzer gerade ⌘/⌥/⌃/⇧ gedrückt? (Fürs saubere Einfügen.)"""
    try:
        import Quartz

        combo = (Quartz.kCGEventFlagMaskCommand | Quartz.kCGEventFlagMaskAlternate
                 | Quartz.kCGEventFlagMaskControl | Quartz.kCGEventFlagMaskShift)
        return bool(_flags() & combo)
    except Exception:
        return False


def permissions_status() -> dict:
    """Prüft die macOS-Berechtigungen für Hotkey (Eingabemonitoring) und ⌘V (Bedienungshilfen)."""
    status = {"input_monitoring": None, "accessibility": None}
    try:
        import Quartz

        status["input_monitoring"] = bool(Quartz.CGPreflightListenEventAccess())
        status["accessibility"] = bool(Quartz.CGPreflightPostEventAccess())
    except Exception:
        log.exception("Berechtigungs-Check fehlgeschlagen")
    return status


def request_permissions() -> None:
    """Löst die macOS-Berechtigungs-Dialoge aus (einmalig nötig)."""
    try:
        import Quartz

        if not Quartz.CGPreflightListenEventAccess():
            Quartz.CGRequestListenEventAccess()
        if not Quartz.CGPreflightPostEventAccess():
            Quartz.CGRequestPostEventAccess()
    except Exception:
        log.exception("Berechtigungs-Anfrage fehlgeschlagen")
