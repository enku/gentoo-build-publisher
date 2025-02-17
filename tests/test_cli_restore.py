"""Tests for the cli restore subcommand"""

# pylint: disable=missing-docstring

import io
from pathlib import Path
from typing import Iterable
from unittest import mock

from unittest_fixtures import requires

from gentoo_build_publisher import publisher
from gentoo_build_publisher.cli.restore import handler as restore
from gentoo_build_publisher.types import Build

from . import TestCase
from .factories import BuildFactory
from .helpers import parse_args


@requires("console", "publisher", "tmpdir")
class RestoreTests(TestCase):
    def test_restore_all(self) -> None:
        builds = create_builds()
        first_build = builds[0]
        publisher.publish(first_build)
        last_build = builds[-1]
        publisher.tag(last_build, "last")
        path = self.fixtures.tmpdir / "test.tar"
        dump_builds(builds, path)
        delete_builds(builds)

        path = self.fixtures.tmpdir / "test.tar"
        cmdline = f"gbp restore {path}"

        args = parse_args(cmdline)
        gbp = mock.Mock()
        console = self.fixtures.console

        status = restore(args, gbp, console)

        self.assertEqual(0, status)

        for build in builds:
            self.assertTrue(publisher.storage.pulled(build))
            self.assertTrue(publisher.repo.build_records.exists(build))

        self.assertTrue(publisher.published(first_build))
        self.assertEqual(["last"], publisher.tags(last_build))

    def test_restore_from_stdin(self) -> None:
        builds = create_builds()
        restore_image = io.BytesIO()
        publisher.dump(builds, restore_image)
        delete_builds(builds)
        restore_image.seek(0)

        cmdline = "gbp restore -"

        args = parse_args(cmdline)
        gbp = mock.Mock()
        console = self.fixtures.console

        with mock.patch("gentoo_build_publisher.cli.restore.sys.stdin") as stdin:
            stdin.buffer = restore_image
            status = restore(args, gbp, console)

        self.assertEqual(0, status)

        for build in builds:
            self.assertTrue(publisher.storage.pulled(build))
            self.assertTrue(publisher.repo.build_records.exists(build))

    def test_verbose_flag(self) -> None:
        builds = create_builds()
        builds.sort(key=lambda build: (build.machine, build.build_id))
        restore_image = io.BytesIO()
        publisher.dump(builds, restore_image)
        delete_builds(builds)
        restore_image.seek(0)

        cmdline = "gbp restore -v -"

        args = parse_args(cmdline)
        gbp = mock.Mock()
        console = self.fixtures.console

        with mock.patch("gentoo_build_publisher.cli.restore.sys.stdin") as stdin:
            stdin.buffer = restore_image
            status = restore(args, gbp, console)

        self.assertEqual(0, status)
        expected = (
            "\n".join(f"restoring storage for {build}" for build in builds)
            + "\n"
            + "\n".join(f"restoring records for {build}" for build in builds)
            + "\n"
        )

        self.assertEqual(expected, console.err.file.getvalue())


def create_builds() -> list[Build]:
    builds = [
        *BuildFactory.create_batch(3, machine="nebula"),
        *BuildFactory.create_batch(2, machine="quasar"),
        *BuildFactory.create_batch(1, machine="titanium"),
    ]
    for build in builds:
        publisher.pull(build)

    return builds


def dump_builds(builds: Iterable[Build], path: Path) -> None:
    with path.open("wb") as outfile:
        publisher.dump(builds, outfile)


def delete_builds(builds: Iterable[Build]) -> None:
    for build in builds:
        publisher.delete(build)
