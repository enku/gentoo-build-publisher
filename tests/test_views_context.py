"""Tests for the views context helpers"""
# pylint: disable=missing-docstring
import datetime as dt
from typing import Any
from unittest import mock
from zoneinfo import ZoneInfo

from django.utils import timezone

from gentoo_build_publisher import publisher
from gentoo_build_publisher.utils import Color
from gentoo_build_publisher.utils.time import SECONDS_PER_DAY, localtime, utctime
from gentoo_build_publisher.views.context import (
    MachineInputContext,
    ViewInputContext,
    create_dashboard_context,
    create_machine_context,
)

from . import QuickCache, TestCase
from .factories import (
    ArtifactFactory,
    BuildFactory,
    BuildRecordFactory,
    package_factory,
)


class CreateDashboardContextTests(TestCase):
    """Tests for create_dashboard_context()"""

    def input_context(self, **kwargs: Any) -> ViewInputContext:
        defaults: dict[str, Any] = {
            "cache": QuickCache(),
            "color_range": (Color(255, 0, 0), Color(0, 0, 255)),
            "days": 2,
            "now": timezone.localtime(),
        }
        defaults |= kwargs
        return ViewInputContext(**defaults)

    def test(self) -> None:
        lighthouse1 = BuildFactory(machine="lighthouse")
        for cpv in ["dev-vcs/git-2.34.1", "app-portage/gentoolkit-0.5.1-r1"]:
            self.artifact_builder.build(lighthouse1, cpv)
        publisher.pull(lighthouse1)

        polaris1 = BuildFactory(machine="polaris")
        publisher.publish(polaris1)
        polaris2 = BuildFactory(machine="polaris")
        publisher.pull(polaris2)

        polaris3 = BuildRecordFactory(machine="polaris")
        publisher.records.save(polaris3)

        input_context = self.input_context()
        ctx = create_dashboard_context(input_context)
        self.assertEqual(len(ctx["chart_days"]), 2)
        self.assertEqual(ctx["build_count"], 4)
        self.assertEqual(
            ctx["build_packages"],
            {
                str(lighthouse1): [
                    "app-portage/gentoolkit-0.5.1-r1",
                    "dev-vcs/git-2.34.1",
                ],
                str(polaris2): [],
            },
        )
        self.assertEqual(ctx["gradient_colors"], ["#ff0000", "#0000ff"])
        self.assertEqual(ctx["builds_per_machine"], [3, 1])
        self.assertEqual(ctx["machines"], ["polaris", "lighthouse"])
        self.assertEqual(ctx["now"], input_context.now)
        self.assertEqual(ctx["package_count"], 14)
        self.assertEqual(ctx["unpublished_builds_count"], 2)
        self.assertEqual(
            ctx["total_package_size_per_machine"], {"lighthouse": 3238, "polaris": 3906}
        )
        self.assertEqual(
            ctx["recent_packages"],
            {
                "app-portage/gentoolkit-0.5.1-r1": {"lighthouse"},
                "dev-vcs/git-2.34.1": {"lighthouse"},
            },
        )

    def test_not_completed(self) -> None:
        publisher.pull(BuildFactory())
        build = BuildFactory()
        record = publisher.record(build).save(publisher.records, completed=None)

        ctx = create_dashboard_context(self.input_context())
        self.assertEqual(ctx["builds_not_completed"], [record])

    def test_latest_published(self) -> None:
        babette = BuildFactory(machine="babette")
        publisher.publish(babette)
        publisher.pull(BuildFactory(machine="lighthouse"))
        publisher.pull(BuildFactory(machine="polaris"))

        ctx = create_dashboard_context(self.input_context())
        self.assertEqual(ctx["latest_published"], set([publisher.record(babette)]))
        self.assertEqual(ctx["unpublished_builds_count"], 2)

    def test_builds_over_time_and_build_recently(self) -> None:
        now = dt.datetime(2024, 1, 17, 4, 51, tzinfo=dt.timezone.utc)
        for machine in ["babette", "lighthouse"]:
            for day in range(2):
                for _ in range(3):
                    build = BuildFactory(machine=machine)
                    record = publisher.record(build)
                    record = record.save(
                        publisher.records, submitted=now - dt.timedelta(days=day)
                    )
                    publisher.pull(record)
                    if day == 0:
                        break

        localtimezone = "gentoo_build_publisher.utils.time.LOCAL_TIMEZONE"
        with mock.patch(localtimezone, new=ZoneInfo("America/Chicago")):
            ctx = create_dashboard_context(self.input_context(now=localtime(now)))
        self.assertEqual(ctx["builds_over_time"], [[3, 1], [3, 1]])
        self.assertEqual(len(ctx["built_recently"]), 2)


class CreateMachineContextTests(TestCase):
    def setUp(self) -> None:
        super().setUp()

        self.pf = package_factory()
        ab: ArtifactFactory = self.artifact_builder
        ab.initial_packages = []
        ab.timer = int(localtime(dt.datetime(2024, 1, 16)).timestamp())

    def input_context(self, **kwargs: Any) -> MachineInputContext:
        defaults: dict[str, Any] = {
            "cache": QuickCache(),
            "color_range": (Color(255, 0, 0), Color(0, 0, 255)),
            "days": 2,
            "now": timezone.localtime(),
        }
        defaults |= kwargs
        return MachineInputContext(**defaults)

    def test_average_storage(self) -> None:
        total_size = 0
        build_size = 0

        for _ in range(3):
            self.artifact_builder.advance(3600)
            build = BuildFactory()
            for _pkgs in range(3):
                cpv = next(self.pf)
                pkg = self.artifact_builder.build(build, cpv)
                build_size += pkg.size
            total_size += build_size
            publisher.pull(build)

        now = localtime(dt.datetime.fromtimestamp(self.artifact_builder.timer))
        input_context = self.input_context(now=now, machine=build.machine)
        ctx = create_machine_context(input_context)

        self.assertEqual(ctx["average_storage"], total_size / 3)

    def test_packages_built_today(self) -> None:
        for day in [1, 1, 1, 0]:
            self.artifact_builder.advance(day * SECONDS_PER_DAY)
            build = BuildFactory()
            for _ in range(3):
                cpv = next(self.pf)
                self.artifact_builder.build(build, cpv)
            publisher.pull(build)

        now = localtime(dt.datetime.fromtimestamp(self.artifact_builder.timer))
        input_context = self.input_context(now=now, machine=build.machine)
        ctx = create_machine_context(input_context)

        self.assertEqual(len(ctx["packages_built_today"]), 6)

    def test_packages_built_today_when_build_built_is_none(self) -> None:
        built = utctime(dt.datetime(2021, 4, 25, 7, 50, 7))
        submitted = utctime(dt.datetime(2021, 4, 25, 7, 56, 2))
        completed = utctime(dt.datetime(2021, 4, 25, 7, 56, 36))
        build = BuildFactory()

        cpv = "dev-build/autoconf-2.71-r6"
        self.artifact_builder.timer = int(built.timestamp())
        self.artifact_builder.build(build, cpv)
        publisher.pull(build)
        record = publisher.record(build)

        # In 2021 GBP didn't have a built field and in the database. They were
        # back-filled to NULL
        record = record.save(
            publisher.records,
            built=None,
            submitted=submitted,
            completed=completed,
        )
        now = localtime(dt.datetime(2024, 1, 19, 7, 38))
        input_context = self.input_context(now=now, machine=build.machine)
        ctx = create_machine_context(input_context)

        self.assertEqual(len(ctx["packages_built_today"]), 0)
