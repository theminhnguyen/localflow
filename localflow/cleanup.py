"""Text-Bereinigung nach der Transkription: Füllwörter, Wörterbuch, Snippets.

Das ist die "KI-Edit"-Schicht von Wispr Flow als Regel-Pipeline —
Whisper liefert bereits Zeichensetzung und Groß-/Kleinschreibung,
hier räumen wir den Rest auf.
"""

import re

# Füllwörter, die in keiner Sprache echte Wörter sind — immer entfernen.
_FILLERS_ALWAYS = r"ähm+|äh+m*|öhm+|ähem|mhm+|hmm+|uhm+|erm+"
# Nur im Englischen entfernen ("um" ist im Deutschen eine echte Präposition!)
_FILLERS_EN = r"um+|uh+"

# Füllwörter werden in zwei Schritten entfernt:
#  1) als Einschub zwischen zwei Kommas: ", äh," -> ","  (ein Komma bleibt erhalten)
#  2) am Wortanfang / freistehend: "Ähm, hallo" -> "hallo", " äh " -> " "
def _interjection_re(fillers: str) -> re.Pattern:
    return re.compile(r"(?i),\s*(?:" + fillers + r")\s*,")


def _boundary_re(fillers: str) -> re.Pattern:
    return re.compile(r"(?i)(?:^|(?<=\s))(?:" + fillers + r")[,.]?(?=\s|$)")

_INTERJ_ALWAYS = _interjection_re(_FILLERS_ALWAYS)
_INTERJ_EN = _interjection_re(_FILLERS_EN)
_BOUND_ALWAYS = _boundary_re(_FILLERS_ALWAYS)
_BOUND_EN = _boundary_re(_FILLERS_EN)

_RE_SNIPPET = re.compile(r"(?i)^\s*(?:snippet|schnipsel)\s+(.+?)[\s.!?]*$")


def remove_fillers(text: str, language: str = "") -> str:
    text = _INTERJ_ALWAYS.sub(",", text)
    text = _BOUND_ALWAYS.sub("", text)
    if language.startswith("en"):
        text = _INTERJ_EN.sub(",", text)
        text = _BOUND_EN.sub("", text)
    return text


def apply_corrections(text: str, corrections: dict) -> str:
    """Ersetzt falsch erkannte Wörter/Phrasen (case-insensitiv, längste zuerst)."""
    for wrong in sorted(corrections, key=len, reverse=True):
        right = corrections[wrong]
        text = re.sub(
            r"(?i)(?<![\wäöüß])" + re.escape(wrong) + r"(?![\wäöüß])", right, text
        )
    return text


def match_snippet(text: str, snippets: dict):
    """Erkennt "Snippet <Name>" und liefert den Textbaustein, sonst None."""
    m = _RE_SNIPPET.match(text.strip())
    if not m:
        return None
    key = m.group(1).strip().lower()
    for name, body in snippets.items():
        if name.strip().lower() == key:
            return body
    return None


def tidy(text: str) -> str:
    """Whitespace/Interpunktions-Reste nach dem Füllwort-Entfernen reparieren."""
    text = re.sub(r"\s+([,.!?;:])", r"\1", text)   # Leerzeichen vor Satzzeichen
    text = re.sub(r"([,;])\1+", r"\1", text)         # ",," -> ","
    text = re.sub(r"^\s*[,.;:!?]+\s*", "", text)     # Satzzeichen am Anfang
    text = re.sub(r"[ \t]{2,}", " ", text)            # Mehrfach-Leerzeichen
    text = text.strip()
    if text and text[0].islower():
        text = text[0].upper() + text[1:]
    return text


def clean(raw: str, language: str = "", dictionary: dict | None = None,
          snippets: dict | None = None) -> str:
    """Komplette Pipeline: Snippets -> Füllwörter -> Wörterbuch -> Aufräumen."""
    dictionary = dictionary or {}
    snippets = snippets or {}

    snippet = match_snippet(raw, snippets)
    if snippet is not None:
        return snippet

    text = remove_fillers(raw, language)
    text = apply_corrections(text, dictionary.get("corrections", {}))
    return tidy(text)
