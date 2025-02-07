# pylint: disable=missing-docstring,comparison-with-callable
import datetime as dt
import io
import os
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Iterable, Sequence
from unittest import mock

import rich.console
from django.test.client import Client
from gbpcli.config import AuthDict
from gbpcli.gbp import GBP
from gbpcli.theme import DEFAULT_THEME
from gbpcli.types import Console
from requests import Response, Session
from requests.adapters import BaseAdapter
from requests.structures import CaseInsensitiveDict
from rich.theme import Theme
from yarl import URL

from gentoo_build_publisher import publisher
from gentoo_build_publisher.cli import apikey
from gentoo_build_publisher.jenkins import (
    Jenkins,
    JenkinsConfig,
    JenkinsMetadata,
    ProjectPath,
)
from gentoo_build_publisher.types import ApiKey, Build

BASE_DIR = Path(__file__).resolve().parent / "data"
LOCAL_TIMEZONE = dt.timezone(dt.timedelta(days=-1, seconds=61200), "PDT")


class QuickCache:
    """Supports the CacheProtocol"""

    def __init__(self) -> None:
        self.cache: dict[str, Any] = {}

    def get(self, key: str, default: Any = None) -> Any:
        return self.cache.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self.cache[key] = value


class MockJenkins(Jenkins):
    """Jenkins with requests mocked out"""

    mock_get = None
    get_build_logs_mock_get = None

    def __init__(self, config: JenkinsConfig):
        # pylint: disable=import-outside-toplevel,cyclic-import
        from .factories import ArtifactFactory

        super().__init__(config)

        self.artifact_builder = ArtifactFactory()
        self.scheduled_builds: list[str] = []
        mock_jenkins_session = mock.MagicMock(wraps=MockJenkinsSession())
        mock_jenkins_session.auth = config.auth
        self.session = mock_jenkins_session
        self.root = mock_jenkins_session.root

    def download_artifact(self, build: Build) -> Iterable[bytes]:
        with mock.patch.object(self.session, "get") as mock_get:
            mock_get.return_value.iter_content.side_effect = (
                lambda *args, **kwargs: self.artifact_builder.get_artifact(build)
            )
            self.mock_get = mock_get
            return super().download_artifact(build)

    def get_logs(self, build: Build) -> str:
        with mock.patch.object(self.session, "get") as mock_get:
            mock_get.return_value.text = BUILD_LOGS
            self.get_build_logs_mock_get = mock_get

            return super().get_logs(build)

    def get_metadata(self, build: Build) -> JenkinsMetadata:
        build_time = self.artifact_builder.build_info(build).build_time
        return JenkinsMetadata(duration=124, timestamp=build_time)

    def schedule_build(self, machine: str, **_params: Any) -> str:
        self.scheduled_builds.append(machine)

        return str(self.config.base_url / "job" / machine / "build")


class MockJenkinsSession(Session):
    """Mock requests.Session for Jenkins"""

    def __init__(self) -> None:
        super().__init__()
        self.root = Tree()
        self.responses: dict[tuple[str, str], Response] = {}

    @staticmethod
    def response(status_code: int, content: bytes = b"") -> Response:
        response: Response = mock.MagicMock(wraps=Response)()
        response.status_code = status_code
        response.raw = io.BytesIO(content)

        return response

    def mock_response(self, method: str, path: str, response: Response) -> None:
        self.responses[(method, path)] = response

    def head(self, url: str, *args: Any, **kwargs: Any) -> Response:
        path = URL(url).path
        project_path = self.project_path(path)

        try:
            self.root.get(project_path.parts[1:])
        except KeyError:
            return self.response(404)

        return self.response(200)

    def post(self, url: str, *args, **kwargs) -> Response:
        url_obj = URL(url)

        if url_obj.path == "/pluginManager/installNecessaryPlugins":
            try:
                assert "data" in kwargs
                payload = kwargs["data"]
                tree = ET.fromstring(payload)
                install = tree.find("install")
                assert install is not None
                assert "plugin" in install.attrib
            except AssertionError:
                return self.response(500)

            return self.response(200)

        if url_obj.name == "createItem":
            path = url_obj.parent.path
            project_path = self.project_path(path) / kwargs["params"]["name"]

            try:
                self.root.set(project_path.parts[1:], kwargs.get("data", ""))
            except KeyError:
                return self.response(404)

            return self.response(200)

        return self.response(400)

    def get(self, url: str, *args, **kwargs) -> Response:
        url_obj = URL(url)

        if response := self.responses.get(("GET", url_obj.path)):
            return response

        if url_obj.name != "config.xml":
            return self.response(400)

        project_path = self.project_path(url_obj.parent.path)

        try:
            value = self.root.get(project_path.parts[1:])
        except KeyError:
            return self.response(404)

        return self.response(200, value.encode())

    def project_path(self, url_path: str) -> ProjectPath:
        return ProjectPath("/".join(url_path.split("/job/")))


