"""
telemetry.py — raw Wingman export -> clean per-trip table.
=========================================================
Vendored, trimmed copy of the Wingman trip pipeline (originally split across
rider_classifier.py + final_model.py). Only what the streak calendar needs is
kept: parsing, GAP-BASED trip segmentation, per-trip distance, and cleaning.
The persona scoring / KMeans layers are intentionally left out.

Expected input columns (a Wingman telemetry CSV or XLSX):
    IST_time_stamp, IMEI, VIN, ECU_TYPE, Speed, Odometer, Delta_Distance,
    Vehicle_Speed_Samples_separated, Engine_Speed_Samples, Throttle_Opening,
    Gear_Position, Altitude
"""
import re
import numpy as np
import pandas as pd

from .config import SESSION_GAP_S


# --------------------------------------------------------------------------- #
#  parsing helpers
# --------------------------------------------------------------------------- #
def num(s):
    return pd.to_numeric(s, errors="coerce")


def parse_burst(cell):
    """'[1670;1720;0;0;0;0]' -> [1670., 1720., 0, 0, 0, 0]"""
    if pd.isna(cell):
        return []
    out = []
    for t in re.split(r"[;,\[\]\s]+", str(cell)):
        if t not in ("", "nan"):
            try:
                out.append(float(t))
            except ValueError:
                pass
    return out


def read_any(path):
    """Load a telemetry CSV/XLSX, normalise timestamps + VIN/ECU per IMEI, and
    segment into gap-based trips. Returns a row-level DataFrame with TRIP_ID."""
    p = str(path).lower()
    if p.endswith((".xlsx", ".xls")):
        df = pd.read_excel(path)
    elif p.endswith(".csv"):
        df = pd.read_csv(path)
    else:
        raise ValueError("Input must be .csv or .xlsx")
    df["ts"] = pd.to_datetime(df["IST_time_stamp"], errors="coerce")
    df = df.sort_values("ts")
    df["ECU_TYPE"] = df.groupby("IMEI")["ECU_TYPE"].transform(
        lambda s: s.dropna().mode().iloc[0] if s.notna().any() else "NA")
    vmap = df.groupby("IMEI")["VIN"].apply(
        lambda s: s.dropna().mode().iloc[0] if s.notna().any() else "NA")
    df["VIN"] = df["IMEI"].map(vmap)
    return assign_trip_ids(df)


# --------------------------------------------------------------------------- #
#  trip segmentation (gap-based) + per-trip features
# --------------------------------------------------------------------------- #
def assign_trip_ids(df):
    """Segment the telemetry stream into trips by TIME GAPS: a contiguous run of
    telemetry with no gap > SESSION_GAP_S is one trip. Keep only sessions that
    actually MOVED (max GPS speed > 5) so parked heartbeat blips don't count."""
    df = df.sort_values(["IMEI", "ts"]).reset_index(drop=True)
    newid = np.full(len(df), np.nan, dtype=object)
    counter = 0
    for _, idx in df.groupby("IMEI").groups.items():
        pos = np.asarray(idx)
        sub = df.loc[pos]
        gap = sub["ts"].diff().dt.total_seconds().fillna(1e9).to_numpy()
        seg = np.cumsum(gap > SESSION_GAP_S)          # local session index
        spd = num(sub["Speed"]).to_numpy()
        for s in np.unique(seg):
            m = seg == s
            smax = np.nanmax(np.where(np.isfinite(spd) & m, spd, np.nan)) if m.any() else np.nan
            if m.sum() >= 2 and np.isfinite(smax) and smax > 5:
                counter += 1
                newid[pos[m]] = counter
    df["TRIP_ID"] = newid
    return df


def trip_features(t):
    """Per-trip distance + the few signals cleaning needs, for a single trip."""
    f = {}
    # distance: prefer odometer delta, fall back to summed Delta_Distance
    odo = num(t["Odometer"]).dropna()
    dist = (odo.max() - odo.min()) if len(odo) > 1 else num(t["Delta_Distance"]).sum() / 1000.0
    f["distance_km"] = max(dist, 0.0)

    # altitude spread — used only to reject GPS-altitude glitches in clean_trips
    alt = num(t["Altitude"]).dropna()
    f["alt_range"] = (alt.max() - alt.min()) if len(alt) > 1 else 0.0

    f["duration_min"] = (t["ts"].max() - t["ts"].min()).total_seconds() / 60.0
    f["start_hour"] = t["ts"].min().hour
    return f


def build_trip_table(df):
    rows = []
    for tid, t in df.groupby("TRIP_ID"):
        if len(t) < 2:
            continue
        r = trip_features(t)
        r["TRIP_ID"] = tid
        rows.append(r)
    if not rows:
        return pd.DataFrame(columns=["distance_km", "alt_range", "duration_min",
                                     "start_hour"]).set_index(
            pd.Index([], name="TRIP_ID"))
    return pd.DataFrame(rows).set_index("TRIP_ID")


def clean_trips(trips):
    """Drop odometer glitches (>300 km single trip) and GPS-altitude spikes."""
    trips = trips.copy()
    trips.loc[trips["distance_km"] > 300, "distance_km"] = np.nan
    trips.loc[trips["alt_range"] > 800, "alt_range"] = np.nan
    return trips


def identity(vin, ecu):
    """Card identity fields. At Motoverse these come from the registration form."""
    return {"vin": vin, "ecu": f"ECU · {ecu}",
            "qr": f"https://royalenfield.com/wingman/{vin}"}
