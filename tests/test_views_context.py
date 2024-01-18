"""Tests for the views context helpers"""
# pylint: disable=missing-docstring
import datetime as dt
from typing import Any
from unittest import mock
from zoneinfo import ZoneInfo

from django.utils import timezone

from gentoo_build_publisher.utils import Color
from gentoo_build_publisher.utils.time import SECONDS_PER_DAY, localtime
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
            "publisher": self.publisher,
        }
        defaults |= kwargs
        return ViewInputContext(**defaults)

    def test(self) -> None:
        publisher = self.publisher
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
        cxt = create_dashboard_context(input_context)
        self.assertEqual(len(cxt["chart_days"]), 2)
        self.assertEqual(cxt["build_count"], 4)
        self.assertEqual(
            cxt["build_packages"],
            {
                str(lighthouse1): [
                    "app-portage/gentoolkit-0.5.1-r1",
                    "dev-vcs/git-2.34.1",
                ],
                str(polaris2): [],
            },
        )
        self.assertEqual(cxt["gradient_colors"], ["#ff0000", "#0000ff"])
        self.assertEqual(cxt["builds_per_machine"], [3, 1])
        self.assertEqual(cxt["machines"], ["polaris", "lighthouse"])
        self.assertEqual(cxt["now"], input_context.now)
        self.assertEqual(cxt["package_count"], 14)
        self.assertEqual(cxt["unpublished_builds_count"], 2)
        self.assertEqual(
            cxt["total_package_size_per_machine"], {"lighthouse": 3238, "polaris": 3906}
        )
        self.assertEqual(
            cxt["recent_packages"],
            {
                "app-portage/gentoolkit-0.5.1-r1": {"lighthouse"},
                "dev-vcs/git-2.34.1": {"lighthouse"},
            },
        )

    def test_not_completed(self) -> None:
        publisher = self.publisher

        publisher.pull(BuildFactory())
        build = BuildFactory()
        record = publisher.record(build).save(publisher.records, completed=None)

        cxt = create_dashboard_context(self.input_context())
        self.assertEqual(cxt["builds_not_completed"], [record])

    def test_latest_published(self) -> None:
        babette = BuildFactory(machine="babette")
        self.publisher.publish(babette)
        self.publisher.pull(BuildFactory(machine="lighthouse"))
        self.publisher.pull(BuildFactory(machine="polaris"))

        cxt = create_dashboard_context(self.input_context())
        self.assertEqual(cxt["latest_published"], set([self.publisher.record(babette)]))
        self.assertEqual(cxt["unpublished_builds_count"], 2)

    def test_builds_over_time_and_build_recently(self) -> None:
        now = dt.datetime(2024, 1, 17, 4, 51, tzinfo=dt.timezone.utc)
        for machine in ["babette", "lighthouse"]:
            for day in range(2):
                for _ in range(3):
                    build = BuildFactory(machine=machine)
                    record = self.publisher.record(build)
                    record = record.save(
                        self.publisher.records, submitted=now - dt.timedelta(days=day)
                    )
                    self.publisher.pull(record)
                    if day == 0:
                        break

        localtimezone = "gentoo_build_publisher.utils.time.LOCAL_TIMEZONE"
        with mock.patch(localtimezone, new=ZoneInfo("America/Chicago")):
            cxt = create_dashboard_context(self.input_context(now=localtime(now)))
        self.assertEqual(cxt["builds_over_time"], [[3, 1], [3, 1]])
        self.assertEqual(len(cxt["built_recently"]), 2)


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
            "publisher": self.publisher,
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
            self.publisher.pull(build)

        now = localtime(dt.datetime.fromtimestamp(self.artifact_builder.timer))
        input_context = self.input_context(now=now, machine=build.machine)
        cxt = create_machine_context(input_context)

        self.assertEqual(cxt["average_storage"], total_size / 3)

    def test_packages_built_today(self) -> None:
        for day in [1, 1, 1, 0]:
            self.artifact_builder.advance(day * SECONDS_PER_DAY)
            build = BuildFactory()
            for _ in range(3):
                cpv = next(self.pf)
                self.artifact_builder.build(build, cpv)
            self.publisher.pull(build)

        now = localtime(dt.datetime.fromtimestamp(self.artifact_builder.timer))
        input_context = self.input_context(now=now, machine=build.machine)
        cxt = create_machine_context(input_context)

        self.assertEqual(len(cxt["packages_built_today"]), 6)
