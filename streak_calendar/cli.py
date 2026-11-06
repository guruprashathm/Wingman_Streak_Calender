"""
cli.py — telemetry file OR live OBD API -> one streak card per rider.
=====================================================================
    # from a file export (unchanged):
    python -m streak_calendar <path.csv|xlsx> [--today YYYY-MM-DD]

    # from the live Wingman OBD API (one card per --vin):
    python -m streak_calendar --vin <VIN> [--vin <VIN> ...] [--today YYYY-MM-DD]

For every rider (keyed by IMEI; for the API, IMEI = VIN) it computes the streak
summary over the last WINDOW_DAYS and writes streak_<VIN>.png into the output dir
(config.OUT_DIR, override with STREAK_OUT). If no --today is given, the latest
timestamp in the data is used, so the window is the last WINDOW_DAYS of whatever
the source contains.

The API token comes from --token or the RE_API_TOKEN env var (short-lived JWT).
"""
import argparse
import sys

import pandas as pd

from .config import OUT_DIR
from .telemetry import read_any, identity
from .api import read_obd_api
from .layer import rider_streak_summary
from .card import card_from_summary


def _load(args):
    """Build one combined frame from the file source and/or each --vin."""
    frames = []
    if args.source:
        frames.append(read_any(args.source))
    for vin in args.vin or []:
        frames.append(read_obd_api(vin, token=args.token, base_url=args.base_url))
    frames = [f for f in frames if f is not None and len(f)]
    if not frames:
        return None
    return pd.concat(frames, ignore_index=True) if len(frames) > 1 else frames[0]


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="streak_calendar",
        description="Render Rider Streak cards from a telemetry file or the live OBD API.")
    parser.add_argument("source", nargs="?",
                        help="telemetry export path (.csv/.xlsx)")
    parser.add_argument("--vin", action="append", metavar="VIN",
                        help="fetch this VIN live from the OBD API (repeatable)")
    parser.add_argument("--token", default=None,
                        help="API bearer token (else RE_API_TOKEN env var)")
    parser.add_argument("--base-url", dest="base_url", default=None,
                        help="override the GraphQL endpoint (else RE_API_URL)")
    parser.add_argument("--today", default=None, metavar="YYYY-MM-DD",
                        help="window end date (default: latest timestamp in data)")
    args = parser.parse_args(list(sys.argv[1:] if argv is None else argv))

    if not args.source and not args.vin:
        parser.print_help()
        return 1

    df = _load(args)
    if df is None or len(df) == 0:
        print("  no telemetry / OBD rows for the given source(s)")
        return 1

    today = pd.Timestamp(args.today) if args.today else df["ts"].max()
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
