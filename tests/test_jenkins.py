"""Tests for the Jenkins type"""
# pylint: disable=missing-class-docstring,missing-function-docstring,no-self-use
import io
import os
from unittest import TestCase, mock

from yarl import URL

from gentoo_build_publisher import Build, Jenkins, Settings

from . import MockJenkins, test_data


class JenkinsTestCase(TestCase):
    """Tests for the Jenkins api wrapper"""

    def test_build_url(self):
        """.build_url() should return the url of the given build artifact"""
        # Given the Jenkins instance
        jenkins = Jenkins(
            base_url=URL("https://jenkins.invalid"), api_key="foo", user="jenkins"
        )

        # Given the build
        build = Build(name="babette", number=193)

        # When we call .build_url
        build_url = jenkins.build_url(build)

        # Then we get the expected url
        self.assertEqual(
            build_url,
            URL("https://jenkins.invalid/job/babette/193/artifact/build.tar.gz"),
        )

    def test_download_artifact(self):
        """.download_artifact should download the given build artifact"""
        # Given the Jenkins instance
        jenkins = MockJenkins(
            base_url=URL("https://jenkins.invalid"),
            api_key="foo",
            user="jenkins",
            artifact_name="build.tar.gz",
        )

        # Given the build
        build = Build(name="babette", number=193)

        # When we call download_artifact on the build
        stream = jenkins.download_artifact(build)

        # Then it streams the build artifact's contents
        bytes_io = io.BytesIO()
        for chunk in stream:
            bytes_io.write(chunk)

        expected = test_data("build.tar.gz")
        self.assertEqual(bytes_io.getvalue(), expected)
        jenkins.mock_get.assert_called_with(
            "https://jenkins.invalid/job/babette/193/artifact/build.tar.gz",
            auth=("jenkins", "foo"),
            stream=True,
        )

    def test_download_artifact_with_no_auth(self):
        # Given the Jenkins instance having no user/api_key
        jenkins = MockJenkins(
            base_url=URL("https://jenkins.invalid"),
            artifact_name="build.tar.gz",
        )

        # Given the build
        build = Build(name="babette", number=193)

        # When we call download_artifact on the build
        jenkins.download_artifact(build)

        # Then it requests the artifact with no auth
        jenkins.mock_get.assert_called_with(
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

        # When we instantiate Jenkins.from_settings
        jenkins = Jenkins.from_settings(settings)

        # Then we get a Jenkins instance with attributes from my_settings
        self.assertIsInstance(jenkins, Jenkins)
        self.assertEqual(jenkins.base_url, URL("https://foo.bar.invalid/jenkins"))
        self.assertEqual(jenkins.api_key, "super secret key")
        self.assertEqual(jenkins.user, "admin")
        self.assertEqual(jenkins.artifact_name, "stuff.tar")
