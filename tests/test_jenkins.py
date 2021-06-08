"""Tests for the JenkinsBuild type"""
# pylint: disable=missing-class-docstring,missing-function-docstring,no-self-use
import io
import os
from unittest import TestCase, mock

from yarl import URL

from gentoo_build_publisher.build import Build
from gentoo_build_publisher.jenkins import JenkinsBuild
from gentoo_build_publisher.settings import Settings

from . import MockJenkinsBuild, test_data


class JenkinsBuildTestCase(TestCase):
    """Tests for the JenkinsBuild api wrapper"""

    def test_artiact_url(self):
        """.build_url() should return the url of the given build artifact"""
        # Given the JenkinsBuild instance
        jenkins_build = JenkinsBuild(
            build=Build(name="babette", number=193),
            base_url=URL("https://jenkins.invalid"),
            api_key="foo",
            user="jenkins",
        )

        # When we call .build_url
        build_url = jenkins_build.artifact_url()

        # Then we get the expected url
        self.assertEqual(
            build_url,
            URL("https://jenkins.invalid/job/babette/193/artifact/build.tar.gz"),
        )

    def test_download_artifact(self):
        """.download_artifact should download the given build artifact"""
        # Given the JenkinsBuild instance
        jenkins_build = MockJenkinsBuild(
            build=Build(name="babette", number=193),
            base_url=URL("https://jenkins.invalid"),
            api_key="foo",
            user="jenkins",
            artifact_name="build.tar.gz",
        )

        # When we call download_artifact on the build
        stream = jenkins_build.download_artifact()

        # Then it streams the build artifact's contents
        bytes_io = io.BytesIO()
        for chunk in stream:
            bytes_io.write(chunk)

        expected = test_data("build.tar.gz")
        self.assertEqual(bytes_io.getvalue(), expected)
        jenkins_build.mock_get.assert_called_with(
            "https://jenkins.invalid/job/babette/193/artifact/build.tar.gz",
            auth=("jenkins", "foo"),
            stream=True,
        )

    def test_download_artifact_with_no_auth(self):
        # Given the JenkinsBuild instance having no user/api_key
        jenkins_build = MockJenkinsBuild(
            build=Build(name="babette", number=193),
            base_url=URL("https://jenkins.invalid"),
            artifact_name="build.tar.gz",
        )

        # When we call download_artifact on the build
        jenkins_build.download_artifact()

        # Then it requests the artifact with no auth
        jenkins_build.mock_get.assert_called_with(
            "https://jenkins.invalid/job/babette/193/artifact/build.tar.gz",
            auth=None,
            stream=True,
        )

    @mock.patch.dict(os.environ, {}, clear=True)
    def test_from_settings(self):
        """.from_settings() should return an instance instantiated from settings"""
        # Given the settings
        settings = Settings(
            JENKINS_BASE_URL="https://foo.bar.invalid/jenkins",
            JENKINS_API_KEY="super secret key",
            JENKINS_USER="admin",
            JENKINS_ARTIFACT_NAME="stuff.tar",
            STORAGE_PATH="/dev/null",
        )

        build = Build(name="babette", number=193)

        # When we instantiate JenkinsBuild.from_settings
        jenkins_build = JenkinsBuild.from_settings(build, settings)

        # Then we get a JenkinsBuild instance with attributes from my_settings
        self.assertIsInstance(jenkins_build, JenkinsBuild)
        self.assertEqual(jenkins_build.base_url, URL("https://foo.bar.invalid/jenkins"))
        self.assertEqual(jenkins_build.api_key, "super secret key")
        self.assertEqual(jenkins_build.user, "admin")
        self.assertEqual(jenkins_build.artifact_name, "stuff.tar")
        self.assertEqual(jenkins_build.build, build)
