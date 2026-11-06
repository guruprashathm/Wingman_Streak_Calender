"""
Unit tests for the live-OBD-API source (offline — no network, no token).
The sample records below mirror a real `getObdHistoryByVin` response.
Run:  pytest
"""
import numpy as np
import pandas as pd
import pytest

import streak_calendar.api as api
from streak_calendar.api import obd_to_dataframe, read_obd_api, _FRAME_COLS
from streak_calendar.telemetry import _finalize, build_trip_table
from streak_calendar.layer import rider_streak_summary

VIN = "ME3P7B6FLN1000035"

# Two sessions, ~15 h apart (gap >> 20 min -> different trips):
#  * a MOVING session (speed 25 > 5)  -> kept, distance = 26767.50 - 26767.20 = 0.30 km
#  * a PARKED session (speed 0 only)  -> dropped by assign_trip_ids
SAMPLE = [
    {"vehiclenumber": VIN, "ts": "1793768085", "vehicleSpeed": "25.062",
     "obdDistance": "26767.50", "ecu_type": "M4C"},
    {"vehiclenumber": VIN, "ts": "1793768027", "vehicleSpeed": "0",
     "obdDistance": "26767.20", "ecu_type": "M4C"},
    {"vehiclenumber": VIN, "ts": "1793712593", "vehicleSpeed": "0",
     "obdDistance": "26766.80", "ecu_type": "M4C"},
    {"vehiclenumber": VIN, "ts": "1793712548", "vehicleSpeed": "0",
     "obdDistance": "26766.80", "ecu_type": "M4C"},
]


def test_columns_and_dtypes():
    df = obd_to_dataframe(SAMPLE)
    assert list(df.columns) == _FRAME_COLS
    assert pd.api.types.is_datetime64_any_dtype(df["IST_time_stamp"])
    assert df["Speed"].dtype.kind == "f"
    assert df["Odometer"].dtype.kind == "f"
    assert df["IMEI"].iloc[0] == VIN and df["VIN"].iloc[0] == VIN
    assert df["ECU_TYPE"].iloc[0] == "M4C"


def test_epoch_seconds_become_ist():
    df = obd_to_dataframe(SAMPLE)
    expected = (pd.to_datetime(1793768085, unit="s", utc=True)
                  .tz_convert("Asia/Kolkata").tz_localize(None))
    assert df["IST_time_stamp"].max() == expected


def test_empty_records_keep_schema():
    df = obd_to_dataframe([])
    assert len(df) == 0
    assert list(df.columns) == _FRAME_COLS


def test_parked_dropped_and_odometer_distance():
    trips = build_trip_table(_finalize(obd_to_dataframe(SAMPLE)))
    assert len(trips) == 1                      # only the moving session survives
    assert trips["distance_km"].iloc[0] == pytest.approx(0.30, abs=1e-6)


def test_end_to_end_summary():
    df = _finalize(obd_to_dataframe(SAMPLE))
    summary = rider_streak_summary(df, today=df["ts"].max())
    assert summary["riding_days"] >= 1
    assert summary["total_km"] == pytest.approx(0.30, abs=1e-6)
    assert set(summary["mix"]) == {"NONE", "LIGHT", "MEDIUM", "HEAVY"}


def test_read_obd_api_uses_fetch(monkeypatch):
    """read_obd_api should reshape whatever fetch_obd_history returns, no network."""
    monkeypatch.setattr(api, "fetch_obd_history", lambda *a, **k: SAMPLE)
    df = read_obd_api(VIN, token="dummy")
    assert len(df) > 0
    assert df["VIN"].iloc[0] == VIN


def test_missing_optional_field_falls_back():
    """If the API omits ecu_type, the frame still builds (ECU_TYPE -> NA via mode)."""
    recs = [{k: v for k, v in r.items() if k != "ecu_type"} for r in SAMPLE]
    df = _finalize(obd_to_dataframe(recs))
    assert (df["ECU_TYPE"] == "NA").all()
