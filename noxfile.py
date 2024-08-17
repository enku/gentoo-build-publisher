# pylint: disable=missing-docstring
import nox


@nox.session(python=("3.11", "3.12", "3.13"))
def tests(session: nox.Session) -> None:
    session.run("pdm", "install", "--dev", external=True)
    session.run("pdm", "run", "coverage", "run", "./tests/runtests.py", external=True)
