# BrainOS developer commands. See CLAUDE.md.
SHELL := /bin/bash
VENV  := .venv
PY    := $(VENV)/bin/python
NPM   := npm --prefix frontend

.PHONY: setup dev run build test test-backend test-frontend lint e2e bench schema clean

setup:  ## create .venv (Python 3.12) and install backend + frontend deps
	@command -v uv >/dev/null && uv venv --python 3.12 $(VENV) || python3.12 -m venv $(VENV)
	@if command -v uv >/dev/null; then uv pip install --python $(PY) -e "backend[dev]"; \
	  else $(PY) -m pip install -e "backend[dev]"; fi
	$(NPM) ci

build:  ## build the console + board app into frontend/dist
	$(NPM) run build

run: build  ## serve API + console + board from http://127.0.0.1:8000
	$(PY) -m brainos.server

dev:  ## backend with reload on :8000 + Vite dev server on :5173
	@trap 'kill 0' EXIT; \
	BRAINOS_STATIC_DIR=/nonexistent $(VENV)/bin/uvicorn --factory brainos.server.app:create_app --reload --reload-dir backend/src --port 8000 & \
	$(NPM) run dev

test: test-backend test-frontend  ## all unit/integration tests; writes reports/ for the console Tests tab

test-backend:
	@mkdir -p reports
	cd backend && ../$(PY) -m pytest -q --junitxml=../reports/pytest-junit.xml

test-frontend:
	@mkdir -p reports
	$(NPM) run test:report

lint:  ## ruff + mypy (strict) + tsc
	cd backend && ../$(VENV)/bin/ruff check src tests examples ../scripts && ../$(VENV)/bin/ruff format --check src tests examples ../scripts
	cd backend && ../$(VENV)/bin/mypy
	$(NPM) run typecheck

e2e: build  ## Playwright demo against a fresh server; writes reports/e2e.json
	node e2e/demo.cjs

bench:  ## measured throughput/latency on this machine -> docs/BENCHMARKS.md
	$(PY) scripts/bench.py --write docs/BENCHMARKS.md

schema:  ## regenerate contracts/event-envelope.v1.schema.json
	$(PY) scripts/export_schema.py

clean:
	rm -rf frontend/dist reports e2e/screenshots
