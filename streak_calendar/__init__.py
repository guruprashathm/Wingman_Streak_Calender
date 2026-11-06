"""
streak_calendar — a self-contained "Rider Streak" calendar card generator.
==========================================================================
A GitHub-style riding-activity calendar rendered as a 1080x1920 share card,
extracted from the Wingman persona project into a standalone package.

Three layers:
    streak_calendar.telemetry  raw export        -> clean per-trip table
    streak_calendar.layer      per-trip table    -> daily buckets / streaks / summary
    streak_calendar.card       summary           -> 1080x1920 PNG

Typical use:

    from streak_calendar import read_any, rider_streak_summary, card_from_summary, identity

    df = read_any("ride_export.xlsx")
    for _, t in df.groupby("IMEI"):
        summary = rider_streak_summary(t, today="2026-07-10")
        card_from_summary(summary, identity(t["VIN"].iloc[0], t["ECU_TYPE"].iloc[0]),
                          out="streak.png")

A rider's history can come from a file export (`read_any`) or straight from the
live Wingman OBD API (`read_obd_api`) — both yield the same frame shape.

CLI:  python -m streak_calendar <path.csv|xlsx> [--today YYYY-MM-DD]
      python -m streak_calendar --vin <VIN> [--today YYYY-MM-DD]
"""
from .telemetry import (
    read_any, identity, build_trip_table, clean_trips, assign_trip_ids,
)
from .api import (
    read_obd_api, fetch_obd_history, obd_to_dataframe, OBD_FIELDS,
)
from .layer import (
    rider_streak_summary, daily_series, with_buckets, compute_streaks,
    bucket_of, BUCKETS,
)
from .card import (
    card_from_summary, streak_to_cfg, render_streak, BUCKET_COLOR, DEFAULT_ACCENT,
)
from .config import WINDOW_DAYS, TH_LIGHT_MAX, TH_MEDIUM_MAX

__version__ = "1.0.0"

__all__ = [
    # telemetry
    "read_any", "identity", "build_trip_table", "clean_trips", "assign_trip_ids",
    # live OBD API source
    "read_obd_api", "fetch_obd_history", "obd_to_dataframe", "OBD_FIELDS",
    # data layer
    "rider_streak_summary", "daily_series", "with_buckets", "compute_streaks",
    "bucket_of", "BUCKETS",
    # render layer
    "card_from_summary", "streak_to_cfg", "render_streak",
    "BUCKET_COLOR", "DEFAULT_ACCENT",
    # config
    "WINDOW_DAYS", "TH_LIGHT_MAX", "TH_MEDIUM_MAX",
]
