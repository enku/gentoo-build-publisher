.SHELL := /bin/bash

name := $(shell pdm show --name)
version := $(shell pdm show --version)
sdist := dist/$(name)-$(version).tar.gz
venv := .venv/pyvenv.cfg
wheel := dist/$(subst -,_,$(name))-$(version)-py3-none-any.whl
src := $(shell find src -type f -print)
tests := $(shell find tests -type f -print)

PYTHONDONTWRITEBYTECODE=1

export PYTHONDONTWRITEBYTECODE


.coverage: $(venv) $(src) $(tests)
	pdm run coverage run ./tests/runtests.py

test: .coverage
.PHONY: test


coverage-report: .coverage
	pdm run coverage html
	pdm run python -m webbrowser -t file://$(CURDIR)/htmlcov/index.html

build: $(sdist) $(wheel)

wheel: $(wheel)
.PHONY: wheel


sdist: $(sdist)
.PHONY: sdist


$(sdist): $(src) $(venv)
	pdm build --no-wheel

$(wheel): $(src) $(venv)
	pdm build --no-sdist

$(venv):
	rm -rf .venv
	pdm sync --dev
	touch $@

venv: $(venv)
.PHONY: venv


clean: clean-build clean-venv
	rm -rf .coverage htmlcov .mypy_cache node_modules
.PHONY: clean


clean-build:
	rm -rf dist build
.PHONY: clean-build


clean-venv:
	rm -rf .venv
.PHONY: clean-venv


shell: $(venv)
	pdm run $(.SHELL) -l
.PHONY: shell


pylint:
	pdm run pylint src tests
.PHONY: pylint


eslint:
	npx eslint src/gentoo_build_publisher/static
.PHONY: eslint


mypy:
	pdm run mypy
.PHONY: mypy


csslint:
	npx csslint src/gentoo_build_publisher/static
.PHONY: csslint


lint: pylint mypy csslint eslint
.PHONY: lint


fmt: $(venv)
	pdm run python -m isort --line-width=88 src tests
	pdm run python -m black src tests
.PHONY: fmt
