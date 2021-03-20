"""GBP io"""
import os
import shutil
import tarfile


def extract_tarfile(name: str, target_dir: str):
    """Extract gzipped-tarball into work_dir"""
    os.makedirs(target_dir)

    with tarfile.open(name, mode="r") as tar_file:
        tar_file.extractall(target_dir)


def replace(old: str, new: str):
    """Replace old with new, preserving old"""
    if os.path.exists(old):
        new_old_name = f"{old}.old"

        if os.path.exists(new_old_name):
            shutil.rmtree(new_old_name)

        os.rename(old, new_old_name)

    os.makedirs(os.path.dirname(old), exist_ok=True)
    os.rename(new, old)
