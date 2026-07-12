"""KI-Feinschliff: Backend-Erkennung, Fallback, Validierung (ohne echtes LLM)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from localflow import llm


def test_disabled_returns_unchanged():
    text, used = llm.maybe_polish("Hallo Welt.", {"llm_enabled": False})
    assert text == "Hallo Welt." and used is False


def test_no_backend_falls_back(monkeypatch):
    monkeypatch.setattr(llm, "resolve", lambda *a, **k: None)
    text, used = llm.maybe_polish("Hallo Welt.", {"llm_enabled": True})
    assert text == "Hallo Welt." and used is False


def test_polish_error_falls_back(monkeypatch):
    monkeypatch.setattr(llm, "polish", lambda *a, **k: None)
    text, used = llm.maybe_polish("Hallo Welt.", {"llm_enabled": True})
    assert text == "Hallo Welt." and used is False


def test_polish_success(monkeypatch):
    monkeypatch.setattr(llm, "polish", lambda *a, **k: "Hallo, Welt!")
    text, used = llm.maybe_polish("Hallo Welt.",
                                  {"llm_enabled": True, "llm_smart": False})
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


# ---- Backend-Erkennung ----

def test_pick_prefers_wanted_then_gemma():
    models = ["deepseek-r1", "gemma-4-e2b-it", "text-embed-nomic"]
    assert llm._pick(models, "gemma") == "gemma-4-e2b-it"      # Wunsch-Teilstring
    assert llm._pick(models, None) == "gemma-4-e2b-it"          # Gemma-Vorzug
    assert llm._pick(["deepseek-r1", "llama3"], None) == "deepseek-r1"  # sonst erstes
    assert llm._pick(["text-embedding-only"], None) is None     # nur Embeddings


def test_resolve_prefers_lmstudio(monkeypatch):
    monkeypatch.setattr(llm, "_lmstudio_models", lambda *a, **k: ["gemma-4-e2b-it"])
    monkeypatch.setattr(llm, "_ollama_models", lambda *a, **k: ["gemma3:4b"])
    backend, url, model = llm.resolve({"llm_backend": "auto", "llm_model": "gemma"})
    assert backend == "lmstudio" and model == "gemma-4-e2b-it"


def test_resolve_falls_back_to_ollama(monkeypatch):
    monkeypatch.setattr(llm, "_lmstudio_models", lambda *a, **k: [])
    monkeypatch.setattr(llm, "_ollama_models", lambda *a, **k: ["gemma3:4b"])
    r = llm.resolve({"llm_backend": "auto"})
    assert r is not None and r[0] == "ollama"


def test_resolve_forced_backend(monkeypatch):
    monkeypatch.setattr(llm, "_lmstudio_models", lambda *a, **k: [])
    monkeypatch.setattr(llm, "_ollama_models", lambda *a, **k: ["gemma3:4b"])
    assert llm.resolve({"llm_backend": "lmstudio"}) is None  # nur LM Studio erlaubt
    assert llm.resolve({"llm_backend": "ollama"}) is not None


def test_resolve_none_when_nothing(monkeypatch):
    monkeypatch.setattr(llm, "_lmstudio_models", lambda *a, **k: [])
    monkeypatch.setattr(llm, "_ollama_models", lambda *a, **k: [])
    assert llm.resolve({"llm_backend": "auto"}) is None
    assert llm.available({"llm_backend": "auto"}) is False


def test_status_ready(monkeypatch):
    monkeypatch.setattr(llm, "resolve", lambda *a, **k: ("lmstudio", llm.LMSTUDIO_URL, "gemma-4-e2b-it"))
    st = llm.status({"llm_backend": "auto"})
    assert st["ready"] and st["backend"] == "lmstudio" and st["model"] == "gemma-4-e2b-it"


def test_maybe_polish_skips_without_backend(monkeypatch):
    monkeypatch.setattr(llm, "resolve", lambda *a, **k: None)
    called = []
    text, used = llm.maybe_polish("Hallo Welt.", {"llm_enabled": True})
    assert used is False and text == "Hallo Welt."


# ---- 🚀 Schnell-Modus ----

def test_needs_polish_skips_short_clean():
    cfg = {"llm_smart": True, "llm_smart_min_words": 14}
    assert llm.needs_polish("Bitte schick mir die Unterlagen bis morgen.", cfg) is False


def test_needs_polish_triggers_on_correction():
    cfg = {"llm_smart": True}
    assert llm.needs_polish("Treffen um zwei, nein, um drei.", cfg) is True
    assert llm.needs_polish("Erstens das Angebot, zweitens die Preise.", cfg) is True
    assert llm.needs_polish("Meeting monday no wait tuesday.", cfg) is True


def test_needs_polish_triggers_on_length():
    cfg = {"llm_smart": True, "llm_smart_min_words": 5}
    assert llm.needs_polish("eins zwei drei vier fünf sechs", cfg) is True


def test_needs_polish_off_means_always():
    assert llm.needs_polish("Kurz.", {"llm_smart": False}) is True


def test_maybe_polish_smart_skip(monkeypatch):
    called = []
    monkeypatch.setattr(llm, "polish", lambda *a, **k: called.append(1) or "X")
    text, used = llm.maybe_polish(
        "Bitte schick mir die Unterlagen.", {"llm_enabled": True, "llm_smart": True})
    assert used is False and called == []
