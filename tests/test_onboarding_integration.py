"""Onboarding End-to-End: kompletter Tick-getriebener Durchlauf durch MenubarApp.

Alle rumps.alert()-Aufrufe werden abgefangen (simuliert 'OK' anklicken, ohne
echte Dialoge zu zeigen), subprocess.run wird abgefangen (öffnet keine echten
Systemeinstellungen-Fenster). Läuft komplett isoliert gegen ein Test-Home —
rührt ~/.localflow des Nutzers nicht an.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import rumps

from localflow import config, onboarding
from localflow.main import FlowController
from localflow.menubar import MenubarApp


class FakeRecorder:
    active = False

    def start(self):
        pass

    def stop(self):
        import numpy as np
        return np.zeros(16000, dtype="float32")


class FakeEngine:
    def __init__(self):
        self.loaded = False
        self.repo = "fake/repo"

    def warmup_async(self):
        pass

    def transcribe(self, *a, **k):
        return {"text": "x", "language": "de", "seconds": 1.0, "ms": 10}


def make_app(tmp_path, monkeypatch, initial_perms):
    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "config.json")
    monkeypatch.setattr(config, "DICT_FILE", tmp_path / "dictionary.json")
    monkeypatch.setattr(config, "SNIPPETS_FILE", tmp_path / "snippets.json")
    monkeypatch.setattr(config, "HISTORY_FILE", tmp_path / "history.json")
    monkeypatch.setattr(config, "LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr(config, "TOKEN_FILE", tmp_path / "secret.token")
    monkeypatch.setattr(onboarding, "MARKER_FILE", tmp_path / "onboarded")
    config.ensure_files()

    cfg = config.load_config()
    cfg["hotkey"] = "alt_r"
    ctrl = FlowController(cfg, recorder=FakeRecorder(), engine=FakeEngine())
    ctrl.set_toggle = lambda k, v: ctrl.cfg.__setitem__(k, v)

    alerts, opens = [], []
    monkeypatch.setattr(rumps, "alert", lambda **kw: alerts.append(kw) or 1)
    import subprocess as _sp
    monkeypatch.setattr(_sp, "run", lambda *a, **k: opens.append(a))
    from localflow.hotkey import permissions_status as _real_perms
    import localflow.hotkey as hotkey_mod
    monkeypatch.setattr(hotkey_mod, "permissions_status", lambda: dict(initial_perms))
    monkeypatch.setattr(hotkey_mod, "request_permissions", lambda: None)
    import sounddevice as _sd
    monkeypatch.setattr(_sd, "InputStream",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("kein Gerät im Test")))

    app = MenubarApp(ctrl)
    return app, ctrl, alerts, opens


def test_onboarding_full_walkthrough_permissions_already_granted(tmp_path, monkeypatch):
    both = {"input_monitoring": True, "accessibility": True}
    app, ctrl, alerts, opens = make_app(tmp_path, monkeypatch, both)

    assert app._onb_active is True
    assert onboarding.is_onboarded() is False

    # 1) WELCOME
    app._tick(None)
    assert len(alerts) == 1 and "Schritt 1 von 4" in alerts[-1]["title"]
    assert app._onb_stage == onboarding.MICROPHONE

    # 2) MICROPHONE
    app._tick(None)
    assert len(alerts) == 2 and "Schritt 2 von 4" in alerts[-1]["title"]
    assert app._onb_stage == onboarding.PERMISSIONS

    # 3) PERMISSIONS — beide schon von Anfang an gesetzt -> "continue", kein Neustart
    app._tick(None)
    assert len(alerts) == 3 and "Schritt 3 von 4" in alerts[-1]["title"]
    assert len(opens) == 2  # zwei Systemeinstellungen-Fenster "geöffnet"
    app._tick(None)  # zweiter Tick in PERMISSIONS: prüft current vs initial
    assert app._onb_stage == onboarding.MODEL

    # 4) MODEL — Download-Thread simulieren, dann Engine als geladen markieren
    app._tick(None)
    assert len(alerts) == 4 and "Schritt 4 von 4" in alerts[-1]["title"]
    assert app._onb_download_started is True
    ctrl.engine.loaded = True
    app._tick(None)
    assert app._onb_stage == onboarding.DONE

    # 5) DONE
    app._tick(None)
    assert len(alerts) == 5 and "Fertig" in alerts[-1]["title"]
    assert app._onb_active is False
    assert onboarding.is_onboarded() is True

    # Danach: normaler Tick-Betrieb (keine weiteren Onboarding-Alerts)
    app._tick(None)
    assert len(alerts) == 5


def test_onboarding_requires_restart_when_granted_mid_session(tmp_path, monkeypatch):
    import localflow.hotkey as hotkey_mod

    none_perms = {"input_monitoring": False, "accessibility": False}
    app, ctrl, alerts, opens = make_app(tmp_path, monkeypatch, none_perms)

    app._tick(None)  # WELCOME
    app._tick(None)  # MICROPHONE -> PERMISSIONS
    app._tick(None)  # PERMISSIONS erster Tick: initial_perms = none_perms
    assert app._onb_stage == onboarding.PERMISSIONS

    # Noch nicht erteilt -> "wait"
    app._tick(None)
    assert app._onb_stage == onboarding.PERMISSIONS

    # Jetzt erteilt der Nutzer beide Rechte (simuliert)
    monkeypatch.setattr(hotkey_mod, "permissions_status",
                        lambda: {"input_monitoring": True, "accessibility": True})
    restart_calls = []
    monkeypatch.setattr(onboarding, "restart_app", lambda: restart_calls.append(1))
    app._tick(None)
    assert app._onb_stage == onboarding.RESTART

    app._tick(None)  # RESTART-Schritt: zeigt Alert, ruft restart_app() auf
    assert restart_calls == [1]
    assert any("neu starten" in a["message"].lower() or "🎉" in a["title"] for a in alerts)


def test_onboarding_restart_failure_falls_back_gracefully(tmp_path, monkeypatch):
    both = {"input_monitoring": True, "accessibility": True}
    app, ctrl, alerts, opens = make_app(tmp_path, monkeypatch, both)
    app._onb_stage = onboarding.RESTART

    def boom():
        raise OSError("execv nicht erlaubt in diesem Test")

    monkeypatch.setattr(onboarding, "restart_app", boom)
    quit_calls = []
    monkeypatch.setattr(rumps, "quit_application", lambda: quit_calls.append(1))

    app._tick(None)  # darf NICHT werfen
    assert quit_calls == [1]  # sauberer Fallback statt Absturz


def test_onboarding_survives_unexpected_exception(tmp_path, monkeypatch):
    both = {"input_monitoring": True, "accessibility": True}
    app, ctrl, alerts, opens = make_app(tmp_path, monkeypatch, both)

    def boom(**kw):
        raise RuntimeError("überraschender Fehler")

    monkeypatch.setattr(rumps, "alert", boom)
    app._tick(None)  # darf NICHT werfen
    assert app._onb_active is False  # Onboarding wird sauber abgebrochen
    assert onboarding.is_onboarded() is True  # trotzdem als erledigt markiert


def test_restart_onboarding_menu_action_resets_state(tmp_path, monkeypatch):
    both = {"input_monitoring": True, "accessibility": True}
    app, ctrl, alerts, opens = make_app(tmp_path, monkeypatch, both)
    onboarding.mark_onboarded("0.4.0")
    app._onb_active = False

    app._restart_onboarding(None)
    assert app._onb_active is True
    assert app._onb_stage == onboarding.WELCOME
    assert onboarding.is_onboarded() is False
