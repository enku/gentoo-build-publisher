"""Django views for Gentoo Build Publisher"""

from __future__ import annotations

from ariadne_django.views import GraphQLView
from django.conf import settings
from django.core.cache import cache
from django.http import Http404, HttpRequest

from gentoo_build_publisher import publisher
from gentoo_build_publisher.graphql import schema
from gentoo_build_publisher.types import TAG_SYM, Build
from gentoo_build_publisher.utils import Color
from gentoo_build_publisher.views.context import (
    MachineInputContext,
    ViewInputContext,
    create_dashboard_context,
    create_machine_context,
)
from gentoo_build_publisher.views.utils import (
    ViewContext,
    get_query_value_from_request,
    render,
    view,
)

GBP_SETTINGS = getattr(settings, "BUILD_PUBLISHER", {})


@view("", name="dashboard")
@render("gentoo_build_publisher/dashboard/main.html")
def dashboard(request: HttpRequest) -> ViewContext:
    """Dashboard view"""
    color_range = color_range_from_settings()
    days = get_query_value_from_request(request, "chart_days", int, 7)
    input_context = ViewInputContext(cache=cache, color_range=color_range, days=days)

    return create_dashboard_context(input_context)


@view("machines/<str:machine>/")
@render("gentoo_build_publisher/machine/main.html")
def machines(request: HttpRequest, machine: str) -> ViewContext:
    """Response for the machines page"""
    if not next(iter(publisher.repo.build_records.for_machine(machine)), None):
        raise Http404("No builds for this machine")

    days = get_query_value_from_request(request, "chart_days", int, 7)
    color_range = color_range_from_settings()
    input_context = MachineInputContext(
        cache=cache, color_range=color_range, days=days, machine=machine
    )
    return create_machine_context(input_context)


@view("machines/<str:machine>/repos.conf")
@render("gentoo_build_publisher/repos.conf", content_type="text/plain")
def repos_dot_conf(request: HttpRequest, machine: str) -> ViewContext:
    """Create a repos.conf entry for the given machine"""
    build, _, dirname = parse_tag_or_raise_404(machine)
    hostname = request.headers.get("Host", "localhost").partition(":")[0]
    repos = publisher.storage.repos(build)

    return {"dirname": dirname, "hostname": hostname, "repos": repos}


@view("machines/<str:machine>/binrepos.conf")
@render("gentoo_build_publisher/binrepos.conf", content_type="text/plain")
def binrepos_dot_conf(request: HttpRequest, machine: str) -> ViewContext:
    """Create a binrepos.conf entry for the given machine"""
    dirname = parse_tag_or_raise_404(machine)[2]
    uri = request.build_absolute_uri(f"/binpkgs/{dirname}/")

    return {"machine": machine, "uri": uri}


view("graphql")(GraphQLView.as_view(schema=schema))


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
        build = publisher.MachineInfo(machine).published_build

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
