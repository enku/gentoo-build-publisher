.SHELL := /bin/bash

name := $(shell pdm show --name)
version := $(shell pdm show --version)
sdist := dist/$(name)-$(version).tar.gz
wheel := dist/$(subst -,_,$(name))-$(version)-py3-none-any.whl
src := $(shell find src -type f -print)
tests := $(shell find tests -type f -print)
python_src := $(filter %.py, $(src) $(tests))

PYTHONDONTWRITEBYTECODE=1

export PYTHONDONTWRITEBYTECODE


.coverage: $(src) $(tests)
	pdm run coverage run -m tests

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


$(sdist): $(src)
	pdm build --no-wheel

$(wheel): $(src)
	pdm build --no-sdist

clean: clean-build
	rm -rf .coverage .fmt htmlcov .mypy_cache node_modules
.PHONY: clean


clean-build:
	rm -rf dist build
.PHONY: clean-build


shell:
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


.PHONY: typos
typos:
	typos --format=brief


lint: pylint mypy csslint eslint typos
.PHONY: lint


.fmt: $(python_src)
	pdm run python -m isort --line-width=88 $?
	pdm run python -m black $?
	touch $@

.PHONY: fmt
fmt: .fmt


.PHONY: update
update:
	pdm update --update-eager
