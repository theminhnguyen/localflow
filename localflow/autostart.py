"""Autostart bei der Anmeldung über einen LaunchAgent (an-/abschaltbar im Menü)."""

import logging
import plistlib
import subprocess
from pathlib import Path

log = logging.getLogger("localflow.autostart")

AGENT_ID = "studio.minh.localflow"
AGENT_PATH = Path.home() / "Library" / "LaunchAgents" / f"{AGENT_ID}.plist"
APP_NAME = "LocalFlow"


def enabled() -> bool:
    return AGENT_PATH.exists()


def enable() -> bool:
    """Legt den LaunchAgent an: startet die LocalFlow-App bei jeder Anmeldung."""
    try:
        AGENT_PATH.parent.mkdir(parents=True, exist_ok=True)
        plist = {
            "Label": AGENT_ID,
            "ProgramArguments": ["/usr/bin/open", "-a", APP_NAME],
            "RunAtLoad": True,
        }
        with open(AGENT_PATH, "wb") as f:
            plistlib.dump(plist, f)
        log.info("Autostart aktiviert (%s)", AGENT_PATH)
        return True
    except OSError:
        log.exception("Autostart konnte nicht aktiviert werden")
        return False


def disable() -> bool:
    try:
        # Falls für diese Sitzung geladen: still entladen (Fehler egal)
        subprocess.run(
            ["launchctl", "bootout", f"gui/{_uid()}/{AGENT_ID}"],
            capture_output=True,
        )
        AGENT_PATH.unlink(missing_ok=True)
        log.info("Autostart deaktiviert")
        return True
    except OSError:
        log.exception("Autostart konnte nicht deaktiviert werden")
        return False


def _uid() -> int:
    import os

    return os.getuid()
