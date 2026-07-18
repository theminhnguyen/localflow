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

    def __init__(self):
        self.prewarm_calls = 0

    def transcribe(self, audio, language=None, prompt_terms=None):
        return {"text": "Hallo vom Handy.", "language": "de",
                "seconds": round(len(audio) / SAMPLE_RATE, 2), "ms": 10}

    def prewarm_if_cold(self):
        self.prewarm_calls += 1


class FakeController:
    def __init__(self, cfg):
        self.cfg = cfg
        self.history_dirty = False
        self.stats = {"count": 0, "audio_s": 0.0, "engine_ms": 0, "llm_used": 0}
        self.state = "idle"
        self.noted = []
        self.calls = []

    def effective_language(self):
        lang = self.cfg.get("language", "auto")
        return lang if lang != "auto" else None

    def note_detected_language(self, language, text):
        self.noted.append((language, bool(text)))

    def set_language(self, code):
        self.cfg["language"] = code
        self.calls.append(("set_language", code))

    def set_hotkey(self, code):
        self.cfg["hotkey"] = code
        self.calls.append(("set_hotkey", code))

    def set_model(self, code):
        self.cfg["model"] = code
        self.calls.append(("set_model", code))

    def set_toggle(self, key, value):
        self.cfg[key] = value
        self.calls.append(("set_toggle", key, value))

    def set_autostart(self, value):
        self.calls.append(("set_autostart", value))
        return value  # simuliert erfolgreich erreichten Zustand


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
    # require_auth=False: diese Tests prüfen Endpunkt-Verhalten, nicht den
    # Auth-Layer — der hat eigene, dedizierte Tests weiter unten (auth_client).
    cfg = dict(config.DEFAULT_CONFIG)
    cfg.update({"llm_enabled": False, "phone_insert": True, "share_history": True,
                "require_auth": False})
    ctrl = FakeController(cfg)
    # Verlauf in temporäre Datei umlenken
    monkeypatch.setattr(config, "HISTORY_FILE", tmp_path / "history.json")
    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config, "TOKEN_FILE", tmp_path / "secret.token")
    app = create_app(FakeEngine(), lambda: "de", controller=ctrl)
    app.config["TESTING"] = True
    return app.test_client(), ctrl


def test_ping_reports_flags(client):
    c, ctrl = client
    j = c.get("/api/ping").get_json()
    assert j["ok"] and j["insert_allowed"] and j["history_allowed"]
    ctrl.cfg["phone_insert"] = False
    assert c.get("/api/ping").get_json()["insert_allowed"] is False


def test_prewarm_endpoint_triggers_engine(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config, "TOKEN_FILE", tmp_path / "secret.token")
    cfg = dict(config.DEFAULT_CONFIG)
    cfg["require_auth"] = False
    engine = FakeEngine()
    app = create_app(engine, lambda: "de", controller=FakeController(cfg))
    app.config["TESTING"] = True
    r = app.test_client().post("/api/prewarm")
    assert r.status_code == 200 and r.get_json()["ok"] is True
    assert engine.prewarm_calls == 1


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


def test_api_insert_calls_inserter(client, monkeypatch):
    c, ctrl = client
    calls = []
    import localflow.inserter as ins

    monkeypatch.setattr(ins, "insert_text", lambda t, m="paste": (calls.append((t, m)), True)[1])
    r = c.post("/api/insert", json={"text": "Hallo Swift-Hülle"})
    assert r.status_code == 200
    assert r.get_json()["inserted"] is True
    assert calls == [("Hallo Swift-Hülle", "paste")]


def test_api_insert_rejects_empty_text(client):
    c, ctrl = client
    r = c.post("/api/insert", json={"text": "   "})
    assert r.status_code == 400
    r = c.post("/api/insert", json={})
    assert r.status_code == 400


def test_api_insert_requires_auth(auth_client, monkeypatch):
    c, ctrl, token = auth_client
    import localflow.inserter as ins

    monkeypatch.setattr(ins, "insert_text", lambda t, m="paste": True)
    r = c.post("/api/insert", json={"text": "x"})
    assert r.status_code == 401
    r = c.post("/api/insert", json={"text": "x"}, headers={"X-LocalFlow-Key": token})
    assert r.status_code == 200


