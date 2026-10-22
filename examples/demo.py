"""
demo.py — render a streak card from SYNTHETIC data (no telemetry file needed).
=============================================================================
Proves the render path end-to-end:

    python examples/demo.py          # writes streak_demo.png

It fabricates a plausible 90-day riding history, runs it through the data layer
(buckets + streaks), then renders the card — so you can see the output without a
real Wingman export. For real data, use the CLI instead:

    python -m streak_calendar <path.csv|xlsx> [YYYY-MM-DD]
"""
import numpy as np
import pandas as pd

from streak_calendar.layer import with_buckets, compute_streaks, BUCKETS
from streak_calendar.card import card_from_summary


def synthetic_summary(today="2026-07-10", window_days=90, seed=7):
    rng = np.random.default_rng(seed)
    today = pd.Timestamp(today)
    idx = pd.date_range(today - pd.Timedelta(days=window_days), today, freq="D")
    rode = rng.random(len(idx)) < 0.65                     # ~65% of days ridden
    km = np.where(rode, rng.gamma(2.0, 7.0, len(idx)), 0.0)
    trips = (km > 0).astype(int) + (km > 15).astype(int)   # 1-2 trips on riding days
    daily = with_buckets(pd.DataFrame({"km": km, "trips": trips}, index=idx))

    streaks = compute_streaks(daily)
    ride_days = daily["bucket"] != "NONE"
    return dict(
        daily=daily, window_days=window_days, as_of=today.date(),
        current_streak=streaks["current"], highest_streak=streaks["highest"],
        highest_streak_start=streaks["highest_start"], highest_streak_end=streaks["highest_end"],
        total_km=float(daily["km"].sum()), total_trips=int(daily["trips"].sum()),
        riding_days=int(ride_days.sum()), no_ride_days=int((~ride_days).sum()),
        mix={b: int((daily["bucket"] == b).sum()) for b in BUCKETS},
    )


if __name__ == "__main__":
    summary = synthetic_summary()
    ident = {"vin": "DEMO0000000000001", "ecu": "ECU · M4C",
             "qr": "https://royalenfield.com/wingman/demo"}
    out = card_from_summary(summary, ident, "streak_demo.png", accent=(224, 166, 58))
    print(f"wrote {out}  —  current {summary['current_streak']}d / "
          f"best {summary['highest_streak']}d, {summary['riding_days']} riding days")
