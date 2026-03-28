"""Formatting helpers for time and duration display."""


def fmt_seconds(s: int) -> str:
    """Format a duration in seconds as 'Xh Ym' or 'Ym'."""
    h, m = divmod(s // 60, 60)
    return f"{h}h {m}m" if h else f"{m}m"


def fmt_time_of_day(s: int) -> str:
    """Format seconds since midnight as 'HH:MM'."""
    h, m = divmod(s // 60, 60)
    return f"{h:02d}:{m:02d}"
