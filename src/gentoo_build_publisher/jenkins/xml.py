"""XML Handling For Jenkins"""

import xml.etree.ElementTree as ET
from typing import TypeGuard

from gentoo_build_publisher.types import EbuildRepo, MachineJob
from gentoo_build_publisher.utils import read_package_file

CREATE_BUILD = read_package_file("create_machine_job.xml")
CREATE_REPO = read_package_file("create_repo_job.xml")
FOLDER = read_package_file("folder.xml")
PATH_SEPARATOR = "/"
PATHS = {
    "BRANCH_NAME": "scm/branches/hudson.plugins.git.BranchSpec/name",
    "BRANCH_PLUGIN": "definition/scm/branches/hudson.plugins.git.BranchSpec/name",
    "SCM_URL": "scm/userRemoteConfigs/hudson.plugins.git.UserRemoteConfig/url",
    "USER_REMOTE_URL": "definition/scm/userRemoteConfigs/hudson.plugins.git.UserRemoteConfig/url",
}


def install_plugin(plugin: str) -> str:
    """Return XML config for installing a Jenkins plugin"""
    return f'<jenkins><install plugin="{plugin}" /></jenkins>'


def build_repo(repo: EbuildRepo) -> str:
    """Return XML config for the given repo"""
    xml = ET.fromstring(CREATE_REPO)

    if is_element(branch := xml.find(PATHS["BRANCH_NAME"])):
        branch.text = f"*/{repo.branch}"
        if is_element(url := xml.find(PATHS["SCM_URL"])):
            url.text = repo.url
            return ET.tostring(xml).decode("UTF-8")

    raise ValueError("Invalid XML")  # pragma: no cover


def build_machine(job: MachineJob) -> str:
    """Return XML config for the given machine"""
    xml = ET.fromstring(CREATE_BUILD)
    parts = [
        "properties",
        "org.jenkinsci.plugins.workflow.job.properties.PipelineTriggersJobProperty",
        "triggers",
        "jenkins.triggers.ReverseBuildTrigger/upstreamProjects",
    ]
    repos_path = PATH_SEPARATOR.join(parts)

    if is_element(upstream_repos := xml.find(repos_path)):
        upstream_repos.text = ",".join(f"repos/{repo}" for repo in job.ebuild_repos)
        if is_element(url := xml.find(PATHS["USER_REMOTE_URL"])):
            url.text = job.repo.url
            if is_element(branch_name := xml.find(PATHS["BRANCH_PLUGIN"])):
                branch_name.text = f"*/{job.repo.branch}"
                return ET.tostring(xml).decode("UTF-8")

    raise ValueError("Invalid XML")  # pragma: no cover


def is_folder(xml_str: str) -> bool:
    """Return True if project_path is a folder"""
    tree = ET.fromstring(xml_str)

    return tree.tag == "com.cloudbees.hudson.plugins.folder.Folder"


def is_element(value: ET.Element | None) -> TypeGuard[ET.Element]:
    """Return True if the value is an Element instance"""
    return value is not None
