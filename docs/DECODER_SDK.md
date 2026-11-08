# Concord decoder SDK (API 1.0): decoders, model files, compatibility, calibration

The decoder SDK (`packages/concord-decoder-sdk`, import name `concord_decoder_sdk`) lets a
third party bring a **decoder** to Concord without changing Concord. A decoder turns per-bin
neural *features* into decoder outputs: continuous values, class posteriors, or event
probabilities such as a click. Concord checks the decoder against the source before it runs,
runs third-party code in an isolated process, validates every output, and publishes the
outputs as `intent.kinematics` events.

Decoder outputs are **never application commands** on their own. Only the operator's command
router turns them into `intent.pointer` / `intent.selection` / `intent.text`, and those reach
only applications the operator authorized (docs/CONTROL_BRIDGE.md).

* Normative API: `concord_decoder_sdk/api.py`. Rules: `concord_decoder_sdk/manifest.py`.
  Loaders and trust: `concord_decoder_sdk/formats.py`.
* Runtime side:
  - `backend/src/concord/decoding/` (`families.py`, `model.py`, `registry.py`, `engine.py`,
    `monitor.py`, `calibrate.py`, `metrics.py`);
  - `runtime/pipeline.py`;
  - `server/decoder_routes.py`.
* Example: [`examples/decoders/concord-example-decoder`](../examples/decoders/concord-example-decoder/README.md).

**Validation level** (docs/VALIDATION_LEVELS.md): software only. The decoders shipped here
fall into three groups:

- Concord-trained models fitted on recordings (real FALCON data, or synthetic data);
- the lead's Kalman / click families;
- test and example decoders.

None has been used for closed-loop control by a person.

## 1. Concepts

| Concept | Where | Meaning |
| --- | --- | --- |
| Manifest | `ModelManifest` (JSON: `concord.decoder-manifest/1`) | Everything Concord checks before inference: modality, inputs, preprocessing, participant/sessions, calibration requirements, outputs, confidence semantics, provenance, and (for files) the artifact. |
| Decoder | `Decoder` subclass | Lifecycle `load()`, `reset()`, `step(features, timestamp_s) -> DecodeOutput`, `close()`. Causal: current and earlier bins only. |
| Family | e.g. `ridge`, `lda`, `kalman`, `click`, `onnx`, `sklearn`, `torchscript` | The kind of model. Built-in JSON families run in the Concord process; everything else runs in a decoder host. |
| Origin (console) | `concord-trained`, `imported`, `plugin`, and for passthrough `historical` / `external` | Where the decoder comes from. |
| `provenance.model_origin` (contract 1.4) | `concord` / `external` / `historical` | On every decoded event:<br>• `concord`: a model Concord trained or loaded (built-in, file or plugin);<br>• `external`: a live external system's decoder, e.g. BCI2000 via a source plugin;<br>• `historical`: the recorded outputs of a research system's original decoder, replayed.<br>Never re-labelled. |

### Ways to bring a decoder

| | Decoder plugin | Model file | Built-in family |
| --- | --- | --- | --- |
| What | A `Decoder` subclass with a class attribute `manifest`, in the `concord.decoders` entry-point group of an installed package | `<model id>.manifest.json` + artifact in Concord's models directory | A JSON model of a family registered in `decoding/families.py` |
| Runs | Decoder host process | Decoder host process | In the Concord process |
| Listed | `POST /models/discover` (also at server start): `host --list` probes each plugin in its own process | On every `GET /models` | On every `GET /models` |

## 2. Manifest reference

