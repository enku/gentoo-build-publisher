# pylint: disable=missing-docstring
import nox


@nox.session(python=("3.12", "3.13", "3.14"))
def tests(session: nox.Session) -> None:
    dev_dependencies = nox.project.load_toml("pyproject.toml")["dependency-groups"][
        "dev"
    ]
    session.install(".[redis,test]", *dev_dependencies)

    session.run("coverage", "run", "-m", "tests")
    session.run("coverage", "report", "-m")
