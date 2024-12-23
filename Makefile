ENV ?=
include .env
-include .env.$(ENV)

MAKE = make
PYTHON = python

check-deps:  ## Check new versions and update deps
	$(PYTHON) -m pur -r requirements.dev.txt -d

update-dev-deps:  ## Check new versions and update deps
	$(PYTHON) -m pur -r requirements.dev.txt

install-deps:  ## Install dependencies
	$(PYTHON) -m pip install -r requirements.txt

isort:
	$(PYTHON) -m isort --check-only . --profile black

black:
	$(PYTHON) -m black --check -l 79 .

mypy-install:
	$(PYTHON) -m mypy --install-types

mypy:
	$(PYTHON) -m mypy .

flake8:
	$(PYTHON) -m flake8 --per-file-ignores="__init__.py:F401" .

bandit:
	$(PYTHON) -m bandit -c pyproject.toml -r .

lint: isort black mypy bandit flake8

install: install-deps

enable-pre-commit:
	pre-commit install

dev-install-deps:
	$(PYTHON) -m pip install -r requirements.dev.txt

dev-install: dev-install-deps update-dev-deps mypy-install enable-pre-commit

api:
	uvicorn api:dzg_api --host 127.0.0.1 --port 8502 --workers 1
