"""End-to-End: macOS-Stimme -> Audio -> Whisper -> Cleanup. Braucht das Modell (langsam).

Ausführen:  .venv/bin/python -m pytest tests/test_e2e.py -q -s
"""

import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from localflow.audio import decode_upload
from localflow.cleanup import clean
from localflow.engine import Engine


@pytest.fixture(scope="module")
def engine():
    e = Engine("turbo")
    e.warmup()
    return e


def _say(text: str, voice: str = "Anna") -> bytes:
    with tempfile.TemporaryDirectory() as d:
        aiff = Path(d) / "s.aiff"
        subprocess.run(["say", "-v", voice, "-o", str(aiff), text], check=True)
        return aiff.read_bytes()


def _transcribe(engine, text, language="de"):
    audio = decode_upload(_say(text), "s.aiff")
    result = engine.transcribe(audio, language=language)
    cleaned = clean(result["text"], result["language"])
    print(f"\n  gesprochen: {text!r}\n  erkannt:    {cleaned!r}  ({result['ms']}ms)")
    return cleaned.lower()


def _contains_most(got: str, words: list, need: float = 0.7) -> bool:
    hits = sum(1 for w in words if w.lower() in got)
    return hits >= len(words) * need


def test_simple_german(engine):
    got = _transcribe(engine, "Hallo, das ist ein Test.")
    assert _contains_most(got, ["hallo", "test"])


def test_longer_german(engine):
    got = _transcribe(engine, "Bitte kauf noch Milch, Brot und Eier für das Frühstück.")
    assert _contains_most(got, ["milch", "brot", "eier", "frühstück"])


def test_english(engine):
    got = _transcribe(engine, "The quick brown fox jumps over the lazy dog.", language="en")
    assert _contains_most(got, ["quick", "brown", "fox", "lazy", "dog"])


def test_silence_is_empty(engine):
    """Stille darf NICHT als Text halluziniert werden."""
    import numpy as np

    from localflow.audio import is_silent

    silence = np.zeros(16000, dtype=np.float32)
    assert is_silent(silence)  # wird vor der Transkription abgefangen
