"""Zwischenablage-Helfer: Regression für den Umlaut-Mojibake-Bug.

Hintergrund: Über LocalFlows synthetisches ⌘V eingefügte Umlaute kamen in der
Ziel-App manchmal als Mojibake an, obwohl `pbpaste` die Zwischenablage korrekt
zeigte — die Ziel-App las offenbar eine andere, vom System zusätzlich
mit-erzeugte Variante als das, was ankam. Der zuverlässige Fix: Zwischenablage
direkt über NSPasteboard (Cocoa) setzen/lesen statt über die pbcopy/pbpaste-
Kommandozeilen-Werkzeuge — der Weg, den auch echte Mac-Apps nutzen.
`_pbcopy_env()` (LC_CTYPE aus der Umgebung entfernen, siehe PEP 538
C-Locale-Coercion) ist nur noch der Fallback, falls NSPasteboard mal fehlt.
"""

import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from localflow import inserter
from localflow.inserter import (
    _pbcopy_env,
    _pbpaste,
    copy_to_clipboard,
    needs_leading_space,
)

UMLAUT_TEXT = "Über ärgerliche Änderungen können wir später sprechen. äöüÄÖÜß"


@pytest.fixture(autouse=True)
def _reset_restore_state():
    # Modul-globaler Zustand des Restore-Timers -> zwischen Tests zurücksetzen,
    # sonst könnte ein Test vom Timing eines vorigen abhängen.
    yield
    with inserter._restore_lock:
        if inserter._restore_timer is not None:
            inserter._restore_timer.cancel()
        inserter._restore_timer = None
        inserter._restore_value = None


def test_pbcopy_env_strips_lc_ctype(monkeypatch):
    monkeypatch.setenv("LC_CTYPE", "C.UTF-8")
    env = _pbcopy_env()
    assert "LC_CTYPE" not in env


def test_pbcopy_env_keeps_other_vars(monkeypatch):
    monkeypatch.setenv("LC_CTYPE", "C.UTF-8")
    monkeypatch.setenv("HOME", "/Users/test")
    env = _pbcopy_env()
    assert env.get("HOME") == "/Users/test"


def test_clipboard_roundtrip_preserves_umlauts(monkeypatch):
    # Reproduziert exakt die Bedingung, unter der der Bug auftrat.
    monkeypatch.setenv("LC_CTYPE", "C.UTF-8")
    copy_to_clipboard(UMLAUT_TEXT)
    assert _pbpaste() == UMLAUT_TEXT


# ---- Leerzeichen zwischen aufeinanderfolgenden Diktaten ----

def test_space_after_word_in_same_line():
    # Cursor klebt direkt hinter dem vorigen Diktat -> Leerzeichen nötig
    assert needs_leading_space("Wie geht es", previous_char="n") is True


def test_space_after_sentence_end():
    assert needs_leading_space("Wie geht es", previous_char=".") is True


def test_no_space_at_line_start():
    # char_before_cursor() liefert None am Zeilen-/Feldanfang
    assert needs_leading_space("Guten Morgen", previous_char=None) is False


def test_no_space_after_existing_space():
    assert needs_leading_space("Guten Morgen", previous_char=" ") is False


def test_no_space_after_newline():
    assert needs_leading_space("Neue Zeile", previous_char="\n") is False


def test_no_space_before_punctuation():
    # "Hallo" + ", oder?" darf nicht zu "Hallo , oder?" werden
    assert needs_leading_space(", oder?", previous_char="o") is False


def test_no_space_for_empty_text():
    assert needs_leading_space("", previous_char="a") is False


def test_insert_text_prepends_space(monkeypatch):
    seen = []
    monkeypatch.setattr(inserter, "char_before_cursor", lambda: "n")
    monkeypatch.setattr(inserter, "_insert_by_paste", lambda t: (seen.append(t), True)[1])
    assert inserter.insert_text("Wie geht es") is True
    assert seen == [" Wie geht es"]


def test_insert_text_without_context_stays_unchanged(monkeypatch):
    # App gibt keine Auskunft -> altes Verhalten, kein Leerzeichen
    seen = []
    monkeypatch.setattr(inserter, "char_before_cursor", lambda: None)
    monkeypatch.setattr(inserter, "_insert_by_paste", lambda t: (seen.append(t), True)[1])
    inserter.insert_text("Guten Morgen")
    assert seen == ["Guten Morgen"]


