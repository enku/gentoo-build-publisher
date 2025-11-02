"""Functions/data to support the dashboard view"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, fields, is_dataclass
from functools import wraps
from typing import Any, Callable, Mapping, Protocol

from django.conf import settings
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import render as _render
from django.urls import URLPattern, path

from gentoo_build_publisher import publisher
from gentoo_build_publisher.machines import MachineInfo
from gentoo_build_publisher.records import BuildRecord, RecordNotFound
from gentoo_build_publisher.types import TAG_SYM, Build, Package
from gentoo_build_publisher.utils import Color


@dataclass(frozen=True)
class TemplateContext(Protocol):  # pylint: disable=too-few-public-methods
    """Any of the context dataclasses defined in .context"""


type BuildID = str  # pylint: disable=invalid-name
type CPV = str  # pylint: disable=invalid-name
type Gradient = list[str]
type MachineName = str
type View = Callable[..., HttpResponse]
type TemplateView[T: TemplateContext | Mapping[str, Any]] = Callable[..., T]


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
) -> Callable[[TemplateView[Any]], View]:
    """Instruct a view to render the given template

    The view should return a dataclass
    """

    def dec(view_func: TemplateView[Any]) -> View:
        @wraps(view_func)
        def wrapper(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
            value = view_func(request, *args, **kwargs)
            context = (
                {f.name: getattr(value, f.name) for f in fields(value)}
                if is_dataclass(value)
                else value  # backwards compat
            )
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


def days_strings(start: dt.datetime, days: int) -> list[str]:
    """Return list of datetimes from start as strings"""
    fmt = "%A" if days <= 7 else "%x"
    return [datetime.strftime(fmt) for datetime in get_chart_days(start, days)]


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


def request_to_wsgi_environ(request: HttpRequest) -> dict[str, Any]:
    """Convert the given Django request to a WSGI environ"""
    updates = {
        "PATH_INFO": request.path,
        "wsgi.input": request,
        "wsgi.method": request.method,
        "wsgi.url_scheme": request.scheme,
        "SERVER_NAME": request.get_host(),
        "SERVER_PORT": request.get_port(),
    }
    return {**request.META, **updates}


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
    build: Build | None = None
    machine, _, tag_name = machine_tag.partition(TAG_SYM)

    if tag_name:
        try:
            build = publisher.resolve_tag(machine_tag)
        except ValueError:
            pass
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
