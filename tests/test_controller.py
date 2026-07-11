"""Zustands-Maschine des FlowControllers: Serien-Diktate, Wächter, Freihand.

Alles ohne Mikrofon/Modell — Recorder, Engine und Einfügen sind Attrappen.
"""

import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))

from localflow.engine import SAMPLE_RATE
from localflow.main import FlowController

# 1s "Sprache" (Rauschen über der Stille-Schwelle)
def speech(seconds=1.0):
    rng = np.random.default_rng(42)
    return (rng.standard_normal(int(SAMPLE_RATE * seconds)) * 0.1).astype(np.float32)


class FakeRecorder:
    def __init__(self):
        self.active = False
        self.starts = 0

    def start(self):
        self.active = True
        self.starts += 1

    def stop(self):
        self.active = False
        return speech()


class FakeEngine:
    def __init__(self):
        self.loaded = True
        self.repo = "fake-model"
        self.calls = 0

    def transcribe(self, audio, language=None, prompt_terms=None):
        self.calls += 1
        time.sleep(0.05)  # simulierte Rechenzeit
        return {"text": f"Diktat {self.calls}", "language": "de",
                "seconds": round(len(audio) / SAMPLE_RATE, 2), "ms": 50}

    def warmup_async(self):
        pass


def make_controller(**cfg_extra):
    cfg = {"language": "de", "min_duration": 0.3, "silence_rms": 0.006,
           "sounds": False, "llm_enabled": False, "handsfree": True,
           "max_record_seconds": 120, "insert_mode": "paste"}
    cfg.update(cfg_extra)
    c = FlowController(cfg, recorder=FakeRecorder(), engine=FakeEngine())
    c.inserted = []
    c._insert = lambda text, mode="paste": (c.inserted.append(text), True)[1]
    c._phys_down = lambda: True
    # Config-Speichern in Tests neutralisieren
    c.set_toggle = lambda k, v: c.cfg.__setitem__(k, v)
    # Worker-Thread wie in start(), aber ohne Hotkey/Berechtigungen
    import threading

    threading.Thread(target=c._work_loop, daemon=True).start()
    return c


def wait_idle(c, timeout=3.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if not c.recording and c.state != "busy":
            return True
        time.sleep(0.02)
    return False


def press_hold_release(c, hold=0.4):
    c.on_press()
    time.sleep(hold)
    c.on_release()


def test_normal_dictation():
    c = make_controller()
    press_hold_release(c)
    assert wait_idle(c)
    assert c.inserted == ["Diktat 1"]
    assert c.stats["count"] == 1


def test_rapid_sequential_dictations_keep_order():
    """DER Bug-Fall: nächstes Diktat starten, während das vorige noch verarbeitet."""
    c = make_controller()
    press_hold_release(c)          # Diktat 1 -> geht in die Queue
    press_hold_release(c)          # Diktat 2 sofort hinterher
    press_hold_release(c)          # Diktat 3
    assert wait_idle(c, 5)
    assert c.inserted == ["Diktat 1", "Diktat 2", "Diktat 3"]  # Reihenfolge!
    assert c.state == "idle"       # nichts hängt


def test_recording_possible_while_busy():
    c = make_controller()
    press_hold_release(c)
    # Sofort neue Aufnahme starten, während Worker noch rechnet
    c.on_press()
    assert c.recording is True     # Aufnahme läuft trotz busy
    time.sleep(0.4)
    c.on_release()
    assert wait_idle(c, 5)
    assert len(c.inserted) == 2


def test_watchdog_rescues_lost_release():
    """Loslassen-Ereignis geht verloren -> Wächter beendet die Aufnahme selbst."""
    c = make_controller()
    c.on_press()
    time.sleep(0.4)
    c._phys_down = lambda: False   # Taste ist physisch längst oben
    time.sleep(0.5)                # STUCK_GRACE_S = 0.8 gesamt überschreiten
    assert c._watchdog_step() is True
    assert c.recording is False
    assert wait_idle(c)
    assert c.inserted == ["Diktat 1"]  # Aufnahme wurde gerettet, nicht verworfen


def test_watchdog_respects_held_key():
    c = make_controller()
    c.on_press()
    time.sleep(1.0)
    assert c._watchdog_step() is False  # Taste physisch unten -> kein Eingriff
    assert c.recording is True
    c.on_release()
    assert wait_idle(c)


def test_max_duration_cap():
    c = make_controller(max_record_seconds=1)
    c.on_press()
    time.sleep(1.2)
    assert c._watchdog_step() is True   # Deckel greift
    assert c.recording is False
    assert wait_idle(c)


def test_handsfree_double_tap_locks():
    c = make_controller()
    # Doppel-Tipp: zwei kurze Drücke
    c.on_press(); time.sleep(0.05); c.on_release()
    c.on_press(); time.sleep(0.05); c.on_release()
    assert c.recording is True and c.locked is True   # eingerastet
    time.sleep(0.4)
    c.on_press(); time.sleep(0.05); c.on_release()    # beliebiger Tipp stoppt
    assert c.recording is False
    assert wait_idle(c)
    assert c.inserted == ["Diktat 1"]


def test_handsfree_off_means_taps_do_nothing():
    c = make_controller(handsfree=False)
    c.on_press(); time.sleep(0.05); c.on_release()
    c.on_press(); time.sleep(0.05); c.on_release()
    assert c.recording is False and c.locked is False
    assert wait_idle(c)
    assert c.inserted == []


def test_single_short_tap_discards():
    c = make_controller()
    c.on_press(); time.sleep(0.05); c.on_release()
    time.sleep(0.7)  # außerhalb des Doppel-Tipp-Fensters
    assert c.recording is False
    assert wait_idle(c)
    assert c.inserted == []


def test_silence_not_inserted():
    c = make_controller()
    c.recorder.stop = lambda: np.zeros(SAMPLE_RATE, dtype=np.float32)
    press_hold_release(c)
    assert wait_idle(c)
    assert c.inserted == []
