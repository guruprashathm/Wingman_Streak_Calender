"""
theme.py — shared visual toolkit (RENDER primitives).
=====================================================
Vendored, trimmed subset of the Motoverse card toolkit (originally
make_templates.py + make_combined.py): the gunmetal canvas, fonts, letter-spaced
text, QR, film grain / vignette, and the WINGMAN x MOTOVERSE co-brand lockup.
Everything the streak card draws with lives here; card.py composes it.

Fonts are loaded from config.FONTS; the two brand logos (config.LOGO,
config.WINGMAN_LOGO) are optional — the co-brand falls back to a text lockup if
a logo file is missing.
"""
import math

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

from .config import FONTS, LOGO, WINGMAN_LOGO

W, H = 1080, 1920

# ---- palette ----
INK_TOP, INK_BOT = (18, 20, 24), (28, 25, 22)      # gunmetal gradient
CREAM = (232, 227, 216)
MUTE = (129, 126, 120)
FAINT = (60, 62, 66)
ZEN, MAV, RED = (74, 182, 142), (224, 166, 58), (224, 79, 55)  # LIGHT / MEDIUM / HEAVY

# persona accent colours (so a streak card can match its companion persona card)
ACCENT = {
    "ZEN": (74, 182, 142), "MAVERICK": (224, 166, 58), "REDLINER": (224, 79, 55),
    "GRAND VOYAGER": (52, 178, 200), "IRON MARATHONER": (214, 120, 44),
    "HIGHWAY STORM": (255, 106, 43), "LONG-HAUL MONK": (206, 166, 78),
    "ODYSSEY RIDER": (150, 122, 224),
}


def F(name, size):
    return ImageFont.truetype(str(FONTS / name), size)


# --------------------------------------------------------------------------- #
#  canvas textures
# --------------------------------------------------------------------------- #
def vgrad():
    top = np.array(INK_TOP); bot = np.array(INK_BOT)
    ramp = (top[None, :] * (1 - np.linspace(0, 1, H)[:, None]) +
            bot[None, :] * np.linspace(0, 1, H)[:, None]).astype(np.uint8)
    return Image.fromarray(np.repeat(ramp[:, None, :], W, axis=1), "RGB")


def grain(img, amt=9):
    n = (np.random.default_rng(7).integers(-amt, amt + 1, (H, W, 1))
         .repeat(3, 2)).astype(np.int16)
    a = np.asarray(img).astype(np.int16) + n
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), "RGB")


def vignette(img, k=0.55):
    yy, xx = np.mgrid[0:H, 0:W]
    d = np.sqrt(((xx - W / 2) / (W / 2)) ** 2 + ((yy - H / 2) / (H / 2)) ** 2)
    m = np.clip(1 - k * np.clip(d - 0.55, 0, 1), 0, 1)
    return Image.fromarray((np.asarray(img) * m[:, :, None]).astype(np.uint8), "RGB")


# --------------------------------------------------------------------------- #
#  letter-spaced text + QR
# --------------------------------------------------------------------------- #
def track_len(font, s, tr):
    return sum(font.getlength(c) + tr for c in s) - (tr if s else 0)


def ttext(d, x, y, s, font, fill, tr=0, anchor="l"):
    total = track_len(font, s, tr)
    if anchor == "m":
        x -= total / 2
    elif anchor == "r":
        x -= total
    cx = x
    for c in s:
        d.text((cx, y), c, font=font, fill=fill)
        cx += font.getlength(c) + tr
    return total


QR_DARK = (24, 24, 28)      # near-black modules
QR_LIGHT = CREAM            # light tile behind them


