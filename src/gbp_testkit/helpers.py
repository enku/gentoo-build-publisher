# pylint: disable=missing-docstring,comparison-with-callable
import argparse
import datetime as dt
import io
import json as jsonlib
import os
import shlex
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence
from unittest import mock
from zoneinfo import ZoneInfo

import gbpcli
import rich.console
from ariadne import graphql_sync
from django.test.client import RequestFactory
from gbpcli.config import AuthDict, Config
from gbpcli.gbp import GBP
from gbpcli.theme import get_theme_from_string
from gbpcli.types import Console
from requests import Response, Session
from yarl import URL

from gentoo_build_publisher import publisher
from gentoo_build_publisher.cli import apikey
from gentoo_build_publisher.graphql import schema
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
        self.scheduled_builds: list[tuple[str, dict[str, Any]]] = []
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

    def schedule_build(self, machine: str, **params: Any) -> str:
        self.scheduled_builds.append((machine, params))

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
            if payload := kwargs.get("data"):
                tree = ET.fromstring(payload)
                install = tree.find("install")
                if install is not None and "plugin" in install.attrib:
                    return self.response(200)
            return self.response(500)

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


class TestConsole:
    def __init__(self) -> None:
        out = io.StringIO()
        err = io.StringIO()
        theme = get_theme_from_string(os.environ.get("GBPCLI_COLORS", ""))
        c = Console(
            out=rich.console.Console(
                file=out, width=88, theme=theme, highlight=False, record=True
            ),
            err=rich.console.Console(file=err, width=88, record=True),
        )
        self.out = c.out
        self.err = c.err

    # pylint: disable=no-member
    @property
    def stdout(self) -> str:
        return self.out.file.getvalue()  # type: ignore

    @property
    def stderr(self) -> str:
        return self.err.file.getvalue()  # type: ignore


def make_gbpcli(gbp: GBP, console: Console) -> Callable[[str], int]:
    """Return a function that you can pass a gbpcli command line to

    e.g.

    >>> gbpcli = make_gbpcli(gbp, console)
    >>> gbpcli("gbp check")
    """

    def gbpcli_(cmdline: str) -> int:
        args = parse_args(cmdline)
        func: Callable[[argparse.Namespace, GBP, Console], int] = args.func

        print_command(cmdline, console)

        return func(args, gbp, console)

    return gbpcli_


def mock_gbp_session_post(url: str, *, json: dict[str, Any] | None = None) -> Response:
    """Mock GBP Query session post"""
    assert json
    success, data = graphql_sync(schema, json)
    encoding = "UTF-8"

    content = jsonlib.dumps(data).encode(encoding)
    requests_response = Response()
    requests_response.raw = io.BytesIO(content)
    requests_response.raw.seek(0)
    requests_response.status_code = 200 if success else 500
    requests_response.encoding = encoding
    requests_response.url = url

    return requests_response


def test_gbp(url: str, auth: AuthDict | None = None) -> GBP:
    """Return a gbp instance capable of calling the /graphql view"""
    gbp = GBP(url, auth=auth)
    gbp.query._session.post = mock_gbp_session_post  # pylint: disable=protected-access

    return gbp


def graphql(_: Any, query: str, variables: dict[str, Any] | None = None) -> Any:
    """Execute GraphQL query

    The first argument is unused and is there for backwards compatibility.

    Return the JSON response.
    """
    rf = RequestFactory()
    request = rf.post("/graphql", headers={"Content-Type": "application/json"})
    data = {"query": query, "variables": variables}

    return graphql_sync(schema, data, context_value={"request": request})[1]


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


def test_data(filename: str) -> bytes:
    """Return all the data in filename"""
    return (BASE_DIR / filename).read_bytes()


BUILD_LOGS = test_data("logs.txt").decode("UTF-8")


def parse_args(cmdline: str) -> argparse.Namespace:
    """Return cmdline as parsed arguments"""
    args = shlex.split(cmdline)
    parser = gbpcli.build_parser(Config(url="http://gbp.invalid/"))

    return parser.parse_args(args[1:])


def print_command(cmdline: str, console: Console) -> None:
    """Pretty print the cmdline to console"""
    console.out.print(f"[green]$ [/green]{cmdline}")


def ts(ts_string: str, tzinfo: dt.timezone | ZoneInfo | None = dt.UTC) -> dt.datetime:
    """Convert the ts_string to a TZ-aware datetime"""
    datetime = dt.datetime

    return datetime.strptime(ts_string, "%Y-%m-%d %H:%M:%S").replace(tzinfo=tzinfo)
