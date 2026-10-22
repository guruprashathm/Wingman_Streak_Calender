"""Package entry point:  python -m streak_calendar <path.csv|xlsx> [YYYY-MM-DD]"""
from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
