# Concord developer commands. See DEVELOPMENT.md.
SHELL := /bin/bash
VENV  := .venv
PY    := $(VENV)/bin/python
NPM   := npm --prefix frontend
# the public adapter SDK, the backend, and the example third-party source plugin (editable)
PY_PKGS := -e packages/concord-adapter-sdk -e "backend[server,dev,nwb,dsp,live]" \
           -e examples/adapters/concord-example-adapter \
           -e packages/concord-brainflow -e packages/concord-bci2000 \
           -e "packages/concord-certify[dev]"
PLUGIN_SRC := ../packages/concord-adapter-sdk ../examples/adapters/concord-example-adapter \
              ../packages/concord-brainflow ../packages/concord-bci2000 ../packages/concord-certify
PACKAGE_TESTS := packages/concord-brainflow packages/concord-bci2000 examples/adapters/concord-example-adapter \
                 packages/concord-certify

.PHONY: setup dev run build test test-backend test-frontend lint e2e e2e-setup bench bench-live dist-check schema clean \
        dataset dataset-all model decoding-report dataset-t15 dataset-t15-day cursorclick-report e2e-communication

setup:  ## create .venv (Python 3.12) and install backend + frontend deps
	@command -v uv >/dev/null && uv venv --python 3.12 $(VENV) || python3.12 -m venv $(VENV)
	@if command -v uv >/dev/null; then uv pip install --python $(PY) $(PY_PKGS); \
	  else $(PY) -m pip install $(PY_PKGS); fi
	$(NPM) ci

build:  ## build the console + board app into frontend/dist
	$(NPM) run build

run: build  ## serve API + console + board from http://127.0.0.1:8000
	$(PY) -m concord.server

dev:  ## backend with reload on :8000 + Vite dev server on :5173
	@trap 'kill 0' EXIT; \
	CONCORD_STATIC_DIR=/nonexistent $(VENV)/bin/uvicorn --factory concord.server.app:create_app --reload --reload-dir backend/src --port 8000 & \
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
	# text files opened without encoding= are cp1252 on Windows (PLW1514: a ruff preview rule)
	cd backend && ../$(VENV)/bin/ruff check --preview --select PLW1514 src tests examples ../scripts ../packaging ../packages ../examples
	cd backend && ../$(VENV)/bin/mypy && ../$(VENV)/bin/mypy --strict examples/reference_app examples/center_out_task.py
	$(VENV)/bin/mypy --strict packages/concord-adapter-sdk/src/concord_adapter_sdk \
	  examples/adapters/concord-example-adapter/src/concord_example_adapter
	cd packages/concord-brainflow && ../../$(VENV)/bin/mypy --strict src/concord_brainflow
	cd packages/concord-bci2000 && ../../$(VENV)/bin/mypy --strict src/concord_bci2000
	cd packages/concord-certify && ../../$(VENV)/bin/mypy
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
	$(PY) -m concord.datasets.fetch

dataset-all:  ## all 13 FALCON H1 held-in calibration blocks (~66 MiB) for the decoding report
	$(PY) -m concord.datasets.fetch --all-calib

model:  ## train + evaluate the baseline decoder on downloaded blocks -> data/models/, reports/decoding.json
	$(PY) -m concord.decoding.evaluate_falcon

decoding-report: dataset-all  ## regenerate docs/DECODING.md from all 13 blocks
	$(PY) -m concord.decoding.evaluate_falcon --write docs/DECODING.md

# ---- Milestone 5 (P0): cursor + click dataset (Singer-Clark et al., Dryad, CC0). Dryad needs an
# API token for downloads: export DRYAD_TOKEN=... (or DRYAD_CLIENT_ID + DRYAD_CLIENT_SECRET).
dataset-t15:  ## T15 cursor+click demo subset (day 468 blocks 0-3, ~90 MiB) -> data/datasets/dryad-prr4xgxzq
	$(PY) -m concord.datasets.dryad

dataset-t15-day:  ## all 18 blocks of T15 day 468 (~472 MiB) for the cursor+click report
	$(PY) -m concord.datasets.dryad --subset day468

cursorclick-report: dataset-t15-day  ## decoders + click + word selection -> docs/CURSOR_CLICK.md, demo models
	$(PY) -m concord.evaluation.run_cursorclick --write docs/CURSOR_CLICK.md

e2e-communication: build  ## real board selects words from replayed T15 data (needs dataset-t15) -> reports/communication_e2e.json
	node e2e/communication.cjs

schema:  ## regenerate contracts/event-envelope.v1.schema.json
	$(PY) scripts/export_schema.py

clean:
	rm -rf frontend/dist reports e2e/screenshots

# ---- Milestone 5, workstream B: human ECoG (AJILE12, DANDI 000055; docs/ECOG.md) ----
.PHONY: dataset-ecog dataset-ecog-all ecog-report

dataset-ecog:  ## stream the 2 pinned demo ECoG slices (~157 MiB) to data/datasets/dandi-000055/
	$(PY) -m concord.datasets.fetch ajile12

dataset-ecog-all:  ## all 6 pinned ECoG slices (78.75 min, ~550 MiB)
	$(PY) -m concord.datasets.fetch ajile12 --all

ecog-report: dataset-ecog-all  ## ECoG move-vs-rest model -> data/models/, docs/ECOG_DECODING.md
	$(PY) -m concord.decoding.evaluate_ecog --write docs/ECOG_DECODING.md

