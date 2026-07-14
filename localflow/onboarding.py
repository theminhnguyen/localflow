"""Einmaliger Einrichtungs-Assistent beim allerersten Start.

Reine Zustands-/Fortschritts-Logik hier — vollständig ohne GUI testbar. Die
eigentliche Anzeige (rumps.alert-Sequenz, Status-Zeile) übernimmt menubar.py,
getrieben vom selben rumps.Timer-Tick wie der Rest der App (kein Aufruf vor
app.run() nötig — vermeidet Unklarheiten rund um NSAlert vor aktivem Run-Loop).

Ablauf (siehe menubar.MenubarApp._onboarding_tick):
  WELCOME -> MICROPHONE -> PERMISSIONS (Poll) -> [RESTART, falls Berechtigungen
  gerade erst erteilt wurden] -> MODEL (Download mit Fortschritt) -> DONE
"""

import threading
from pathlib import Path

from . import config

MARKER_FILE = config.CONFIG_DIR / "onboarded"

# Stage-Namen (Strings statt Enum: einfach über rumps/JSON-Grenzen zu reichen)
WELCOME = "welcome"
MICROPHONE = "microphone"
PERMISSIONS = "permissions"
RESTART = "restart"
MODEL = "model"
DONE = "done"

STAGE_ORDER = [WELCOME, MICROPHONE, PERMISSIONS, MODEL, DONE]  # RESTART ist eine Abzweigung


def is_onboarded() -> bool:
    return MARKER_FILE.exists()


def mark_onboarded(version: str) -> None:
    config.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    MARKER_FILE.write_text(version, encoding="utf-8")


def reset_onboarding() -> None:
    MARKER_FILE.unlink(missing_ok=True)


def onboarded_version() -> str:
    """Version, mit der zuletzt onboarded wurde ('' wenn nie)."""
    try:
        return MARKER_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


# ---- Schritt 3: Berechtigungen (Poll-Schleife) ----

def permissions_step_action(initial_perms: dict, current_perms: dict) -> str:
    """Was während der Warteschleife von Schritt 3 als Nächstes zu tun ist.

    initial_perms: Snapshot der Berechtigungen beim EINTRITT in diesen Schritt
                   (zu Beginn dieses App-Starts).
    current_perms: aktueller Stand (wird per Timer alle ~1s neu abgefragt).

    -> "wait"     mindestens eine Berechtigung fehlt noch -> weiter pollen
    -> "restart"  beide jetzt da, waren es beim Eintritt aber NICHT beide ->
                  der Hotkey-Event-Tap greift erst nach einem Prozess-Neustart
    -> "continue" beide waren schon beim Eintritt da (z.B. Berechtigungen aus
                  einer früheren Installation noch vorhanden) -> kein Neustart nötig
    """
    both_now = bool(current_perms.get("input_monitoring")) and bool(
        current_perms.get("accessibility"))
    both_initially = bool(initial_perms.get("input_monitoring")) and bool(
        initial_perms.get("accessibility"))
    if not both_now:
        return "wait"
    return "continue" if both_initially else "restart"


# ---- Schritt 3b: Neustart nach Berechtigungs-Erteilung ----

def _restart_argv() -> list:
    """Reine Berechnung der execv-Argumente (testbar, ohne den Prozess zu ersetzen)."""
    import sys

    if getattr(sys, "frozen", False):
        # PyInstaller-Bundle: sys.executable IST die App-Binary.
        return [sys.executable]
    # Entwicklungsmodus: als Modul neu starten, sonst brechen die relativen
    # Package-Importe (from . import ...) beim direkten Datei-Aufruf.
    return [sys.executable, "-m", "localflow.main"]


def restart_app() -> None:
    """Ersetzt den laufenden Prozess durch eine frische Instanz (os.execv).

    Kann fehlschlagen (z.B. exotische Sandbox-Restriktionen) — der Aufrufer
    fängt das ab und zeigt dann den manuellen 'bitte neu starten'-Hinweis.
    """
    import os
    import sys

    os.execv(sys.executable, _restart_argv())


# ---- Schritt 4: Modell-Download mit Fortschritt ----

def make_progress_tqdm_class(on_progress):
    """tqdm-Subklasse für huggingface_hub(tqdm_class=...): meldet den Fortschritt
    über ALLE Dateien einer snapshot_download()-Sitzung als 0-100-Prozentwert an
    on_progress(pct). Erbt von der echten tqdm-Klasse -> volle Kompatibilität mit
    huggingface_hub's interner Nutzung, nur update()/close() sind erweitert.
    """
    import tqdm as _tqdm_pkg

    lock = threading.Lock()
    state = {"totals": {}, "done": {}}

    def _report():
        total = sum(state["totals"].values())
        done = sum(state["done"].values())
        if total > 0:
            on_progress(min(100, int(done / total * 100)))

    class _ProgressTqdm(_tqdm_pkg.tqdm):
        # disable=True lässt tqdm intern update() abkürzen (self.n bleibt dann
        # immer 0) — wir zählen den Fortschritt darum selbst mit (_pt_done).
        def __init__(self, *args, **kwargs):
            kwargs.setdefault("disable", True)  # kein Terminal-/Log-Spam
            super().__init__(*args, **kwargs)
            self._pt_done = kwargs.get("initial", 0) or 0
            with lock:
                state["totals"][id(self)] = self.total or 0
                state["done"][id(self)] = self._pt_done
            _report()

        def update(self, n=1):
            result = super().update(n)
            self._pt_done += n
            with lock:
                state["done"][id(self)] = self._pt_done
            _report()
            return result

        def close(self):
            with lock:
                state["totals"].pop(id(self), None)
                state["done"].pop(id(self), None)
            return super().close()

    return _ProgressTqdm


def download_with_progress(repo_id: str, on_progress) -> None:
    """Lädt ein HF-Repo mit Fortschritts-Rückmeldung herunter.

    Nutzt denselben Cache wie mlx_whisper — läuft danach engine.warmup(), findet
    es alles bereits lokal vor und lädt nicht doppelt herunter.
    """
    from huggingface_hub import snapshot_download

    snapshot_download(repo_id=repo_id, tqdm_class=make_progress_tqdm_class(on_progress))
