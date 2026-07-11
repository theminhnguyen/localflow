"""Whisper-Engine: lokale Spracherkennung via mlx-whisper (Apple Silicon GPU)."""

import logging
import threading
import time

import numpy as np

log = logging.getLogger("localflow.engine")

# Kurznamen -> Hugging-Face-Repos (werden beim ersten Start automatisch geladen)
MODELS = {
    "turbo": "mlx-community/whisper-large-v3-turbo",
    "small": "mlx-community/whisper-small-mlx",
    "base": "mlx-community/whisper-base-mlx",
    "tiny": "mlx-community/whisper-tiny",
}

SAMPLE_RATE = 16000


class Engine:
    """Lädt das Modell einmal (lazy) und transkribiert 16-kHz-Mono-Float32-Audio."""

    def __init__(self, model: str = "turbo"):
        self.repo = MODELS.get(model, model)
        self._lock = threading.Lock()
        self._loaded = False

    def warmup(self) -> None:
        """Lädt Modellgewichte vorab (1s Stille transkribieren)."""
        self.transcribe(np.zeros(SAMPLE_RATE, dtype=np.float32), language="de")
        log.info("Modell %s geladen", self.repo)

    def warmup_async(self) -> threading.Thread:
        t = threading.Thread(target=self._safe_warmup, daemon=True)
        t.start()
        return t

    def _safe_warmup(self):
        try:
            self.warmup()
        except Exception:
            log.exception("Modell-Warmup fehlgeschlagen")

    @property
    def loaded(self) -> bool:
        return self._loaded

    def transcribe(self, audio: np.ndarray, language: str | None = None,
                   prompt_terms: list | None = None) -> dict:
        """Audio (float32, mono, 16 kHz) -> {"text", "language", "seconds", "ms"}.

        language=None/"auto" = automatische Erkennung.
        prompt_terms = Eigennamen/Fachbegriffe als Erkennungs-Hinweis.
        """
        import mlx_whisper  # lazy: Import dauert, nur bei Bedarf

        if language in (None, "", "auto"):
            language = None
        # initial_prompt als schlichte Wortliste (ohne einleitende Wörter wie
        # "Glossar:", die Whisper sonst wörtlich in die Ausgabe echot).
        initial_prompt = None
        if prompt_terms:
            terms = [t.strip() for t in prompt_terms if t and t.strip()]
            if terms:
                initial_prompt = ", ".join(terms)

        start = time.monotonic()
        # mlx ist nicht thread-sicher -> immer nur eine Transkription gleichzeitig
        with self._lock:
            result = mlx_whisper.transcribe(
                audio,
                path_or_hf_repo=self.repo,
                language=language,
                initial_prompt=initial_prompt,
                fp16=True,
            )
            self._loaded = True
        ms = int((time.monotonic() - start) * 1000)

        return {
            "text": (result.get("text") or "").strip(),
            "language": result.get("language") or (language or ""),
            "seconds": round(len(audio) / SAMPLE_RATE, 2),
            "ms": ms,
        }
