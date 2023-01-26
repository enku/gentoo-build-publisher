"""Django views for Gentoo Build Publisher"""
from __future__ import annotations

from django.conf import settings
from django.core.cache import cache
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import render
from django.utils import timezone

from gentoo_build_publisher.publisher import MachineInfo, get_publisher
from gentoo_build_publisher.types import TAG_SYM, Build
from gentoo_build_publisher.utils import Color
from gentoo_build_publisher.utils.dashboard import create_dashboard_context

GBP_SETTINGS = getattr(settings, "BUILD_PUBLISHER", {})


def dashboard(request: HttpRequest) -> HttpResponse:
    """Dashboard view"""
    color_start = Color(*GBP_SETTINGS.get("COLOR_START", (80, 69, 117)))
    color_end = Color(*GBP_SETTINGS.get("COLOR_END", (221, 218, 236)))
    context = create_dashboard_context(
        timezone.localtime(),
        7,
        timezone.get_current_timezone(),
        (color_start, color_end),
        get_publisher(),
        cache,
    )

    return render(request, "gentoo_build_publisher/dashboard.html", context)


def repos_dot_conf(request: HttpRequest, machine: str) -> HttpResponse:
    """Create a repos.conf entry for the given machine"""
    build, _, dirname = parse_tag_or_raise_404(machine)
    publisher = get_publisher()

    context = {
        "dirname": dirname,
        "hostname": request.headers.get("Host", "localhost").partition(":")[0],
        "repos": publisher.storage.repos(build),
    }
    return render(
        request, "gentoo_build_publisher/repos.conf", context, content_type="text/plain"
    )


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
            build = get_publisher().storage.resolve_tag(machine_tag)
        except (ValueError, FileNotFoundError):
            build = None
    else:
        build = MachineInfo(machine).published_build

    if build is None:
        raise Http404("Published build for that machine does not exist")

    dirname = machine if not tag_name else f"{build.machine}{TAG_SYM}{tag_name}"

    return build, tag_name, dirname
