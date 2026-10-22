"""
cli.py — telemetry file -> one streak card per rider.
=====================================================
    python -m streak_calendar <path.csv|xlsx> [YYYY-MM-DD]

For every rider (keyed by IMEI) in the export, computes the streak summary over
the last WINDOW_DAYS and writes figures/streak_<VIN>.png into the output dir
(config.OUT_DIR, override with the STREAK_OUT env var). If no "today" date is
given, the latest timestamp in the data is used, so the window is the last
WINDOW_DAYS of whatever the file contains.
"""
import sys

import pandas as pd

from .config import OUT_DIR
from .telemetry import read_any, identity
from .layer import rider_streak_summary
from .card import card_from_summary


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print("Usage: python -m streak_calendar <path.csv|xlsx> [YYYY-MM-DD]")
        return 1

    df = read_any(argv[0])
    today = pd.Timestamp(argv[1]) if len(argv) > 1 else df["ts"].max()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    made = 0
    for _, t in df.groupby("IMEI"):
        vin, ecu = t["VIN"].iloc[0], t["ECU_TYPE"].iloc[0]
        summary = rider_streak_summary(t, today)
        if summary["riding_days"] == 0:
            print(f"  {vin}: no riding activity in window - skipped")
            continue
        out = card_from_summary(summary, identity(vin, ecu), OUT_DIR / f"streak_{vin}.png")
        made += 1
        print(f"  {vin} [{ecu}] streak {summary['current_streak']:2d}/"
              f"{summary['highest_streak']:2d}d  {summary['total_km']:.0f}km "
              f"{summary['total_trips']} trips  ->  {out}")

    print(f"\n  {made} card(s) written to {OUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
