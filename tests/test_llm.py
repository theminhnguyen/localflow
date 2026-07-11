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


def test_available_requires_model(monkeypatch):
    monkeypatch.setattr(llm, "server_up", lambda *a, **k: True)
    monkeypatch.setattr(llm, "has_model", lambda m, **k: m == "gemma3:4b")
    assert llm.available() is True                 # ohne Modellprüfung
    assert llm.available("gemma3:4b") is True       # Modell vorhanden
    assert llm.available("fehlt:1b") is False       # Modell fehlt


def test_available_false_when_server_down(monkeypatch):
    monkeypatch.setattr(llm, "server_up", lambda *a, **k: False)
    assert llm.available() is False
    assert llm.available("gemma3:4b") is False


def test_maybe_polish_skips_when_model_missing(monkeypatch):
    monkeypatch.setattr(llm, "server_up", lambda *a, **k: True)
    monkeypatch.setattr(llm, "has_model", lambda m, **k: False)
    called = []
    monkeypatch.setattr(llm, "polish", lambda *a, **k: called.append(1) or "X")
    text, used = llm.maybe_polish("Hallo Welt.", {"llm_enabled": True, "llm_model": "gemma3:4b"})
    assert used is False and text == "Hallo Welt." and called == []
