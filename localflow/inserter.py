"""Fügt Text an der Cursor-Position der aktiven App ein.

Standard: Zwischenablage setzen -> ⌘V simulieren -> Zwischenablage wiederherstellen.
Alternative ("type"): Zeichen einzeln tippen (langsamer, lässt Clipboard unberührt).

Wichtig gegen den „roter Kreis hängt"-Bug: Vor dem simulierten ⌘V warten wir,
bis der Nutzer KEINE Modifier-Taste (⌥/⌘/⌃/⇧) mehr hält. Sonst würde aus ⌘V
z.B. ⌘⌥V (falscher Befehl in vielen Apps), und das künstliche Tasten-Ereignis
könnte den Hotkey-Listener aus dem Tritt bringen.
"""

import logging
import os
import subprocess
import threading
import time

log = logging.getLogger("localflow.inserter")


def _pbcopy_env() -> dict:
    """Umgebung für den pbcopy/pbpaste-Fallback ohne das von Python selbst
    gesetzte LC_CTYPE (PEP 538 C-Locale-Coercion) — pbcopy kennt "C.UTF-8"
    nicht als echte macOS-Locale und kann Text sonst falsch kodieren."""
    env = dict(os.environ)
    env.pop("LC_CTYPE", None)
    return env


def _pbpaste() -> str:
    # Direkt über NSPasteboard (Cocoa) statt über die pbcopy/pbpaste-Shell-Tools:
    # zuverlässiger als Subprocess+Locale und das, was echte Mac-Apps selbst nutzen.
    # Ein Bug, bei dem über LocalFlows eigenes synthetisches ⌘V eingefügte Umlaute
    # als Mojibake ankamen (Ziel-App las eine falsche Zwischenablage-Variante),
    # verschwand reproduzierbar, sobald NSPasteboard statt der pbcopy-Shell schrieb.
    try:
        from AppKit import NSPasteboard, NSPasteboardTypeString

        pb = NSPasteboard.generalPasteboard()
        return pb.stringForType_(NSPasteboardTypeString) or ""
    except Exception:
        log.debug("NSPasteboard nicht verfügbar, Fallback auf pbpaste", exc_info=True)
        r = subprocess.run(["pbpaste"], capture_output=True, env=_pbcopy_env())
        try:
            return r.stdout.decode("utf-8")
        except UnicodeDecodeError:
            return ""


def _pbcopy(text: str) -> None:
    try:
        from AppKit import NSPasteboard, NSPasteboardTypeString

        pb = NSPasteboard.generalPasteboard()
        pb.clearContents()
        pb.setString_forType_(text, NSPasteboardTypeString)
    except Exception:
        log.debug("NSPasteboard nicht verfügbar, Fallback auf pbcopy", exc_info=True)
        subprocess.run(["pbcopy"], input=text.encode("utf-8"), check=True,
                        env=_pbcopy_env())


def copy_to_clipboard(text: str) -> None:
    """Öffentlicher Zwischenablage-Helfer (Menü: Verlauf/Diktat/Link kopieren) —
    nutzt denselben NSPasteboard-Weg wie das Einfügen."""
    _pbcopy(text)


def _post_cmd_v_quartz() -> bool:
    """Schneller Weg: ⌘V direkt als CGEvent posten (~200ms flotter als osascript).

    Nur wenn die Bedienungshilfen-Berechtigung sicher da ist — ohne sie würden
    die Events lautlos verpuffen, während osascript wenigstens laut scheitert.
    """
    try:
        import Quartz

        if not Quartz.CGPreflightPostEventAccess():
            return False
        v_key = 9  # kVK_ANSI_V (gleiche Position auf QWERTY und QWERTZ)
        src = Quartz.CGEventSourceCreate(Quartz.kCGEventSourceStateHIDSystemState)
        for is_down in (True, False):
            ev = Quartz.CGEventCreateKeyboardEvent(src, v_key, is_down)
            Quartz.CGEventSetFlags(ev, Quartz.kCGEventFlagMaskCommand)
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, ev)
        return True
    except Exception:
        log.debug("Quartz-Paste nicht möglich, nutze osascript", exc_info=True)
        return False


def _press_cmd_v() -> None:
    if _post_cmd_v_quartz():
        return
    subprocess.run(
        ["osascript", "-e",
         'tell application "System Events" to keystroke "v" using command down'],
        check=True, capture_output=True,
    )


