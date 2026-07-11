"""Unit-Tests für die Cleanup-Pipeline (schnell, ohne Audio/Modell)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from localflow.cleanup import apply_corrections, clean, match_snippet, remove_fillers


def test_fillers_german():
    assert clean("Ähm, hallo zusammen.", "de") == "Hallo zusammen."
    # Füllwort als Einschub -> ein Komma bleibt (natürlicher Satz)
    assert clean("Das ist, äh, ein Test.", "de") == "Das ist, ein Test."
    assert clean("Öhm, also ich denke, mhm, das passt.", "de") == "Also ich denke, das passt."


def test_german_um_is_kept():
    # "um" ist im Deutschen ein echtes Wort und darf NICHT entfernt werden
    assert clean("Wir treffen uns um drei Uhr.", "de") == "Wir treffen uns um drei Uhr."


def test_fillers_english():
    assert clean("Um, hello there.", "en") == "Hello there."
    assert clean("This is, uh, a test.", "en") == "This is, a test."


def test_word_boundaries():
    # Füllwort-Regex darf keine Wortteile treffen
    assert "Zähmung" in clean("Die Zähmung war schwierig.", "de")
    assert "Museum" in clean("Wir gehen ins Museum.", "en")
    assert "Uhr" in clean("Es ist drei Uhr.", "de")


def test_corrections():
    corrections = {"local flow": "LocalFlow", "wisper": "Whisper"}
    assert apply_corrections("Ich nutze local flow mit wisper.", corrections) == \
        "Ich nutze LocalFlow mit Whisper."
    assert apply_corrections("Local Flow ist gut.", corrections) == "LocalFlow ist gut."


def test_corrections_word_boundary():
    assert apply_corrections("Erikas Katze", {"erika": "Erika M."}) == "Erikas Katze"


def test_snippets():
    snippets = {"gruß": "Viele Grüße\nMinh"}
    assert match_snippet("Snippet Gruß", snippets) == "Viele Grüße\nMinh"
    assert match_snippet("snippet gruß.", snippets) == "Viele Grüße\nMinh"
    assert match_snippet("Schnipsel Gruß!", snippets) == "Viele Grüße\nMinh"
    assert match_snippet("Ganz normaler Satz.", snippets) is None
    assert clean("Snippet Gruß.", "de", {}, snippets) == "Viele Grüße\nMinh"


def test_tidy():
    assert clean("ähm", "de") == ""  # nur Füllwort -> leer
    assert clean("  hallo   welt  ", "de") == "Hallo welt"
    assert clean(", also gut.", "de") == "Also gut."


def test_empty():
    assert clean("", "de") == ""
    assert remove_fillers("", "de") == ""


def test_capitalize_first():
    assert clean("das ist ein test.", "de") == "Das ist ein test."


def test_initial_prompt_is_plain_wordlist(monkeypatch):
    """Regression: initial_prompt ist eine schlichte Wortliste ohne Einleitung wie
    'Glossar:', die Whisper sonst wörtlich in die Ausgabe echot."""
    import sys
    import types
    from pathlib import Path

    import numpy as np

    sys.path.insert(0, str(Path(__file__).parent.parent))
    from localflow.engine import Engine

    captured = {}
    fake = types.ModuleType("mlx_whisper")

    def fake_transcribe(audio, **kw):
        captured["initial_prompt"] = kw.get("initial_prompt")
        return {"text": "ok", "language": "de"}

    fake.transcribe = fake_transcribe
    monkeypatch.setitem(sys.modules, "mlx_whisper", fake)

    eng = Engine("turbo")
    eng.transcribe(np.zeros(16000, dtype=np.float32), language="de",
                   prompt_terms=["LocalFlow", "Whisper"])
    assert captured["initial_prompt"] == "LocalFlow, Whisper"
    assert "Glossar" not in (captured["initial_prompt"] or "")

    # Keine Terms -> gar kein Prompt (nichts kann geechot werden)
    eng.transcribe(np.zeros(16000, dtype=np.float32), language="de", prompt_terms=[])
    assert captured["initial_prompt"] is None
