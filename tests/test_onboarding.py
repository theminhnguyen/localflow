"""Onboarding: Marker-Logik, Berechtigungs-Zustandsmaschine, Fortschritts-Hook."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from localflow import onboarding


# ---- Marker-Datei ----

def test_not_onboarded_when_marker_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(onboarding, "MARKER_FILE", tmp_path / "onboarded")
    assert onboarding.is_onboarded() is False
    assert onboarding.onboarded_version() == ""


def test_mark_onboarded_writes_version(tmp_path, monkeypatch):
    monkeypatch.setattr(onboarding, "MARKER_FILE", tmp_path / "onboarded")
    onboarding.mark_onboarded("0.5.0")
    assert onboarding.is_onboarded() is True
    assert onboarding.onboarded_version() == "0.5.0"


def test_reset_onboarding_removes_marker(tmp_path, monkeypatch):
    monkeypatch.setattr(onboarding, "MARKER_FILE", tmp_path / "onboarded")
    onboarding.mark_onboarded("0.5.0")
    onboarding.reset_onboarding()
    assert onboarding.is_onboarded() is False


def test_reset_onboarding_when_absent_does_not_raise(tmp_path, monkeypatch):
    monkeypatch.setattr(onboarding, "MARKER_FILE", tmp_path / "does-not-exist")
    onboarding.reset_onboarding()  # darf nicht werfen


# ---- Berechtigungs-Zustandsmaschine ----

NONE_PERMS = {"input_monitoring": False, "accessibility": False}
PARTIAL_PERMS = {"input_monitoring": True, "accessibility": False}
BOTH_PERMS = {"input_monitoring": True, "accessibility": True}


def test_permissions_wait_when_none_granted():
    assert onboarding.permissions_step_action(NONE_PERMS, NONE_PERMS) == "wait"


def test_permissions_wait_when_partial():
    assert onboarding.permissions_step_action(NONE_PERMS, PARTIAL_PERMS) == "wait"


def test_permissions_restart_when_granted_during_session():
    assert onboarding.permissions_step_action(NONE_PERMS, BOTH_PERMS) == "restart"
    assert onboarding.permissions_step_action(PARTIAL_PERMS, BOTH_PERMS) == "restart"


def test_permissions_continue_when_already_granted_at_start():
    assert onboarding.permissions_step_action(BOTH_PERMS, BOTH_PERMS) == "continue"


def test_permissions_matrix_never_crashes_on_missing_keys():
    # permissions_status() könnte theoretisch None statt bool liefern
    weird = {"input_monitoring": None, "accessibility": None}
    assert onboarding.permissions_step_action(weird, weird) == "wait"


# ---- Neustart-Argumente ----

def test_restart_argv_frozen_uses_executable_only(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", "/Applications/LocalFlow.app/Contents/MacOS/LocalFlow")
    argv = onboarding._restart_argv()
    assert argv == ["/Applications/LocalFlow.app/Contents/MacOS/LocalFlow"]


def test_restart_argv_dev_mode_uses_module_flag(monkeypatch):
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    monkeypatch.setattr(sys, "executable", "/usr/bin/python3")
    argv = onboarding._restart_argv()
    assert argv == ["/usr/bin/python3", "-m", "localflow.main"]


# ---- Fortschritts-Hook (tqdm-Subklasse) ----

def test_progress_hook_single_file():
    reported = []
    Hook = onboarding.make_progress_tqdm_class(reported.append)
    h = Hook(total=100)
    h.update(50)
    assert reported[-1] == 50
    h.update(50)
    assert reported[-1] == 100
    h.close()


def test_progress_hook_aggregates_multiple_files():
    reported = []
    Hook = onboarding.make_progress_tqdm_class(reported.append)
    a = Hook(total=80)   # großes File
    b = Hook(total=20)   # kleines File
    a.update(40)         # 40 von insgesamt 100 -> 40%
    assert reported[-1] == 40
    b.update(20)         # +20 von insgesamt 100 -> 60%
    assert reported[-1] == 60
    a.update(40)         # +40 -> 100%
    assert reported[-1] == 100
    a.close()
    b.close()


def test_progress_hook_zero_total_reports_nothing():
    reported = []
    Hook = onboarding.make_progress_tqdm_class(reported.append)
    h = Hook(total=0)
    h.update(0)
    assert reported == []  # keine Division durch 0, kein Fantasie-Prozentwert


def test_progress_hook_never_exceeds_100():
    reported = []
    Hook = onboarding.make_progress_tqdm_class(reported.append)
    h = Hook(total=10)
    h.update(50)  # mehr als total (Randfall) -> darf nicht über 100 melden
    assert reported[-1] <= 100


# ---- Regressionstests: die drei Bugs vom 2026-07-14 ----

def test_permission_wait_timeout_constant_exists():
    """Ohne Ausstieg aus der Warteschleife hängt der Assistent endlos, weil
    CGPreflight* bei ad-hoc signierten Apps auch nach dem Setzen der Häkchen
    weiter False meldet (Wert ist pro Prozess gecacht)."""
    assert isinstance(onboarding.PERMISSION_WAIT_TIMEOUT_S, (int, float))
    assert onboarding.PERMISSION_WAIT_TIMEOUT_S > 0


def test_other_app_copies_empty_in_dev_mode(monkeypatch):
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    assert onboarding.other_app_copies() == []


def test_other_app_copies_excludes_running_copy(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(
        onboarding, "running_app_path", lambda: "/Applications/LocalFlow.app")

    class FakeRun:
        stdout = "/Applications/LocalFlow.app\n/Users/x/Downloads/LocalFlow.app\n"

    import subprocess
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: FakeRun())
    monkeypatch.setattr(onboarding.Path, "exists", lambda self: True)

    others = onboarding.other_app_copies()
    assert others == ["/Users/x/Downloads/LocalFlow.app"]  # laufende Kopie NICHT dabei


def test_other_app_copies_survives_mdfind_failure(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    import subprocess

    def boom(*a, **k):
        raise OSError("mdfind nicht verfügbar")

    monkeypatch.setattr(subprocess, "run", boom)
    assert onboarding.other_app_copies() == []  # darf nicht werfen


def test_running_app_path_dev_mode(monkeypatch):
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    assert "Entwicklungsmodus" in onboarding.running_app_path()


def test_running_app_path_frozen_finds_bundle(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(
        sys, "executable", "/Applications/LocalFlow.app/Contents/MacOS/LocalFlow")
    assert onboarding.running_app_path() == "/Applications/LocalFlow.app"
