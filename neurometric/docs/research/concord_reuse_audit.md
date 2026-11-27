# Concord reuse audit for NeuroMetric

Date: 2026-11-27. Scope: which parts of the Concord repository (`/home/user/concord`, Concord
0.3.2, event schema 1.4, commit `85ce957`) NeuroMetric (functional-outcome measurement for BCIs
and assistive technology) can reuse, and how to import Concord data into NeuroMetric.

Conventions: labels follow `CONVENTIONS.md`. Everything in this file is **[V]** (checked in this
session against the Concord source code, its tests or files it produced) unless it carries
another label. Nothing in Concord was modified; all work products are under `neurometric/`.

---

## 0. Summary

| Component | Recommendation |
| --- | --- |
| Event envelope + provenance/quality model (`contracts/events.py`, JSON Schema) | **Port and adapt with attribution** (design pattern + field semantics); read Concord files with an importer, do not depend on the package |
| Concord recording format (`concord.recording/1`) + replay reader | **Reference only**: write an independent ~150-line NeuroMetric importer (spec in §5) |
| Communication board pointer integration / dwell / scan logic (`frontend/src/apps/board/model.ts`, `methods.ts`) | **Port and adapt with attribution** (the integration rule is needed to reconstruct x, y losslessly; the input-method taxonomy maps onto NeuroMetric's task battery) |
| T15 cursor+click evaluation metrics (`evaluation/cursorclick.py`) | **Port and adapt** the generic pieces (event matching with tolerance, achieved bitrate, false activations/min, trial-completion); the rest is T15-specific |
| Simulated profiles A/B (`adapters/simulated/`) | **Reference only**: not a degradation simulator (fixed noise + quantization + constant discrete latency; no drift, no dropout model) |
| Scripted test decoder (`testing/scripted.py`) | **Reference only** (good pattern for deterministic ground truth); used here to generate the importer fixture |
| Command router click rule (threshold / debounce / refractory / hysteresis) | **Port and adapt** as a NeuroMetric "decoder-output → discrete event" stage of the degradation simulator |
| Recorder durability (`runtime/recorder.py`) | **Reference only** (the 0600 files / lock / flush / recovery design is good; NeuroMetric's recorder should copy the ideas, not the code) |
| Session log + export bundle + `concord reproduce` | **Reference only** (pattern for NeuroMetric replay/reproducibility bundles) |
| `security.py` (bind policy, private files, log redaction) | **Port and adapt** (stdlib only, ~300 lines, small and well tested) if NeuroMetric ships a local server |
| `concord-certify`, `concord-hwval` | **Do not reuse** (certifies neural source plugins against Concord's adapter SDK; wrong domain). Reuse only the idea of a report with an explicit, evidence-derived validation level |
| Adapter SDK / decoder SDK / plugin host IPC | **Do not reuse** (neural-signal plugin APIs; NeuroMetric's devices are mouse/switch/gaze/BCI-cursor input) |
| Desktop control bridge (`backend/examples/desktop_bridge`) | **Do not reuse** for input capture (it *drives* the OS pointer from decoded commands; it does not capture mouse/switch/gaze input) |
| Python / TS SDK `CommandGuard` | **Reference only** (staleness + dead-man rules are worth mirroring if NeuroMetric consumes a live Concord stream) |

**License blocker for everything above:** Concord is declared **"Proprietary"** (§1). There is
no LICENSE file and no grant. "Reuse" and "port with attribution" are only lawful if the
NeuroMetric rights holder also holds Concord's rights or obtains written permission. Until that
is recorded, treat every "port" row as "reference only" and write clean-room code from the
field specifications in §4–§5 (facts about a file format are not themselves copyrightable
[INF]; this is not legal advice).

---

## 1. License

| Where | What it says |
| --- | --- |
| `LICENSE` / `COPYING` at repo root | **absent** |
| `backend/pyproject.toml` (`concordos` 0.3.2) | `license = { text = "Proprietary" }` |
| `packages/*/pyproject.toml` (adapter-sdk, decoder-sdk, certify, hwval, brainflow, bci2000) | `license = { text = "Proprietary (internal preview)" }` |
| `CITATION.cff` | no license field; authors "Concord contributors"; version `0.3.0` (pyproject says `0.3.2`) |
| git history | 94 commits, a single author identity |
| Third-party content | Datasets are never committed (downloaded, pinned by SHA-256; DANDI terms forbid redistribution). The GPL Open Ephys client is downloaded at test time, not vendored. Runtime deps are permissive (pydantic, numpy, scipy, httpx, websockets, fastapi). |

Consequences for NeuroMetric:

1. Do not add `concordos` as a dependency of a product that will be distributed under different
   terms unless the rights holder grants it in writing; it is also not on PyPI (LIMITATIONS.md,
   "Nothing is published to PyPI yet").
2. Reading Concord-format files (an importer) needs no Concord code: §5 gives the format.
3. If the rights holder is the same, record an internal license/assignment note in
   `neurometric/docs/regulatory/` before porting code, and keep a `NOTICE`/attribution header in
   each ported file ("Adapted from Concord <path> @85ce957").

---

## 2. Environment and test evidence

### 2.1 Install

```bash
SP=<scratchpad>
uv venv --python /usr/local/bin/python3.13 $SP/venv313
uv pip install --python $SP/venv313/bin/python \
  -e packages/concord-adapter-sdk -e packages/concord-decoder-sdk \
  -e "backend[server,dev,nwb,dsp,live]" -e examples/adapters/concord-example-adapter \
  -e packages/concord-brainflow -e packages/concord-bci2000 -e "packages/concord-certify[dev]"
# added after the first full run (Makefile:134 also installs these):
uv pip install --python $SP/venv313/bin/python \
  -e "packages/concord-decoder-sdk[onnx,sklearn,dev]" -e examples/decoders/concord-example-decoder
```

* The Makefile's `make setup` pins **Python 3.12** (`uv venv --python 3.12`); `pyproject` says
  `requires-python >= 3.12`. Python **3.13.x** installed and ran every suite below with no
  compatibility failure attributable to 3.13 (see §2.2).
* I first installed the package set of the Makefile's first `PY_PKGS` line only and missed the
  later `PY_PKGS +=` line (Makefile:134), which adds `packages/concord-decoder-sdk[onnx,sklearn,dev]`
  and `examples/decoders/concord-example-decoder`; that produced the single error in the full
  run below (`test_decoder_example.py`: "the example decoder plugin is not installed"). After
  installing both, the decoder tests passed (17 passed). This was my setup error, not a Concord
  defect; `make setup` and CI (`.github/workflows/ci.yml`) install both.
* `make setup` also runs `npm ci` inside `frontend/`. To keep the Concord tree unmodified I ran the
  frontend in a copy (`$SP/fe/frontend`) with `compat/` symlinked.

### 2.2 Test results (exact commands, run 2026-11-27)

All backend commands ran from `/home/user/concord/backend` with
`$SP/venv313/bin/python -m pytest -q -p no:cacheprovider` (`-p no:cacheprovider` keeps
`.pytest_cache` out of the Concord tree).

| Subset | Command (files) | Result |
| --- | --- | --- |
| Contracts, cursor+click, recorder, runtime, SDK guard, control, sessions/export/reproduce, security | `tests/test_contracts.py tests/test_cursorclick_format.py tests/test_cursorclick_chain.py tests/test_cursorclick_real.py tests/test_kalman_click.py tests/test_recording_autostop.py tests/test_recording_names.py tests/test_m5_recording_limits.py tests/test_m5_recovery.py tests/test_m5_sessions.py tests/test_m5_security.py tests/test_runtime.py tests/test_adapters.py tests/test_sdk.py tests/test_sdk_guard.py tests/test_control.py tests/test_control_state.py` | **304 passed, 11 skipped, 0 failed** (52 s) |
| per file (collected) | contracts 87 · adapters 30 · runtime 27 · control 22 · control_state 15 · kalman_click 22 · cursorclick_format 10 · cursorclick_chain 3 (all skipped) · cursorclick_real 8 (all skipped) · m5_recording_limits 22 · m5_recovery 8 · m5_sessions 5 (includes export + `reproduce`, and the session/audit log) · m5_security 22 · recording_names 14 · recording_autostop 2 · sdk 5 · sdk_guard 13 | |
| Full backend suite | `pytest -q -p no:cacheprovider -rs` | **874 passed, 43 skipped, 1 error** (348 s). The error = missing example decoder in my first install (see above); after installing it `tests/test_decoder_example.py tests/test_decoder_pipeline.py` → **17 passed**. Skips: 39 real-data tests (FALCON H1 ×19, AJILE12 ×9, T15 ×11; datasets not downloaded), tkinter ×2, Xvfb/xdotool ×1 (desktop bridge), onnx ×1 (before the decoder-SDK extra was installed). |
| `concord-certify` | `cd packages/concord-certify && pytest -q -p no:cacheprovider` | **88 passed** (90 s) |
| Other packages (same command in each dir) | concord-decoder-sdk · concord-brainflow · concord-bci2000 · example adapter · example decoder | **91 passed / 2 skipped · 41 passed · 38 passed / 1 skipped · 2 passed · 3 passed**. `concord-adapter-sdk` has no own tests dir (covered by backend `test_plugin_*`). `concord-hwval` not installed/run (needs LabRecorder / Open Ephys GUI; irrelevant to NeuroMetric). |
| Frontend (board model, board UI, boundary, TS SDK, guard) | `npx vitest run src/apps/board src/sdk` | **108 passed (5 files)** |
| Frontend full + typecheck | `npx vitest run` ; `npx tsc -b` | **225 passed (17 files)**; tsc exit 0. (In the copy, 1 test failed until `compat/` was symlinked: it reads `../compat/registry.json`; an artifact of the copy, not a Concord defect.) |

In the targeted subset, the 11 skips are all the T15 real-data tests: *"T15 cursor+click files not found in
data/datasets/dryad-prr4xgxzq"*. Downloading them needs a Dryad account/token (LIMITATIONS.md),
which this session does not have. **Therefore the numbers in docs/CURSOR_CLICK.md (angle error,
click precision, word-selection accuracy) were not reproduced here**; only the format reader
(on synthetic `.mat` fixtures) and the metric functions' unit tests ran.

### 2.3 Fixture generation (also a test of the recorder end to end)

`neurometric/tests/fixtures/concord/generate_concord_fixtures.py` drives Concord's own `Runtime`
+ `Recorder` and wrote three genuine `concord.recording/1` files (§5.4). Checks on the output:
header valid, one `session_id` per file, `seq` strictly increasing, `timestamp_ns`
non-decreasing, and — for the decoded fixture — integrating the decoded pointer stream with the
board's rule lands at exactly (0.625, 0.125) when the single decoded click fires, matching the
scripted target. This reproduces the claim tested in
`tests/test_control_state.py::test_scripted_cursor_click_through_the_pipeline`.

---

## 3. Component-by-component

Format per component: location · what it does · test evidence · quality · fit · recommendation.

### 3.1 Event envelope, capabilities, provenance, quality

* **Location:** `backend/src/concord/contracts/events.py` (502 lines), `capabilities.py`,
  `protocol.py`; exported JSON Schema `contracts/event-envelope.v1.schema.json`
  (`$id https://concord.local/schemas/event-envelope.v1.json`, title "Concord EventEnvelope 1.4").
* **What:** a pydantic v2 discriminated union of 13 event types; each maps to exactly one
  capability; `extra="forbid"`, frozen, NaN/Inf rejected. Provenance rules (raw signal vs
  behavioral label vs simulated vs decoded intent) are enforced in a model validator.
* **Tests:** `test_contracts.py` 87 passed (includes a schema-drift test against the committed
  JSON Schema).
* **Quality:** high. Strict, small, no I/O, numpy optional.
* **Caveat (documentation vs artifact):** the JSON Schema file encodes field types/ranges but
  **not** the cross-field rules (capability↔event type, provenance kind↔event type,
  `decoded_intent ⇒ model_id`, `historical ⇒ replayed`). A consumer validating only against the
  JSON Schema accepts envelopes Concord's own validator rejects. The NeuroMetric importer must
  re-implement those checks (listed in §4.3).
* **Fit:** the *provenance separation* idea is exactly what NeuroMetric needs to keep
  "real participant input", "simulated", "replayed" and "decoder-generated" apart in outcome
  metrics. The payloads themselves are neural-BCI shaped (velocity intents, features) and do not
  cover mouse/switch/gaze (no absolute position, no button up/down, no scroll, no dwell).
* **Recommendation:** **port and adapt with attribution** the provenance/quality design
  (`kind`, `synthetic`, `replayed`, `model_id`, `model_origin`, `quality.score/flags`), subject
  to §1. Do not depend on the package.

### 3.2 Recording format and replay

* **Location:** `adapters/replay/format.py` (`RecordingHeader`, `ConcordRecordingSource`),
  `adapters/replay/adapter.py` (`ReplayAdapter`: timing, speed 0.1–64×, loop, pause),
  `runtime/recorder.py` (632 lines).
* **What:** JSONL; line 1 header, then one validated envelope per line in `seq` order. Recorder:
  0600 files, OS lock, 0.25 s flush, fsync on stop, crash recovery into
  `.recovery.json`/`.discarded.bin`, size/duration/free-disk limits, `exclude_raw`.
* **Tests:** runtime record→replay (`test_runtime.py`), recovery 8, limits 22, names 14,
  autostop 2 — all passed. Fixture generation (§2.3) exercised it end to end.
* **Quality:** high; durability design is careful.
* **Limits that matter for NeuroMetric:** what is recorded is the **bus**, i.e. events, not what
  an application *did*. `control.state` notices are per-subscriber and are **not recorded**
  (LIMITATIONS.md, confirmed in code). App-side state (board cursor position, dwell selections,
  scan highlights) is never in a Concord recording; it exists only in the board's
  `window.__concordBoard` snapshot (version 1). Recordings started after connect contain no
  initial `device.status`. Replay cannot seek.
* **Recommendation:** **reference only**; write an independent reader (§5). Copy the recorder's
  durability ideas into NeuroMetric's own session recorder.

### 3.3 Communication board (participant board) and its input methods

* **Location:** `frontend/src/apps/board/` — `model.ts` (577 lines, pure reducer, no clocks),
  `methods.ts`, `snapshot.ts`, `provenance.ts`, `settings.ts`.
* **What:** device-agnostic AAC-style board. Methods chosen from granted capabilities:
  `cursor_click` (pointer + selection), `cursor_dwell` (pointer only), `navigate`, `direct`
  (select/activate/cancel), `scan`. Workspace = unit square, x right, **y down**, origin top-left,
  cursor starts at (0.5, 0.5), clamped to [0, 1]; tile = `row*cols+col`.
  Pointer integration: `pos += v·dt`, `dt` = difference of `device_timestamp_ns` (else
  `timestamp_ns`) between consecutive pointer events of the same session and clock, clamped to
  `[0, MAX_DT_S = 0.1 s]`; the first event after a (re)start only sets the clock. Click debounce
  `clickRefractoryMs` on the event clock. **Dwell timing uses the browser wall clock (`nowMs`),
  not event time**, and arms only after the cursor moved.
* **Tests:** vitest 108 passed for board + SDK (model, UI, boundary rule that apps import only the
  SDK); Python mirror `evaluation/board_e2e.py` / `cursorclick.board_chain_positions`.
* **Fit:** high for the *task battery* idea (selection by click/dwell/scan/navigation on a grid is
  a standard functional task) and essential for the importer (velocity → position).
  LIMITATIONS.md: not keyboard/mouse operable by design, no usability/accessibility evaluation,
  fixed 200-word prediction list.
* **Recommendation:** **port and adapt with attribution** the pure pieces (`tileAt`, the
  integration rule, method availability logic, `SelectionRecord {n, page, tile, label, via,
  atMs, cursor, event}`) — subject to §1. Do not reuse the UI.

### 3.4 Cursor + click evaluation (T15) and decoders

* **Location:** `evaluation/cursorclick.py` (275 lines), `evaluation/run_cursorclick.py`,
  `evaluation/board_e2e.py`, `decoding/{kalman,click,ridge,lda,metrics,monitor}.py`,
  `adapters/cursorclick/{reader,source}.py`.
* **What:** offline, open-loop metrics: angle error vs ReFIT-style intention, R², anchored
  endpoints, n×n board accuracy, click matching (greedy one-to-one within ±250 ms), clicks/min,
  precision/recall vs the original decoder, false activations/min, trials with an on-target click,
  achieved bitrate `(correct − wrong)·log2(N − 1)/s` floored at 0.
* **Tests:** `test_kalman_click.py` 22 passed, `test_cursorclick_format.py` 10 passed; the 11
  real-data tests skipped (no Dryad data) — see §2.2.
* **Quality:** good, explicit about open-loop limits. Most functions take a `T15Block`, so they
  are coupled to that dataset's structure.
* **Fit:** the generic metrics (event matching with tolerance, bitrate, false activations per
  minute, trial completion) are directly NeuroMetric task metrics; T15-specific labelling is not.
* **Recommendation:** **port and adapt** the generic metric functions (re-typed on NeuroMetric
  events); **reference only** for the rest. Note the bitrate formula is the grid/"achieved
  bitrate" form, not Wolpaw ITR; NeuroMetric should report which one it uses.

### 3.5 Simulated decoders / profiles — do they model degradation?

| Source | What it actually does | Noise | Latency | Drift | Dropout |
| --- | --- | --- | --- | --- | --- |
| Simulated Profile A `sim-a` (`adapters/simulated/profile_a.py`) | operator sets normalized velocity in [−1, 1]² (dead-man 0.5 s); emitted at 50 Hz as int16-quantized `vx, vy` × max_speed 2.0 workspace/s | additive Gaussian, σ = 0.01 normalized (= 0.02 workspace/s), clipped | **pointer: none**; selection: constant 30 ms | none | none in data; 2 % of packets get a `low_link_quality` flag (quality score 0.6) but values are unchanged |
| Simulated Profile B `sim-b` | selection + character text from operator; JSON lines, ms clock | none on data | constant 150 ms (selection/text) | none | none |
| Fault injection `/api/v1/sim/faults` | `link_drop` (reconnect), `link_fail`, `malformed_packet`, `timestamp_regression` (−REGRESSION_US) | — | — | — | link-level only, operator-triggered |
| Selection `confidence` (A, B) | **random**: A `uniform(0.85, 0.99)`, B `uniform(0.70, 0.95)` | — | — | — | — |
| Scripted test decoder (`testing/scripted.py`) | piecewise-constant scripted vx/vy/click through an identity "model" and the real router | none | pipeline only | none | none |
| LSL `SyntheticEphysPublisher` | noise + spikes cosine-tuned to a latent 2-D velocity (exercises decoding) | yes (signal level) | — | none | — |
| `decoding/monitor.py` | *detects* feature shift / output drift on a running decoder (heuristic thresholds) | — | — | detection only | — |

**Conclusion:** Concord has **no decoder-degradation simulator**. The documentation's "the
simulator adds profile-specific quantization, noise, and latency" (ARCHITECTURE.md §5.1,
intent_source.py) is true only in a narrow sense: latency applies to discrete intents only, noise
to pointer only, with fixed parameters and no drift, no dropout, no gain/bias error, no
false-positive click model. NeuroMetric must build its own simulator. Reusable *ideas*: the
router click rule (threshold, debounce, refractory, hysteresis, min-confidence gate) and pointer
mapping (gain, dead-zone, clamp, y inversion) as the final stage of a simulated decoder.
**Recommendation:** profiles — reference only; router rules — port and adapt (subject to §1).
Never import Concord simulated `confidence` as a real confidence.

### 3.6 Command router, authorization, CommandGuard

* **Location:** `runtime/router.py` (465 lines), `runtime/control.py`, `sdk/guard.py`,
  `frontend/src/sdk/guard.ts`.
* **Tests:** control 22, control_state 15, sdk_guard 13, TS guard tests — passed.
* **Fit:** NeuroMetric measures, it does not route commands; but a live importer should honour
  the same staleness semantics (drop commands older than 500 ms; dead-man → zero velocity).
* **Recommendation:** reference only (router click rule → §3.5).

### 3.7 Sessions, audit log, export, reproduce

* **Location:** `runtime/sessions.py` (`log.jsonl` entries `{at_ns, kind, ...}`),
  `server/audit.py` (`SessionAuditMiddleware`), `runtime/export.py`
  (`concord.session-bundle/1` zip + `manifest.json` with SHA-256), `reproduce.py`.
* **Tests:** `test_m5_sessions.py` 5 passed, including export → `reproduce(bundle)` →
  `status == "reproduced"`, max decoded difference 0.0, and the operator-action log kinds.
* **Fit:** strong pattern for NeuroMetric's replay/reproducibility (hash-manifested bundle,
  personal data excluded by default, a `reproduce` command with exit codes 0/1/2).
* **Recommendation:** **reference only** (re-implement; the code is coupled to Concord's server,
  models and recordings).

### 3.8 Security helpers

* **Location:** `backend/src/concord/security.py` (296 lines, stdlib only): loopback bind policy,
  0700/0600 private dirs/files, permission hardening, secret/IP/home-path log redaction,
  rotating redacting log handler; `server/origin.py` (`LocalOriginMiddleware`, DNS-rebinding
  refusal).
* **Tests:** `test_m5_security.py` 22 passed.
* **Recommendation:** **port and adapt with attribution** (subject to §1) if NeuroMetric runs a
  local web server collecting participant data.

### 3.9 Certification / conformance harness (`packages/concord-certify`, `concord-hwval`)

* **What:** runs a *neural source plugin* in Concord's plugin host and checks rate, jitter, clock
  domain, throughput, latency, reconnect, resource use; writes a report with a validation level
  (`adapter_implementation` granted by the toolkit; `protocol_tested` on operator statement;
  `hardware_tested` on an Ed25519-signed attestation; `human_participant_validated` never).
* **Tests:** see §2.2.
* **Fit:** low; NeuroMetric's devices are input devices, not neural sources, and the harness is
  bound to the adapter SDK IPC. The *evidence-derived level* concept (levels are computed from
  evidence, never typed in) is worth copying for NeuroMetric's device-validation claims.
* **Recommendation:** **do not reuse** code; reference the levels concept.

### 3.10 Adapter SDK, decoder SDK, cross-platform pieces

* Adapter SDK (`packages/concord-adapter-sdk`): read-only plugin API for neural sources (roles
  SIGNAL, SPIKE_COUNTS, BEHAVIOR, MARKERS, DECODER_OUTPUT). Decoder SDK: decoder plugins/model
  files (ONNX, sklearn, TorchScript) in an isolated host. BrainFlow / BCI2000 plugins.
* None captures OS input (mouse, switch, gaze). The only OS-facing component,
  `backend/examples/desktop_bridge`, goes the other way (decoded command → OS pointer via
  xdotool/pynput; relative moves and primary click only; pynput backend untested per
  LIMITATIONS.md).
* **Recommendation:** **do not reuse**. Exception worth noting: the BCI2000 App Connector plugin
  could matter later if NeuroMetric wants BCI2000 cursor tasks; reference only.

### 3.11 Benchmarks

`scripts/bench.py`, `docs/BENCHMARKS*.md`: runtime envelope throughput and WebSocket latency on a
4-vCPU cloud VM (Python 3.12.3). Software-pipeline numbers only. **Reference only**; not
re-run here.

---

## 4. Precise schema of Concord intent / cursor events

### 4.1 Envelope (every event)

| Field | Type / constraint | Semantics |
| --- | --- | --- |
| `schema_version` | `"^\d+\.\d+$"`, major must be 1; current `"1.4"` | consumers accept the same major |
| `session_id` | `^ses_[A-Za-z0-9]{6,64}$` | one per **device connection** (a reconnect keeps it; a switch makes a new one). Not the research session id (`<data>/sessions/<id>`). |
| `device_id` | `^[a-z0-9][a-z0-9_.:\-]{0,63}$` | e.g. `sim-a`, `sim-b`, `replay:<name>`, `t15:day00468-block03-…`, `lsl:…`, `plugin:<pkg>:<key>`, `test-scripted-decoder` |
| `seq` | int ≥ 0 | runtime-assigned, strictly increasing per session; **not contiguous** in a recording made with `exclude_raw` or for a subscriber that lacks some grants |
| `timestamp_ns` | int ≥ 0 | **Concord host wall clock (`time.time_ns()`, UTC ns) at ingest**. Not monotonic (NTP steps can move it); in a replay it is the *replay* time, not the original. |
| `device_timestamp_ns` | int ≥ 0 or null | source clock, passed through unchanged, **arbitrary epoch** per source: Profile A = µs since connect ×1000; Profile B = ms since connect ×10⁶; T15 = bin-end time on the block clock; scripted/pipeline = bin end; LSL = LSL clock. Regressions are flagged (`timestamp_regression`, score ≤ 0.5), never reordered; monotonicity is per (event_type, adapter) stream. |
| `event_type` / `capability` | closed enums; must match (see 4.2) | |
| `quality` | `{score ∈ [0,1], flags ⊆ {synthetic, replayed, low_link_quality, timestamp_regression, saturated, dropped_samples} (≤16)}` | adapter estimate; 1 = nominal |
| `provenance` | `{kind, adapter "name@x.y.z", synthetic: bool, model_id: str\|null, origin: str, replayed: bool, model_origin: "concord"\|"external"\|"historical"\|null}` | see 4.3 |
| `payload` | per event type | |

### 4.2 Intent and related payloads

| event_type (capability) | Payload fields | Units / frame |
| --- | --- | --- |
| `intent.pointer` (`pointer_intent`) | `vx`, `vy` ∈ [−10, 10], finite | **velocity** in workspace units / s; workspace = unit square, **x → right, y → down**. No position field exists. Profile A: 50 Hz, max 2.0. Router: `pointer_scale` `training_std` (z-score × gain) or `native`; dead-zone, clamp `max_speed` (default 2.0), optional `invert_y`. |
| `intent.selection` (`selection`) | `action` ∈ {`primary`, `activate`, `cancel`} (default `primary`); `confidence` ∈ [0, 1] | a click is `primary` (or `activate` if the router click rule is so configured). Confidence: decoded = class posterior or click output clipped to [0,1] at firing; **simulated = random number** (§3.5). |
| `intent.text` (`text_intent`) | `text` (1–64 chars), `mode` ∈ {`character`, `word`}, `confidence` | |
| `intent.navigate` (`navigation`, 1.4) | `direction` ∈ {up, down, left, right, next, previous}, `confidence` | |
| `intent.kinematics` (`kinematic_intent`) | `quantity`, `dims[]`, `unit`, `values[]`, `space` | decoder output, never a command. T15 historical: `quantity "velocity"`, dims `vx, vy`, unit `screen_height/s`, space `t15_screen` (+y **up**, origin screen centre); click: `quantity "click_decision"`, dims `["click"]`, unit `probability` (0/1 values). Scripted: `quantity "velocity_and_click"`, dims `vx, vy, click`. |
| `behavior.sample` (`behavior`) | `quantity`, `dims[]`, `unit`, `values[]`, `sample_index`, `valid` | ground truth, never a command. T15: `cursor_position` and `target_position`, dims `x, y`, unit `screen_height`, origin screen centre, **+y up**. |
| `recording.annotation` (`recording`) | `label`, `value` (number/string/null), `duration_ms` | T15: `block` and `trial_start` (`"trial k target (x, y)"`) |
| `control.state` (`control_status`, 1.4) | `active` (strict bool), `capabilities[]`, `reason` (≤256, human text, do not parse) | per-app, **not recorded** |
| `device.status` (`device_status`) | `state` ∈ {connected, streaming, paused, reconnecting, disconnected, error, ended}, `detail` | |

### 4.3 Provenance rules (enforced by Concord's validator, not by the JSON Schema)

* `intent.*` → `kind ∈ {simulated_intent, decoded_intent}`; `simulated_intent ⇒ synthetic = true`;
  `decoded_intent ⇒ model_id` required; `model_id`/`model_origin` only on `decoded_intent`;
  `model_origin = historical ⇒ replayed = true`.
* `behavior.sample`, `recording.annotation` → `behavioral_label`; `features.*` →
  `processed_feature`; `recording.frame` → `raw_signal`; `telemetry.sample` → `device_report`;
  `device.status` → `device_report|runtime`; `control.state` → `runtime`.
* Replayed events keep their original `kind` and get `replayed: true` + flag `replayed`.

---

## 5. Concord → NeuroMetric bridge spec

### 5.1 Input files

`*.concord.jsonl` (`concord.recording/1`):

* line 1 header: `format` (= `"concord.recording/1"`), `schema_version` (major 1), `created_at_ns`
  (wall clock), `device` (full DeviceDescriptor: `device_id`, `display_name`, `kind` ∈
  {simulated, replay, hardware, stream}, `adapter`, `description`, `native_format`,
  `capabilities[] {capability, params, description}`, `synthetic`, optional `modality` ∈ {eeg,
  meg, emg, ecog, seeg, intracortical, other}, `invasive`, `integration`), `synthetic`, `note`,
  optional `source_metadata`, `timing` (text), `limits`. The header model forbids unknown keys.
* lines 2..n: one envelope per line (§4). A last line truncated by a crash must be skipped, not
  fatal (Concord does the same). Sidecar `<name>.recovery.json` marks a recording incomplete.

### 5.2 Minimal fields read from each envelope

`session_id`, `device_id`, `seq`, `timestamp_ns`, `device_timestamp_ns`, `event_type`, `payload`,
`provenance.{kind, synthetic, replayed, model_id, model_origin, adapter, origin}`,
`quality.{score, flags}`; from the header: `device.kind`, `device.modality`, `device.synthetic`,
`device.capabilities[pointer_intent].params` (`rate_hz`, `max_speed`, `scale`).

### 5.3 Mapping to NeuroMetric events `{t_ms, kind, x, y, device_id, modality, session_id, confidence}`

**Time (`t_ms`, monotonic):**
1. Sort/keep by `seq` (file order). Group into **streams** by `(event_type, provenance.adapter)`.
2. Primary clock: `device_timestamp_ns` when every intent event of the file has one (true for all
   Concord intent sources checked: sim A/B, router/pipeline output, T15). Convert:
   `t_ms = (device_timestamp_ns − t0_device_ns) / 1e6`, with `t0` the first intent event's value.
   Different streams of one source share that clock in Concord (pipeline output is stamped with
   bin-end device time), so one `t0` per session.
3. If a stream's device time regresses (quality flag `timestamp_regression`), do **not** reorder:
   clamp `t_ms` to the previous value of that stream and set a NeuroMetric quality flag.
4. Fallback when `device_timestamp_ns` is null: `timestamp_ns` (wall clock) made monotonic with a
   running max. Keep the original `timestamp_ns` as `wall_ns` for audit; never use it for
   intervals in replayed data (it is the replay time).
5. Never mix sessions: a new `session_id` starts a new NeuroMetric segment (Concord's board also
   resets integration on a session change).

**Kinds:**

| Concord | NeuroMetric `kind` | x, y | confidence |
| --- | --- | --- | --- |
| `intent.pointer` | `pointer_move` | **reconstructed position**, normalized 0..1, y down: start (0.5, 0.5); for each pointer event `dt = clamp((t − t_prev)/1e9, 0, 0.1 s)` on the device clock (first event of a session: dt = 0); `x = clamp01(x + vx·dt)`, `y = clamp01(y + vy·dt)`. Also carry the raw `vx, vy` (workspace/s) — needed for lossless round trip, since position is derived. | none |
| `intent.selection` `primary` | `click` (Concord has no separate down/up; emit `click` only, do not invent `pointer_down/up`) | last reconstructed cursor position (null if no pointer stream) | `payload.confidence` **only if** `provenance.kind == decoded_intent`; null for `simulated_intent` |
| `intent.selection` `activate` | `click` with `button = "activate"` (or `switch` when the session has no pointer capability, i.e. switch/scanning use) | as above | as above |
| `intent.selection` `cancel` | `cancel` | — | as above |
| `intent.text` | `text` (`text`, `mode`) | — | as above |
| `intent.navigate` | `switch` with `direction` (closest NeuroMetric kind; consider adding `navigate`) | — | as above |
| `device.status` `paused` / `streaming` | `pause` / resume marker | — | — |
| `intent.kinematics`, `behavior.sample`, `features.*`, `recording.*`, `telemetry.*` | **not input events.** Keep `behavior.sample cursor_position/target_position` as task ground truth (T15: convert from screen-height, centre origin, +y up: `x_n = x/h_grid + 0.5`, `y_n = 0.5 − y/h_grid` with `h_grid` = the block's grid height (`T15Block.grid_height`; 0.92 screen heights per docs/CONTROL_BRIDGE.md, grid centred at the origin), as Concord's board e2e uses) | | |
| — | `scroll`, `dwell_select`, `pointer_down`, `pointer_up`, `assist` | **no Concord source.** Dwell is computed by the board on wall-clock time and is not recorded; T15 `assist_amount` / `click_assist` exist in the `.mat` files but are not emitted as events by Concord's T15 source. | |

**Other fields:**
* `device_id` = envelope `device_id` (prefix with `concord:` to avoid collisions).
* `modality`: from provenance and header, not guessed: `simulated_intent` → `simulated`;
  `decoded_intent` → `bci` (+ `device.modality`, e.g. `intracortical`, when declared; null otherwise)
  with `model_id` and `model_origin` kept (`historical` = original research decoder, not Concord);
  replayed data flagged `replayed`.
* `session_id` = envelope `session_id` (plus the recording file's SHA-256 as `source_hash`).
* Keep `seq`, `provenance`, `quality` in a `source` sub-object so the import is lossless and the
  original envelope can be regenerated.

### 5.4 Fixtures for the importer tests

**No Concord recording file is committed anywhere in the Concord repository** (searched for
`*.concord.jsonl`, `*.jsonl`, `concord.recording/1`; `data/` is git-ignored; T15/FALCON/AJILE12
data are downloaded, never committed). The only committed capture,
`packages/concord-bci2000/tests/fixtures/bci2000_connector_output.json`, is raw BCI2000 App
Connector UDP datagrams, not Concord format. Synthetic `.mat` fixtures for T15 are generated in
memory by `backend/tests/test_cursorclick_format.py`.

I therefore generated genuine recordings with Concord's own runtime/recorder (synthetic data
only):

| Path | Content | Size |
| --- | --- | --- |
| `neurometric/tests/fixtures/concord/scripted_decoded_click.concord.jsonl` | **primary importer fixture.** Device `test-scripted-decoder` (synthetic). 171 `features.vector`, 171 `intent.kinematics` (decoded_intent), 171 decoded `intent.pointer`, 1 decoded `intent.selection` (`primary`, confidence 1.0), all `model_origin: concord`, `model_id: test-scripted-identity`, 20 ms bins, contiguous `seq`. **Ground truth:** integrating per §5.3 gives cursor (0.625, 0.125) at the click. | ~312 KB |
| `neurometric/tests/fixtures/concord/sim_a_pointer_select.concord.jsonl` | Simulated Profile A, raw frames excluded: 81 `intent.pointer` (simulated_intent, 50 Hz, noisy, quantized), 2 `intent.selection`, 1 `telemetry.sample`; `seq` non-contiguous (frames excluded) | ~42 KB |
| `neurometric/tests/fixtures/concord/sim_b_select_text.concord.jsonl` | Simulated Profile B: 1 `intent.selection`, 2 `intent.text` (`h`, `i`); ms-resolution device clock | ~3 KB |
| `neurometric/tests/fixtures/concord/generate_concord_fixtures.py` | regenerates the three files (needs Concord installed; timestamps change per run) | |

Format: `concord.recording/1`, schema 1.4, UTF-8 JSONL, header + envelopes (§5.1). Importer
tests should assert: counts per kind, `t_ms` monotonic, the (0.625, 0.125) click position, null
confidence for simulated events, and round-trip back to the original envelopes.

---

## 6. Documentation vs code discrepancies found

1. **"No audit log"** (ARCHITECTURE.md §8 "Planned (not implemented): … audit log";
   LIMITATIONS.md Security "No TLS, no audit log") vs ARCHITECTURE.md M5-D.4 and
   `server/audit.py`: a `SessionAuditMiddleware` records operator actions into the session log
   (tested in `test_m5_sessions.py`). Reconciliation: it is a non-tamper-proof session log that
   does not identify who acted (LIMITATIONS.md M5-D). The two security sections are stale.
2. **Simulator degradation claim**: "the simulator adds profile-specific quantization, noise, and
   latency" — pointer intents get noise + quantization but **no latency**; discrete intents get
   constant latency but no noise; no drift/dropout (§3.5).
3. **JSON Schema completeness**: ARCHITECTURE.md presents the exported schema as the contract,
   but cross-field provenance rules live only in Python validators (§3.1).
4. **docs/CONCEPTS.md** says "The twelve capabilities" and lists 11; the code enum also has 11.
5. **Versions**: `CITATION.cff` says 0.3.0; `pyproject` 0.3.2; ARCHITECTURE.md header "Concord
   0.3.0 (Milestone 5)".
6. **Certify README** says `hardware_tested` rests on "an operator-signed attestation it does not
   verify"; code (`levels.py`) verifies the Ed25519 signature and plugin identity, not the
   hardware claims (LIMITATIONS.md states it correctly).
7. **Cursor+click numbers** (docs/CURSOR_CLICK.md) could not be re-verified here: their tests skip
   without the Dryad files. Code is consistent with the doc's definitions (e.g. median endpoint
   error and progress per block, bitrate formula, ±250 ms matching, 1 s refractory).
8. **`format.py` docstring** shows a header `"schema_version": "1.0"` and no M5 fields; real
   headers carry the current version (1.4) plus `timing`/`limits` (minor, docstring only).
9. **Simulated `confidence`** on `intent.selection`/`intent.text` is a random draw, which the
    docs do not state; any consumer treating it as a decoder confidence is wrong.

Housekeeping: test runs created `__pycache__` directories in the Concord tree (git-ignored); I
removed the ones created this session. No tracked Concord file changed (`git status` shows only
`neurometric/` untracked).
