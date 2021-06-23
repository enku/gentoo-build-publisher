"""Tests for GBP managers"""
# pylint: disable=missing-class-docstring,missing-function-docstring
import datetime
from unittest import mock

from django.test import TestCase

from gentoo_build_publisher.build import Build
from gentoo_build_publisher.diff import Change, Status
from gentoo_build_publisher.managers import BuildMan
from gentoo_build_publisher.settings import Settings

from . import TempHomeMixin
from .factories import BuildManFactory, MockJenkinsBuild

utc = datetime.timezone.utc


class BuildManTestCase(TempHomeMixin, TestCase):
    def test_as_dict(self):
        """build.as_dict() should return the expected dict"""
        buildman = BuildManFactory.build()
        buildman.db.keep = True
        buildman.db.save()

        as_dict = buildman.as_dict()

        expected = {
            "name": buildman.name,
            "number": buildman.number,
            "db": {
                "note": None,
                "keep": True,
                "submitted": buildman.db.submitted.isoformat(),
                "completed": None,
            },
            "storage": {
                "published": False,
                "pulled": False,
            },
            "jenkins": {
                "url": (
                    "https://jenkins.invalid/job/"
                    f"{buildman.name}/{buildman.number}/artifact/build.tar.gz"
                ),
            }
        }
        self.assertEqual(as_dict, expected)

    def test_as_dict_with_buildnote(self):
        buildman = BuildManFactory.build()
        buildman.db.note = "This is a test"
        buildman.db.save()

        as_dict = buildman.as_dict()

        expected = {
            "name": buildman.name,
            "number": buildman.number,
            "db": {
                "note": "This is a test",
                "completed": None,
                "submitted": buildman.db.submitted.isoformat(),
                "keep": False,
            },
            "jenkins": {
                "url": (
                    "https://jenkins.invalid/job/"
                    f"{buildman.name}/{buildman.number}/artifact/build.tar.gz"
                ),
            },
            "storage": {
                "published": False,
                "pulled": False,
            }
        }
        self.assertEqual(as_dict, expected)

    def test_publish(self):
        """.publish should publish the build artifact"""
        buildman = BuildManFactory.build()

        buildman.publish()

        self.assertIs(buildman.storage_build.published(), True)

    def test_pull_without_db(self):
        """pull creates db instance and pulls from jenkins"""
        build = Build(name="babette", number=193)
        settings = Settings.from_environ()
        jenkins_build = MockJenkinsBuild.from_settings(build, settings)
        buildman = BuildMan(build, jenkins_build=jenkins_build)

        buildman.pull()

        self.assertIs(buildman.storage_build.pulled(), True)
        self.assertIsNot(buildman.db, None)

    def test_pull_stores_build_logs(self):
        """Should store the logs of the build"""
        buildman = BuildManFactory.build()

        buildman.pull()

        url = str(buildman.logs_url())
        buildman.jenkins_build.get_build_logs_mock_get.assert_called_once()
        call_args = buildman.jenkins_build.get_build_logs_mock_get.call_args
        self.assertEqual(call_args[0][0], url)

        self.assertEqual(buildman.db.logs, "foo\n")

    def test_pull_updates_build_models_completed_field(self):
        """Should update the completed field with the current timestamp"""
        now = datetime.datetime.now()
        buildman = BuildManFactory.build()

        with mock.patch("gentoo_build_publisher.managers.utcnow") as mock_now:
            mock_now.return_value = now
            buildman.pull()

        buildman.db.model.refresh_from_db()
        self.assertEqual(buildman.db.model.completed, now.replace(tzinfo=utc))

    def test_pull_writes_built_pkgs_in_note(self):
        now = datetime.datetime.now().replace(tzinfo=utc)
        prev_build = BuildManFactory.build()
        prev_build.db.model.completed = now
        prev_build.db.model.save()

        buildman = BuildManFactory.build()

        with mock.patch("gentoo_build_publisher.diff.dirdiff") as mock_dirdiff:
            mock_dirdiff.return_value = iter(
                [
                    Change(item="app-crypt/gpgme-1.14.0-1", status=Status.REMOVED),
                    Change(item="app-crypt/gpgme-1.14.0-2", status=Status.ADDED),
                    Change(item="sys-apps/sandbox-2.24-1", status=Status.CHANGED),
                    Change(item="sys-apps/sandbox-2.24-1", status=Status.CHANGED),
                ]
            )
            buildman.pull()

        buildman.db.refresh()

        self.assertEqual(
            buildman.db.note,
            "Packages built:\n\n* app-crypt/gpgme-1.14.0-2\n* sys-apps/sandbox-2.24-1",
        )
