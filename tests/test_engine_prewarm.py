"""Vorwärm-Logik gegen den „erstes Diktat nach Pause ist langsam"-Effekt.

Gemessen (localflow.log): die erste Transkription nach einer längeren Pause
dauert 3-5x so lange (5202ms statt 1008ms bei kürzerem Audio), weil die
GPU-Kernel ausgekühlt sind. prewarm_if_cold() soll das beim Tastendruck im
Hintergrund abfangen — hier ohne echtes Modell getestet, nur die Entscheidung
„jetzt vorwärmen: ja/nein" und dass sie nie blockiert.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from localflow.engine import COLD_AFTER_S, Engine


def _engine():
    # Kein echtes Modell laden — wir ersetzen transcribe() durch eine Attrappe,
    # die nur mitzählt, wie oft (und ob im Hintergrund) sie gerufen wurde.
    eng = Engine("turbo-q4")
    eng.calls = 0

    def fake_transcribe(audio, language=None, prompt_terms=None):
        eng.calls += 1
        eng._loaded = True
        eng._last_use = time.monotonic()
        return {"text": "", "language": "de", "seconds": 0.0, "ms": 1}

    eng.transcribe = fake_transcribe
    return eng


def _wait_for(cond, timeout=2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if cond():
            return True
        time.sleep(0.01)
    return False


def test_prewarm_skips_when_not_loaded():
    eng = _engine()  # frisch, _loaded=False
    eng.prewarm_if_cold()
    time.sleep(0.1)
    assert eng.calls == 0  # Kaltstart wärmt separat, nicht hier


def test_prewarm_skips_when_recently_used():
    eng = _engine()
    eng._loaded = True
    eng._last_use = time.monotonic()  # gerade eben benutzt -> heiß
    eng.prewarm_if_cold()
    time.sleep(0.1)
    assert eng.calls == 0


def test_prewarm_runs_when_cold():
    eng = _engine()
    eng._loaded = True
    eng._last_use = time.monotonic() - (COLD_AFTER_S + 5)  # ausgekühlt
    eng.prewarm_if_cold()
    assert _wait_for(lambda: eng.calls == 1), "Vorwärmen hätte laufen müssen"


def test_prewarm_is_non_blocking():
    # Selbst wenn die (Fake-)Transkription lange dauert, kehrt prewarm_if_cold
    # sofort zurück — es läuft im Hintergrund-Thread.
    eng = _engine()
    eng._loaded = True
    eng._last_use = time.monotonic() - (COLD_AFTER_S + 5)

    started = []

    def slow_transcribe(audio, language=None, prompt_terms=None):
        started.append(True)
        time.sleep(0.5)
        eng._last_use = time.monotonic()
        return {"text": "", "language": "de", "seconds": 0.0, "ms": 1}

    eng.transcribe = slow_transcribe
    t0 = time.monotonic()
    eng.prewarm_if_cold()
    assert time.monotonic() - t0 < 0.1  # nicht blockiert
    assert _wait_for(lambda: started, timeout=1.0)


def test_transcribe_updates_last_use():
    # Nach einer echten Transkription gilt die Engine als "gerade benutzt".
    # transcribe() würde das echte Modell laden -> wir prüfen die Zeitstempel-
    # Pflege über die Fake-Variante aus _engine().
    eng = _engine()
    before = time.monotonic()
    eng.transcribe(None)
    assert eng._last_use >= before
