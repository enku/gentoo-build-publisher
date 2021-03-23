"""GBP io"""
import os
import tarfile


def extract_tarfile(name: str, target_dir: str):
    """Extract gzipped-tarball into work_dir"""
    with tarfile.open(name, mode="r") as tar_file:
        tar_file.extractall(target_dir)


def symlink(source: str, target: str):
    """If target is a symlink remove it. If it otherwise exists raise an error"""
    if os.path.islink(target):
        os.unlink(target)
    elif os.path.exists(target):
        raise EnvironmentError(f"{target} exists but is not a symlink")

    os.symlink(source, target)
