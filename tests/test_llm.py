"""KI-Feinschliff: Fallback-Verhalten und Antwort-Validierung (ohne echtes Ollama)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from localflow import llm


def test_disabled_returns_unchanged():
    text, used = llm.maybe_polish("Hallo Welt.", {"llm_enabled": False})
    assert text == "Hallo Welt." and used is False


def test_unavailable_falls_back(monkeypatch):
    monkeypatch.setattr(llm, "available", lambda *a, **k: False)
    text, used = llm.maybe_polish("Hallo Welt.", {"llm_enabled": True})
    assert text == "Hallo Welt." and used is False


def test_polish_error_falls_back(monkeypatch):
    monkeypatch.setattr(llm, "available", lambda *a, **k: True)
    monkeypatch.setattr(llm, "polish", lambda *a, **k: None)
    text, used = llm.maybe_polish("Hallo Welt.", {"llm_enabled": True})
    assert text == "Hallo Welt." and used is False


def test_polish_success(monkeypatch):
    monkeypatch.setattr(llm, "available", lambda *a, **k: True)
    monkeypatch.setattr(llm, "polish", lambda *a, **k: "Hallo, Welt!")
    text, used = llm.maybe_polish("Hallo Welt.", {"llm_enabled": True})
    assert text == "Hallo, Welt!" and used is True


def test_validate_strips_quotes_and_think():
    assert llm._validate("abc", '"Hallo."') == "Hallo."
    assert llm._validate("abc", "<think>hmm</think>Hallo.") == "Hallo."
    assert llm._validate("abc", "```\nHallo.\n```") == "Hallo."


def test_validate_rejects_garbage():
    assert llm._validate("kurz", "") is None
    assert llm._validate("kurz", "x" * 5000) is None       # explodierte Länge
    assert llm._validate("kurz", "Als KI kann ich…") is None  # Meta-Gerede


def test_short_text_skipped():
    text, used = llm.maybe_polish("Ok", {"llm_enabled": True})
    assert used is False