def test_char_before_cursor_survives_missing_permission():
    # Ohne Bedienungshilfen-Recht (z.B. aus dem Test-Prozess heraus) darf die
    # Abfrage nur None liefern, niemals fliegen.
    assert inserter.char_before_cursor() is None


# ---- Zwischenablage-Restore: abbrechbar, überlebt Serien-Diktate (P0.2) ----
#
# Ohne Fix konnte der verzögerte Restore von Diktat 1 zwischen "Zwischenablage
# = Text 2 setzen" und dem simulierten ⌘V von Diktat 2 feuern -> eingefügt
# wurde die ALTE Zwischenablage statt Text 2. Diese Tests treiben genau dieses
# Szenario ohne echte Zwischenablage/Tasten (gemockt), damit sie schnell und
# deterministisch laufen.

class _FakeClipboard:
    """pbcopy/pbpaste-Attrappe: hält den Inhalt in einer Python-Variable."""

    def __init__(self, initial=""):
        self.value = initial
        self.history = []  # jeder gesetzte Wert, in Reihenfolge

    def copy(self, text):
        self.value = text
        self.history.append(text)

    def paste(self):
        return self.value


@pytest.fixture()
def fake_clipboard(monkeypatch):
    clip = _FakeClipboard("ORIGINAL")
    monkeypatch.setattr(inserter, "_pbpaste", clip.paste)
    monkeypatch.setattr(inserter, "_pbcopy", clip.copy)
    monkeypatch.setattr(inserter, "_press_cmd_v", lambda: None)
    monkeypatch.setattr(inserter, "_wait_modifiers_clear", lambda timeout=4.0: None)
    monkeypatch.setattr(inserter, "needs_leading_space", lambda text: False)
    return clip


def test_single_insert_schedules_restore_of_original(fake_clipboard):
    inserter.insert_text("Diktat 1")
    assert fake_clipboard.paste() == "Diktat 1"  # sofort eingefügt
    time.sleep(0.8)  # Restore-Timer (0.6s) abwarten
    assert fake_clipboard.paste() == "ORIGINAL"


def test_second_insert_within_restore_window_wins(fake_clipboard):
    # Kernszenario: Diktat 2 kommt INNERHALB der 0,6s-Restore-Frist von Diktat 1.
    inserter.insert_text("Diktat 1")
    assert fake_clipboard.paste() == "Diktat 1"

    time.sleep(0.2)  # deutlich vor Ablauf der 0,6s
    inserter.insert_text("Diktat 2")
    # Diktat 2 muss auf der Zwischenablage stehen -- NICHT von Diktat 1s
    # Restore überschrieben werden.
    assert fake_clipboard.paste() == "Diktat 2"

    time.sleep(0.8)  # jetzt darf der (einzige verbleibende) Restore feuern
    assert fake_clipboard.paste() == "ORIGINAL"


def test_restore_after_series_uses_original_not_intermediate_text(fake_clipboard):
    # Der wiederhergestellte Wert muss der Inhalt von VOR der ganzen Serie
    # sein ("ORIGINAL"), nicht "Diktat 1" oder "Diktat 2" (Zwischenstände).
    inserter.insert_text("Diktat 1")
    time.sleep(0.1)
    inserter.insert_text("Diktat 2")
    time.sleep(0.1)
    inserter.insert_text("Diktat 3")
    assert fake_clipboard.paste() == "Diktat 3"  # letzter Diktattext sofort sichtbar
    time.sleep(0.8)
    assert fake_clipboard.paste() == "ORIGINAL"  # danach der ursprüngliche Inhalt


def test_capture_old_clipboard_reads_real_clipboard_without_pending_timer(fake_clipboard):
    assert inserter._restore_timer is None
    assert inserter._capture_old_clipboard() == "ORIGINAL"


def test_failed_insert_leaves_text_in_clipboard_without_restore(monkeypatch, fake_clipboard):
    import subprocess

    def boom():
        raise subprocess.CalledProcessError(1, ["osascript"], stderr=b"nope")

    monkeypatch.setattr(inserter, "_press_cmd_v", boom)
    ok = inserter.insert_text("Diktat fehlgeschlagen")
    assert ok is False
    assert fake_clipboard.paste() == "Diktat fehlgeschlagen"  # bewusst nicht zurückgesetzt
    time.sleep(0.8)
    assert fake_clipboard.paste() == "Diktat fehlgeschlagen"  # immer noch, kein Restore geplant
