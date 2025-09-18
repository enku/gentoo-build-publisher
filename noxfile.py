# pylint: disable=missing-docstring
import nox


@nox.session(python=("3.12", "3.13", "3.14"))
def tests(session: nox.Session) -> None:
    session.run("pdm", "install", "--dev", "-G:all", external=True)
    session.run("pdm", "run", "coverage", "run", "-m", "tests", external=True)
