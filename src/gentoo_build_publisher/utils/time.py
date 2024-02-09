"""Utilities for dealing with time and dates"""

import datetime as dt

LOCAL_TIMEZONE = dt.datetime.now().astimezone().tzinfo
SECONDS_PER_DAY = 86400

now = dt.datetime.now


def lapsed(start: dt.datetime, end: dt.datetime) -> int:
    """Return the number of seconds between `start` and `end`"""
    return int((end - start).total_seconds())


def localtime(time: dt.datetime | None = None) -> dt.datetime:
    """Return the given time (or now) in the local timezone"""
    if time is None:
        time = now()

    return time.astimezone(LOCAL_TIMEZONE)


def utctime(time: dt.datetime | None = None) -> dt.datetime:
    """Return time but with the timezone being UTC"""
    if time is None:
        return now(dt.UTC)

    return time.replace(tzinfo=dt.UTC)


def is_same_day(first: dt.datetime, second: dt.datetime) -> bool:
    """Return True if dates are on the same day"""
    return first.date() == second.date()


def is_previous_day(first: dt.datetime, second: dt.datetime) -> bool:
    """Return True if first is on the day before second"""
    day_before = (second - dt.timedelta(days=1)).date()

    return first.date() == day_before


def as_time(time: dt.datetime) -> str:
    """Return the time portion in the locale's format"""
    return time.strftime("%H:%M:%S")


def as_date(time: dt.datetime) -> str:
    """Return the date portion in the locale's format"""
    return time.strftime("%b %-d")


def as_date_and_time(time: dt.datetime) -> str:
    """Return the date and time in the locale's format"""
    return time.strftime("%b %-d %H:%M")
