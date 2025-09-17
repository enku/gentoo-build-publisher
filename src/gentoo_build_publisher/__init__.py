"""Gentoo Build Publisher

GBP is a system which pull Jenkins artifacts and publishes them as "builds" for
different machine configurations (machines). The published builds are made available to
client machines which point to their respective machine configurations.

- The emerge --sync, emerge --update @world cycle installs only binary packages that
  were built specifically for the machine.

- CI/CD pulls repos (portage & overlays) and only starts a build when they have changed.

- The machines' portage configuration (/etc/portage`, repos, world file, etc.) are kept
  in version control and is synced to the machines the same way packages and portage
  tree are.

- Binary packages are built inside of server-less, root-less containers using buildah.

- All builds are not "published" until they are completed and successful.

- Machines sync a build's portage repos via rsync and pull binary packages build from
  the repos via http.

+--------------------+     +-----------+     +--------+       +---------+
| ebuild             |     |           |     |        |       |         |
| repos              | =>  |           |     |        |  =>   |         |
+--------------------+     |  Jenkins  |     |   GBP  | rsync | Gentoo  |
                           |           |  => |        |       | machine |
+--------------------+     |           |     |        |  =>   |         |
| machine definition | =>  |-----------|     |--------| http  |         |
| repo               |     | artifacts |     | builds |       |         |
+--------------------+     +-----------+     +--------+       +---------+
"""

from __future__ import annotations

import importlib
import importlib.metadata
import os
import warnings
from functools import cache
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover
    from gentoo_build_publisher.build_publisher import BuildPublisher

__version__ = importlib.metadata.version("gentoo-build-publisher")


publisher: BuildPublisher

os.environ.setdefault("BUILD_PUBLISHER_JENKINS_BASE_URL", "http://jenkins.invalid/")
os.environ.setdefault("BUILD_PUBLISHER_STORAGE_PATH", "__testing__")


plugin = {
    "name": "gentoo-build-publisher",
    "version": __version__,
    "app": "gentoo_build_publisher.django.gentoo_build_publisher.apps.GentooBuildPublisherConfig",
    "urls": "gentoo_build_publisher.django.gentoo_build_publisher.urls",
    "description": "Gentoo build server, binhost, ebuild repo server, and config manager",
    "graphql": "gentoo_build_publisher.graphql",
    "checks": {
        "build-content": "gentoo_build_publisher.checks:build_content",
        "orphans": "gentoo_build_publisher.checks:orphans",
        "inconsistent_tags": "gentoo_build_publisher.checks:inconsistent_tags",
        "dirty_temp": "gentoo_build_publisher.checks:dirty_temp",
        "corrupt_gbp_json": "gentoo_build_publisher.checks:corrupt_gbp_json",
    },
    "priority": 0,
}


@cache
def __getattr__(name: str) -> Any:
    if name == "publisher":
        build_publisher = importlib.import_module(
            "gentoo_build_publisher.build_publisher"
        )
        settings = importlib.import_module("gentoo_build_publisher.settings")
        return build_publisher.BuildPublisher.from_settings(
            settings.Settings.from_environ()
        )
    if name == "fs":
        warnings.warn(
            "The fs module has moved to utils (gentoo_build_publisher.utils.fs). "
            "Please import it from there.",
            category=DeprecationWarning,
        )
        return importlib.import_module("gentoo_build_publisher.utils.fs")

    raise AttributeError(name)
