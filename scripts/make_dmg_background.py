"""Erzeugt das Hintergrundbild fürs DMG-Fenster (LocalFlow-Branding, Retina-scharf).

Aufruf: .venv/bin/python scripts/make_dmg_background.py
Schreibt packaging/dmg_background.png — Koordinaten hier MÜSSEN mit den
Icon-Positionen in packaging/build_dmg.sh (AppleScript-Abschnitt) übereinstimmen.
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

OUT = Path(__file__).parent.parent / "packaging" / "dmg_background.png"

# Alles in "2x"-Pixelmaßen gezeichnet (= knackscharf auf Retina), das
# DMG-Fenster wird in build_dmg.sh mit denselben Zahlen als Punktgröße gesetzt.
W, H = 1320, 760
BG = (15, 17, 23)          # #0f1117
CARD = (26, 30, 42)        # #1a1e2a
TEXT = (238, 241, 247)     # #eef1f7
MUTED = (139, 147, 167)    # #8b93a7
ACCENT = (91, 140, 255)    # #5b8cff

# Muss zu den Icon-Positionen im AppleScript passen (dort in "1x"-Punkten,
# hier doppelt so groß gezeichnet -> /2 beim Eintragen dort).
APP_X, ICON_Y = 360, 430
APPLICATIONS_X = 960


def sf(size: int, weight: bytes = b"Regular"):
    f = ImageFont.truetype("/System/Library/Fonts/SFNS.ttf", size)
    try:
        f.set_variation_by_name(weight)
    except Exception:
        pass
    return f


def centered_text(d, xy, text, font, fill, anchor="mm"):
    d.text(xy, text, font=font, fill=fill, anchor=anchor)


def main():
    img = Image.new("RGB", (W, H), BG)

    # Weiches Glühen hinter dem App-Icon (ein Kreis + kräftiger Weichzeichner,
    # statt sichtbarer Ringe -> wirkt wie ein sanfter Lichtschein, keine Zielscheibe)
    glow = Image.new("L", (W, H), 0)
    gd = ImageDraw.Draw(glow)
    r = 190
    gd.ellipse([APP_X - r, ICON_Y - r, APP_X + r, ICON_Y + r], fill=70)
    glow = glow.filter(ImageFilter.GaussianBlur(90))
    tint = Image.new("RGB", (W, H), ACCENT)
    img = Image.composite(tint, img, glow)
    d = ImageDraw.Draw(img)

    # Kopfzeile: Wortmarke
    d.text((W / 2, 92), "Local", font=sf(56, b"Bold"), fill=TEXT, anchor="rm")
    d.text((W / 2 + 4, 92), "Flow", font=sf(56, b"Bold"), fill=ACCENT, anchor="lm")
    centered_text(d, (W / 2, 148), "Diktieren, lokal & kostenlos.",
                  sf(24), MUTED)

    # Trennlinie
    d.line([(90, 190), (W - 90, 190)], fill=(42, 48, 64), width=2)

    # Pfeil zwischen App-Icon (links) und "Programme" (rechts)
    arrow_y = ICON_Y
    x0, x1 = APP_X + 130, APPLICATIONS_X - 130
    d.line([(x0, arrow_y), (x1 - 28, arrow_y)], fill=ACCENT, width=6)
    d.polygon([(x1, arrow_y), (x1 - 34, arrow_y - 20), (x1 - 34, arrow_y + 20)],
              fill=ACCENT)

    # Keine eigenen "LocalFlow"/"Programme"-Beschriftungen hier: Finder zeichnet
    # unter jedem platzierten Icon automatisch dessen Dateinamen als Label.

    # Kurzanleitung unten
    footer = "Rechtsklick → Öffnen beim ersten Start · ein Assistent führt durch die Einrichtung"
    centered_text(d, (W / 2, H - 56), footer, sf(21), MUTED)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    img.save(OUT)
    print("geschrieben:", OUT, img.size)


if __name__ == "__main__":
    main()
