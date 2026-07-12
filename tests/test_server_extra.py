"""Server-Endpunkte: Verlauf, Status, Handy-Einfügen (mit Attrappen, ohne Modell)."""

import io
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import localflow.server as server_mod
from localflow import config
from localflow.engine import SAMPLE_RATE
from localflow.server import create_app


class FakeEngine:
    loaded = True
    repo = "fake-model"

    def transcribe(self, audio, language=None, prompt_terms=None):
        return {"text": "Hallo vom Handy.", "language": "de",
                "seconds": round(len(audio) / SAMPLE_RATE, 2), "ms": 10}


class FakeController:
    def __init__(self, cfg):
        self.cfg = cfg
        self.history_dirty = False
        self.stats = {"count": 0, "audio_s": 0.0, "engine_ms": 0, "llm_used": 0}
        self.state = "idle"
        self.noted = []

    def effective_language(self):
        lang = self.cfg.get("language", "auto")
        return lang if lang != "auto" else None

    def note_detected_language(self, language, text):
        self.noted.append((language, bool(text)))


def wav_bytes(seconds=1.0, amplitude=0.1):
    rng = np.random.default_rng(7)
    data = (rng.standard_normal(int(SAMPLE_RATE * seconds)) * amplitude * 32767)
    pcm = np.clip(data, -32767, 32767).astype("<i2").tobytes()
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(pcm)
    return buf.getvalue()


@pytest.fixture()
def client(monkeypatch, tmp_path):
    cfg = dict(config.DEFAULT_CONFIG)
    cfg.update({"llm_enabled": False, "phone_insert": True, "share_history": True})
    ctrl = FakeController(cfg)
    # Verlauf in temporäre Datei umlenken
    monkeypatch.setattr(config, "HISTORY_FILE", tmp_path / "history.json")
    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path)
    app = create_app(FakeEngine(), lambda: "de", controller=ctrl)
    app.config["TESTING"] = True
    return app.test_client(), ctrl


def test_ping_reports_flags(client):
    c, ctrl = client
    j = c.get("/api/ping").get_json()
    assert j["ok"] and j["insert_allowed"] and j["history_allowed"]
    ctrl.cfg["phone_insert"] = False
    assert c.get("/api/ping").get_json()["insert_allowed"] is False


def test_transcribe_and_history(client):
    c, ctrl = client
    r = c.post("/api/transcribe", data={
        "audio": (io.BytesIO(wav_bytes()), "a.wav"), "language": "de"})
    j = r.get_json()
    assert r.status_code == 200 and j["text"] == "Hallo vom Handy."
    assert ctrl.stats["count"] == 1
    h = c.get("/api/history").get_json()
    assert h["enabled"] and h["entries"][0]["text"] == "Hallo vom Handy."
    assert h["entries"][0]["source"] == "phone"


def test_history_can_be_disabled(client):
    c, ctrl = client
    ctrl.cfg["share_history"] = False
    h = c.get("/api/history").get_json()
    assert h["enabled"] is False and h["entries"] == []


def test_insert_flag_calls_inserter(client, monkeypatch):
    c, ctrl = client
    calls = []
    import localflow.inserter as ins

    monkeypatch.setattr(ins, "insert_text", lambda t, m="paste": (calls.append(t), True)[1])
    r = c.post("/api/transcribe", data={
        "audio": (io.BytesIO(wav_bytes()), "a.wav"), "insert": "1"})
    assert r.get_json()["inserted"] is True
    assert calls == ["Hallo vom Handy."]


def test_insert_respects_setting(client, monkeypatch):
    c, ctrl = client
    ctrl.cfg["phone_insert"] = False
    calls = []
    import localflow.inserter as ins

    monkeypatch.setattr(ins, "insert_text", lambda t, m="paste": (calls.append(t), True)[1])
    r = c.post("/api/transcribe", data={
        "audio": (io.BytesIO(wav_bytes()), "a.wav"), "insert": "1"})
    assert r.get_json()["inserted"] is False
    assert calls == []


def test_silence_returns_empty(client):
    c, ctrl = client
    r = c.post("/api/transcribe", data={
        "audio": (io.BytesIO(wav_bytes(amplitude=0.0001)), "a.wav")})
    j = r.get_json()
    assert r.status_code == 200 and j["text"] == "" and "note" in j


def test_status_endpoint(client):
    c, ctrl = client
    j = c.get("/api/status").get_json()
    assert j["model"] == "fake-model" and "llm" in j and j["state"] == "idle"


def test_missing_audio_is_400(client):
    c, ctrl = client
    assert c.post("/api/transcribe", data={}).status_code == 400
