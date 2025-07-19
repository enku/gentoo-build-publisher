"""Functions/data to support the dashboard view"""

from __future__ import annotations

import datetime as dt
from functools import lru_cache, wraps
from typing import Any, Callable, Mapping, TypeAlias

from django.conf import settings
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import render as _render
from django.urls import URLPattern, path

from gentoo_build_publisher import publisher
from gentoo_build_publisher.machines import MachineInfo
from gentoo_build_publisher.records import BuildRecord, RecordNotFound
from gentoo_build_publisher.types import (
    TAG_SYM,
    Build,
    CacheProtocol,
    GBPMetadata,
    Package,
)
from gentoo_build_publisher.utils import Color
from gentoo_build_publisher.utils.time import SECONDS_PER_DAY, lapsed, localtime

BuildID: TypeAlias = str  # pylint: disable=invalid-name
CPV: TypeAlias = str  # pylint: disable=invalid-name
Gradient: TypeAlias = list[str]
MachineName: TypeAlias = str
View: TypeAlias = Callable[..., HttpResponse]
ViewContext: TypeAlias = Mapping[str, Any]
TemplateView: TypeAlias = Callable[..., ViewContext]


_NOT_FOUND = object()
GBP_SETTINGS = getattr(settings, "BUILD_PUBLISHER", {})


def view(pattern: str, **kwargs: Any) -> Callable[[View], View]:
    """Decorator to register a view"""

    def dec(view_func: View) -> View:
        ViewFinder.register(pattern, view_func, **kwargs)
        return view_func

    return dec


class ViewFinder:
    """Django view registry"""

    pattern_views: list[URLPattern] = []

    @classmethod
    def register(cls, pattern: str, view_func: View, **kwargs: Any) -> None:
        """Register the given view for the given pattern"""
        cls.pattern_views.append(path(pattern, view_func, **kwargs))

    @classmethod
    def find(cls) -> list[URLPattern]:
        """Return a list of url_path/view mappings for the Django url resolver"""
        return cls.pattern_views


