# BrainOS developer commands. See CLAUDE.md.
SHELL := /bin/bash
VENV  := .venv
PY    := $(VENV)/bin/python
NPM   := npm --prefix frontend
# the public adapter SDK, the backend, and the example third-party source plugin (editable)
PY_PKGS := -e packages/brainos-adapter-sdk -e "backend[server,dev,nwb,dsp,live]" \
           -e examples/adapters/brainos-example-adapter \
           -e packages/brainos-brainflow -e packages/brainos-bci2000 \
           -e "packages/brainos-certify[dev]"
PLUGIN_SRC := ../packages/brainos-adapter-sdk ../examples/adapters/brainos-example-adapter \
              ../packages/brainos-brainflow ../packages/brainos-bci2000 ../packages/brainos-certify
PACKAGE_TESTS := packages/brainos-brainflow packages/brainos-bci2000 examples/adapters/brainos-example-adapter \
                 packages/brainos-certify

.PHONY: setup dev run build test test-backend test-frontend lint e2e e2e-setup bench bench-live dist-check schema clean \
        dataset dataset-all model decoding-report dataset-t15 dataset-t15-day cursorclick-report

setup:  ## create .venv (Python 3.12) and install backend + frontend deps
	@command -v uv >/dev/null && uv venv --python 3.12 $(VENV) || python3.12 -m venv $(VENV)
	@if command -v uv >/dev/null; then uv pip install --python $(PY) $(PY_PKGS); \
	  else $(PY) -m pip install $(PY_PKGS); fi
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
	@for p in $(PACKAGE_TESTS); do (cd $$p && $(CURDIR)/$(PY) -m pytest -q) || exit 1; done

test-frontend:
	@mkdir -p reports
	$(NPM) run test:report

lint:  ## ruff + mypy (strict) + tsc
	cd backend && ../$(VENV)/bin/ruff check src tests examples ../scripts && ../$(VENV)/bin/ruff format --check src tests examples ../scripts
	cd backend && ../$(VENV)/bin/ruff check $(PLUGIN_SRC) && ../$(VENV)/bin/ruff format --check $(PLUGIN_SRC)
	cd backend && ../$(VENV)/bin/mypy && ../$(VENV)/bin/mypy --strict examples/reference_app examples/center_out_task.py
	$(VENV)/bin/mypy --strict packages/brainos-adapter-sdk/src/brainos_adapter_sdk \
	  examples/adapters/brainos-example-adapter/src/brainos_example_adapter
	cd packages/brainos-brainflow && ../../$(VENV)/bin/mypy --strict src/brainos_brainflow
	cd packages/brainos-bci2000 && ../../$(VENV)/bin/mypy --strict src/brainos_bci2000
	cd packages/brainos-certify && ../../$(VENV)/bin/mypy
	$(NPM) run typecheck
	# M5-C: the opt-in desktop control bridge (SDK-only, separate process)
	cd backend && ../$(VENV)/bin/mypy --strict examples/desktop_bridge

e2e-setup:  ## one-time: install Playwright (repo-local, not saved) + Chromium
	npm install --no-save --no-package-lock playwright@1.63.0
	npx playwright install chromium

e2e: build  ## Playwright demo against a fresh server; writes reports/e2e.json
	node e2e/demo.cjs

dist-check:  ## build wheels; adapter dev / lab / app dev flows in fresh virtualenvs
	$(PY) scripts/dist_check.py

bench:  ## measured throughput/latency on this machine -> docs/BENCHMARKS.md
	$(PY) scripts/bench.py --write docs/BENCHMARKS.md

bench-live:  ## LSL / Open Ephys -> pipeline -> decoder, measured here -> docs/BENCHMARKS_LIVE.md
	$(PY) scripts/bench_live.py --write docs/BENCHMARKS_LIVE.md

dataset:  ## download the verified demo recordings (2 FALCON H1 blocks, ~8.7 MiB) to data/datasets/
	$(PY) -m brainos.datasets.fetch

dataset-all:  ## all 13 FALCON H1 held-in calibration blocks (~66 MiB) for the decoding report
	$(PY) -m brainos.datasets.fetch --all-calib

model:  ## train + evaluate the baseline decoder on downloaded blocks -> data/models/, reports/decoding.json
	$(PY) -m brainos.decoding.evaluate_falcon

decoding-report: dataset-all  ## regenerate docs/DECODING.md from all 13 blocks
	$(PY) -m brainos.decoding.evaluate_falcon --write docs/DECODING.md

# ---- Milestone 5 (P0): cursor + click dataset (Singer-Clark et al., Dryad, CC0). Dryad needs an
# API token for downloads: export DRYAD_TOKEN=... (or DRYAD_CLIENT_ID + DRYAD_CLIENT_SECRET).
dataset-t15:  ## T15 cursor+click demo subset (day 468 blocks 0-3, ~90 MiB) -> data/datasets/dryad-prr4xgxzq
	$(PY) -m brainos.datasets.dryad

dataset-t15-day:  ## all 18 blocks of T15 day 468 (~472 MiB) for the cursor+click report
	$(PY) -m brainos.datasets.dryad --subset day468

cursorclick-report: dataset-t15-day  ## decoders + click + word selection -> docs/CURSOR_CLICK.md, demo models
	$(PY) -m brainos.evaluation.run_cursorclick --write docs/CURSOR_CLICK.md

schema:  ## regenerate contracts/event-envelope.v1.schema.json
	$(PY) scripts/export_schema.py

clean:
	rm -rf frontend/dist reports e2e/screenshots

# ---- Milestone 5, workstream B: human ECoG (AJILE12, DANDI 000055; docs/ECOG.md) ----
.PHONY: dataset-ecog dataset-ecog-all ecog-report

dataset-ecog:  ## stream the 2 pinned demo ECoG slices (~157 MiB) to data/datasets/dandi-000055/
	$(PY) -m brainos.datasets.fetch ajile12

dataset-ecog-all:  ## all 6 pinned ECoG slices (78.75 min, ~550 MiB)
	$(PY) -m brainos.datasets.fetch ajile12 --all

ecog-report: dataset-ecog-all  ## ECoG move-vs-rest model -> data/models/, docs/ECOG_DECODING.md
	$(PY) -m brainos.decoding.evaluate_ecog --write docs/ECOG_DECODING.md

# ---------------------------------------------------------------- Workstream F (M5): compatibility registry
.PHONY: compat compat-check

compat:  ## derive compat/registry.json (+ schema, docs/COMPATIBILITY.md section) from the evidence
	$(PY) -m brainos.compat.build

compat-check:  ## fail if the committed compatibility registry is stale (run in CI)
	$(PY) -m brainos.compat.build --check