def test_api_insert_remote_respects_phone_insert_off(client, monkeypatch):
    # Entferntes Gerät (Handy) + Schalter aus -> verweigert. Ohne diese Prüfung
    # konnte /api/insert den phone_insert-Schalter umgehen (siehe /api/transcribe,
    # das ihn schon immer respektiert hatte).
    c, ctrl = client
    ctrl.cfg["phone_insert"] = False
    import localflow.inserter as ins

    calls = []
    monkeypatch.setattr(ins, "insert_text", lambda t, m="paste": (calls.append(t), True)[1])
    r = c.post("/api/insert", json={"text": "x"},
               environ_base={"REMOTE_ADDR": "192.168.1.50"})
    assert r.status_code == 403
    assert r.get_json()["code"] == "insert_disabled"
    assert calls == []


def test_api_insert_remote_allowed_when_phone_insert_on(client, monkeypatch):
    c, ctrl = client
    ctrl.cfg["phone_insert"] = True
    import localflow.inserter as ins

    monkeypatch.setattr(ins, "insert_text", lambda t, m="paste": True)
    r = c.post("/api/insert", json={"text": "x"},
               environ_base={"REMOTE_ADDR": "192.168.1.50"})
    assert r.status_code == 200


def test_api_insert_local_ignores_phone_insert_off(client, monkeypatch):
    # Die Swift-Hülle läuft auf demselben Mac und ist kein "Handy" — sie soll
    # unabhängig vom phone_insert-Schalter einfügen dürfen.
    c, ctrl = client
    ctrl.cfg["phone_insert"] = False
    import localflow.inserter as ins

    calls = []
    monkeypatch.setattr(ins, "insert_text", lambda t, m="paste": (calls.append(t), True)[1])
    r = c.post("/api/insert", json={"text": "x"},
               environ_base={"REMOTE_ADDR": "127.0.0.1"})
    assert r.status_code == 200
    assert calls == ["x"]


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
    assert "version" in j and j["version"]


def test_missing_audio_is_400(client):
    c, ctrl = client
    assert c.post("/api/transcribe", data={}).status_code == 400


# ---- Kopplungs-Token / Auth-Guard (require_auth=True, der echte Standard) ----

@pytest.fixture()
def auth_client(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "HISTORY_FILE", tmp_path / "history.json")
    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config, "TOKEN_FILE", tmp_path / "secret.token")
    cfg = dict(config.DEFAULT_CONFIG)
    cfg.update({"llm_enabled": False, "phone_insert": True, "share_history": True,
                "require_auth": True})
    ctrl = FakeController(cfg)
    app = create_app(FakeEngine(), lambda: "de", controller=ctrl)
    app.config["TESTING"] = True
    token = config.load_or_create_token()
    return app.test_client(), ctrl, token


def test_auth_blocks_transcribe_without_token(auth_client):
    c, ctrl, token = auth_client
    r = c.post("/api/transcribe", data={"audio": (io.BytesIO(wav_bytes()), "a.wav")})
    assert r.status_code == 401
    assert r.get_json()["code"] == "unauthorized"


def test_auth_allows_with_correct_token(auth_client):
    c, ctrl, token = auth_client
    r = c.post("/api/transcribe", headers={"X-LocalFlow-Key": token},
               data={"audio": (io.BytesIO(wav_bytes()), "a.wav")})
    assert r.status_code == 200
    assert r.get_json()["text"] == "Hallo vom Handy."


def test_auth_rejects_wrong_token(auth_client):
    c, ctrl, token = auth_client
    r = c.post("/api/transcribe", headers={"X-LocalFlow-Key": "definitiv-falsch"},
               data={"audio": (io.BytesIO(wav_bytes()), "a.wav")})
    assert r.status_code == 401


def test_auth_protects_history_and_status(auth_client):
    c, ctrl, token = auth_client
    assert c.get("/api/history").status_code == 401
    assert c.get("/api/status").status_code == 401
    assert c.get("/api/history", headers={"X-LocalFlow-Key": token}).status_code == 200
    assert c.get("/api/status", headers={"X-LocalFlow-Key": token}).status_code == 200


def test_auth_ping_stays_open(auth_client):
    c, ctrl, token = auth_client
    assert c.get("/api/ping").status_code == 200  # kein Header nötig


def test_auth_static_pwa_stays_open(auth_client):
    c, ctrl, token = auth_client
    assert c.get("/").status_code == 200
    assert c.get("/manifest.webmanifest").status_code == 200


