"""KI-Feinschliff über ein lokales LLM. Zwei Backends, automatisch erkannt:

- **LM Studio** (OpenAI-kompatible API, Port 1234) — Modelle werden in der
  LM-Studio-App geladen.
- **Ollama** (native API, Port 11434) — `ollama serve` + `ollama pull <modell>`.

Auto-Modus nimmt, was läuft und ein Chat-Modell bereitstellt. Bei jedem Problem
(kein Backend, Timeout, komische Antwort) lautloser Fallback auf den Regel-Text.
Alles lokal — nichts verlässt den Mac.
"""

import json
import logging
import re
import urllib.error
import urllib.request

log = logging.getLogger("localflow.llm")

OLLAMA_URL = "http://127.0.0.1:11434"
LMSTUDIO_URL = "http://127.0.0.1:1234/v1"

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

# 🚀 Schnell-Modus: Anzeichen, dass der Text den LLM-Feinschliff wirklich braucht —
# Selbstkorrekturen, Streichungen oder gesprochene Aufzählungen.
_TRIGGER_RE = re.compile(
    r"(?i)\b(nein|ne warte|warte|ich mein(e|te)|quatsch|falsch|korrektur|"
    r"streich das|vergiss das|"
    r"erstens|zweitens|drittens|viertens|punkt (eins|zwei|drei|vier)|"
    r"actually|i meant?|no wait|scratch that|forget that|"
    r"first(ly)?|second(ly)?|third(ly)?)\b"
)


def needs_polish(text: str, cfg: dict) -> bool:
    """Schnell-Modus: lohnt sich das LLM für diesen Text überhaupt?

    True bei Korrektur-/Aufzählungs-Anzeichen oder langen Diktaten.
    Kurze, saubere Sätze überspringen das LLM komplett (~1s gespart).
    """
    if not cfg.get("llm_smart", True):
        return True
    if _TRIGGER_RE.search(text):
        return True
    return len(text.split()) >= int(cfg.get("llm_smart_min_words", 14))


# ---------- HTTP-Helfer ----------

def _get_json(url: str, timeout: float):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _post_json(url: str, payload: dict, timeout: float):
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


# ---------- Modell-Listen je Backend ----------

def _lmstudio_models(timeout: float = 0.6) -> list:
    try:
        d = _get_json(f"{LMSTUDIO_URL}/models", timeout)
        return [m.get("id", "") for m in d.get("data", []) if m.get("id")]
    except (urllib.error.URLError, OSError, ValueError, json.JSONDecodeError):
        return []


def _ollama_models(timeout: float = 0.6) -> list:
    try:
        d = _get_json(f"{OLLAMA_URL}/api/tags", timeout)
        return [m.get("name", "") for m in d.get("models", []) if m.get("name")]
    except (urllib.error.URLError, OSError, ValueError, json.JSONDecodeError):
        return []


def _pick(models: list, want: str | None) -> str | None:
    """Wählt ein passendes Chat-Modell (Embeddings ausgeschlossen)."""
    chat = [m for m in models if "embed" not in m.lower()]
    if not chat:
        return None
    if want:
        base = want.split(":")[0].lower()
        for m in chat:
            if m.lower() == want.lower() or (base and base in m.lower()):
                return m
    for m in chat:              # Gemma ist ein guter DE-Allrounder
        if "gemma" in m.lower():
            return m
    return chat[0]


def resolve(cfg: dict, timeout: float = 0.6):
    """Ermittelt das aktive Backend. -> (backend, base_url, model) oder None."""
    pref = cfg.get("llm_backend", "auto")
    want = cfg.get("llm_model") or None

    if pref in ("auto", "lmstudio"):
        model = _pick(_lmstudio_models(timeout), want)
        if model:
            return ("lmstudio", LMSTUDIO_URL, model)
        if pref == "lmstudio":
            return None
    if pref in ("auto", "ollama"):
        model = _pick(_ollama_models(timeout), want)
        if model:
            return ("ollama", OLLAMA_URL, model)
    return None


def status(cfg: dict) -> dict:
    """Diagnose-Info fürs Menü/API: welches Backend, welches Modell, bereit?"""
    r = resolve(cfg)
    if r is None:
        lm = bool(_lmstudio_models())  # nur zur Unterscheidung der Meldung
        return {"ready": False, "backend": None, "model": None,
                "hint": ("LM Studio: Modell laden; oder Ollama: 'ollama serve' + pull"
                         if not lm else "kein Chat-Modell geladen")}
    backend, _, model = r
    return {"ready": True, "backend": backend, "model": model, "hint": ""}


def available(cfg=None, **_) -> bool:
    """True, wenn ein lokales LLM samt Modell bereitsteht.

    cfg darf ein Config-Dict ODER (rückwärtskompatibel) ein Modellname/None sein.
    """
    if cfg is None:
        cfg = {"llm_backend": "auto"}
    elif isinstance(cfg, str):
        cfg = {"llm_backend": "auto", "llm_model": cfg}
    return resolve(cfg) is not None


# ---------- Feinschliff ----------

def polish(text: str, cfg: dict, timeout: float = 30.0):
    """Schickt text durch das erkannte LLM. Liefert den Text oder None bei Problemen."""
    r = resolve(cfg)
    if r is None:
        return None
    backend, base, model = r
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": text},
    ]
    # Ausgabe ist nie viel länger als die Eingabe -> knappes Token-Budget
    # (bremst Ausreißer, ohne normale Antworten zu beschneiden)
    max_tokens = min(1000, max(160, len(text.split()) * 4))
    try:
        if backend == "lmstudio":
            data = _post_json(f"{base}/chat/completions", {
                "model": model, "messages": messages,
                "temperature": 0.2, "max_tokens": max_tokens, "stream": False,
            }, timeout)
            out = (data["choices"][0]["message"]["content"] or "").strip()
        else:  # ollama
            data = _post_json(f"{base}/api/chat", {
                "model": model, "messages": messages, "stream": False,
                "options": {"temperature": 0.2, "num_predict": max_tokens},
            }, timeout)
            out = ((data.get("message") or {}).get("content") or "").strip()
    except (urllib.error.URLError, OSError, ValueError, KeyError,
            IndexError, json.JSONDecodeError) as e:
        log.warning("LLM (%s) fehlgeschlagen: %s", backend, e)
        return None
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
    if not needs_polish(text, cfg):  # 🚀 Schnell-Modus
        return text, False
    out = polish(text, cfg, float(cfg.get("llm_timeout", 30)))
    if out is None:
        return text, False
    return out, True
