"""Storage (filesystem) interface for Gentoo Build Publisher"""
from __future__ import annotations

import logging
import os
import shutil
import tarfile
import tempfile
from collections.abc import Iterable
from functools import lru_cache
from pathlib import Path
from typing import IO, Callable

from gentoo_build_publisher import utils
from gentoo_build_publisher.common import TAG_SYM, Build, Content, GBPMetadata, Package
from gentoo_build_publisher.settings import JENKINS_DEFAULT_CHUNK_SIZE, Settings

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
        self.root = root
        self.tmpdir = self.root / "tmp"
        self.tmpdir.mkdir(parents=True, exist_ok=True)

        for content in Content:
            content_path = self.root / content.value
            content_path.mkdir(exist_ok=True)

    def __repr__(self) -> str:
        cls = type(self)

        return f"{cls.__qualname__}({repr(self.root)})"

    def __hash__(self) -> int:
        return hash(self.root)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Storage):
            return NotImplemented

        return self.root == other.root

    @classmethod
    def from_settings(cls, settings: Settings) -> Storage:
        """Instatiate from settings"""
        return cls(settings.STORAGE_PATH)

    @lru_cache(maxsize=256 * len(Content))
    def get_path(self, build: Build, content: Content) -> Path:
        """Return the Path of the content type for build

        Were it to be downloaded.
        """
        return self.root / content.value / str(build)

    def extract_artifact(
        self,
        build: Build,
        byte_stream: Iterable[bytes],
        previous: Build | None = None,
    ) -> None:
        """Pull and unpack the artifact

        If `previous_build` is given, then if a file exists in that location it will be
        hard linked to the extracted tree instead of being copied from the artifact.
        This is similiar to the "--link-dest" argument in rsync and is used to save disk
        space.
        """
        if self.pulled(build):
            return

        with tempfile.NamedTemporaryFile(dir=self.tmpdir, suffix="tar.gz") as artifact:
            artifact.writelines(byte_stream)
            artifact.flush()

            logger.info("Extracting build: %s", build)
            bufsize = JENKINS_DEFAULT_CHUNK_SIZE

            with tarfile.open(artifact.name, mode="r", bufsize=bufsize) as tar_file:
                self._extract(build, tar_file, previous)

            logger.info("Extracted build: %s", build)

    def _extract(
        self, build: Build, tar_file: tarfile.TarFile, previous: Build | None
    ) -> None:
        """Extract the given TarFile into the storage system as the given Build.

        If previous is given, use its extracted files and, when possible, create hard
        links from previous build's files to build's when they are the same file.
        """
        with tempfile.TemporaryDirectory(dir=self.tmpdir) as dirpath:
            tar_file.extractall(dirpath)

            for content in Content:
                src = Path(dirpath) / content.value
                dst = self.get_path(build, content)

                if dst.exists():
                    msg = "Extract destination already exists: %s. Removing"
                    logger.warning(msg, dst)
                    shutil.rmtree(dst)

                if previous:
                    copy = copy_or_link(self.get_path(previous, content), dst)
                    shutil.copytree(src, dst, symlinks=True, copy_function=copy)
                else:
                    os.renames(src, dst)

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

        utils.check_tag_name(tag_name)
        name = f"{build.machine}{TAG_SYM}{tag_name}" if tag_name else build.machine

        for item in Content:
            path = self.root / item.value / name
            self.symlink(str(build), str(path))

    def untag(self, machine: str, tag_name: str = "") -> None:
        """Untag a build.

        If tag_name is the empty string, unpublishes the machine.
        Fail silently if the given tag does not exist.
        """
        utils.check_tag_name(tag_name)
        # We don't need to check for the existance of the target here.  In fact we don't
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
        utils.check_tag_name(tag_name)

        if not tag_name:
            raise ValueError(f"Invalid tag: {tag}")

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
            return Build(machine, next(iter(target_builds)))

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
            (symlink := self.root / item.value / name).exists()
            and os.path.realpath(symlink) == str(self.get_path(build, item))
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

    @staticmethod
    def symlink(source: str, target: str) -> None:
        """If target is a symlink remove it. If it otherwise exists raise an error"""
        if os.path.islink(target):
            os.unlink(target)
        elif os.path.exists(target):
            raise EnvironmentError(f"{target} exists but is not a symlink")

        os.symlink(source, target)

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

            return [*make_packages(package_index_file)]

    def get_metadata(self, build: Build) -> GBPMetadata:
        """Read binpkg/gbp.json and return GBPMetadata instance

        If the file does not exist (e.g. not pulled), raise LookupError
        """
        path = self.get_path(build, Content.BINPKGS) / "gbp.json"

        try:
            with path.open("r") as gbp_json:
                return GBPMetadata.from_json(gbp_json.read())  # type: ignore # pylint: disable=no-member
        except FileNotFoundError:
            raise LookupError(f"gbp.json does not exist for {build}") from None

    def set_metadata(self, build: Build, metadata: GBPMetadata) -> None:
        """Save metadata to "gbp.json" in the binpkgs directory"""
        path = self.get_path(build, Content.BINPKGS) / "gbp.json"
        with path.open("w") as gbp_json:
            gbp_json.write(metadata.to_json())  # type: ignore # pylint: disable=no-member


def quick_check(file1: str, file2: str) -> bool:
    """Do an rsync-style quick check. Return true if files appear identical"""
    try:
        stat1 = os.stat(file1, follow_symlinks=False)
        stat2 = os.stat(file2, follow_symlinks=False)
    except FileNotFoundError:
        return False

    return stat1.st_mtime == stat2.st_mtime and stat1.st_size == stat2.st_size


def copy_or_link(link_dest: Path, dst_root: Path) -> Callable[[str, str], None]:
    """Create a copytree copy_function that uses rsync's link_dest logic"""

    def copy(src: str, dst: str, follow_symlinks: bool = True) -> None:
        relative = Path(dst).relative_to(dst_root)
        target = str(link_dest / relative)
        if quick_check(src, target):
            os.link(target, dst, follow_symlinks=follow_symlinks)
        else:
            shutil.copy2(src, dst, follow_symlinks=follow_symlinks)

    return copy


def make_package_from_lines(lines: Iterable[str]) -> Package:
    """Given the appropriate lines from Packages, return a Package object"""
    package_info: dict[str, str] = {}

    for line in lines:
        key, _, value = line.partition(":")
        key = key.rstrip().lower()
        value = value.lstrip()
        package_info[key] = value

    try:
        return Package(
            package_info["cpv"],
            package_info["repo"],
            package_info["path"],
            int(package_info["build_id"]),
            int(package_info["size"]),
            int(package_info["build_time"]),
        )
    except KeyError as error:
        raise ValueError(
            f"Package lines missing {error.args[0].upper()} value"
        ) from None


def make_packages(package_index_file: IO[str]) -> Iterable[Package]:
    """Yield Packages from Package index file

    Assumes file pointer is after the preamble.
    """
    while True:
        section_lines: list[str] = []
        while line := package_index_file.readline().rstrip():
            section_lines.append(line)

        if not section_lines:
            break

        yield make_package_from_lines(section_lines)