def qr(img, x, y, size, data, logo=True, panel=True):
    """Draw a scannable QR for `data` at (x, y) with side `size` (px) onto `img`.

    Design notes (all verified by decoding the output, see tests):
      * DARK modules on a LIGHT (cream) rounded tile. Inverted QR (light-on-dark)
        is poorly supported by real-world phone scanners, so we do NOT do that.
      * Error-correction level H (~30% recovery) lets the Royal Enfield mark sit
        in the centre without breaking the scan.
      * A quiet-zone margin is baked in — required for reliable scanning.
      * Keep `data` SHORT (use a short domain / short-link). A ~22-char URL stays
        at QR version 3 and scans from ~120px; a ~48-char URL needs version 6 and
        ~200px. Budget the card layout accordingly.

    `data` is whatever the QR should resolve to — today a placeholder URL; swap in
    the real download link (object-store / CDN) later with no code change here.
    Falls back to a non-scannable placeholder if `qrcode` isn't installed.
    """
    d = ImageDraw.Draw(img)
    pad = max(6, int(size * 0.09))          # quiet zone (required for reliable scans)
    if panel:
        d.rounded_rectangle([x - pad, y - pad, x + size + pad, y + size + pad],
                            radius=int(pad * 1.2), fill=QR_LIGHT)

    try:
        import qrcode
        q = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_H,
                          border=0, box_size=1)
        q.add_data(data); q.make(fit=True)
        m = q.get_matrix()
        scannable = True
    except Exception:
        m = [[(i * 7 + j * 13) % 3 == 0 for j in range(21)] for i in range(21)]
        scannable = False

    n = len(m); c = size / n
    r = max(0, int(c * 0.28))               # gently rounded modules, on-brand
    for i in range(n):
        for j in range(n):
            if not m[i][j]:
                continue
            x0, y0 = x + j * c, y + i * c
            d.rounded_rectangle([x0, y0, x0 + c, y0 + c], radius=r, fill=QR_DARK)

    # centre logo — only safe with H-level correction (hence the real-QR guard)
    if logo and scannable and LOGO.exists():
        try:
            badge = int(size * 0.24)        # ~6% area; well within H's 30% budget
            cx, cy = x + size / 2, y + size / 2
            knock = int(badge * 0.64)       # clear the modules behind the mark
            d.rounded_rectangle([cx - knock, cy - knock, cx + knock, cy + knock],
                                radius=int(knock * 0.4), fill=QR_LIGHT)
            lg = Image.open(LOGO).convert("RGBA")
            h = int(lg.height * badge / lg.width)
            lg = lg.resize((badge, h))
            img.paste(lg, (int(cx - badge / 2), int(cy - h / 2)), lg)
        except Exception:
            pass


# --------------------------------------------------------------------------- #
#  WINGMAN x MOTOVERSE co-brand lockup (footer)
# --------------------------------------------------------------------------- #
def paste_logo(canvas, cx, cy, target_w):
    if not LOGO.exists():
        return False
    lg = Image.open(LOGO).convert("RGBA")
    h = int(lg.height * target_w / lg.width); lg = lg.resize((target_w, h))
    canvas.paste(lg, (cx - target_w // 2, cy - h // 2), lg)
    return True


def paste_wingman(canvas, cx, cy, target_w):
    if not WINGMAN_LOGO.exists():
        return False
    lg = Image.open(WINGMAN_LOGO).convert("RGBA")
    h = int(lg.height * target_w / lg.width); lg = lg.resize((target_w, h))
    canvas.paste(lg, (cx - target_w // 2, cy - h // 2), lg)
    return True


def _collab_mark(d, cx, cy, acc):
    """Two interlocking rings (soft-white + accent) = the two brands linked."""
    r, off = 14, 9
    soft, faint = (208, 203, 194), (98, 95, 88)
    d.line([(cx - 50, cy), (cx - r - off - 4, cy)], fill=faint, width=2)
    d.line([(cx + r + off + 4, cy), (cx + 50, cy)], fill=faint, width=2)
    d.ellipse([cx - off - r, cy - r, cx - off + r, cy + r], outline=soft, width=3)
    d.ellipse([cx + off - r, cy - r, cx + off + r, cy + r], outline=acc, width=3)


def cobrand(img, cy, acc):
    """WINGMAN x MOTOVERSE lockup, centred, joined by the collaboration mark."""
    wing_w, mv_w, gap = 250, 188, 116
    total = wing_w + gap + mv_w
    x0 = (W - total) // 2 - 6
    wcx = x0 + wing_w // 2
    mcx = x0 + wing_w + gap + mv_w // 2
    divx = x0 + wing_w + gap // 2
    if not paste_wingman(img, wcx, cy, wing_w):
        d0 = ImageDraw.Draw(img)
        ttext(d0, wcx, cy - 20, "WINGMAN", F("BigShoulders-Bold.ttf", 44), CREAM, tr=8, anchor="m")
    paste_logo(img, mcx, cy, mv_w)
    d = ImageDraw.Draw(img)
    _collab_mark(d, divx, cy, acc)
    return d
