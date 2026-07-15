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

from localflow.inserter import _pbcopy_env, _pbpaste, copy_to_clipboard

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
