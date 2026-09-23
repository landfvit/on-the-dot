"""UTC allocation windows shared by catalog, history and quiz selection."""
from datetime import datetime, time, timedelta, timezone


def week_window(now_ms):
    day = datetime.fromtimestamp(now_ms / 1000, timezone.utc).date()
    start = day - timedelta(days=day.weekday())
    reset = datetime.combine(start + timedelta(days=7), time.min, timezone.utc)
    return start, reset
