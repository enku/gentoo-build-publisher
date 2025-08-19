"""Template tags for numerical values"""

import datetime as dt
from typing import Any

from django import template
from django.urls import reverse
from django.utils.safestring import mark_safe

from gentoo_build_publisher import publisher
from gentoo_build_publisher.records import BuildRecord
from gentoo_build_publisher.types import Build, Package
from gentoo_build_publisher.utils import time

localtime = time.localtime
register = template.Library()


@register.filter(is_safe=False)
def rstrip(val: Any) -> str:
    """Call .rstrip() on (stringified) val and return the result"""
    return str(val).rstrip()


@register.filter(is_safe=False)
def numberize(val: float | int, precision: int | str = 2) -> str:
    """Format number, `val` as a string.

    E.g. `1000` is returned as `"1k"` (precision 0), `123000000` as `"1.23M"` (precision
    2) etc.
    """
    if not isinstance(val, (float, int)):
        raise template.TemplateSyntaxError(
            f"Value must be a float or integer. {val!r} is not"
        )

    if isinstance(precision, str):
        base = {"b": 1024, "d": 1000}[precision[0]]
        precision = int("0" + precision[1:])
    else:
        base = 1000

    if (x := val / base**3) >= 1:
        unit = "G"
    elif (x := val / base**2) >= 1:
        unit = "M"
    elif (x := val / base) >= 1:
        unit = "k"
    else:
        x = val
        unit = ""

    if float(x).is_integer():
        return f"{int(x)}{unit}"

    return f"{x:.{precision}f}{unit}"


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
def build_row(
    build: BuildRecord, build_packages: dict[str, list[str]]
) -> dict[str, Any]:
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
def roundrect(text: str, title: str, color: str, scale: float = 1.0) -> dict[str, Any]:
    """Render a circle with a number in it and name below"""
    return {
        "color": color,
        "font_size": round(scale * 50),
        "height": round(scale * 140),
        "letter_spacing": round(scale * 8),
        "text": text,
        "title": title,
    }


@register.inclusion_tag("gentoo_build_publisher/machine/build_row.html")
def machine_build_row(build: Build) -> dict[str, Any]:
    """Render a (Jenkins) build row"""
    packages_built = publisher.build_metadata(build).packages.built
    packages_built_str = "<br/>".join(p.cpv for p in packages_built)

    return {
        "build": build,
        "package_count": len(packages_built),
        "packages_built": packages_built_str,
    }


@register.filter(is_safe=True)
def machine_link(machine: str) -> str:
    """Render machine link (anchor tag)"""
    path = reverse("gbp-machines", args=(machine,))
    return mark_safe(f'<a class="machine-link" href="{path}">{machine}</a>')


@register.filter(is_safe=True)
def build_link(build: BuildRecord) -> str:
    """Render build link"""
    path = reverse(
        "gbp-builds", kwargs={"machine": build.machine, "build_id": build.build_id}
    )
    text = f'<a class="build-link" href="{path}">{build.build_id}</a>'

    if publisher.published(build):
        text = f"<b>{text}</b>"

    if build.note:
        text = f"{text} 🗒"

    if tags := publisher.tags(build):
        tags = [f"@{tag}" for tag in tags]
        text = f'{text} <span class="tags">{" ".join(tags)}</span>'

    return mark_safe(text)


@register.filter
def build_with_slash(build: Build) -> str:
    """Return build with slash between machine name and build ID"""
    return f"{build.machine}/{build.build_id}"


@register.filter(is_safe=True)
def logs_link(build: Build) -> str:
    """Render the build logs link"""
    path = reverse(
        "gbp-logs", kwargs={"machine": build.machine, "build_id": build.build_id}
    )
    return f'<a class="logs-link" href="{path}"><i class="bi bi-download"></i></a>'


@register.inclusion_tag("gentoo_build_publisher/machine/package_row.html")
def machine_package_row(package: Package) -> dict[str, Any]:
    """Render a package row"""

    return {
        "package": package,
        "build_time": localtime(dt.datetime.fromtimestamp(package.build_time)),
    }


@register.inclusion_tag("gentoo_build_publisher/card_item.html")
def card_item(left: Any, right: Any, pill: bool = False) -> dict[str, Any]:
    """Render a card item"""
    return {"left": left, "right": right, "pill": pill}


@register.filter(is_safe=True)
def build_id(build: BuildRecord) -> str:
    """Simply renders the build's build_id"""
    cls = "build_id published" if publisher.published(build) else "build_id"

    return mark_safe(f'<span class="{cls}">{build.build_id}</span>')
