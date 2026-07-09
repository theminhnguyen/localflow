"""Audio-Tests: RMS/Stille-Erkennung und WAV-Laden (schnell, ohne Modell)."""

import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))

from localflow.audio import decode_upload, is_silent, load_wav, resample, rms
from localflow.engine import SAMPLE_RATE


def test_rms_silence():
    assert rms(np.zeros(16000, dtype=np.float32)) == 0.0
    assert is_silent(np.zeros(16000, dtype=np.float32))


def test_rms_signal():
    t = np.linspace(0, 1, SAMPLE_RATE, endpoint=False)
    tone = (0.3 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
    assert rms(tone) > 0.1
    assert not is_silent(tone)


def test_resample_length():
    data = np.zeros(48000, dtype=np.float32)
    out = resample(data, 48000, 16000)
    assert abs(len(out) - 16000) <= 1


def test_say_produces_loadable_wav():
    """macOS 'say' -> AIFF -> afconvert WAV -> laden. Belegt die Upload-Kette."""
    with tempfile.TemporaryDirectory() as d:
        aiff = Path(d) / "s.aiff"
        subprocess.run(["say", "-v", "Anna", "-o", str(aiff), "Hallo Welt"], check=True)
        audio = decode_upload(aiff.read_bytes(), "s.aiff")
        assert len(audio) > SAMPLE_RATE * 0.3   # mind. 0,3 s Audio
        assert not is_silent(audio)              # echte Sprache, keine Stille
