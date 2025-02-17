"""Tests for the GBP publisher"""

# pylint: disable=missing-docstring
import datetime as dt
import io
import json
import tarfile as tar
from unittest import mock
from zoneinfo import ZoneInfo

from unittest_fixtures import (
    BaseTestCase,
    FixtureContext,
    FixtureOptions,
    Fixtures,
    requires,
)
from yarl import URL

from gentoo_build_publisher import publisher as gbp
from gentoo_build_publisher.build_publisher import BuildPublisher
from gentoo_build_publisher.records.memory import RecordDB
from gentoo_build_publisher.settings import Settings
from gentoo_build_publisher.signals import dispatcher
from gentoo_build_publisher.types import Build, Content, GBPMetadata, Package
from gentoo_build_publisher.utils.time import utctime

from . import TestCase
from .factories import BuildFactory, BuildRecordFactory
from .helpers import BUILD_LOGS


@requires("tmpdir")
class BuildPublisherFromSettingsTestCase(BaseTestCase):
    def test_from_settings_returns_publisher_with_given_settings(self) -> None:
        settings = Settings(
            JENKINS_BASE_URL="https://testserver.invalid/",
            RECORDS_BACKEND="memory",
            STORAGE_PATH=self.fixtures.tmpdir / "test_from_settings",
        )
        pub = BuildPublisher.from_settings(settings)

        self.assertEqual(
            pub.jenkins.config.base_url, URL("https://testserver.invalid/")
        )
        self.assertEqual(pub.storage.root, self.fixtures.tmpdir / "test_from_settings")
        self.assertIsInstance(pub.repo.build_records, RecordDB)


