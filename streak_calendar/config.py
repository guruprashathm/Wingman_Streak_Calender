"""
Paths, output location and tunable thresholds for streak-calendar.
=================================================================
Everything here is overridable via environment variables so the package runs
unchanged whether it is pip-installed, vendored, or run from a checkout.

    STREAK_FONTS   directory holding the .ttf fonts   (default: packaged fonts)
    STREAK_OUT     directory the CLI writes cards into (default: ./streak_cards)
"""
import os
from pathlib import Path

PKG_ROOT = Path(__file__).resolve().parent
ASSETS = PKG_ROOT / "assets"

# ---- fonts + brand marks (all shipped inside the package) ----
FONTS = Path(os.environ.get("STREAK_FONTS", str(ASSETS / "fonts")))
LOGO = ASSETS / "re_logo.png"            # Royal Enfield mark (co-brand footer)
WINGMAN_LOGO = ASSETS / "wingman_logo.png"

# ---- where the CLI drops rendered cards ----
OUT_DIR = Path(os.environ.get("STREAK_OUT", "streak_cards")).resolve()

# ---- analysis window ----
WINDOW_DAYS = 90                         # "last 3 months" calendar window

# ---- day-level distance buckets (km ridden in one calendar day) ----
# Fleet-data-derived tertiles (p33 / p66 of active days). Provisional — recalibrate
# on a larger fleet. 0 km -> NONE, <= LIGHT -> LIGHT, <= MEDIUM -> MEDIUM, else HEAVY.
TH_LIGHT_MAX = 8.0
TH_MEDIUM_MAX = 20.0

# a telemetry gap longer than this (seconds) starts a NEW trip/session
SESSION_GAP_S = 1200

# ---- live OBD history source (Wingman GraphQL API) ----
# Override any of these via environment. The token is a short-lived JWT, so it is
# only read from the environment (RE_API_TOKEN) and never committed.
RE_API_URL = os.environ.get(
    "RE_API_URL", "https://connected-api-sit.royalenfield.com/graphql")
RE_API_TOKEN = os.environ.get("RE_API_TOKEN", "")
RE_API_TIMEOUT_S = float(os.environ.get("RE_API_TIMEOUT_S", "30"))
