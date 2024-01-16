"""Template tags for numerical values"""
import datetime as dt
from typing import Any

from django import template
from django.urls import reverse
from django.utils.safestring import mark_safe

from gentoo_build_publisher import views
from gentoo_build_publisher.common import Build, Package
from gentoo_build_publisher.publisher import BuildPublisher
from gentoo_build_publisher.settings import Settings
from gentoo_build_publisher.utils import time

localtime = time.localtime
register = template.Library()


@register.filter(is_safe=False)
def numberize(val: int, precision: int = 2) -> str:
    """Format number, `val` as a string.

    E.g. `1000` is returned as `"1k"` (precision 0), `123000000` as `"1.23M"` (precision
    2) etc.
    """
    if not isinstance(val, int):
        raise template.TemplateSyntaxError(
            f"Value must be an integer. {val!r} is not an integer"
        )

    str_val = str(val)
    num_digits = len(str_val)

    if num_digits >= 10:
        split, suffix = -9, "G"
    elif num_digits >= 7:
        split, suffix = -6, "M"
    elif num_digits > 4:
        split, suffix = -3, "k"
    else:
        return str_val

    dec, frac = str_val[:split], str_val[split:]
    rest = f".{frac[:precision]}" if precision else ""

    return f"{dec}{rest}{suffix}"


@register.filter
def display_time(timestamp: dt.datetime) -> str:
    """Display the timestamp according to how long ago it was"""
    timestamp = localtime(timestamp)
    now = localtime()

    if time.is_same_day(timestamp, now):
        return time.as_time(timestamp)

    if time.is_previous_day(timestamp, now):
        return time.as_date_and_time(timestamp)

    return time.as_date(timestamp)


@register.inclusion_tag("gentoo_build_publisher/circle.html")
def circle(number: int, name: str, color: str) -> dict[str, Any]:
    """Render a circle with a number in it and name below"""
    if number >= 100_000:
        number_display = numberize(number, precision=0)
        number_hover = str(number)
    else:
        number_display = str(number)
        number_hover = ""

    return {
        "color": color,
        "name": name,
        "number": number_hover,
        "number_display": number_display,
    }


@register.inclusion_tag("gentoo_build_publisher/chart.html")
def chart(
    dom_id: str, title: str, *, cols: int = 6, width: int = 500, height: int = 500
) -> dict[str, Any]:
    """Render a chart.js scaffold"""
    return {
        "cols": cols,
        "height": height,
        "id": dom_id,
        "title": title,
        "width": width,
    }


@register.inclusion_tag("gentoo_build_publisher/build_row.html")
def build_row(build: Build, build_packages: dict[str, list[str]]) -> dict[str, Any]:
    """Render a (Jenkins) build row"""
    packages = build_packages.get(str(build), [])
    packages_str = "<br/>".join(packages)
    package_count = len(packages)

    return {"build": build, "packages": packages_str, "package_count": package_count}


@register.inclusion_tag("gentoo_build_publisher/package_row.html")
def package_row(package: str, machines: list[str]) -> dict[str, Any]:
    """Render a package row"""
    machines_str = "<br/>".join(machines)

    return {
        "machine_count": len(machines),
        "machines": machines_str,
        "package": package,
    }


@register.inclusion_tag("gentoo_build_publisher/roundrect.html")
def roundrect(text: str, title: str, color: str) -> dict[str, Any]:
    """Render a circle with a number in it and name below"""
    return {"text": text, "title": title, "color": color}


@register.inclusion_tag("gentoo_build_publisher/machine/build_row.html")
def machine_build_row(build: Build) -> dict[str, Any]:
    """Render a (Jenkins) build row"""
    publisher = BuildPublisher.from_settings(Settings.from_environ())
    packages_built = publisher.storage.get_metadata(build).packages.built
    packages_built_str = "<br/>".join(p.cpv for p in packages_built)

    return {
        "build": build,
        "package_count": len(packages_built),
        "packages_built": packages_built_str,
    }


@register.filter(is_safe=True)
def machine_link(machine: str) -> str:
    """Render machine link (anchor tag)"""
    path = reverse(views.machines, args=(machine,))
    return mark_safe(f'<a class="machine-link" href="{path}">{machine}</a>')


@register.inclusion_tag("gentoo_build_publisher/machine/package_row.html")
def machine_package_row(package: Package) -> dict[str, Any]:
    """Render a package row"""

    return {
        "package": package,
        "build_time": localtime(dt.datetime.fromtimestamp(package.build_time))
    }