@requires("build", "publisher")
class BuildPublisherTestCase(TestCase):  # pylint: disable=too-many-public-methods
    def test_publish(self) -> None:
        """.publish should publish the build artifact"""
        fixtures = self.fixtures
        publisher = fixtures.publisher

        publisher.publish(fixtures.build)

        self.assertIs(publisher.storage.published(fixtures.build), True)

    def test_pull_without_db(self) -> None:
        """pull creates db record and pulls from jenkins"""
        fixtures = self.fixtures
        publisher = fixtures.publisher

        publisher.pull(fixtures.build)

        self.assertIs(publisher.storage.pulled(fixtures.build), True)
        self.assertIs(publisher.repo.build_records.exists(fixtures.build), True)

    def test_pull_stores_build_logs(self) -> None:
        """Should store the logs of the build"""
        fixtures = self.fixtures
        publisher = fixtures.publisher
        publisher.pull(fixtures.build)

        url = str(publisher.jenkins.url.logs(fixtures.build))
        publisher.jenkins.get_build_logs_mock_get.assert_called_once_with(url)

        record = publisher.record(fixtures.build)
        self.assertEqual(record.logs, BUILD_LOGS)

    def test_pull_updates_build_models_completed_field(self) -> None:
        """Should update the completed field with the current timestamp"""
        fixtures = self.fixtures
        publisher = fixtures.publisher
        now = utctime()

        with mock.patch("gentoo_build_publisher.build_publisher.utctime") as mock_now:
            mock_now.return_value = now
            publisher.pull(fixtures.build)

        record = publisher.record(fixtures.build)
        self.assertEqual(record.completed, now)

    def test_pull_updates_build_models_built_field(self) -> None:
        fixtures = self.fixtures
        publisher = fixtures.publisher
        build = fixtures.build

        publisher.pull(build)

        record = publisher.record(build)

        jenkins_timestamp = dt.datetime.utcfromtimestamp(
            publisher.jenkins.artifact_builder.build_info(build).build_time / 1000
        ).replace(tzinfo=dt.UTC)
        self.assertEqual(record.built, jenkins_timestamp)

    def test_pull_does_not_download_when_already_pulled(self) -> None:
        fixtures = self.fixtures
        build = fixtures.build

        self.fixtures.publisher.pull(build)
        assert self.fixtures.publisher.pulled(build)

        pulled = self.fixtures.publisher.pull(build)

        self.assertFalse(pulled)

    def test_pulled_when_storage_is_ok_but_db_is_not(self) -> None:
        # On rare occasion (server crash) the build appears to be extracted but the
        # record.completed field is None.  In this case Publisher.pulled(build) should
        # be False
        fixtures = self.fixtures
        publisher = fixtures.publisher
        build = fixtures.build

        with mock.patch.object(
            publisher, "_update_build_metadata"
        ) as update_build_metadata:
            # _update_build_metadata sets the completed attribute
            update_build_metadata.return_value = None, None, None  # dummy values
            publisher.pull(build)

        self.assertFalse(publisher.pulled(build))

    def test_build_timestamps(self) -> None:
        fixtures = self.fixtures
        publisher = fixtures.publisher
        datetime = dt.datetime
        localtimezone = "gentoo_build_publisher.utils.time.LOCAL_TIMEZONE"

        with mock.patch(localtimezone, new=ZoneInfo("America/New_York")):
            submitted = datetime(2024, 1, 19, 11, 5, 49, tzinfo=dt.UTC)
            now = "gentoo_build_publisher.utils.time.now"
            with mock.patch(now, return_value=submitted):
                publisher.jenkins.artifact_builder.timer = (
                    1705662194  # 2024-01-19 11:03 UTC
                )
                build = BuildFactory()
                publisher.pull(build)
                record = publisher.record(build)

        ct = ZoneInfo("America/Chicago")
        self.assertEqual(record.built, datetime(2024, 1, 19, 5, 3, 24, tzinfo=ct))
        self.assertEqual(record.submitted, datetime(2024, 1, 19, 5, 5, 49, tzinfo=ct))
        self.assertEqual(record.completed, datetime(2024, 1, 19, 5, 5, 49, tzinfo=ct))

    def test_pull_with_note(self) -> None:
        fixtures = self.fixtures
        publisher = fixtures.publisher

        publisher.pull(fixtures.build, note="This is a test")

        self.assertIs(publisher.storage.pulled(fixtures.build), True)
        build_record = publisher.record(fixtures.build)
        self.assertEqual(build_record.note, "This is a test")

    def test_pull_with_tags(self) -> None:
        fixtures = self.fixtures
        publisher = fixtures.publisher
        build = fixtures.build
        tags = {"this", "is", "a", "test"}

        publisher.pull(build, tags=tags)

        self.assertIs(publisher.storage.pulled(build), True)
        self.assertEqual(set(publisher.tags(build)), tags)

    def test_purge_deletes_old_build(self) -> None:
        """Should remove purgeable builds"""
        fixtures = self.fixtures
        publisher = fixtures.publisher
        old_build = fixtures.build
        publisher.pull(old_build)
        record = publisher.record(old_build)
        publisher.repo.build_records.save(
            record, submitted=dt.datetime(1970, 1, 1, tzinfo=dt.UTC)
        )

        new_build = BuildFactory()
        publisher.pull(new_build)
        record = publisher.record(new_build)
        publisher.repo.build_records.save(
            record, submitted=dt.datetime(1970, 12, 31, tzinfo=dt.UTC)
        )

        publisher.purge(old_build.machine)

        self.assertIs(publisher.repo.build_records.exists(old_build), False)

        for item in Content:
            path = publisher.storage.get_path(old_build, item)
            self.assertIs(path.exists(), False, path)

    def test_purge_does_not_delete_old_tagged_builds(self) -> None:
        """Should remove purgeable builds"""

        fixtures = self.fixtures
        publisher = fixtures.publisher
        repo = publisher.repo
        datetime = dt.datetime
        kept_build = BuildFactory(machine="lighthouse")
        repo.build_records.save(
            publisher.record(kept_build),
            submitted=datetime(1970, 1, 1, tzinfo=dt.UTC),
            keep=True,
        )
        tagged_build = BuildFactory(machine="lighthouse")
        repo.build_records.save(
            publisher.record(tagged_build),
            submitted=datetime(1970, 1, 1, tzinfo=dt.UTC),
        )
        publisher.pull(tagged_build)
        publisher.tag(tagged_build, "prod")
        repo.build_records.save(
            publisher.record(BuildFactory(machine="lighthouse")),
            submitted=datetime(1970, 12, 31, tzinfo=dt.UTC),
        )

        publisher.purge("lighthouse")

        self.assertIs(repo.build_records.exists(kept_build), True)
        self.assertIs(repo.build_records.exists(tagged_build), True)

    def test_purge_doesnt_delete_old_published_build(self) -> None:
        """Should not delete old build if published"""
        fixtures = self.fixtures
        publisher = fixtures.publisher
        build = fixtures.build
        repo = publisher.repo

        publisher.publish(build)
        repo.build_records.save(
            publisher.record(build), submitted=dt.datetime(1970, 1, 1, tzinfo=dt.UTC)
        )
        repo.build_records.save(
            publisher.record(BuildFactory()),
            submitted=dt.datetime(1970, 12, 31, tzinfo=dt.UTC),
        )

        publisher.purge(build.machine)

        self.assertIs(repo.build_records.exists(build), True)

    def test_update_build_metadata(self) -> None:
        # pylint: disable=protected-access
        fixtures = self.fixtures
        publisher = fixtures.publisher
        record = publisher.record(fixtures.build)

        publisher._update_build_metadata(record)

        record = publisher.record(fixtures.build)
        self.assertEqual(record.logs, BUILD_LOGS)
        self.assertIsNot(record.completed, None)

    def test_diff_binpkgs_should_be_empty_if_left_and_right_are_equal(self) -> None:
        fixtures = self.fixtures
        left = fixtures.build
        publisher = fixtures.publisher
        publisher.get_packages = mock.Mock(wraps=publisher.get_packages)
        right = left

        # This should actually fail if not short-circuited because the builds have not
        # been pulled
        diff = [*gbp.diff_binpkgs(left, right)]

        self.assertEqual(diff, [])
        self.assertEqual(publisher.get_packages.call_count, 0)

    def test_tags_returns_the_list_of_tags_except_empty_tag(self) -> None:
        fixtures = self.fixtures
        publisher = fixtures.publisher
        build = fixtures.build

        publisher.publish(build)
        publisher.storage.tag(build, "prod")

        self.assertEqual(publisher.storage.get_tags(build), ["", "prod"])
        self.assertEqual(publisher.tags(build), ["prod"])

    def test_tag_tags_the_build_at_the_storage_layer(self) -> None:
        fixtures = self.fixtures
        build = fixtures.build

        gbp.pull(build)
        gbp.tag(build, "prod")
        gbp.tag(build, "albert")

        self.assertEqual(gbp.storage.get_tags(build), ["albert", "prod"])

    def test_untag_removes_tag_from_the_build(self) -> None:
        fixtures = self.fixtures
        publisher = fixtures.publisher
        build = fixtures.build

        publisher.pull(build)
        publisher.tag(build, "prod")
        publisher.tag(build, "albert")

        publisher.untag(build.machine, "albert")

        self.assertEqual(publisher.storage.get_tags(build), ["prod"])

    def test_untag_with_empty_unpublishes_the_build(self) -> None:
        fixtures = self.fixtures
        publisher = fixtures.publisher
        build = fixtures.build

        publisher.publish(build)
        self.assertTrue(publisher.published(build))

        publisher.untag(build.machine, "")

        self.assertFalse(publisher.published(build))

    def test_save(self) -> None:
        r1 = BuildRecordFactory()
        r2 = gbp.save(r1, note="This is a test")

        self.assertEqual(r2.note, "This is a test")

        r3 = gbp.record(Build(r1.machine, r1.build_id))
        self.assertEqual(r2, r3)

    def test_machines(self) -> None:
        builds = [
            *BuildFactory.create_batch(3, machine="foo"),
            *BuildFactory.create_batch(2, machine="bar"),
            *BuildFactory.create_batch(1, machine="baz"),
        ]
        publisher = self.fixtures.publisher
        for build in builds:
            publisher.pull(build)

        machines = publisher.machines()

        self.assertEqual(len(machines), 3)

    def test_machines_with_filter(self) -> None:
        builds = [
            *BuildFactory.create_batch(3, machine="foo"),
            *BuildFactory.create_batch(2, machine="bar"),
            *BuildFactory.create_batch(1, machine="baz"),
        ]
        publisher = self.fixtures.publisher
        for build in builds:
            publisher.pull(build)
        machines = publisher.machines(names={"bar", "baz", "bogus"})

        self.assertEqual(len(machines), 2)


