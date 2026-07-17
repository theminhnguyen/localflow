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
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from localflow import inserter
from localflow.inserter import (
    _pbcopy_env,
    _pbpaste,
    copy_to_clipboard,
    needs_leading_space,
)

UMLAUT_TEXT = "Über ärgerliche Änderungen können wir später sprechen. äöüÄÖÜß"


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
