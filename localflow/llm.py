"""KI-Feinschliff über ein lokales LLM (Ollama, z.B. gemma3:4b).

Optionale Stufe NACH dem Regel-Cleanup: entfernt Versprecher/Selbstkorrekturen,
formt gesprochene Aufzählungen zu Listen, glättet Grammatik. Fällt bei jedem
Problem (Ollama aus, Timeout, komische Antwort) lautlos auf den Regel-Text zurück.
Komplett lokal — nichts verlässt den Mac.
"""

import json
import logging
import re
import urllib.error
import urllib.request

log = logging.getLogger("localflow.llm")

BASE_URL = "http://127.0.0.1:11434"

SYSTEM_PROMPT = (
    "Du bist ein unsichtbarer Diktier-Editor. Du erhältst diktierten Rohtext "
    "und gibst NUR den überarbeiteten Text zurück — ohne Anführungszeichen, "
    "ohne Erklärung, ohne Einleitung.\n"
    "Regeln:\n"
    "1. Entferne Versprecher und Selbstkorrekturen: bei 'um 2, nein, um 3 Uhr' "
    "bleibt nur 'um 3 Uhr'.\n"
    "2. Wird eine Aufzählung gesprochen (erstens/zweitens, Punkt eins/zwei, "
    "und dann ... und dann), forme sie in Zeilen mit '- ' um — aber nur ab "
    "zwei Punkten.\n"
    "3. Korrigiere Grammatik und Zeichensetzung behutsam.\n"
    "4. Behalte Sprache, Inhalt, Ton und Wortwahl bei. Erfinde nichts dazu, "
    "lasse nichts Inhaltliches weg.\n"
    "5. Ist der Text bereits gut, gib ihn unverändert zurück."
)

_THINK_RE = re.compile(r"<think>.*?</think>\s*", re.S)
_FENCE_RE = re.compile(r"^```[a-z]*\n(.*?)\n```$", re.S)


def available(timeout: float = 0.5) -> bool:
    """True, wenn der Ollama-Server lokal antwortet."""
    try:
        with urllib.request.urlopen(f"{BASE_URL}/api/version", timeout=timeout):
            return True
    except (urllib.error.URLError, OSError, ValueError):
        return False


def polish(text: str, model: str, timeout: float = 20.0):
    """Schickt text durch das LLM. Liefert den Text oder None bei Problemen."""
    payload = {
        "model": model,
        "stream": False,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ],
        "options": {"temperature": 0.2, "num_predict": 1000},
    }
    req = urllib.request.Request(
        f"{BASE_URL}/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError, json.JSONDecodeError) as e:
        log.warning("LLM nicht erreichbar/fehlgeschlagen: %s", e)
        return None

    out = ((data.get("message") or {}).get("content") or "").strip()
    return _validate(text, out)


def _validate(original: str, out: str):
    """Sicherheitsnetz gegen kaputte/ausufernde LLM-Antworten."""
    if not out:
        return None
    out = _THINK_RE.sub("", out).strip()  # Denk-Blöcke mancher Modelle
    m = _FENCE_RE.match(out)
    if m:
        out = m.group(1).strip()
    # Umschließende Anführungszeichen entfernen
    if len(out) > 1 and out[0] in "\"'„»" and out[-1] in "\"'“«":
        out = out[1:-1].strip()
    if not out:
        return None
    # Grob explodierte Länge oder Meta-Gerede -> verwerfen
    if len(out) > max(len(original) * 3, len(original) + 200):
        return None
    lowered = out.lower()
    for phrase in ("als ki", "as an ai", "hier ist der", "here is the"):
        if lowered.startswith(phrase):
            return None
    return out


def maybe_polish(text: str, cfg: dict):
    """Wendet das LLM an, wenn aktiviert und verfügbar. -> (text, wurde_genutzt)"""
    if not cfg.get("llm_enabled", False):
        return text, False
    if len(text.strip()) < 3:
        return text, False
    if not available():
        return text, False
    out = polish(text, cfg.get("llm_model", "gemma3:4b"),
                 float(cfg.get("llm_timeout", 20)))
    if out is None:
        return text, False
    return out, True
