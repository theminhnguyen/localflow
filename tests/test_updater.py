"""Update-Check: Versionsvergleich + GitHub-API-Aufruf (gemockt, kein echtes Netz)."""

import sys
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from localflow import updater


def test_is_newer_true():
    assert updater.is_newer("v0.5.0", "0.4.0") is True
    assert updater.is_newer("0.4.1", "0.4.0") is True
    assert updater.is_newer("1.0.0", "0.9.9") is True


def test_is_newer_false_for_equal_or_older():
    assert updater.is_newer("v0.4.0", "0.4.0") is False
    assert updater.is_newer("0.3.9", "0.4.0") is False
    assert updater.is_newer("0.4.0", "0.4.0") is False


def test_is_newer_handles_v_prefix_both_sides():
    assert updater.is_newer("v0.5.0", "v0.4.0") is True


def test_is_newer_unparseable_is_false():
    assert updater.is_newer("nightly-build", "0.4.0") is False
    assert updater.is_newer("0.5.0", "") is False
    assert updater.is_newer("", "") is False


def test_fetch_latest_success(monkeypatch):
    class FakeResp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b'{"tag_name": "v0.5.0", "html_url": "https://github.com/x/y/releases/tag/v0.5.0"}'

    monkeypatch.setattr(updater.urllib.request, "urlopen", lambda *a, **k: FakeResp())
    result = updater.fetch_latest()
    assert result == {"tag": "v0.5.0", "url": "https://github.com/x/y/releases/tag/v0.5.0"}


def test_fetch_latest_network_error_returns_none(monkeypatch):
    def raise_err(*a, **k):
        raise urllib.error.URLError("kein Netz")

    monkeypatch.setattr(updater.urllib.request, "urlopen", raise_err)
    assert updater.fetch_latest() is None


def test_fetch_latest_bad_json_returns_none(monkeypatch):
    class FakeResp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b"nicht-json"

    monkeypatch.setattr(updater.urllib.request, "urlopen", lambda *a, **k: FakeResp())
    assert updater.fetch_latest() is None


def test_fetch_latest_missing_fields_returns_none(monkeypatch):
    class FakeResp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b'{"some_other_field": 1}'

    monkeypatch.setattr(updater.urllib.request, "urlopen", lambda *a, **k: FakeResp())
    assert updater.fetch_latest() is None


def test_check_for_update_returns_none_when_not_newer(monkeypatch):
    monkeypatch.setattr(updater, "fetch_latest",
                        lambda *a, **k: {"tag": "v0.4.0", "url": "https://x"})
    assert updater.check_for_update("0.4.0") is None


def test_check_for_update_returns_info_when_newer(monkeypatch):
    monkeypatch.setattr(updater, "fetch_latest",
                        lambda *a, **k: {"tag": "v0.5.0", "url": "https://x"})
    assert updater.check_for_update("0.4.0") == {"tag": "v0.5.0", "url": "https://x"}


def test_check_for_update_none_when_fetch_fails(monkeypatch):
    monkeypatch.setattr(updater, "fetch_latest", lambda *a, **k: None)
    assert updater.check_for_update("0.4.0") is None