# ---------------------------------------------------------------- Workstream F (M5): compatibility registry
.PHONY: compat compat-check

compat:  ## derive compat/registry.json (+ schema, docs/COMPATIBILITY.md section) from the evidence
	$(PY) -m concord.compat.build

compat-check:  ## fail if the committed compatibility registry is stale (run in CI)
	$(PY) -m concord.compat.build --check

# ---------------------------------------------------------------- Milestone 5, workstream A
# Decoder SDK (decoder plugins + model files in an isolated host) and the example decoder
# plugin. torch is an optional extra (concord-decoder-sdk[torch]); its tests skip without it.
PY_PKGS += -e "packages/concord-decoder-sdk[onnx,sklearn,dev]" -e examples/decoders/concord-example-decoder
PLUGIN_SRC += ../packages/concord-decoder-sdk ../examples/decoders/concord-example-decoder
PACKAGE_TESTS += packages/concord-decoder-sdk examples/decoders/concord-example-decoder

# ---------------------------------------------------------------- Milestone 5: hardware validation
# concord-hwval compares Concord recordings with independent reference recordings (LabRecorder
# XDF, Open Ephys Binary); docs/HARDWARE_VALIDATION.md. `make test` runs its synthetic-defect
# and CLI tests; `make test-hwval` also runs the real LabRecorderCLI and Open Ephys GUI
# (downloaded on first use, pinned by SHA-256, never vendored; Linux x86_64 with
# libpugixml1v5, xvfb and pulseaudio installed), as the CI workflow hwval.yml does.
PY_PKGS += -e "packages/concord-hwval[dev,openephys,capture]"
HWVAL := packages/concord-hwval
.PHONY: lint-hwval test-hwval
lint: lint-hwval
lint-hwval:  ## ruff + mypy --strict: hardware-validation toolkit (src + tests)
	cd $(HWVAL) && ../../$(VENV)/bin/ruff check . && ../../$(VENV)/bin/ruff format --check . && ../../$(VENV)/bin/mypy
test-backend: test-hwval-synthetic
.PHONY: test-hwval-synthetic
test-hwval-synthetic:
	cd $(HWVAL) && $(CURDIR)/$(PY) -m pytest -q -m "not reference_software"
test-hwval:  ## all hwval tests incl. real LabRecorder + Open Ephys GUI; none may be skipped
	cd $(HWVAL) && HWVAL_REQUIRE_REFERENCE_SOFTWARE=1 $(CURDIR)/$(PY) -m pytest -q -rs

.PHONY: lint-decoders
lint: lint-decoders
lint-decoders:  ## mypy --strict: decoder SDK + example decoder plugin
	cd packages/concord-decoder-sdk && ../../$(VENV)/bin/mypy src/concord_decoder_sdk
	cd examples/decoders/concord-example-decoder && ../../../$(VENV)/bin/mypy --strict src/concord_example_decoder

# ------------------------------------------------------------------------ M5-D
# Release workstream D: installation, desktop bundle, lab acceptance. Ordinary use needs none
# of these: `concord start` (pip install) or Concord.app (docs/INSTALL_MAC.md).
.PHONY: console-stage app app-smoke lab-acceptance lint-packaging
APP_EXE := $(if $(filter Darwin,$(shell uname -s)),packaging/dist/Concord.app/Contents/MacOS/Concord,packaging/dist/Concord/Concord)

console-stage:  ## copy the built console into the Python package (wheels and the app ship it)
	$(PY) packaging/stage_console.py --build

app:  ## desktop bundle (PyInstaller): Concord.app + .dmg on macOS, Concord/ on Linux -> packaging/dist/
	@if command -v uv >/dev/null; then uv pip install --python $(PY) -e packages/concord-bci2000 -r packaging/requirements.txt; \
	  else $(PY) -m pip install -e packages/concord-bci2000 -r packaging/requirements.txt; fi
	$(PY) packaging/build_app.py --build-console $(if $(filter Darwin,$(shell uname -s)),--dmg,)

app-smoke:  ## run the built bundle like a user (headless, crash recovery); add ARGS=--window for the window
	$(PY) packaging/smoke_test.py $(APP_EXE) --report reports/smoke-app.json $(ARGS)

lab-acceptance:  ## clean-room lab acceptance from built wheels in fresh venvs -> reports/lab-acceptance.json
	$(PY) scripts/lab_acceptance.py

lint-packaging:  ## ruff + mypy --strict for packaging/ (CI: package-linux)
	cd backend && ../$(VENV)/bin/ruff check ../packaging && ../$(VENV)/bin/ruff format --check ../packaging
	cd backend && ../$(VENV)/bin/mypy --strict ../packaging/app_entry.py ../packaging/stage_console.py \
	  ../packaging/build_app.py ../packaging/smoke_test.py

# ---- M5-E: performance at scale (docs/PERFORMANCE.md) -------------------------------------
.PHONY: bench-scale
bench-scale:  ## scaling to 4096 ch, multi-stream, 10-min soak, end-to-end over WS (~30 min) -> docs/BENCHMARKS_SCALE.md
	@mkdir -p reports
	$(PY) scripts/bench_scale.py --json reports/bench_scale.json --write docs/BENCHMARKS_SCALE.md
