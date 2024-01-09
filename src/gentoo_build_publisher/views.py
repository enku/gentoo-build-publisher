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
from django.utils import timezone

from gentoo_build_publisher.common import TAG_SYM, Build
from gentoo_build_publisher.graphql import schema
from gentoo_build_publisher.publisher import BuildPublisher, MachineInfo
from gentoo_build_publisher.utils import Color
from gentoo_build_publisher.utils.views import (
    create_dashboard_context,
    create_machine_context,
)

GBP_SETTINGS = getattr(settings, "BUILD_PUBLISHER", {})
View: TypeAlias = Callable[..., HttpResponse]


def view(pattern: str) -> Callable[[View], View]:
    """Decorator to register a view"""

    def dec(view_func: View) -> View:
        ViewFinder.register(pattern, view_func)
        return view_func

    return dec


class ViewFinder:
    """Django view registry"""

    pattern_views: list[tuple[str, View]] = []

    @classmethod
    def register(cls, pattern: str, view_func: View) -> None:
        """Register the given view for the given pattern"""
        cls.pattern_views.append((pattern, view_func))

    @classmethod
    def find(cls) -> list[URLPattern]:
        """Return a list of url_path/view mappings for the Django url resolver"""
        return [path(pattern, view_func) for pattern, view_func in cls.pattern_views]


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


@view("")
def dashboard(request: HttpRequest) -> HttpResponse:
    """Dashboard view"""
    color_start = Color(*GBP_SETTINGS.get("COLOR_START", (80, 69, 117)))
    color_end = Color(*GBP_SETTINGS.get("COLOR_END", (221, 218, 236)))
    context = create_dashboard_context(
        timezone.localtime(),
        7,
        timezone.get_current_timezone(),
        (color_start, color_end),
        BuildPublisher.get_publisher(),
        cache,
    )

    return render(request, "gentoo_build_publisher/dashboard/main.html", context)


@view("machines/<str:machine>/")
@experimental
def machines(request: HttpRequest, machine: str) -> HttpResponse:
    """Response for the machines page"""
    color_start = Color(*GBP_SETTINGS.get("COLOR_START", (80, 69, 117)))
    color_end = Color(*GBP_SETTINGS.get("COLOR_END", (221, 218, 236)))
    publisher = BuildPublisher.get_publisher()
    context = create_machine_context(machine, color_start, color_end, publisher, cache)

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
