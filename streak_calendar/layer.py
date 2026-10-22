"""
layer.py — daily ride-activity calendar + streak calculation (DATA layer).
=========================================================================
Turns the per-trip table into a per-CALENDAR-DAY picture over the rider's last
WINDOW_DAYS: did they ride, and how much. Each day falls into one bucket:

    NONE    - no ride that day (gray on the calendar)
    LIGHT   - a short/easy day      (0 < km <= TH_LIGHT_MAX)
    MEDIUM  - a normal riding day    (TH_LIGHT_MAX < km <= TH_MEDIUM_MAX)
    HEAVY   - a big-mileage day      (km > TH_MEDIUM_MAX)

Pure calculation — no PIL, no I/O. `rider_streak_summary` returns everything a
card needs as a plain dict. Thresholds live in config.py.
"""
import numpy as np
import pandas as pd

from .config import WINDOW_DAYS, TH_LIGHT_MAX, TH_MEDIUM_MAX
from .telemetry import build_trip_table, clean_trips

BUCKETS = ["NONE", "LIGHT", "MEDIUM", "HEAVY"]


def bucket_of(km):
    if km is None or (isinstance(km, float) and np.isnan(km)) or km <= 0:
        return "NONE"
    if km <= TH_LIGHT_MAX:
        return "LIGHT"
    if km <= TH_MEDIUM_MAX:
        return "MEDIUM"
    return "HEAVY"


def daily_series(df_rider, today, window_days=WINDOW_DAYS):
    """Per-calendar-day distance + trip count over the last `window_days`, with
    every day present (0 km on days with no telemetry / no ride)."""
    today = pd.Timestamp(today)
    cutoff = today - pd.Timedelta(days=window_days)
    win = df_rider[(df_rider["ts"] >= cutoff) & (df_rider["ts"] <= today)]
    idx = pd.date_range(cutoff.normalize(), today.normalize(), freq="D")
    if len(win) == 0:
        return pd.DataFrame({"km": 0.0, "trips": 0}, index=idx)

    trips = clean_trips(build_trip_table(win))
    if len(trips) == 0:
        return pd.DataFrame({"km": 0.0, "trips": 0}, index=idx)

    start_ts = win.groupby("TRIP_ID")["ts"].min()
    trips = trips.join(start_ts.rename("start_ts"))
    trips["date"] = trips["start_ts"].dt.normalize()

    km = trips.groupby("date")["distance_km"].sum()
    n = trips.groupby("date").size()
    out = pd.DataFrame({"km": km, "trips": n}).reindex(idx, fill_value=0)
    out["km"] = out["km"].fillna(0.0)
    out["trips"] = out["trips"].fillna(0).astype(int)
    return out


def with_buckets(daily):
    daily = daily.copy()
    daily["bucket"] = daily["km"].apply(bucket_of)
    return daily


def compute_streaks(daily):
    """Longest run of consecutive ride-days (any bucket != NONE) in the window,
    and the CURRENT run.

    "Current" is gap-tolerant by exactly one day: telemetry for "today" often
    hasn't landed yet, so a streak whose last ride was YESTERDAY still counts as
    live; two or more consecutive no-ride days break it. Mirrors how
    GitHub / Duolingo streaks read as "still going" until a full day is missed.
    """
    rode = (daily["bucket"] != "NONE").to_numpy()
    if not rode.any():
        return dict(current=0, highest=0, highest_start=None, highest_end=None)

    run_id = np.cumsum(~rode)                  # bumps every time a NONE day is hit
    run_id = np.where(rode, run_id, -1)
    best_len, best_start, best_end = 0, None, None
    for rid in np.unique(run_id[run_id >= 0]):
        mask = run_id == rid
        length = int(mask.sum())
        if length > best_len:
            best_len = length
            idxs = np.where(mask)[0]
            best_start, best_end = daily.index[idxs[0]], daily.index[idxs[-1]]

    active_idx = np.where(rode)[0]
    last_active_pos = int(active_idx[-1])
    gap_to_end = (len(daily) - 1) - last_active_pos     # 0 = today rode, 1 = yesterday
    if gap_to_end > 1:
        current = 0
    else:
        current = 0
        for v in rode[:last_active_pos + 1][::-1]:
            if not v:
                break
            current += 1

    return dict(current=int(current), highest=int(best_len),
                highest_start=best_start, highest_end=best_end)


def rider_streak_summary(df_rider, today, window_days=WINDOW_DAYS):
    """Everything a streak card needs for one rider, as a plain dict."""
    daily = with_buckets(daily_series(df_rider, today, window_days))
    streaks = compute_streaks(daily)
    rode = daily["bucket"] != "NONE"
    return dict(
        daily=daily,
        window_days=window_days,
        as_of=pd.Timestamp(today).date(),
        current_streak=streaks["current"],
        highest_streak=streaks["highest"],
        highest_streak_start=streaks["highest_start"],
        highest_streak_end=streaks["highest_end"],
        total_km=float(daily["km"].sum()),
        total_trips=int(daily["trips"].sum()),
        riding_days=int(rode.sum()),
        no_ride_days=int((~rode).sum()),
        mix={b: int((daily["bucket"] == b).sum()) for b in BUCKETS},
    )