def prepull_events(
    _options: FixtureOptions, _fixtures: Fixtures
) -> FixtureContext[list[Build]]:
    events: list[Build] = []

    def prepull(build: Build) -> None:
        events.append(build)

    dispatcher.bind(prepull=prepull)

    yield events


def postpull_events(
    _options: FixtureOptions, _fixtures: Fixtures
) -> FixtureContext[list[tuple[Build, list[Package], GBPMetadata | None]]]:
    events: list[tuple[Build, list[Package], GBPMetadata | None]] = []

    def postpull(
        *, build: Build, packages: list[Package], gbp_metadata: GBPMetadata | None
    ) -> None:
        events.append((build, packages, gbp_metadata))

    dispatcher.bind(postpull=postpull)

    yield events


def publish_events(
    _options: FixtureOptions, _fixtures: Fixtures
) -> FixtureContext[list[Build]]:
    events: list[Build] = []

    def publish(build: Build) -> None:
        events.append(build)

    dispatcher.bind(published=publish)

    yield events


@requires("publisher", prepull_events, postpull_events, publish_events)
class DispatcherTestCase(TestCase):
    maxDiff = None

    def test_pull_single(self) -> None:
        new_build = BuildFactory()
        gbp.pull(new_build)

        packages = gbp.storage.get_packages(new_build)
        expected = (
            gbp.record(new_build),
            packages,
            gbp.gbp_metadata(gbp.jenkins.get_metadata(new_build), packages),
        )
        self.assertEqual(self.fixtures.postpull_events, [expected])
        self.assertEqual(self.fixtures.prepull_events, [new_build])

    def test_pull_multi(self) -> None:
        fixtures = self.fixtures
        build1 = BuildFactory()
        build2 = BuildFactory(machine="fileserver")
        gbp.pull(build1)
        gbp.pull(build2)

        record1 = gbp.record(build1)
        record2 = gbp.record(build2)

        packages = gbp.storage.get_packages(record1)
        event1 = (
            record1,
            packages,
            gbp.gbp_metadata(gbp.jenkins.get_metadata(record1), packages),
        )
        packages = gbp.storage.get_packages(record2)
        event2 = (
            record2,
            packages,
            gbp.gbp_metadata(gbp.jenkins.get_metadata(record2), packages),
        )
        self.assertEqual(fixtures.prepull_events, [build1, build2])
        self.assertEqual(fixtures.postpull_events, [event1, event2])

    def test_publish(self) -> None:
        fixtures = self.fixtures
        new_build = BuildFactory()
        gbp.publish(new_build)

        record = gbp.record(new_build)
        self.assertEqual(fixtures.publish_events, [record])


