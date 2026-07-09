"""Erzeugt die PWA-App-Icons (Mikrofon-Glyph auf dunklem Grund) mit Pillow."""

from pathlib import Path

from PIL import Image, ImageDraw

WEB = Path(__file__).parent.parent / "localflow" / "web"
BG = (15, 17, 23)          # #0f1117
ACCENT = (91, 140, 255)    # #5b8cff


def make(size: int) -> Image.Image:
    img = Image.new("RGB", (size, size), BG)
    d = ImageDraw.Draw(img)
    s = size / 512.0

    # Mikrofon-Kapsel
    cx = size / 2
    cap_w, cap_top, cap_bot = 150 * s, 120 * s, 300 * s
    d.rounded_rectangle(
        [cx - cap_w / 2, cap_top, cx + cap_w / 2, cap_bot],
        radius=cap_w / 2, fill=ACCENT,
    )
    # Bügel (Bogen unter der Kapsel)
    bow = 210 * s
    d.arc([cx - bow / 2, cap_bot - bow / 2, cx + bow / 2, cap_bot + bow / 2],
          start=0, end=180, fill=ACCENT, width=int(26 * s))
    # Ständer + Fuß
    d.line([cx, cap_bot + bow / 2, cx, 420 * s], fill=ACCENT, width=int(26 * s))
    d.line([cx - 70 * s, 420 * s, cx + 70 * s, 420 * s], fill=ACCENT, width=int(26 * s))
    return img


for px in (180, 512):
    out = WEB / f"icon-{px}.png"
    make(px).save(out)
    print("geschrieben:", out)