class DjangoToRequestsAdapter(BaseAdapter):
    """Requests Adapter to call Django views"""

    def send(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self, request, stream=False, timeout=None, verify=True, cert=None, proxies=None
    ) -> Response:
        django_response = Client().generic(
            request.method,
            request.path_url,
            data=request.body,
            content_type=request.headers["Content-Type"],
            headers=request.headers,
        )

        requests_response = Response()
        requests_response.raw = io.BytesIO(django_response.content)
        requests_response.raw.seek(0)
        requests_response.status_code = django_response.status_code
        requests_response.headers = CaseInsensitiveDict(django_response.headers)
        requests_response.encoding = django_response.get("Content-Type", None)
        requests_response.url = str(request.url)
        requests_response.request = request

        return requests_response

    def close(self) -> None:
        return


class Tree:
    """Simple tree structure"""

    def __init__(self, value: Any = None) -> None:
        self.value = value
        self.nodes: dict[str, Tree] = {}

    def set(self, path: Sequence[str], value: Any) -> None:
        """Set node given path. Parent nodes must exist"""
        node = self
        for item in path[:-1]:
            node = node.nodes[item]

        node.nodes[path[-1]] = Tree(value)

    def get(self, path: Sequence[str]) -> Any:
        node = self
        for item in path[:-1]:
            node = node.nodes[item]

        return node.nodes[path[-1]].value


def test_gbp(url: str, auth: AuthDict | None = None) -> GBP:
    """Return a gbp instance capable of calling the /graphql view"""
    gbp = GBP(url, auth=auth)
    gbp.query._session.mount(  # pylint: disable=protected-access
        url, DjangoToRequestsAdapter()
    )

    return gbp


def graphql(client: Client, query: str, variables: dict[str, Any] | None = None) -> Any:
    """Execute GraphQL query on the Django test client.

    Return the parsed JSON response
    """
    response = client.post(
        "/graphql",
        {"query": query, "variables": variables},
        content_type="application/json",
    )

    return response.json()


def create_file(
    path: Path, content: bytes = b"", mtime: dt.datetime | None = None
) -> Path:
    with path.open("wb") as outfile:
        outfile.write(content)

    if mtime is not None:
        stat = os.stat(path)
        atime = stat.st_atime
        os.utime(path, times=(atime, mtime.timestamp()))

    return path


def create_user_auth(user: str) -> str:
    secret = apikey.create_api_key()
    api_key = ApiKey(name=user, key=secret, created=dt.datetime.now(tz=dt.UTC))
    publisher.repo.api_keys.save(api_key)

    return secret


def string_console(**kwargs: Any) -> tuple[Console, io.StringIO, io.StringIO]:
    """StringIO Console"""
    out = io.StringIO()
    err = io.StringIO()

    return (
        Console(
            out=rich.console.Console(file=out, theme=Theme(DEFAULT_THEME), **kwargs),
            err=rich.console.Console(file=err, **kwargs),
        ),
        out,
        err,
    )


def test_data(filename: str) -> bytes:
    """Return all the data in filename"""
    return (BASE_DIR / filename).read_bytes()


BUILD_LOGS = test_data("logs.txt").decode("UTF-8")
