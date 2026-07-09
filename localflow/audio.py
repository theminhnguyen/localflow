"""Audio-Hilfen: WAV laden, Uploads dekodieren (afconvert/ffmpeg), Mikrofon-Aufnahme."""

import logging
import shutil
import subprocess
import tempfile
import wave
from pathlib import Path

import numpy as np

from .engine import SAMPLE_RATE

log = logging.getLogger("localflow.audio")


def load_wav(path: str) -> np.ndarray:
    """Liest 16-bit-PCM-WAV -> float32 mono, resampled auf 16 kHz."""
    with wave.open(str(path), "rb") as w:
        n_channels = w.getnchannels()
        rate = w.getframerate()
        sampwidth = w.getsampwidth()
        frames = w.readframes(w.getnframes())

    if sampwidth == 2:
        data = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
    elif sampwidth == 4:
        data = np.frombuffer(frames, dtype=np.int32).astype(np.float32) / 2147483648.0
    elif sampwidth == 1:
        data = (np.frombuffer(frames, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    else:
        raise ValueError(f"WAV-Samplebreite {sampwidth} nicht unterstützt")

    if n_channels > 1:
        data = data.reshape(-1, n_channels).mean(axis=1)

    if rate != SAMPLE_RATE:
        data = resample(data, rate, SAMPLE_RATE)
    return data


def rms(audio: np.ndarray) -> float:
    """Effektiver Lautstärke-Pegel (Root Mean Square) eines Float32-Signals."""
    if len(audio) == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(audio.astype(np.float64)))))


def is_silent(audio: np.ndarray, threshold: float = 0.006) -> bool:
    """True, wenn die Aufnahme faktisch leer ist (schützt vor Whisper-Halluzinationen)."""
    return rms(audio) < threshold


def resample(data: np.ndarray, src_rate: int, dst_rate: int) -> np.ndarray:
    """Einfaches lineares Resampling (für Sprache völlig ausreichend)."""
    n_dst = int(round(len(data) * dst_rate / src_rate))
    if n_dst <= 0:
        return np.zeros(0, dtype=np.float32)
    x_src = np.linspace(0.0, 1.0, num=len(data), endpoint=False)
    x_dst = np.linspace(0.0, 1.0, num=n_dst, endpoint=False)
    return np.interp(x_dst, x_src, data).astype(np.float32)


def decode_upload(blob: bytes, filename: str = "audio.m4a") -> np.ndarray:
    """Dekodiert hochgeladenes Audio (m4a/mp4/aac/wav/webm...) -> float32 mono 16 kHz.

    Nutzt das macOS-eigene afconvert; ffmpeg als Fallback, falls installiert.
    """
    suffix = Path(filename).suffix or ".m4a"
    with tempfile.TemporaryDirectory(prefix="localflow_") as tmpdir:
        src = Path(tmpdir) / f"in{suffix}"
        dst = Path(tmpdir) / "out.wav"
        src.write_bytes(blob)

        if suffix.lower() == ".wav":
            try:
                return load_wav(src)
            except Exception:
                pass  # kaputter WAV-Header -> Konverter versuchen

        # 1. Versuch: afconvert (kann AAC/M4A/MP4/AIFF/CAF — reicht für iOS/Safari)
        r = subprocess.run(
            ["afconvert", str(src), "-d", "LEI16@16000", "-f", "WAVE", "-c", "1", str(dst)],
            capture_output=True, text=True,
        )
        if r.returncode == 0 and dst.exists():
            return load_wav(dst)
        log.debug("afconvert fehlgeschlagen: %s", r.stderr.strip())

        # 2. Versuch: ffmpeg (falls vorhanden — nötig für webm/opus von Desktop-Browsern)
        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg:
            r = subprocess.run(
                [ffmpeg, "-y", "-i", str(src), "-ar", str(SAMPLE_RATE), "-ac", "1",
                 "-f", "wav", str(dst)],
                capture_output=True, text=True,
            )
            if r.returncode == 0 and dst.exists():
                return load_wav(dst)
            log.debug("ffmpeg fehlgeschlagen: %s", r.stderr.strip()[-500:])

        raise ValueError(
            f"Audioformat '{suffix}' konnte nicht dekodiert werden "
            "(afconvert fehlgeschlagen, ffmpeg nicht installiert)"
        )


class Recorder:
    """Mikrofon-Aufnahme über sounddevice (PortAudio), direkt in 16 kHz mono."""

    def __init__(self):
        self._stream = None
        self._chunks = []

    @property
    def active(self) -> bool:
        return self._stream is not None

    def start(self) -> None:
        if self._stream is not None:
            return
        import sounddevice as sd

        self._chunks = []

        def callback(indata, frames, time_info, status):
            if status:
                log.debug("Aufnahme-Status: %s", status)
            self._chunks.append(indata.copy())

        self._stream = sd.InputStream(
            samplerate=SAMPLE_RATE, channels=1, dtype="float32", callback=callback
        )
        self._stream.start()

    def stop(self) -> np.ndarray:
        if self._stream is None:
            return np.zeros(0, dtype=np.float32)
        stream, self._stream = self._stream, None
        stream.stop()
        stream.close()
        if not self._chunks:
            return np.zeros(0, dtype=np.float32)
        return np.concatenate(self._chunks)[:, 0]
