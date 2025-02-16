"""Storage (filesystem) interface for Gentoo Build Publisher"""

from __future__ import annotations

import logging
import shutil
import tarfile as tar
import tempfile
from functools import lru_cache
from pathlib import Path
from typing import IO, Iterable

import orjson

from gentoo_build_publisher import fs, string, utils
from gentoo_build_publisher.settings import Settings
from gentoo_build_publisher.types import (
    TAG_SYM,
    Build,
    Content,
    DumpCallback,
    GBPMetadata,
    Package,
    PackageMetadata,
    default_dump_callback,
)

INVALID_TEST_PATH = "__testing__"
GBP_METADATA_FILENAME = "gbp.json"
logger = logging.getLogger(__name__)


class Storage:
    """Filesystem storage for Gentoo Build Publisher

    Gentoo Build Publisher hosts files (repos, binpkgs, etc).  There is a "root"
    directory for all the files and the Storage class is the interface to that directory
    tree.

    The directory tree basically looks like the following.
    .
    ├── binpkgs
    │   └── lighthouse.19
    ├── etc-portage
    │   └── lighthouse.19
    ├── repos
    │   └── lighthouse.19
    │       ├── gentoo
    │       └── marduk
    ├── tmp
    └── var-lib-portage
        └── lighthouse.19

    Each of the directories binpkgs, etc-portage, repos, and var-lib-portage hold each
    kind of Content stored in a (Jenkins) build artifact.  So in the above example, if a
    build "lighthouse.19" was pulled, there exists a ./binpkgs/lighthouse.19 directory
    containing the build's binary packages, a ./repos/lighthouse.19 directory containing
    the ebuild repos used for that build, etc. The tmp/ directory, as the name implies,
    is for temporary storage.

    When a build is published, for example "lighthouse.19", then for each of its
    respective directories in Content there exists a symbolic link with just the name of
    the machine, for example, "lighthouse".  Likewise, a tag to a build is a symbolic
    link with the name of the machine, the @ sign and the tag. For example if the build
    "lighthouse.19" had a tag "prod" then for each of it's directories there would be a
    symbolic link lighthouse@prod -> lighthouse.19.
    """

    def __init__(self, root: Path):
        if str(root) != INVALID_TEST_PATH:
            fs.init_root(root, ["tmp"] + [content.value for content in Content])
        self.root = root

    @classmethod
    def from_settings(cls, settings: Settings) -> Storage:
        """Instantiate from settings"""
        return cls(settings.STORAGE_PATH)

    @lru_cache(maxsize=256 * len(Content))
    def get_path(
        self, build: Build, content: Content, *, tag: str | None = None
    ) -> Path:
        """Return the Path of the content type for build

        Were it to be downloaded.

        If the optional tag is provided, returns the path of the given tag.
        """
        if tag is None:
            return self.root.joinpath(content.value, str(build))

        name = f"{build.machine}{TAG_SYM}{tag}" if tag else build.machine
        return self.root.joinpath(content.value, name)

    def extract_artifact(
        self, build: Build, byte_stream: Iterable[bytes], previous: Build | None = None
    ) -> None:
        """Pull and unpack the artifact

        If `previous_build` is given, then if a file exists in that location it will be
        hard linked to the extracted tree instead of being copied from the artifact.
        This is similar to the "--link-dest" argument in rsync and is used to save disk
        space.
        """
        if self.pulled(build):
            return

        logger.info("Extracting build: %s", build)

        tmpdir = self.root / "tmp"
        artifact_file = tempfile.NamedTemporaryFile(dir=tmpdir, suffix=".tar.gz")
        artifact_dir = tempfile.TemporaryDirectory(dir=tmpdir)
        with artifact_file, artifact_dir:
            dirpath = Path(artifact_dir.name)

            fs.save_stream(byte_stream, artifact_file)
            fs.extract(Path(artifact_file.name), dirpath)

            for item in Content:
                src = dirpath / item.value
                dst = self.get_path(build, item)
                link_dest = self.get_path(previous, item) if previous else None

                fs.copy_path(src, dst, link_dest)

        logger.info("Extracted build: %s", build)

    def pulled(self, build: Build) -> bool:
        """Returns True if build has been pulled

        By "pulled" we mean all Build components exist on the filesystem
        """
        return all(self.get_path(build, item).exists() for item in Content)

    def publish(self, build: Build) -> None:
        """Make this build 'active'

        Alias for tag(build, "")
        """
        self.tag(build, "")

    def tag(self, build: Build, tag_name: str) -> None:
        """Create a "tag" for this build

        If tag is non-empty then the resulting symlink will be like, e.g.
        lighthouse@stable -> lighthouse.9429 otherwise it's just an old fashioned
        "published" build, e.g.  `binpkgs/lighthouse`.
        """
        if not self.pulled(build):
            raise FileNotFoundError("The build has not been pulled")

        if tag_name:
            utils.validate_identifier(tag_name)

        name = f"{build.machine}{TAG_SYM}{tag_name}" if tag_name else build.machine

        for item in Content:
            path = self.root / item.value / name
            fs.symlink(str(build), str(path))

    def untag(self, machine: str, tag_name: str = "") -> None:
        """Untag a build.

        If tag_name is the empty string, unpublishes the machine.
        Fail silently if the given tag does not exist.
        """
        if tag_name:
            utils.validate_identifier(tag_name)
        # We don't need to check for the existence of the target here.  In fact we don't
        # want to as this will allow us to remove dangling symlinks
        name = f"{machine}{TAG_SYM}{tag_name}" if tag_name else machine

        for item in Content:
            path = self.root / item.value / name
            if path.is_symlink():
                path.unlink()

    def get_tags(self, build: Build) -> list[str]:
        """Return the tags for the given build.

        If the build is published, the list will contain the empty string.
        Broken and partial tags don't count.
        """
        tags = []
        machine = build.machine

        if self.published(build):
            tags.append("")

        for path in (self.root / Content.BINPKGS.value).glob(f"{machine}{TAG_SYM}*"):
            tag = path.name.partition(TAG_SYM)[2]
            if self.check_symlinks(build, f"{machine}{TAG_SYM}{tag}"):
                tags.append(tag)

        tags.sort()

        return tags

    def resolve_tag(self, tag: str) -> Build:
        """Return the build given the tag name

        If tag doesn't exist or is broken, raise an exception.
        """
        machine, _, tag_name = tag.partition(TAG_SYM)

        if not tag_name:
            raise ValueError(f"Invalid tag: {tag}")

        utils.validate_identifier(tag_name)
        # In order for this tag to resolve, all the content has to exist and point to
        # the same build and the build has to exist in storage
        target_builds = set()
        for item in Content:
            symlink = self.root / item.value / tag
            target = symlink.resolve()

            if not target.exists():
                break

            target_machine, _, target_build = target.name.partition(".")
            if not (target_machine and target_build) or target_machine != machine:
                break

            target_builds.add(target_build)
            if len(target_builds) != 1:
                break
        else:
            return Build(machine, target_builds.pop())

        raise FileNotFoundError(f"Tag is broken or does not exist: {tag}")

    def published(self, build: Build) -> bool:
        """Return True if the build currently published.

        By "published" we mean all content are symlinked. Partially symlinked is
        unstable and therefore considered not published.
        """
        return self.check_symlinks(build, build.machine)

    def check_symlinks(self, build: Build, name: str) -> bool:
        """Return True if the given symlinks point to the given build

        Symlinks have to exist for all `Content`.
        """
        return all(
            fs.check_symlink(
                str(self.root.joinpath(item.value, name)),
                str(self.get_path(build, item)),
            )
            for item in Content
        )

    def repos(self, build: Build) -> set[str]:
        """Return the repos for this (pulled) build"""
        if not self.pulled(build):
            raise FileNotFoundError("The build has not been pulled")

        repos_path = self.get_path(build, Content.REPOS)

        return {path.name for path in repos_path.iterdir() if path.is_dir()}

    def delete(self, build: Build) -> None:
        """Delete files/dirs associated with build

        Does not fix dangling symlinks.
        """
        for item in Content:
            shutil.rmtree(self.get_path(build, item), ignore_errors=True)

    def package_index_file(self, build: Build) -> IO[str]:
        """Return a file object for the Packages index file"""
        package_index_path = self.get_path(build, Content.BINPKGS) / "Packages"

        if not package_index_path.exists():
            logger.warning("Build %s is missing package index", build)
            raise LookupError(f"{package_index_path} is missing")

        return package_index_path.open(encoding="utf-8")

    def get_packages(self, build: Build) -> list[Package]:
        """Return the list of packages for this build"""
        with self.package_index_file(build) as package_index_file:
            # Skip preamble (for now)
            while package_index_file.readline().rstrip():
                pass

            return list(make_packages(package_index_file))

    def dump(
        self,
        builds: Iterable[Build],
        fp: IO[bytes],
        *,
        callback: DumpCallback = default_dump_callback,
    ) -> None:
        """Dump the given builds' contents to the given file object

        The bytes dumped will be a tar archive. This includes any tags associated with
        the build.
        """
        with tar.open(fileobj=fp, mode="w") as tarfile, fs.cd(self.root):
            for build in builds:
                callback("storage", build)
                for content in Content:
                    for tag in [None, *self.get_tags(build)]:
                        path = self.get_path(build, content, tag=tag)
                        path = path.relative_to(self.root)
                        tarfile.add(path)

    def get_metadata(self, build: Build) -> GBPMetadata:
        """Read binpkg/gbp.json and return GBPMetadata instance

        If the file does not exist (e.g. not pulled), raise LookupError
        """
        path = self.get_path(build, Content.BINPKGS) / GBP_METADATA_FILENAME

        try:
            json = orjson.loads(path.read_bytes())  # pylint: disable=no-member
        except FileNotFoundError:
            raise LookupError(
                f"{GBP_METADATA_FILENAME} does not exist for {build}"
            ) from None

        return GBPMetadata(
            build_duration=json["build_duration"],
            packages=PackageMetadata(
                total=json["packages"]["total"],
                size=json["packages"]["size"],
                built=[
                    Package(
                        build_id=built["build_id"],
                        build_time=built["build_time"],
                        cpv=built["cpv"],
                        path=built["path"],
                        repo=built["repo"],
                        size=built["size"],
                    )
                    for built in json["packages"]["built"]
                ],
            ),
        )

    def set_metadata(self, build: Build, metadata: GBPMetadata) -> None:
        """Save metadata to "gbp.json" in the binpkgs directory"""
        path = self.get_path(build, Content.BINPKGS) / GBP_METADATA_FILENAME
        path.write_bytes(orjson.dumps(metadata))  # pylint: disable=no-member


def make_package_from_lines(lines: Iterable[str]) -> Package:
    """Given the appropriate lines from Packages, return a Package object"""
    package_info = {
        name.lower(): value.rstrip()
        for (name, value) in (string.namevalue(line, ":") for line in lines)
    }

    try:
        return Package(
            cpv=package_info["cpv"],
            repo=package_info["repo"],
            path=package_info["path"],
            build_id=int(package_info["build_id"]),
            size=int(package_info["size"]),
            build_time=int(package_info["build_time"]),
        )
    except KeyError as error:
        raise ValueError(
            f"Package lines missing {error.args[0].upper()} value"
        ) from None


def make_packages(package_index_file: IO[str]) -> Iterable[Package]:
    """Yield Packages from Package index file

    Assumes file pointer is after the preamble.
    """
    for section in string.get_sections(package_index_file):
        yield make_package_from_lines(section)