| Field | Meaning | Checked against |
| --- | --- | --- |
| `model_id`, `name`, `version` (semver), `api_version` (`1.0`), `family`, `description`, `author`, `license` | Identity. `model_id` becomes `provenance.model_id` of every decoded event. | Format; API compatibility (`M.m` runs on `M.n`, `m ≤ n`) |
| `modalities` | Non-empty set of `eeg meg emg ecog seeg intracortical other` the model may run on | The source's declared `modality`. Undeclared on the source: a warning, never a guess |
| `inputs[]` | `event_type` (`features.binned` / `features.vector`), `feature`, `bin_ms`, `channel_count`, `channel_labels` (`null` = positional), `unit`, `band_hz`. Several inputs are joined per bin and concatenated in this order. | The pipeline's feature streams: feature, bin, unit, band, channel count, labels **and order** |
| `preprocessing` | `preset` + `params` of the Concord pipeline the features were computed with, and a description of the model's internal steps | The running preset and its parameters (e.g. `threshold_k`, band edges) |
| `compatibility` | `participant_specific`, `source_identity`, `sessions`, `calibration_profile` | The stream's identity (explicit cross-source override needed), session (leakage: refused), selected profile |
| `calibration` | `required`, `task`, `label_quantity`, `label_dims`, `min_labelled_bins` | Shown to the operator |
| `output` | `kind` (`continuous` / `classes` / `event`), `quantity`, `dims`, `unit` (`probability` for classes / events), `space`, `scale` (typical magnitude per continuous dim: the router's normalisation), `y_axis` (`up` / `down`) | Every output (shape, finite, probabilities, sums) |
| `confidence` | `none`, `posterior` (the values are probabilities), `variance` (per dim), `covariance` (dims × dims) | Every output's confidence array |
| `provenance` | Training-data hashes, code version, creation time, trainer, notes | Shown |
| `artifact` | `format`, `file`, `sha256`, `io` (format-specific declarations) — model files only | The file's hash before parsing; the declared I/O against the file |

## 3. Families, serialization and the trust policy

| Format | Loader | Code execution on load | Declared I/O checked |
| --- | --- | --- | --- |
| Concord JSON (`ridge`, `lda`, `kalman`, `click`, …) | `families.family_for(data).from_dict` | none | parameter shapes |
| `onnx` | onnxruntime `InferenceSession`, CPU, 1 thread | none: standard operators only; no custom-op libraries are registered | input/output names and shapes (symbolic or -1 = wildcard); declared recurrent state carried between steps; element type float/double |
| `skops` (scikit-learn) | `skops.io.load` | none for skops' trusted types; **untrusted types refused** unless the operator trusts this exact file | `n_features_in_`; `predict` / `predict_proba`; class labels mapped to output dims |
| `safetensors` (PyTorch `state_dict`) | `safetensors.torch.load_file` into a built-in architecture (`linear`, `gru`) | none (tensors only) | strict `load_state_dict` |
| `torchscript` | `torch.jit.load(map_location="cpu")` | TorchScript IR (a restricted language, not arbitrary Python). It still parses a complex archive, so it runs isolated. Upstream PyTorch now deprecates TorchScript; prefer ONNX or safetensors | one probe step; output shape |
| `pickle` / `joblib` | `pickle.load` / `joblib.load` | **arbitrary code** | refused unless trusted; then as scikit-learn |

* **Hashes first.** Every artifact's SHA-256 is compared with the manifest before anything
  parses it. A changed file is refused.
* **Trust is explicit, per file.** `POST /models/{id}/trust {trusted: true}` records the file's
  SHA-256, who decided and when, in `<models_dir>/_trust.json`. The console offers the button
  only for unsafe formats, with the reason. Changing the file voids the decision. Trust lets
  the host load the file: it adds no protection.
* **`history_bins: k`** (onnx, skops, pickle, joblib, torchscript) gives a stateless model the
  last k bins, oldest first, concatenated. It is causal temporal context without recurrent
  state.
* **Optional dependencies.** `concord-decoder-sdk[onnx]`, `[sklearn]` and `[torch]` must be
  installed in Concord's environment, where the decoder host runs. Torch is not in
  `make setup`: the CPU wheel needs a dedicated index. Without torch, its tests skip with a
  reason.

## 4. Execution and isolation

```
runtime (never imports decoder code)              decoder host (one process per running decoder)
PipelineManager ── engine.IsolatedDecoder ─spawn─▶ python -m concord_decoder_sdk.host <ep | --model m.json>
   AsyncHostClient ◀═ concord.decoder-ipc/1 ═════▶   fd 1 → stderr, fd 0 → /dev/null
   (4-byte length + JSON + raw LE float64 buffers,     manifest validated; load(); every output
    the adapter SDK's framing, bit-exact)              validated (OutputValidator) before it is sent
   every output validated AGAIN
```

| Event | Effect |
| --- | --- |
| Host exits, hangs past 5 s per step, breaks the protocol | Decoder `failed` (reason in status), host killed |
| Invalid output (shape, NaN/inf, probability outside [0, 1], posteriors not summing to 1 ± 1e-3, missing or malformed confidence) | |
| Unexpected exception in `step()` | |

On any failure in that table:

- the decoder stops for the rest of the run;
- if the router was on, it is switched off, so no stale commands are emitted;
- features keep flowing;
- `counters.decoder_failures` and `last_error` record it.

**Isolation is fault isolation, not a security sandbox.** The host runs as the same user, with
the same files and network as Concord. A malicious plugin or trusted pickle can do anything
that user can. Install decoders as you would any Python package.

`step` latency includes one IPC round trip. On this machine `concord-decoder check` measures
it; it is not a benchmark (workstream E).

## 5. Compatibility rules (checked before inference)

`decoding/model.py: check_manifest`, for every decoder, built-in or not. Every mismatch is
reported at once, with both sides, for example:

> model expects 256 channels (256 channels labelled array0, array1, array2, …), source has 96
> (96 channels labelled ch0, ch1, ch2, …); 256 model labels are not in the source (e.g. array0)

1. **Feature stream**: `event_type` + `feature` must exist in the pipeline output. A model with
   several inputs needs every stream.
2. **Bin size, unit, band**: equal, or refused. Concord never rescales.
3. **Channels**:
   - Same labels in the same order, or both sides positional with the same count: accepted.
     If only the model declares labels, there is a warning: the order cannot be verified.
   - Otherwise refused. The one exception is the **explicit, operator-enabled mapping by
     label** (`allow_channel_mapping`). It is offered only when both sides declare unique
     labels and the source has every model label.
   - With the mapping, each model channel is fed the source channel with its label, in the
     model's order; extra source channels are unused. The mapping is logged at WARNING,
     listed in status (`channel_mapping`, `compatibility_warnings`) and shown in the Decoder
     row.
4. **Modality**: declared on both sides and different → refused.
5. **Preprocessing**: a different preset, or a different value of a parameter the model
   declares → refused.
6. **Participant**: `participant_specific` models trained on another (or unknown) source are
   refused unless the operator sets `allow_cross_source`. The override is shown and lowers
   event quality to 0.5. Models declaring `participant_specific: false` run with a warning.
7. **Sessions**: a stream from one of the model's training sessions is refused (leakage).
8. **Calibration profile**: when both the model and the request name one, they must be equal.

`GET /models?preset=…&bin_ms=…&band_low_hz=…` previews the verdict for a processing choice
before anything starts. The console shows it, and shows the mapping toggle only for models
whose labels can be mapped.

## 6. The pipeline with decoders

* `PipelineStartRequest`: `model_id`, `model_ids` (up to 3 more decoders run together, with
  distinct output names, e.g. a Kalman velocity decoder and a click decoder),
  `allow_channel_mapping`, `allow_cross_source`, `calibration_profile`.
* Every decoder publishes its own `intent.kinematics` with `decoded_intent`, its `model_id`
  and `model_origin: "concord"`.
* Built-in families step in-process. The FALCON ridge decoder's streaming output equals its
  offline `predict_counts` bit for bit: same summation order (`filter_step`, row-wise
  products), asserted over LSL in `test_pipeline_live.py`.
* **Multi-input join**: feature streams of one bin are joined by `device_timestamp_ns` (the bin
  end), which must be identical across streams. A bin still incomplete once 8 newer bins exist
  is dropped (`join_dropped`), never padded.
* **Router**: one `CommandRouter` per decoder, for the part of the operator's mapping it
  serves. The pointer comes from the decoder owning `x_dim`/`y_dim`; each discrete rule from
  the decoder owning its output (a class or an event such as `click`).
  - The pointer is z-scored by `training.behavior_std`, or by the manifest's `output.scale`.
  - A decoder whose `y_axis` is `up` must be mapped with `invert_y`, because the workspace's
    +y is down; otherwise the router is refused.
* **Decoded passthrough** (`preset: "decoded_passthrough"`): no model. The source's own decoder
  outputs go to the router unchanged: model id, `model_origin` and `replayed` are preserved.
  - Typical sources: a research system's recorded decoder (T15 cursor + click: `historical`,
    replayed), or BCI2000's live control signal (`external`).
  - The source declares them in its `kinematic_intent` capability params:
    `decoders: [{model_id, dims, quantity, unit, space, model_origin, scale?, y_axis?}]`.
  - Outputs with origin `concord` or no origin are refused.
