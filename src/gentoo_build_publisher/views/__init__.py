"""Django views for Gentoo Build Publisher"""
from __future__ import annotations

from functools import wraps
from typing import Any, Callable, TypeAlias

from ariadne_django.views import GraphQLView
from django.conf import settings
from django.core.cache import cache
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import render
from django.urls import URLPattern, path

from gentoo_build_publisher.common import TAG_SYM, Build
from gentoo_build_publisher.graphql import schema
from gentoo_build_publisher.publisher import BuildPublisher, MachineInfo
from gentoo_build_publisher.utils import Color
from gentoo_build_publisher.views.context import (
    MachineInputContext,
    ViewInputContext,
    create_dashboard_context,
    create_machine_context,
)
from gentoo_build_publisher.views.utils import get_query_value_from_request

GBP_SETTINGS = getattr(settings, "BUILD_PUBLISHER", {})
View: TypeAlias = Callable[..., HttpResponse]


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


@view("", name="dashboard")
def dashboard(request: HttpRequest) -> HttpResponse:
    """Dashboard view"""
    input_context = ViewInputContext(
        cache=cache,
        color_range=color_range_from_settings(),
        days=get_query_value_from_request(request, "chart_days", int, 7),
        publisher=BuildPublisher.get_publisher(),
    )
    context = create_dashboard_context(input_context)

    return render(request, "gentoo_build_publisher/dashboard/main.html", context)


@view("machines/<str:machine>/")
@experimental
def machines(request: HttpRequest, machine: str) -> HttpResponse:
    """Response for the machines page"""
    publisher = BuildPublisher.get_publisher()

    if not next(iter(publisher.records.for_machine(machine)), None):
        raise Http404("No builds for this machine")

    input_context = MachineInputContext(
        cache=cache,
        color_range=color_range_from_settings(),
        days=get_query_value_from_request(request, "chart_days", int, 7),
        machine=machine,
        publisher=publisher,
    )
    context = create_machine_context(input_context)

    return render(request, "gentoo_build_publisher/machine/main.html", context)


@view("machines/<str:machine>/repos.conf")
def repos_dot_conf(request: HttpRequest, machine: str) -> HttpResponse:
    """Create a repos.conf entry for the given machine"""
    build, _, dirname = parse_tag_or_raise_404(machine)
    publisher = BuildPublisher.get_publisher()

    context = {
        "dirname": dirname,
        "hostname": request.headers.get("Host", "localhost").partition(":")[0],
        "repos": publisher.storage.repos(build),
    }
    return render(
        request, "gentoo_build_publisher/repos.conf", context, content_type="text/plain"
    )


@view("machines/<str:machine>/binrepos.conf")
def binrepos_dot_conf(request: HttpRequest, machine: str) -> HttpResponse:
    """Create a binrepos.conf entry for the given machine"""
    [*_, dirname] = parse_tag_or_raise_404(machine)

    context = {"uri": request.build_absolute_uri(f"/binpkgs/{dirname}/")}
    return render(
        request,
        "gentoo_build_publisher/binrepos.conf",
        context,
        content_type="text/plain",
    )


graphql = view("graphql")(GraphQLView.as_view(schema=schema))


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
            build = BuildPublisher.get_publisher().storage.resolve_tag(machine_tag)
        except (ValueError, FileNotFoundError):
            build = None
    else:
        build = MachineInfo(machine).published_build

    if build is None:
        raise Http404("Published build for that machine does not exist")

    dirname = machine if not tag_name else f"{build.machine}{TAG_SYM}{tag_name}"

    return build, tag_name, dirname


def color_range_from_settings() -> tuple[Color, Color]:
    """Return a color tuple for gradients and such based on Django settings"""
    return (
        Color(*GBP_SETTINGS.get("COLOR_START", (80, 69, 117))),
        Color(*GBP_SETTINGS.get("COLOR_END", (221, 218, 236))),
    )
