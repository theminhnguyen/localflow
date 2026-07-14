"""Update-Check gegen die öffentliche GitHub-Releases-API.

Fail-silent: jeder Fehler (kein Netz, Rate-Limit, kaputtes JSON, …) liefert
None statt eine Exception zu werfen — LocalFlow funktioniert genauso gut
offline. Kein automatischer Download/Selbstaustausch, nur ein Hinweis mit
Link zur Release-Seite (ad-hoc-Signatur macht In-App-Replacement fehleranfällig).
"""

import json
import logging
import re
import urllib.error
import urllib.request

log = logging.getLogger("localflow.updater")

RELEASES_API = "https://api.github.com/repos/theminhnguyen/localflow/releases/latest"

_VERSION_RE = re.compile(r"(\d+)\.(\d+)\.(\d+)")


def _parse(version: str):
    """'v0.5.0' oder '0.5.0' -> (0, 5, 0). None bei unerkennbarem Format."""
    m = _VERSION_RE.search(version or "")
    if not m:
        return None
    return tuple(int(x) for x in m.groups())


def is_newer(candidate: str, current: str) -> bool:
    """True, wenn candidate eine höhere Version als current ist."""
    c, cur = _parse(candidate), _parse(current)
    if c is None or cur is None:
        return False
    return c > cur


def fetch_latest(timeout: float = 4.0):
    """Neueste veröffentlichte Version. -> {"tag","url"} oder None bei jedem Fehler."""
    req = urllib.request.Request(
        RELEASES_API,
        headers={"Accept": "application/vnd.github+json",
                 "User-Agent": "LocalFlow-UpdateCheck"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError, json.JSONDecodeError) as e:
        log.debug("Update-Check fehlgeschlagen: %s", e)
        return None
    tag = data.get("tag_name")
    url = data.get("html_url")
    if not tag or not url:
        return None
    return {"tag": tag, "url": url}


def check_for_update(current_version: str, timeout: float = 4.0):
    """fetch_latest() + is_newer()-Vergleich in einem. -> {"tag","url"} oder None."""
    latest = fetch_latest(timeout)
    if latest is None or not is_newer(latest["tag"], current_version):
        return None
    return latest