* Status adds per decoder:
  - family, origin, execution, state / error, pid;
  - the compatibility verdict;
  - the drift monitor.

  It also adds `source_decoders`, `outputs`, `channel_mapping` and `recalibration_recommended`.

## 7. Calibration workflow

`decoding/calibrate.py: calibrate_capability`. REST: `GET /calibration/options`,
`POST /calibration/check`, `POST /calibration/train`. The console's Calibrate sheet follows
these steps.

1. **Choose the output.**
   - *continuous movement* needs continuous targets;
   - *discrete classes* needs small-integer class codes;
   - *click* needs a 0/1 label.

   One calibration task does not fit every modality, so the operator records the task that
   matches the output.
2. **Check the labels** (`check_labels`). Example refusals:
   - integer codes offered as continuous targets;
   - a non-binary click label;
   - too few labelled bins or click events;
   - several dims without `label_dim`.
3. **Record** synchronized features + behavior with the existing recorder (`exclude_raw`).
   Recordings with several feature streams can be joined (`join_features`).
4. **Fit the family.** Defaults: ridge (continuous), LDA (classes, and click as `no_click` /
   `click`). Any registered family with `fit` can be chosen, e.g. the lead's `kalman` and
   `click` (`click_logistic`).
   - Labels: the label nearest each bin end within half a bin.
   - Split: chronological, train → gap → held-out.
   - Only training data is used for fitting, z-scoring and model selection.
