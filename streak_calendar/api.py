"""
api.py — live Wingman OBD history (GraphQL) -> the same frame a file export gives.
=================================================================================
A second, parallel data source to `telemetry.read_any`. Instead of reading a
CSV/XLSX export, this pulls a rider's OBD history straight from the Wingman
GraphQL endpoint (`getObdHistoryByVin`) and reshapes it into the exact column
layout the rest of the pipeline expects, so `telemetry -> layer -> card` runs
unchanged.

Only the handful of fields the streak model actually reads are requested
(`OBD_FIELDS`); the ~30 other engine params on `ObdDataPacket` are not pulled.
Field -> raw-column mapping:

    ts            (epoch seconds)  -> IST_time_stamp  (converted to IST)
    vehicleSpeed                   -> Speed           (trip segmentation)
    obdDistance   (cumulative km)  -> Odometer        (per-trip distance = max-min)
    vehiclenumber                  -> VIN  and  IMEI  (one VIN = one rider)
    ecu_type                       -> ECU_TYPE        (card label)

The query is unauthenticated-token-agnostic: pass a bearer token explicitly or
set RE_API_TOKEN in the environment (the JWT is short-lived).
"""
import json
import urllib.error
import urllib.request

import numpy as np
import pandas as pd

from .config import RE_API_URL, RE_API_TOKEN, RE_API_TIMEOUT_S, WINDOW_DAYS
from .telemetry import _finalize

# Exact GraphQL field names to request. The one place to edit to pull more
# signals later. `imei` is intentionally absent — it is not a field on this query.
OBD_FIELDS = ["vehiclenumber", "ts", "vehicleSpeed", "obdDistance", "ecu_type"]

# OBD `ts` is epoch seconds (UTC); riders' days are IST, and day boundaries drive
# the streak buckets, so timestamps are converted to this zone (then made naive).
IST_ZONE = "Asia/Kolkata"

_QUERY = (
    "query ($vin: String!, $limit: Int, $offset: Int) { "
    "getObdHistoryByVin(vin: $vin, limit: $limit, offset: $offset) { %s } }"
    % " ".join(OBD_FIELDS)
)

# frame columns the downstream pipeline reads (see telemetry.py / cli.py)
_FRAME_COLS = ["IST_time_stamp", "IMEI", "VIN", "ECU_TYPE",
               "Speed", "Odometer", "Delta_Distance", "Altitude"]


# --------------------------------------------------------------------------- #
#  fetch
# --------------------------------------------------------------------------- #
def _post(base_url, token, timeout, variables):
    """One GraphQL POST. Raises RuntimeError with a readable message on any
    transport or GraphQL-level error. Returns the record list (possibly empty)."""
    body = json.dumps({"query": _QUERY, "variables": variables}).encode()
    req = urllib.request.Request(
        base_url, data=body, method="POST",
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:500]
        raise RuntimeError(f"OBD API HTTP {e.code}: {detail}") from None
    except urllib.error.URLError as e:
        raise RuntimeError(f"OBD API unreachable: {e.reason}") from None

    if payload.get("errors"):
        msg = payload["errors"][0].get("message", "unknown GraphQL error")
        # a wrong field name in OBD_FIELDS surfaces here as a readable message
        raise RuntimeError(f"OBD API error: {msg}")
    data = (payload.get("data") or {}).get("getObdHistoryByVin")
    return data or []


def fetch_obd_history(vin, *, token=None, base_url=None, timeout=None,
                      page_size=1000):
    """Pull the full OBD history for one VIN, paging via limit/offset until a
    short/empty page. Returns a flat list of record dicts."""
    token = token or RE_API_TOKEN
    base_url = base_url or RE_API_URL
    timeout = timeout or RE_API_TIMEOUT_S
    if not token:
        raise RuntimeError(
            "No API token. Pass token=... or set the RE_API_TOKEN env var.")

    records, offset = [], 0
    while True:
        page = _post(base_url, token, timeout,
                     {"vin": vin, "limit": page_size, "offset": offset})
        records.extend(page)
        if len(page) < page_size:          # last page reached
            break
        offset += page_size
    return records


# --------------------------------------------------------------------------- #
#  reshape -> pipeline frame
# --------------------------------------------------------------------------- #
def _col(raw, name):
    """A column from the raw frame, or an all-NaN column if the API omitted it."""
    return raw[name] if name in raw.columns else pd.Series([np.nan] * len(raw))


def obd_to_dataframe(records, vin=None):
    """Map raw OBD records to the raw-column frame the pipeline consumes. Does
    NOT segment trips — that happens in `_finalize` (same as the file path)."""
    if not records:
        return pd.DataFrame(columns=_FRAME_COLS)

    raw = pd.DataFrame(records)

    # epoch seconds (UTC) -> IST wall-clock, naive (matches file timestamps)
    ts = pd.to_numeric(_col(raw, "ts"), errors="coerce")
    ist = (pd.to_datetime(ts, unit="s", utc=True)
             .dt.tz_convert(IST_ZONE).dt.tz_localize(None))

    vehnum = _col(raw, "vehiclenumber")
    if "vehiclenumber" not in raw.columns and vin is not None:
        vehnum = pd.Series([vin] * len(raw))

    return pd.DataFrame({
        "IST_time_stamp": ist,
        "IMEI": vehnum,                     # no IMEI field -> key riders by VIN
        "VIN": vehnum,
        "ECU_TYPE": _col(raw, "ecu_type"),
        "Speed": pd.to_numeric(_col(raw, "vehicleSpeed"), errors="coerce"),
        "Odometer": pd.to_numeric(_col(raw, "obdDistance"), errors="coerce"),
        "Delta_Distance": np.nan,           # unused; Odometer is present
        "Altitude": np.nan,                 # not in API -> glitch branch skipped
    })


def read_obd_api(vin, *, token=None, base_url=None, timeout=None,
                 days=WINDOW_DAYS):
    """VIN -> live OBD history -> the same segmented frame `read_any` returns.
    The server already returns ~90 days; `days` is a client-side safety clamp."""
    records = fetch_obd_history(vin, token=token, base_url=base_url,
                                timeout=timeout)
    df = obd_to_dataframe(records, vin=vin)
    if len(df) == 0:
        return df

    df = _finalize(df)
    if days and len(df):
        cutoff = df["ts"].max() - pd.Timedelta(days=days)
        df = df[df["ts"] >= cutoff].reset_index(drop=True)
    return df
