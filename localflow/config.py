"""Konfiguration & Nutzerdaten in ~/.localflow/ (Config, Wörterbuch, Snippets, Verlauf)."""

import json
import secrets
import threading
from pathlib import Path

CONFIG_DIR = Path.home() / ".localflow"
CONFIG_FILE = CONFIG_DIR / "config.json"
DICT_FILE = CONFIG_DIR / "dictionary.json"
SNIPPETS_FILE = CONFIG_DIR / "snippets.json"
HISTORY_FILE = CONFIG_DIR / "history.json"
LOG_DIR = CONFIG_DIR / "logs"
TOKEN_FILE = CONFIG_DIR / "secret.token"

DEFAULT_CONFIG = {
    # mlx-community-Repo oder Kurzname ("turbo-q4", "turbo", "small", "base")
    # turbo-q4: gleiche Qualität wie turbo, lädt aber ~3x schneller beim App-Start
    "model": "turbo-q4",
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
    # Sicherheits-Deckel: Aufnahme wird nach so vielen Sekunden automatisch beendet
    "max_record_seconds": 120,
    # Ton-Feedback bei Start/Stopp der Aufnahme
    "sounds": True,
    # --- Feature-Schalter (alle im Menü umschaltbar) ---
    # KI-Feinschliff über lokales LLM; lautloser Fallback, wenn kein LLM läuft.
    "llm_enabled": True,
    # Backend: "auto" (LM Studio ODER Ollama, je nachdem was läuft),
    # "lmstudio" oder "ollama" fest.
    "llm_backend": "auto",
    # Bevorzugtes Modell (Teilstring genügt, z.B. "gemma"); leer = automatisch
    # das erste geladene Chat-Modell.
    "llm_model": "gemma",
    "llm_timeout": 30,
    # 🚀 Schnell-Modus: LLM nur anwenden, wenn der Text es braucht
    # (Korrektur-Wörter, Aufzählungen oder lange Diktate) — spart ~1s pro Diktat
    "llm_smart": True,
    "llm_smart_min_words": 14,
    # Bei Sprache "auto": erkannte Sprache wiederverwenden (spart ~0,7s);
    # alle N Diktate wird sicherheitshalber neu erkannt
    "language_redetect_every": 8,
    # Freihand-Modus: Hotkey doppelt antippen = Aufnahme rastet ein
    "handsfree": True,
    # Handy darf Text direkt an der Mac-Cursor-Position einfügen
    "phone_insert": True,
    # Handy darf den Diktat-Verlauf des Macs sehen
    "share_history": True,
    # Kopplungs-Token für /api/*-Zugriffe verlangen (schützt vor Fremdzugriff im
    # selben WLAN). Bewusst NICHT im ⚙️-Menü — Sicherheit schaltet man nicht
    # versehentlich aus; wer es braucht, editiert config.json.
    "require_auth": True,
    # Diktattexte im Log-File im Klartext mitschreiben. Default AUS: LocalFlows
    # Kernversprechen ist "nichts verlässt den Mac" — dann sollen Texte auch
    # nicht monatelang unverschlüsselt in einer Log-Datei liegen.
    "log_texts": False,
    # Wie viele Verlaufs-Einträge behalten werden (Menü "Verlauf"/PWA). 0 = kein
    # Verlauf speichern.
    "history_keep": 50,
    # Einmal täglich still gegen die öffentliche GitHub-Releases-API prüfen, ob
    # eine neuere Version da ist (kein Auto-Download, nur ein Menü-Hinweis).
    # Der einzige "Telefon-nach-Hause"-Aufruf der App — daher abschaltbar.
    "update_check": True,
}

DEFAULT_DICTIONARY = {
    # Begriffe, die Whisper als Kontext-Hinweis bekommt (Eigennamen, Fachwörter).
    # Standardmäßig leer: ein initial_prompt kann sonst in ruhigen/kurzen Aufnahmen
    # wörtlich in die Ausgabe geechot werden. Nur bewusst gepflegte Begriffe nutzen.
    "terms": [],
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
    LOG_DIR.mkdir(parents=True, exist_ok=True)
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


def clear_history() -> None:
    with _lock:
        _save_json(HISTORY_FILE, [])


def loggable_text(text: str, cfg: dict) -> str:
    """Text fürs Log-File: nur bei bewusst aktiviertem 'log_texts' im Klartext
    (gekürzt), sonst nur die Zeichenzahl. Diktate landen so standardmäßig NICHT
    im Log — siehe 'log_texts' in DEFAULT_CONFIG."""
    if cfg.get("log_texts", False):
        return text[:80]
    return f"[{len(text)} Zeichen]"


def clear_logs() -> int:
    """Leert alle Log-Dateien in LOG_DIR (truncate, Dateien bleiben bestehen).

    Liefert die Anzahl geleerter Dateien.
    """
    if not LOG_DIR.exists():
        return 0
    n = 0
    for f in LOG_DIR.glob("*.log*"):
        try:
            f.write_text("", encoding="utf-8")
            n += 1
        except OSError:
            pass
    return n


# ---- Kopplungs-Token (schützt /api/* vor Fremdzugriff im selben WLAN) ----

def _write_token(tok: str) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    tmp = TOKEN_FILE.with_suffix(".tmp")
    tmp.write_text(tok, encoding="utf-8")
    tmp.replace(TOKEN_FILE)
    try:
        TOKEN_FILE.chmod(0o600)
    except OSError:
        pass  # z.B. exotisches Dateisystem — Token bleibt trotzdem geheim genug


def load_or_create_token() -> str:
    """Liefert das Kopplungs-Token, erzeugt es beim allerersten Aufruf."""
    with _lock:
        try:
            tok = TOKEN_FILE.read_text(encoding="utf-8").strip()
            if tok:
                return tok
        except OSError:
            pass
        tok = secrets.token_urlsafe(24)
        _write_token(tok)
        return tok


def reset_token() -> str:
    """Erzeugt ein neues Token — alle bisher gekoppelten Geräte verlieren den Zugriff."""
    with _lock:
        tok = secrets.token_urlsafe(24)
        _write_token(tok)
        return tok
