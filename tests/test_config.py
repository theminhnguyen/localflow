"""Kopplungs-Token: Erzeugung, Persistenz, Dateirechte, Reset."""

import stat
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from localflow import config


def test_token_created_on_first_call(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "TOKEN_FILE", tmp_path / "secret.token")
    assert not (tmp_path / "secret.token").exists()
    tok = config.load_or_create_token()
    assert tok and len(tok) >= 20
    assert (tmp_path / "secret.token").exists()


def test_token_is_stable_across_calls(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "TOKEN_FILE", tmp_path / "secret.token")
    first = config.load_or_create_token()
    second = config.load_or_create_token()
    assert first == second


def test_token_file_permissions_owner_only(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "TOKEN_FILE", tmp_path / "secret.token")
    config.load_or_create_token()
    mode = stat.S_IMODE((tmp_path / "secret.token").stat().st_mode)
    assert mode == 0o600


def test_reset_token_changes_value(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "TOKEN_FILE", tmp_path / "secret.token")
    first = config.load_or_create_token()
    second = config.reset_token()
    assert first != second
    assert config.load_or_create_token() == second  # neuer Wert ist jetzt stabil


def test_tokens_are_reasonably_unique(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "TOKEN_FILE", tmp_path / "a.token")
    a = config.load_or_create_token()
    monkeypatch.setattr(config, "TOKEN_FILE", tmp_path / "b.token")
    b = config.load_or_create_token()
    assert a != b


def test_require_auth_default_true():
    assert config.DEFAULT_CONFIG["require_auth"] is True


def test_clear_history(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "HISTORY_FILE", tmp_path / "history.json")
    config.add_history({"text": "Hallo"})
    assert len(config.load_history()) == 1
    config.clear_history()
    assert config.load_history() == []


def test_version_is_semver_like():
    import re

    from localflow import __version__

    assert re.match(r"^\d+\.\d+\.\d+$", __version__), __version__