def builds_fixture(_options: FixtureOptions, _fixtures: Fixtures) -> list[Build]:
    # So for this case let's say we have 4 builds.  None have built timestamps.  The
    # 3rd one is published (but has no built timestamp) and the first 2 are pulled
    # but not published:
    builds: list[Build] = BuildFactory.create_batch(4)
    return builds


@requires("publisher")
class ScheduleBuildTestCase(TestCase):
    """Tests for the schedule_build function"""

    def test(self) -> None:
        response = gbp.schedule_build("babette")

        self.assertEqual("https://jenkins.invalid/job/babette/build", response)
        self.assertEqual(gbp.jenkins.scheduled_builds, ["babette"])


@requires("publisher")
class DumpTests(TestCase):
    def test(self) -> None:
        builds = [
            *BuildFactory.create_batch(3, machine="foo"),
            *BuildFactory.create_batch(2, machine="bar"),
            *BuildFactory.create_batch(1, machine="baz"),
        ]
        for build in builds:
            gbp.pull(build)

        outfile = io.BytesIO()
        gbp.dump(builds, outfile)
        outfile.seek(0)

        with tar.open(mode="r", fileobj=outfile) as tarfile:
            names = tarfile.getnames()
            self.assertEqual(names, ["storage.tar", "records.json"])

            storage = tarfile.extractfile("storage.tar")
            assert storage is not None
            with storage:
                with tar.open(mode="r", fileobj=storage) as storage_tarfile:
                    names = storage_tarfile.getnames()
                    self.assertEqual(120, len(names))

            records = tarfile.extractfile("records.json")
            assert records is not None
            with records:
                data = json.load(records)
                self.assertEqual(6, len(data))


@requires("publisher")
class RestoreTests(TestCase):
    def test(self) -> None:
        builds = [
            *BuildFactory.create_batch(3, machine="foo"),
            *BuildFactory.create_batch(2, machine="bar"),
            *BuildFactory.create_batch(1, machine="baz"),
        ]
        for build in builds:
            gbp.pull(build)

        fp = io.BytesIO()
        gbp.dump(builds, fp)
        fp.seek(0)

        for build in builds:
            gbp.delete(build)
            self.assertFalse(gbp.storage.pulled(build))
            self.assertFalse(gbp.repo.build_records.exists(build))

        gbp.restore(fp)

        for build in builds:
            self.assertTrue(gbp.storage.pulled(build))
            self.assertTrue(gbp.repo.build_records.exists(build))
