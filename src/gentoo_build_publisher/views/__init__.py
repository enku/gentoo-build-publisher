"""Django views for Gentoo Build Publisher"""

from __future__ import annotations

from ariadne_django.views import GraphQLView
from django.core.cache import cache
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect

from gentoo_build_publisher import publisher
from gentoo_build_publisher.graphql import schema
from gentoo_build_publisher.types import Build
from gentoo_build_publisher.views.context import (
    MachineInputContext,
    ViewInputContext,
    create_dashboard_context,
    create_machine_context,
)
from gentoo_build_publisher.views.utils import (
    ViewContext,
    color_range_from_settings,
    get_query_value_from_request,
    get_url_for_package,
    parse_tag_or_raise_404,
    render,
    view,
)


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


@view(
    "machines/<str:machine>/builds/<str:build_id>/packages/"
    "<str:c>/<str:p>/<str:pv>-<int:b>"
)
def binpkg(  # pylint: disable=too-many-arguments
    request: HttpRequest,
    *,
    machine: str,
    build_id: str,
    c: str,
    p: str,
    pv: str,
    b: int,
) -> HttpResponse:
    """Redirect to the URL of the given build's given package"""
    build = Build(machine=machine, build_id=build_id)
    storage = publisher.storage

    try:
        packages = storage.get_packages(build)
    except LookupError as error:
        raise Http404 from error

    cpv = f"{c}/{pv}"
    try:
        # This is wonky. We need to create an API for this
        [package] = [p for p in packages if p.cpv == cpv and p.build_id == b]
    except ValueError as error:
        raise Http404 from error

    url = get_url_for_package(build, package, request)

    return redirect(url, permanent=True)


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
