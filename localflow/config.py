"""Konfiguration & Nutzerdaten in ~/.localflow/ (Config, Wörterbuch, Snippets, Verlauf)."""

import json
import threading
from pathlib import Path

CONFIG_DIR = Path.home() / ".localflow"
CONFIG_FILE = CONFIG_DIR / "config.json"
DICT_FILE = CONFIG_DIR / "dictionary.json"
SNIPPETS_FILE = CONFIG_DIR / "snippets.json"
HISTORY_FILE = CONFIG_DIR / "history.json"

DEFAULT_CONFIG = {
    # mlx-community-Repo oder Kurzname ("turbo", "small", "base")
    "model": "turbo",
    # "auto" = Sprache automatisch erkennen, sonst ISO-Code ("de", "en", ...)
    "language": "auto",
    # Taste zum Gedrückthalten: "alt_r" (rechte Option), "cmd_r", "ctrl_r", "f13"
    "hotkey": "alt_r",
    # "paste" = Zwischenablage + Cmd-V, "type" = Zeichen einzeln tippen
    "insert_mode": "paste",
    "server_port": 8790,
    # Aufnahmen kürzer als das (Sekunden) werden verworfen (versehentlicher Tastendruck)
    "min_duration": 0.3,
    # Aufnahmen leiser als dieser RMS-Pegel gelten als Stille -> verworfen.
    # Verhindert Whisper-Halluzinationen ("Vielen Dank.") bei leeren Aufnahmen.
    # 0.006 lässt geflüsterte Sprache noch durch, blockt aber digitale Stille.
    "silence_rms": 0.006,
    # Ton-Feedback bei Start/Stopp der Aufnahme
    "sounds": True,
}

DEFAULT_DICTIONARY = {
    # Begriffe, die Whisper als Kontext-Hinweis bekommt (Eigennamen, Fachwörter)
    "terms": ["LocalFlow"],
    # Ersetzungen im fertigen Text: "falsch erkannt" -> "richtig"
    "corrections": {},
}

DEFAULT_SNIPPETS = {
    # Sprich "Snippet Gruß" -> fügt den Baustein ein
    "gruß": "Viele Grüße\nMinh",
}

_lock = threading.Lock()


def _load_json(path: Path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return json.loads(json.dumps(default))


def _save_json(path: Path, data) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    tmp.replace(path)


def ensure_files() -> None:
    """Legt Config-Dateien mit Defaults an, falls sie fehlen."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if not CONFIG_FILE.exists():
        _save_json(CONFIG_FILE, DEFAULT_CONFIG)
    if not DICT_FILE.exists():
        _save_json(DICT_FILE, DEFAULT_DICTIONARY)
    if not SNIPPETS_FILE.exists():
        _save_json(SNIPPETS_FILE, DEFAULT_SNIPPETS)


def load_config() -> dict:
    cfg = dict(DEFAULT_CONFIG)
    cfg.update(_load_json(CONFIG_FILE, {}))
    return cfg


def save_config(cfg: dict) -> None:
    with _lock:
        _save_json(CONFIG_FILE, cfg)


def load_dictionary() -> dict:
    d = dict(DEFAULT_DICTIONARY)
    loaded = _load_json(DICT_FILE, {})
    d.update({k: v for k, v in loaded.items() if k in d})
    return d


def load_snippets() -> dict:
    return _load_json(SNIPPETS_FILE, DEFAULT_SNIPPETS)


def load_history() -> list:
    return _load_json(HISTORY_FILE, [])


def add_history(entry: dict, keep: int = 50) -> None:
    with _lock:
        history = _load_json(HISTORY_FILE, [])
        history.insert(0, entry)
        _save_json(HISTORY_FILE, history[:keep])
