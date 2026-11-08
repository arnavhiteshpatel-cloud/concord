# concord-example-decoder

An example **decoder plugin** for Concord, written against the public decoder SDK
(`concord-decoder-sdk`) only. It shows the whole path a third-party decoder takes: a manifest
that states exactly what the model needs, a causal `step()`, packaging as an entry point, and
Concord running it in an isolated decoder host with every output validated.

**What it decodes.** rest / left / right motor imagery from mu-band (8-13 Hz) log band power at
C3 and C4, by a **hand-set rule** (no training): each channel against its own running
baseline, the C3−C4 lateralization index smoothed, then softmax scores. Its constants were set
by hand on Concord's declared-**synthetic** motor-imagery generator (`backend/tests/mi_source.py`).
On that generator, offline over 2 × 300 s, it reached a balanced accuracy of 0.49 (chance 0.33)
when the constants were chosen; `backend/tests/test_decoder_example.py` runs it through the
real runtime and asserts > 0.40 after a 30 s warm-up. That is the whole evidence: it is **not**
validated on real EEG and must not be used as a decoder for real data.

## Write your own decoder in 15 minutes

```bash
pip install -e packages/concord-decoder-sdk        # in Concord's Python environment
concord-decoder new my-decoder                     # scaffold concord-my-decoder/
pip install -e concord-my-decoder
concord-decoder check my-decoder                   # load + decode synthetic bins in the host
```

1. **Manifest** (`ModelManifest`): declare what the model was trained on — modality, every
   input (`features.binned` / `features.vector`, feature name, bin size, channel count, channel
   labels or `None` for positional, unit, band), the Concord preprocessing preset and
   parameters, the participant (`source_identity`) and training sessions, and the outputs
   (`continuous` / `classes` / `event`, dims, unit, space, `y_axis` if it has one). Concord
   refuses to run the model on data that does not match, with the reason.
2. **`load()`**: load your parameters (ship them in the package).
3. **`reset()` / `step(features, timestamp_s)`**: causal; return `DecodeOutput(values)` with
   the declared shape (posteriors summing to 1 for classes, probabilities for events).
4. **Entry point** in `pyproject.toml` under `concord.decoders`.
5. In Concord: **Start decoding** lists the decoder with its compatibility verdict; outputs
   become `intent.kinematics` (`decoded_intent`, your `model_id`, `model_origin: concord`).
   They become application commands only through the operator's command router, and only for
   applications the operator authorized.

This example needs the operator to enable **mapping channels by label**: it declares two
channels (C3, C4) while EEG sources usually stream more. Concord never selects or reorders
channels on its own.

```bash
pip install -e examples/decoders/concord-example-decoder
pytest -q examples/decoders/concord-example-decoder/tests
```

Guide: [docs/DECODER_SDK.md](../../../docs/DECODER_SDK.md).