def _wait_modifiers_clear(timeout: float = 4.0) -> None:
    """Wartet, bis keine Modifier-Taste mehr gedrückt ist (max. timeout Sekunden)."""
    try:
        from .hotkey import any_modifier_down
    except ImportError:
        return
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if not any_modifier_down():
                return
        except Exception:
            return
        time.sleep(0.05)
    log.debug("Modifier nach %.1fs immer noch gedrückt — füge trotzdem ein", timeout)


# ---- Leerzeichen zwischen aufeinanderfolgenden Diktaten ----
#
# Diktiert man zweimal hintereinander in dieselbe Zeile, klebten die Texte
# sonst aneinander ("HalloWie geht's") — cleanup.clean() strippt den Text ja.
# Statt blind ein Leerzeichen davorzusetzen (das gäbe am Zeilenanfang eine
# Einrückung), fragen wir die Ziel-App über die Bedienungshilfen-Schnittstelle
# nach dem Zeichen direkt vor dem Cursor. Gibt sie keine Auskunft (manche Apps
# tun das nicht), bleibt es beim alten Verhalten ohne Leerzeichen.

def char_before_cursor():
    """Zeichen unmittelbar vor dem Cursor im fokussierten Textfeld.

    None, wenn der Cursor am Anfang steht oder die App keine Auskunft gibt.
    """
    try:
        from ApplicationServices import (
            AXUIElementCopyAttributeValue,
            AXUIElementCopyParameterizedAttributeValue,
            AXUIElementCreateSystemWide,
            AXValueCreate,
            AXValueGetValue,
            kAXFocusedUIElementAttribute,
            kAXSelectedTextRangeAttribute,
            kAXStringForRangeParameterizedAttribute,
            kAXValueTypeCFRange,
        )
        from CoreFoundation import CFRange
    except ImportError:
        log.debug("ApplicationServices nicht verfügbar")
        return None

    try:
        system = AXUIElementCreateSystemWide()
        err, focused = AXUIElementCopyAttributeValue(
            system, kAXFocusedUIElementAttribute, None)
        if err or focused is None:
            return None

        err, range_value = AXUIElementCopyAttributeValue(
            focused, kAXSelectedTextRangeAttribute, None)
        if err or range_value is None:
            return None

        # pyobjc liefert (ok, (location, length))
        ok, cursor = AXValueGetValue(range_value, kAXValueTypeCFRange, None)
        if not ok:
            return None
        location = cursor[0]
        if location <= 0:
            return None  # Feld-/Zeilenanfang -> kein Leerzeichen

        # Gezielt EIN Zeichen lesen statt den ganzen Feldinhalt (in langen
        # Dokumenten wäre das unnötig teuer).
        one = AXValueCreate(kAXValueTypeCFRange, CFRange(location - 1, 1))
        err, previous = AXUIElementCopyParameterizedAttributeValue(
            focused, kAXStringForRangeParameterizedAttribute, one, None)
        if err or not previous:
            return None
        return previous[0]
    except Exception:
        log.debug("Cursor-Kontext nicht lesbar", exc_info=True)
        return None


def needs_leading_space(text: str, previous_char=None) -> bool:
    """Braucht text ein Leerzeichen davor, damit er nicht am Vorigen klebt?

    previous_char nur für Tests; sonst wird der Cursor-Kontext gelesen.
    """
    if not text or text[0] in ",.!?;:":
        return False  # vor Satzzeichen gehört nie ein Leerzeichen
    previous = char_before_cursor() if previous_char is None else previous_char
    if not previous:
        return False
    return not previous.isspace()


def insert_text(text: str, mode: str = "paste") -> bool:
    """Fügt text in die aktive App ein. True bei Erfolg."""
    if not text:
        return False
    if needs_leading_space(text):
        text = " " + text
    if mode == "type":
        return _insert_by_typing(text)
    return _insert_by_paste(text)


def _insert_by_paste(text: str) -> bool:
    old = _pbpaste()
    try:
        _pbcopy(text)
        time.sleep(0.05)  # Clipboard-Sync abwarten
        _wait_modifiers_clear()
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

        _wait_modifiers_clear()
        Controller().type(text)
        return True
    except Exception:
        log.exception("Tippen fehlgeschlagen")
        return False
