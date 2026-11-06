"""
card.py — GitHub-style "Rider Streak" calendar card (RENDER layer).
===================================================================
Renders one 1080x1920 card per rider from a streak summary (layer.py):
  * a day-by-day activity calendar over the window, coloured
    NONE / LIGHT / MEDIUM / HEAVY
  * CURRENT STREAK and HIGHEST STREAK (consecutive ride-days)
  * riding-day mix, TOTAL DISTANCE / TOTAL TRIPS / RIDING DAYS
  * WINGMAN x MOTOVERSE co-brand footer

Public entry point:  card_from_summary(summary, ident, out_path, accent)
"""
import pandas as pd
from PIL import ImageDraw

from .theme import (F, ttext, qr, cobrand, vgrad, grain, vignette,
                    CREAM, MUTE, FAINT, ZEN, MAV, RED, W, H)
from .config import TH_LIGHT_MAX, TH_MEDIUM_MAX

BUCKET_COLOR = {"NONE": (46, 48, 53), "LIGHT": ZEN, "MEDIUM": MAV, "HEAVY": RED}
DEFAULT_ACCENT = (200, 196, 188)   # neutral cream-gray when no persona accent is known


# --------------------------------------------------------------------------- #
#  layout helpers
# --------------------------------------------------------------------------- #
def _week_grid(daily):
    """Align the daily series to full Sun-Sat weeks (GitHub-style), padding the
    partial first/last weeks. Returns a list of 7-length columns (Sun..Sat) of
    (date_or_None, bucket_or_None)."""
    idx = daily.index
    first, last = idx[0], idx[-1]
    grid_start = first - pd.Timedelta(days=(first.weekday() + 1) % 7)    # back to Sunday
    grid_end = last + pd.Timedelta(days=(6 - (last.weekday() + 1) % 7))  # forward to Saturday
    full = pd.date_range(grid_start, grid_end, freq="D")
    lookup = daily["bucket"].to_dict()
    weeks, col = [], []
    for d in full:
        col.append((d, lookup.get(d)))
        if d.weekday() == 5:      # Saturday closes the week (Sun..Sat)
            weeks.append(col); col = []
    if col:
        weeks.append(col)
    return weeks


def _draw_calendar(d, x0, y0, weeks, cell=30, gap=8, acc_month=MUTE):
    """Draw the week-column calendar; returns (y_below, x_right)."""
    row_h = cell + gap
    last_month = None
    for wi, col in enumerate(weeks):
        cx = x0 + wi * row_h
        for d0, bucket in col:
            if d0 is None:
                continue
            if d0.day <= 7 and d0.month != last_month:   # first week touching a new month
                ttext(d, cx, y0 - 30, d0.strftime("%b").upper(),
                      F("GeistMono-Bold.ttf", 18), acc_month, tr=2)
                last_month = d0.month
    for wi, col in enumerate(weeks):
        cx = x0 + wi * row_h
        for ri, (d0, bucket) in enumerate(col):
            cy = y0 + ri * row_h
            if bucket is None:                # padding day outside the actual window
                continue
            d.rounded_rectangle([cx, cy, cx + cell, cy + cell], radius=6, fill=BUCKET_COLOR[bucket])
    for ri, lab in ((1, "M"), (3, "W"), (5, "F")):       # day-of-week labels, Sun=row0
        ttext(d, x0 - 26, y0 + ri * row_h + cell / 2 - 8, lab, F("GeistMono-Regular.ttf", 16), MUTE)
    return y0 + 7 * row_h, x0 + len(weeks) * row_h


def _legend(d, cx, y, cell=18, gap=6):
    ttext(d, cx - 150, y - 6, "LESS", F("GeistMono-Regular.ttf", 16), MUTE, tr=2, anchor="r")
    x = cx - 100
    for key in ("NONE", "LIGHT", "MEDIUM", "HEAVY"):
        d.rounded_rectangle([x, y - cell + 4, x + cell, y + 4], radius=4, fill=BUCKET_COLOR[key])
        x += cell + gap
    ttext(d, x + 6, y - 6, "MORE", F("GeistMono-Regular.ttf", 16), MUTE, tr=2)


def _stat_row(d, cxs, row, y, fD, fMB):
    for x, (lab, val) in zip(cxs, row):
        ttext(d, x, y, val, fD(88), CREAM, anchor="m")
        ttext(d, x, y + 96, lab, fMB(18), MUTE, tr=3, anchor="m")


