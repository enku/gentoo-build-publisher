"""Utilities for dealing with time and dates"""
import datetime as dt


def lapsed(start: dt.datetime, end: dt.datetime) -> int:
    """Return the number of seconds between `start` and `end`"""
    return int((end - start).total_seconds())


def utctime(time: dt.datetime | None = None) -> dt.datetime:
    """Return time but with the timezone being UTC"""
    if time is None:
        time = dt.datetime.utcnow()

    return time.replace(tzinfo=dt.timezone.utc)
