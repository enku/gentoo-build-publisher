"""Tests for the views context helpers"""
# pylint: disable=missing-docstring
import datetime as dt
from unittest import mock
from zoneinfo import ZoneInfo

from django.utils import timezone

from gentoo_build_publisher.utils import Color
from gentoo_build_publisher.views.context import (
    ViewInputContext,
    create_dashboard_context,
)

from . import QuickCache, TestCase
from .factories import BuildFactory, BuildRecordFactory


class CreateDashboardContext(TestCase):
    """Tests for create_dashboard_context()"""

    def input_context(self) -> ViewInputContext:
        return ViewInputContext(
            cache=QuickCache(),
            color_range=(Color(255, 0, 0), Color(0, 0, 255)),
            days=2,
            now=timezone.localtime(),
            publisher=self.publisher,
        )

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
            cxt = create_dashboard_context(self.input_context())
        self.assertEqual(cxt["builds_over_time"], [[3, 1], [3, 1]])
        self.assertEqual(len(cxt["built_recently"]), 2)
