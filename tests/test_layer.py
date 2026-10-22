"""
Unit tests for the pure data layer (no PIL / no telemetry file needed).
Run:  pytest
"""
import numpy as np
import pandas as pd

from streak_calendar.layer import bucket_of, with_buckets, compute_streaks
from streak_calendar.config import TH_LIGHT_MAX, TH_MEDIUM_MAX


def _daily(km_list, end="2026-07-10"):
    """Build a daily frame whose LAST day is `end`, from a list of daily km."""
    end = pd.Timestamp(end)
    idx = pd.date_range(end - pd.Timedelta(days=len(km_list) - 1), end, freq="D")
    return with_buckets(pd.DataFrame({"km": km_list, "trips": [1 if k else 0 for k in km_list]}, index=idx))


def test_bucket_thresholds():
    assert bucket_of(0) == "NONE"
    assert bucket_of(-5) == "NONE"
    assert bucket_of(float("nan")) == "NONE"
    assert bucket_of(TH_LIGHT_MAX) == "LIGHT"
    assert bucket_of(TH_LIGHT_MAX + 0.1) == "MEDIUM"
    assert bucket_of(TH_MEDIUM_MAX) == "MEDIUM"
    assert bucket_of(TH_MEDIUM_MAX + 0.1) == "HEAVY"


def test_no_activity():
    s = compute_streaks(_daily([0, 0, 0, 0]))
    assert s == dict(current=0, highest=0, highest_start=None, highest_end=None)


def test_highest_streak_is_longest_run():
    # runs of 2, then 3 ride-days separated by a rest day
    s = compute_streaks(_daily([5, 5, 0, 10, 10, 10, 0]))
    assert s["highest"] == 3


def test_current_streak_counts_to_today():
    # last 4 days all ridden, day ends today -> current == 4
    s = compute_streaks(_daily([0, 5, 5, 5, 5]))
    assert s["current"] == 4
    assert s["highest"] == 4


def test_current_tolerates_one_day_gap():
    # rode through yesterday, nothing "today" yet -> still live
    s = compute_streaks(_daily([5, 5, 5, 0]))
    assert s["current"] == 3


def test_current_breaks_after_two_missed_days():
    # two trailing rest days -> current resets to 0, highest preserved
    s = compute_streaks(_daily([5, 5, 5, 0, 0]))
    assert s["current"] == 0
    assert s["highest"] == 3
