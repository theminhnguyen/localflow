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


# ---- Privacy-Logging ----

def test_loggable_text_redacts_by_default():
    out = config.loggable_text("Ein geheimes Diktat", {})
    assert "geheimes" not in out
    assert out == "[19 Zeichen]"


def test_loggable_text_shows_when_enabled():
    out = config.loggable_text("Ein geheimes Diktat", {"log_texts": True})
    assert "geheimes" in out


def test_log_texts_default_is_false():
    assert config.DEFAULT_CONFIG["log_texts"] is False


def test_history_keep_default_is_50():
    assert config.DEFAULT_CONFIG["history_keep"] == 50


def test_clear_logs_truncates_files(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "LOG_DIR", tmp_path / "logs")
    config.LOG_DIR.mkdir(parents=True)
    f = config.LOG_DIR / "localflow.log"
    f.write_text("geheimer Log-Inhalt\n" * 5, encoding="utf-8")
    n = config.clear_logs()
    assert n == 1
    assert f.read_text() == ""


def test_clear_logs_no_dir_returns_zero(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "LOG_DIR", tmp_path / "does-not-exist")
    assert config.clear_logs() == 0
