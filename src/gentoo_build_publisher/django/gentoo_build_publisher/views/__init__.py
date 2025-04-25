"""Django views for Gentoo Build Publisher"""

from __future__ import annotations

from ariadne_django.views import GraphQLView
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect

from gentoo_build_publisher import publisher
from gentoo_build_publisher.graphql import schema
from gentoo_build_publisher.types import Build

from . import context as ctx
from . import utils

render = utils.render
view = utils.view
ViewContext = utils.ViewContext


@view("", name="dashboard")
@render("gentoo_build_publisher/dashboard/main.html")
def _(request: HttpRequest) -> ViewContext:
    """Dashboard view"""
    days = utils.get_query_value_from_request(request, "chart_days", int, 7)
    input_context = ctx.ViewInputContext(days=days)

    return ctx.create_dashboard_context(input_context)


@view("machines/<str:machine>/", name="gbp-machines")
@render("gentoo_build_publisher/machine/main.html")
def _(request: HttpRequest, machine: str) -> ViewContext:
    """Response for the machines page"""
    if not next(iter(publisher.repo.build_records.for_machine(machine)), None):
        raise Http404("No builds for this machine")

    days = utils.get_query_value_from_request(request, "chart_days", int, 7)
    input_context = ctx.MachineInputContext(days=days, machine=machine)
    return ctx.create_machine_context(input_context)


@view("about/", name="gbp-about")
@render("gentoo_build_publisher/about/main.html")
def _(request: HttpRequest) -> ViewContext:
    return ctx.create_about_context()


@view(
    "machines/<str:machine>/builds/<str:build_id>/packages/"
    "<str:c>/<str:p>/<str:pv>-<int:b>",
    name="gbp-binpkg",
)
def _(  # pylint: disable=too-many-arguments
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

    url = utils.get_url_for_package(build, package, request)

    return redirect(url, permanent=True)


@view("machines/<str:machine>/repos.conf")
@render("gentoo_build_publisher/repos.conf", content_type="text/plain")
def _(request: HttpRequest, machine: str) -> ViewContext:
    """Create a repos.conf entry for the given machine"""
    build, _, dirname = utils.parse_tag_or_raise_404(machine)
    hostname = request.headers.get("Host", "localhost").partition(":")[0]
    repos = publisher.storage.repos(build)

    return {"dirname": dirname, "hostname": hostname, "repos": repos}


@view("machines/<str:machine>/binrepos.conf")
@render("gentoo_build_publisher/binrepos.conf", content_type="text/plain")
def _(request: HttpRequest, machine: str) -> ViewContext:
    """Create a binrepos.conf entry for the given machine"""
    dirname = utils.parse_tag_or_raise_404(machine)[2]
    uri = request.build_absolute_uri(f"/binpkgs/{dirname}/")

    return {"machine": machine, "uri": uri}


view("graphql")(GraphQLView.as_view(schema=schema))
