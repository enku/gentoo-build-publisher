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

.PHONY: test
test: .coverage

coverage-report: .coverage
	pdm run coverage html
	pdm run python -m webbrowser -t file://$(CURDIR)/htmlcov/index.html

build: $(sdist) $(wheel)

.PHONY: wheel
wheel: $(wheel)

.PHONY: sdist
sdist: $(sdist)

$(sdist): $(src) $(venv)
	pdm build --no-wheel

$(wheel): $(src) $(venv)
	pdm build --no-sdist

$(venv):
	rm -rf .venv
	pdm sync --dev
	touch $@

.PHONY: venv
venv: $(venv)


.PHONY: clean
clean: clean-build clean-venv
	rm -rf .coverage htmlcov .mypy_cache node_modules

.PHONY: clean-build
clean-build:
	rm -rf dist build

.PHONY: clean-venv
clean-venv:
	rm -rf .venv

.PHONY: shell
shell: $(venv)
	pdm run $(.SHELL) -l


.PHONY: pylint
pylint:
	pdm run pylint src tests


.PHONY: eslint
eslint:
	npx eslint src/gentoo_build_publisher/static


.PHONY: mypy
mypy:
	pdm run mypy


.PHONY: csslint
csslint:
	npx csslint src/gentoo_build_publisher/static

.PHONY: lint
lint: pylint mypy csslint eslint


.PHONY: fmt
fmt: $(venv)
	pdm run python -m isort --line-width=88 src tests
	pdm run python -m black src tests