def render(
    template_name: str, content_type: str | None = None
) -> Callable[[TemplateView], View]:
    """Instruct a view to render the given template

    The view should return a context mapping
    """

    def dec(view_func: TemplateView) -> View:
        @wraps(view_func)
        def wrapper(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
            context = view_func(request, *args, **kwargs)
            return _render(request, template_name, context, content_type=content_type)

        return wrapper

    return dec


def experimental(view_func: View) -> View:
    """Mark a view as experimental

    Experimental views return 404s when not in DEBUG mode.
    """

    @wraps(view_func)
    def wrapper(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        if not settings.DEBUG:
            raise Http404
        return view_func(request, *args, **kwargs)

    return wrapper


class StatsCollector:
    """Interface to collect statistics about the Publisher"""

    def __init__(self, cache: CacheProtocol) -> None:
        self.cache = cache

    @lru_cache
    def machine_info(self, machine: MachineName) -> MachineInfo:
        """Return the MachineInfo object for the given machine"""
        return MachineInfo(machine)

    @property
    @lru_cache
    def machines(self) -> list[MachineName]:
        """Returns a list of machines with builds

        Machines are ordered by build count (descending), then machine name (ascending)
        """
        return sorted(
            (m.machine for m in publisher.machines()),
            key=lambda m: (-1 * self.machine_info(m).build_count, m),
        )

    @lru_cache
    def package_count(self, machine: MachineName) -> int:
        """Return the total number of completed builds for the given machine"""
        total = 0

        for build in self.machine_info(machine).builds:
            metadata = get_metadata(build, self.cache)
            if metadata and build.completed:
                total += metadata.packages.total

        return total

    def build_packages(self, build: Build) -> list[str]:
        """Return a list of CPVs build in the given build"""
        metadata = get_metadata(build, self.cache)
        return [i.cpv for i in metadata.packages.built] if metadata is not None else []

    def latest_build(self, machine: MachineName) -> BuildRecord | None:
        """Return the latest build for the given machine

        If the Machine has no builds, return None.
        """
        return self.machine_info(machine).latest_build

    def latest_published(self, machine: MachineName) -> BuildRecord | None:
        """Return the latest build for the given machine if that build is published

        Otherwise return None.
        """
        if latest := self.latest_build(machine):
            if published := self.machine_info(machine).published_build:
                if latest == publisher.record(published):
                    return latest
        return None

    def recent_packages(self, machine: MachineName, maximum: int = 10) -> list[Package]:
        """Return the list of recent packages for a machine (up to maximum)"""
        packages: set[Package] = set()

        for build in self.machine_info(machine).builds:
            if not (metadata := get_metadata(build, self.cache)):
                continue
            packages.update(metadata.packages.built)
            if len(packages) >= maximum:
                break

        return sorted(packages, key=lambda p: p.build_time, reverse=True)[:maximum]

    def total_package_size(self, machine: MachineName) -> int:
        """Return the total size (bytes) of all packages in all builds for machine"""
        total = 0

        for record in self.machine_info(machine).builds:
            if record.completed and (metadata := get_metadata(record, self.cache)):
                total += metadata.packages.size

        return total

    def built_recently(self, build: BuildRecord, now: dt.datetime) -> bool:
        """Return True if the given build was built within 24 hours of the given time"""
        return False if not build.built else lapsed(build.built, now) < SECONDS_PER_DAY

    def builds_by_day(self, machine: MachineName) -> dict[dt.date, int]:
        """Return a dict of count of builds by day for the given machine"""
        bbd: dict[dt.date, int] = {}

        for build in self.machine_info(machine).builds:
            assert build.submitted
            date = localtime(build.submitted).date()
            bbd[date] = bbd.setdefault(date, 0) + 1

        return bbd

    def packages_by_day(self, machine: MachineName) -> dict[dt.date, list[Package]]:
        """Return dict of machine's packages distributed by build date"""
        pbd: dict[dt.date, set[Package]] = {}

        for build in filter(
            lambda b: b.built and b.submitted, self.machine_info(machine).builds
        ):
            date = localtime(build.built).date()

            try:
                metadata = publisher.storage.get_metadata(build)
            except LookupError:
                continue

            pbd.setdefault(date, set()).update(metadata.packages.built)

        return {date: list(packages) for date, packages in pbd.items()}


def days_strings(start: dt.datetime, days: int) -> list[str]:
    """Return list of datetimes from start as strings"""
    fmt = "%A" if days <= 7 else "%x"
    return [datetime.strftime(fmt) for datetime in get_chart_days(start, days)]


def get_metadata(build: Build, cache: CacheProtocol) -> GBPMetadata | None:
    """Return the GBPMetadata for a package.

    This call may be cashed for performance.
    """
    cache_key = f"metadata-{build}"

    if (cached := cache.get(cache_key, _NOT_FOUND)) is _NOT_FOUND:
        try:
            metadata = publisher.storage.get_metadata(build)
        except LookupError:
            return None

        cache.set(cache_key, metadata)

        return metadata

    metadata = cached
    return metadata


def gradient_colors(start: Color, stop: Color, size: int) -> list[str]:
    """Return a list of size color strings (#rrggbb) as a gradient from start to stop"""
    return gradient(start, stop, size)


def gradient(start: Color, end: Color, count: int) -> Gradient:
    """Return gradient from start to end with count colors"""
    return [str(color) for color in Color.gradient(start, end, count)]


def get_chart_days(start: dt.datetime, days: int) -> list[dt.date]:
    """Return initial chart data (all 0s for the given start date and days"""
    return [start.date() - dt.timedelta(days=d) for d in range(days - 1, -1, -1)]


def get_query_value_from_request(
    request: HttpRequest, key: str, type_: type, fallback: Any
) -> Any:
    """Return given query value from the query params"""
    if (query_value := request.GET.get(key, _NOT_FOUND)) == _NOT_FOUND:
        return fallback
    try:
        return type_(query_value)
    except ValueError:
        return fallback


def get_build_record_or_404(machine: str, build_id: str) -> BuildRecord:
    """Return the BuildRecord given the machine and build_id

    If no such record exists, raise Http404.
    """
    repo = publisher.repo
    records = repo.build_records

    try:
        return records.get(Build(machine=machine, build_id=build_id))
    except RecordNotFound:
        raise Http404 from None


def parse_tag_or_raise_404(machine_tag: str) -> tuple[Build, str, str]:
    """Return the build, tag name and dirname given the MACHINE[@TAG] string

    dirname is the name of the symlink in storage (not the full path)
    If it's not a tagged name, the tag_name will be the empty string.
    If the actual target does not exist, raise Http404
    """
    build: Build | None
    machine, _, tag_name = machine_tag.partition(TAG_SYM)

    if tag_name:
        try:
            build = publisher.storage.resolve_tag(machine_tag)
        except (ValueError, FileNotFoundError):
            build = None
    else:
        build = MachineInfo(machine).published_build

    if build is None:
        raise Http404("Published build for that machine does not exist")

    dirname = machine if not tag_name else f"{build.machine}{TAG_SYM}{tag_name}"

    return build, tag_name, dirname


def get_url_for_package(build: Build, package: Package, request: HttpRequest) -> str:
    """Return the URL for the given Package"""
    return request.build_absolute_uri(f"/binpkgs/{build}/{package.path}")


def color_range_from_settings() -> tuple[Color, Color]:
    """Return a color tuple for gradients and such based on Django settings"""
    return (
        Color(*GBP_SETTINGS.get("COLOR_START", (80, 69, 117))),
        Color(*GBP_SETTINGS.get("COLOR_END", (221, 218, 236))),
    )