# --------------------------------------------------------------------------- #
#  main render
# --------------------------------------------------------------------------- #
def render_streak(cfg, out):
    acc = cfg.get("accent", DEFAULT_ACCENT)
    img = vgrad().convert("RGBA")
    d = ImageDraw.Draw(img)
    fD = lambda s: F("BigShoulders-Bold.ttf", s)
    fM = lambda s: F("GeistMono-Regular.ttf", s)
    fMB = lambda s: F("GeistMono-Bold.ttf", s)
    M = 84

    # ---- header ----
    y = 168
    ttext(d, W // 2, y, "WINGMAN · RIDER STREAK", fM(24), acc, tr=8, anchor="m"); y += 74
    ttext(d, W // 2, y, "Your Riding Calendar", fD(86), CREAM, tr=1, anchor="m"); y += 100
    ttext(d, W // 2, y, cfg["subline"], fM(19), MUTE, tr=2, anchor="m"); y += 80

    # ---- hero streak numbers (current + highest, side by side) ----
    d.line([(W // 2, y - 10), (W // 2, y + 142)], fill=FAINT, width=2)
    ttext(d, W // 2 - 220, y, str(cfg["current_streak"]), fD(150), acc, anchor="m")
    ttext(d, W // 2 - 220, y + 110, "CURRENT STREAK (DAYS)", fMB(18), MUTE, tr=2, anchor="m")
    ttext(d, W // 2 + 220, y, str(cfg["highest_streak"]), fD(150), CREAM, anchor="m")
    ttext(d, W // 2 + 220, y + 110, "HIGHEST STREAK (DAYS)", fMB(18), MUTE, tr=2, anchor="m")
    y += 196

    # ---- calendar (the card's centrepiece) ----
    cell, gap = 38, 10
    weeks = cfg["weeks"]
    cal_w = len(weeks) * (cell + gap)
    x0 = W // 2 - cal_w // 2 + cell
    ttext(d, W // 2, y, cfg["cal_caption"], fMB(20), MUTE, tr=5, anchor="m")
    y += 54
    y_end, _ = _draw_calendar(d, x0, y, weeks, cell=cell, gap=gap)
    y = y_end + 26
    _legend(d, W // 2, y)
    y += 54

    # ---- riding-day mix: share of riding days that were light/medium/heavy ----
    d.line([(M, y), (W - M, y)], fill=FAINT, width=2); y += 46
    ttext(d, W // 2, y, "RIDING-DAY MIX", fMB(20), MUTE, tr=5, anchor="m"); y += 40
    mix = cfg["mix_pct"]; bw = 640; bx = W // 2 - bw // 2; left = bx
    for val, col in [(mix["LIGHT"], ZEN), (mix["MEDIUM"], MAV), (mix["HEAVY"], RED)]:
        seg = bw * val / 100.0
        if seg > 0:
            d.rectangle([left, y, left + seg, y + 26], fill=col)
            if val >= 8:
                ttext(d, left + seg / 2, y + 3, f"{val:.0f}", fMB(15), (255, 255, 255), anchor="m")
        left += seg
    y += 38
    ttext(d, W // 2, y,
          f"LIGHT {mix['LIGHT']:.0f}%      MEDIUM {mix['MEDIUM']:.0f}%      HEAVY {mix['HEAVY']:.0f}%",
          fM(20), (200, 196, 188), tr=2, anchor="m")
    y += 60

    # ---- stat row: total distance / total trips / riding days ----
    d.line([(M, y), (W - M, y)], fill=FAINT, width=2); y += 74
    row = [("TOTAL DISTANCE", cfg["total_km_str"]), ("TOTAL TRIPS", str(cfg["total_trips"])),
           ("RIDING DAYS", f"{cfg['riding_days']}/{cfg['window_days']}")]
    xs = [W // 2 + o for o in (-300, 0, 300)]
    for gx in (W // 2 - 150, W // 2 + 150):
        d.line([(gx, y - 56), (gx, y + 108)], fill=FAINT, width=2)
    _stat_row(d, xs, row, y, fD, fMB)
    y += 132

    ttext(d, W // 2, y, cfg["window_caption"], fM(19), (200, 196, 188), tr=1, anchor="m")

    # ---- footer: WINGMAN x MOTOVERSE co-brand lockup ----
    d.line([(M, 1792), (W - M, 1792)], fill=FAINT, width=2)
    cobrand(img, 1672, acc)
    d = ImageDraw.Draw(img)
    ttext(d, M, 1812, "MADE LIKE A GUN · PURE MOTORCYCLING", fM(17), MUTE, tr=3)
    ttext(d, M, 1840, "ROYAL ENFIELD MOTOVERSE // DIGITAL DISPATCH", fMB(17), acc, tr=2)

    img = vignette(grain(img.convert("RGB")))
    # QR is drawn LAST — after grain/vignette — so noise and corner-darkening
    # never touch it. It sits in the bottom-right corner (the most-vignetted
    # area), so keeping it clean here is what makes it reliably scannable.
    # ~128px is near the lower bound for a short URL; the planned redesign
    # should budget >=140px and keep the encoded URL short.
    qr(img, W - M - 136, 1778, 128, cfg.get("qr", "https://royalenfield.com/wingman"))
    img.save(out)
    return out


# --------------------------------------------------------------------------- #
#  summary -> cfg -> card
# --------------------------------------------------------------------------- #
def streak_to_cfg(summary, ident, accent=None):
    daily = summary["daily"]
    weeks = _week_grid(daily)
    start_d = daily.index[0].strftime("%d %b")
    end_d = daily.index[-1].strftime("%d %b %Y")
    rd = max(summary["riding_days"], 1)          # avoid /0 when a rider has no activity
    mix_pct = {k: 100.0 * summary["mix"][k] / rd for k in ("LIGHT", "MEDIUM", "HEAVY")}
    return dict(
        accent=accent or DEFAULT_ACCENT,
        subline=f"VIN {ident.get('vin', '')}   ·   {ident.get('ecu', '')}   ·   as of {summary['as_of']}",
        current_streak=summary["current_streak"],
        highest_streak=summary["highest_streak"],
        weeks=weeks,
        cal_caption=f"ACTIVITY  ·  {start_d} – {end_d}",
        total_km_str=f"{summary['total_km']:.0f}KM",
        total_trips=summary["total_trips"],
        riding_days=summary["riding_days"],
        window_days=summary["window_days"],
        mix_pct=mix_pct,
        window_caption=(f"LIGHT ≤ {TH_LIGHT_MAX:.0f}KM/DAY   ·   MEDIUM ≤ {TH_MEDIUM_MAX:.0f}KM/DAY   "
                        f"·   HEAVY > {TH_MEDIUM_MAX:.0f}KM/DAY"),
        qr=ident.get("qr", "https://royalenfield.com/wingman"),
    )


def card_from_summary(summary, ident, out, accent=None):
    return render_streak(streak_to_cfg(summary, ident, accent), out)
