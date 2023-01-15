"""Time-based purge algorithm

I copied this (idea, not code) from someone years ago but I don't remember so I can't
give a proper attribution.  It's originally a backup purging strategy but I want to be
able to use it for purging builds or anything else for that matter.
"""
from __future__ import annotations

import datetime
from typing import Callable, Generic, Iterable, TypeVar

T = TypeVar("T")  # pylint: disable=invalid-name


class Purger(Generic[T]):
    """Purger of items

    Items must be the same type and must be hashable
    """

    def __init__(
        self,
        items: Iterable[T],
        key: Callable[[T], datetime.datetime],
        start: datetime.datetime | None = None,
        end: datetime.datetime | None = None,
    ):
        self.items = [*items]
        self.key = key

        self.start = start
        self.end = end if end is not None else datetime.datetime.now()

    def purge(self) -> list[T]:
        """Return a list of items to purge"""
        keep: set[T] = set()

        keep.update(self.yesterday_plus())
        keep.update(self.one_per_day_last_week())
        keep.update(self.one_per_week_last_month())
        keep.update(self.one_per_month_last_year())
        keep.update(self.one_per_year())
        keep.update(self.past())

        return sorted(set(self.items) - keep, key=self.key)

    def filter_range(
        self, items: list[T], start: datetime.datetime, end: datetime.datetime
    ) -> list[T]:
        """
        Given a list of items, return a subset of items between start and end
        (inclusive).
        """
        return [item for item in items if start <= self.key(item) <= end]

    @staticmethod
    def last_day_of_month(timestamp: datetime.datetime) -> datetime.datetime:
        """
        Return the last day (hour minute and second) of the month of provided datetime
        object.
        """
        year = timestamp.year
        month = timestamp.month
        next_month = timestamp.replace(
            day=1,
            month=month + 1 if month < 12 else 1,
            year=year if month < 12 else year + 1,
            hour=23,
            minute=59,
            second=59,
            microsecond=0,
        )
        return next_month - datetime.timedelta(days=1)

    def yesterday_plus(self) -> list[T]:
        """Return every datetime object in items from yesterday up."""
        yesterday = self.end - datetime.timedelta(hours=24)
        yesterday = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)

        return [item for item in self.items if self.key(item) >= yesterday]

    def one_per_day_last_week(self) -> list[T]:
        """Return one item for every day within the past week."""
        lst: list[T] = []
        last_week = self.end - datetime.timedelta(days=7)
        last_week = last_week.replace(hour=0, minute=0, second=0, microsecond=0)

        for i in range(7):
            day = last_week + datetime.timedelta(days=i)
            end_of_day = day.replace(hour=23, minute=59, second=59)
            day_list = self.filter_range(self.items, day, end_of_day)
            day_list.sort(key=self.key)
            lst.extend(day_list[-1:])

        return lst

    def one_per_week_last_month(self) -> list[T]:
        """
        Return a the subset of items comprising of at most one from each week last
        month. If multiple datetimes fit within the week, use the later.
        """
        lst: list[T] = []
        today = self.end.replace(hour=0, minute=0, second=0, microsecond=0)
        last_month = today - datetime.timedelta(days=31)
        start_of_month = last_month.replace(day=1)
        end_of_month = today.replace(day=1) - datetime.timedelta(days=1)

        start_day = start_of_month
        while start_day <= end_of_month:
            weekday = start_day.weekday()
            try:
                end_of_week = start_day.replace(day=6 - weekday + start_day.day)
            except ValueError:
                end_of_week = end_of_month
            end_of_week = datetime.datetime(
                year=end_of_week.year,
                month=end_of_week.month,
                day=end_of_week.day,
                hour=23,
                minute=59,
                second=59,
            )
            weeks_backups = self.filter_range(self.items, start_day, end_of_week)
            weeks_backups.sort(key=self.key)
            lst.extend(weeks_backups[-1:])
            start_day = start_day + datetime.timedelta(days=7)

        return lst

    def one_per_month_last_year(self) -> list[T]:
        """
        Return a list of which include a maximum of one for each month of the past year.
        If multiple datetimes fit the criteria for a month, use the latest.
        """
        lst: list[T] = []
        last_year = self.end - datetime.timedelta(days=365)
        last_year = last_year.replace(hour=0, minute=0, second=0, microsecond=0)

        timestamp = last_year
        while timestamp <= self.end:
            start_of_month = timestamp.replace(
                month=timestamp.month, day=1, hour=0, minute=0, second=0
            )
            end_of_month = self.last_day_of_month(start_of_month)
            months_dts = self.filter_range(self.items, start_of_month, end_of_month)
            months_dts.sort(key=self.key)
            lst.extend(months_dts[-1:])
            timestamp = end_of_month + datetime.timedelta(seconds=1)

        return lst

    def one_per_year(self) -> list[T]:
        """
        Return a subset consisting of at most one item per year. If multiple items
        satisfy a given year, use the later.
        """
        lst = []
        years = []
        revsort = sorted(self.items, key=self.key, reverse=True)

        for item in revsort:
            year = self.key(item).year
            if year not in years:
                lst.append(item)
                years.append(year)

        return lst

    def past(self) -> list[T]:
        """Return a subset consisting of all items before start time

        If start is None the list is empty
        """
        if self.start is None:
            return []

        return [i for i in self.items if self.key(i) < self.start]