def test_require_auth_false_bypasses_guard(auth_client):
    c, ctrl, token = auth_client
    ctrl.cfg["require_auth"] = False
    r = c.post("/api/transcribe", data={"audio": (io.BytesIO(wav_bytes()), "a.wav")})
    assert r.status_code == 200


def test_auth_token_survives_reset_of_wrong_guess(auth_client, monkeypatch):
    """Nach config.reset_token() ist das alte Token ungültig, das neue gültig."""
    c, ctrl, token = auth_client
    new_token = config.reset_token()
    assert new_token != token
    old = c.post("/api/transcribe", headers={"X-LocalFlow-Key": token},
                 data={"audio": (io.BytesIO(wav_bytes()), "a.wav")})
    assert old.status_code == 401
    fresh = c.post("/api/transcribe", headers={"X-LocalFlow-Key": new_token},
                   data={"audio": (io.BytesIO(wav_bytes()), "a.wav")})
    assert fresh.status_code == 200


# ---- /api/config (Web-Einstellungsseite) ----

def test_get_config_returns_whitelisted_fields_only(client):
    c, ctrl = client
    j = c.get("/api/config").get_json()
    assert set(j.keys()) == set(server_mod.CONFIG_SCHEMA.keys()) | {"autostart"}
    assert "require_auth" not in j  # interna/Sicherheitsschalter NICHT exponiert
    assert "server_port" not in j


def test_get_config_reflects_current_values(client):
    c, ctrl = client
    ctrl.cfg["language"] = "de"
    ctrl.cfg["llm_enabled"] = True
    j = c.get("/api/config").get_json()
    assert j["language"] == "de"
    assert j["llm_enabled"] is True


def test_put_config_language_calls_setter(client):
    c, ctrl = client
    r = c.put("/api/config", json={"language": "en"})
    assert r.status_code == 200
    assert r.get_json()["applied"] == {"language": "en"}
    assert ("set_language", "en") in ctrl.calls


def test_put_config_bool_calls_set_toggle(client):
    c, ctrl = client
    r = c.put("/api/config", json={"llm_smart": False})
    assert r.status_code == 200
    assert ("set_toggle", "llm_smart", False) in ctrl.calls


def test_put_config_hotkey_and_model(client):
    c, ctrl = client
    r = c.put("/api/config", json={"hotkey": "cmd_r", "model": "small"})
    assert r.status_code == 200
    assert ("set_hotkey", "cmd_r") in ctrl.calls
    assert ("set_model", "small") in ctrl.calls


def test_put_config_autostart_special_cased(client):
    c, ctrl = client
    r = c.put("/api/config", json={"autostart": True})
    assert r.status_code == 200
    assert r.get_json()["applied"] == {"autostart": True}
    assert ("set_autostart", True) in ctrl.calls


def test_put_config_rejects_invalid_choice(client):
    c, ctrl = client
    r = c.put("/api/config", json={"language": "fr"})
    assert r.status_code == 400
    assert ctrl.calls == []


def test_put_config_rejects_wrong_type(client):
    c, ctrl = client
    r = c.put("/api/config", json={"llm_enabled": "ja klar"})
    assert r.status_code == 400
    assert ctrl.calls == []


def test_put_config_rejects_unknown_key(client):
    c, ctrl = client
    r = c.put("/api/config", json={"require_auth": False})
    assert r.status_code == 400
    assert ctrl.calls == []


def test_put_config_rejects_non_object_body(client):
    c, ctrl = client
    r = c.put("/api/config", json=["nicht", "ein", "objekt"])
    assert r.status_code == 400


def test_put_config_without_controller_is_400(monkeypatch):
    # Ohne Controller fällt cfg() auf config.load_config() zurück (echte Datei);
    # require_auth hier explizit aus, damit der Auth-Guard nicht vor unserem
    # eigentlichen Test-Fall (--serve-only-Limitierung) zuschlägt.
    monkeypatch.setattr(config, "load_config", lambda: {"require_auth": False})
    app = create_app(FakeEngine(), lambda: "de", controller=None)
    app.config["TESTING"] = True
    c = app.test_client()
    r = c.put("/api/config", json={"language": "de"})
    assert r.status_code == 400


def test_settings_page_served(client):
    c, ctrl = client
    r = c.get("/settings")
    assert r.status_code == 200
    assert b"LocalFlow" in r.data