5. **Held-out evaluation** with metrics for the output:

   | Output | Metrics |
   | --- | --- |
   | continuous | variance-weighted R², per-dim R², mean-predictor and time-shift controls, **velocity error** (RMSE / MAE per dim, mean error-vector length, relative to mean target speed) |
   | classes | balanced accuracy, per-class recall, confusion, chance levels, time-shift control |
   | click | **event** precision / recall / F1 (an event is a label onset; a detection is a 0.5-threshold crossing within ±300 ms), false clicks per minute, per-bin balanced accuracy / precision / recall / ROC AUC |
6. **Save** `<model_id>.json` with the full manifest (modality from the source, inputs with
   labels / units / bands, `y_axis` if the behavior capability declares one), training
   `feature_stats` / `output_stats`, and the report (`reports/calibration/<id>.md`).
7. **Load later.** A new runtime (after a restart) lists the model and decodes with it.
   `test_calibration_round_trip_across_a_restart` asserts the predictions are identical bit
   for bit.

Offline held-out scores on a recording do not establish closed-loop control performance.

## 8. Performance monitoring and recalibration

`decoding/monitor.py`, one monitor per running decoder, over the last 500 bins:

* **Input-feature shift**:
  - per channel, `z = (window mean − training mean) / training SD`, summarised as the RMS over
    channels and the fraction of channels with |z| > 1;
  - the RMS of `log(window SD / training SD)`.
* **Outputs**:
  - continuous: window mean and SD (z against `output_stats`);
  - classes: occupancy;
  - events: rate.
* **Labels** (only when the source streams `behavior.sample` in the session): rolling R² (dims
  matched by name) or balanced accuracy against the held-out calibration result. Labels feed
  these numbers only, never a decoder or the router.
* **Recalibration recommended** is raised, with at least 200 bins in the window, when any of
  these holds:
  - feature shift RMS > 0.5 training SD;
  - more than 25 % of channels moved > 1 SD;
  - variability changed by more than ×1.5;
  - the rolling labelled metric lost half its held-out margin (R² < ½ held-out R²; balanced
    accuracy below chance + ½ (held-out − chance)).

  The reasons are listed in status and in the Decoder row. **These thresholds are engineering
  heuristics**, tested on a deliberately shifted versus an unshifted synthetic stream. They
  are not validated against closed-loop performance.
* Models without `feature_stats` (trained before Milestone 5) report feature drift as
  unavailable, with the reason. Recalibrate them to enable it.

## 9. Write a third-party decoder, step by step

```bash
pip install -e packages/concord-decoder-sdk          # into Concord's environment
concord-decoder new my-decoder                       # concord-my-decoder/ with a working plugin
pip install -e concord-my-decoder
concord-decoder check my-decoder                     # manifest + load + 200 bins, every output validated
concord-decoder list                                 # what Concord will see
```

1. Edit `src/concord_my_decoder/decoder.py`: replace the placeholder weights. Declare exactly
   what you trained on: inputs with labels, preprocessing, modality, participant
   (`source_identity`) and sessions, outputs (`scale`, `y_axis`).
2. `step()` must be causal and return the declared shape. Use `check_features(manifest, x)`.
3. Ship parameters in the package. Prefer data files (numpy `.npz`, JSON, safetensors); a
   decoder plugin is code, and Concord runs it as code.
4. In Concord: **Start decoding → Search for decoder plugins**. The decoder is listed with its
   origin and the compatibility verdict for the chosen processing.
5. For a model file instead of code:

   ```python
   from concord_decoder_sdk.formats import write_bundle

   write_bundle(models_dir, manifest, "model.onnx", "onnx", io={...})
   ```

   This copies the file, hashes it and writes `<id>.manifest.json`. Then run
   `concord-decoder check --model <id>.manifest.json`.

## 10. Registering a built-in family (Concord developers)

```python
from concord.decoding.families import BuiltinFamily, CalibrationData, register_family

register_family(BuiltinFamily(
    name="kalman", kinds=frozenset({"kalman"}), output="continuous",
    from_dict=KalmanDecoder.from_dict, description="Velocity Kalman filter",
    confidence="covariance", capabilities=frozenset({"continuous"}), fit=fit_calibration,
))
```

Add the module to `families._BUILTIN_MODULES` so it is imported before any model loads.
`decoding/kalman.py` and `decoding/click.py` are registered this way.

The model object provides:

- `model_id`, `dims`, `quantity`, `unit`, `space`;
- `inputs` (or a single `input`), `source`, `training` (`behavior_std`, `feature_stats`),
  `evaluations`;
- an optional `manifest`, and `save()`;
- `streaming()`, returning an object with `step(x) -> ndarray` and `reset()`, plus
  `covariance()` (dims × dims) or `variance()` when declared.
