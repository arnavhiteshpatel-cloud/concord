# Write your own Concord adapter in 15 minutes

This package is a complete, installable Concord source plugin: a **declared-synthetic
motor-imagery EEG generator**. Use it as a template. It depends only on
[`concord-adapter-sdk`](../../../packages/concord-adapter-sdk) and numpy — a plugin never
imports Concord. Reference: [docs/ADAPTER_SDK.md](../../../docs/ADAPTER_SDK.md).

What it generates (synthetic, **not brain data**, not physiologically validated): 8 or 16 EEG
channels at 250 Hz with 10-20 labels (`F3 Fz F4 C3 Cz C4 P3 P4`, or 16 from `Fp1` to `O2`),
in microvolts — 1/f-like background, mu rhythms over both motor cortices, posterior alpha — and
a cue schedule `rest → left|right → rest → …` in which imagined movement lowers 8–12 Hz power
over the opposite motor cortex (C4 for *left*, C3 for *right*; `effect_size` 0.5 = half the
amplitude). Plus a 50 Hz behavior stream `cue_class` (0 rest, 1 left, 2 right) and markers
`cue rest` / `cue left` / `cue right`, all on one clock. Same seed → same samples, regardless
of timing.

## 1. The package (2 minutes)

```
concord-example-adapter/
  pyproject.toml                       # dependencies + the entry point
  src/concord_example_adapter/
    generator.py                       # the signal (pure numpy; nothing Concord-specific)
    plugin.py                          # the plugin: manifest, discover(), open(), session
  tests/test_example_mi_eeg.py         # runs the plugin exactly as Concord does
```

The entry point is what makes Concord find you. The name on the left becomes part of device
ids (`plugin:example-mi-eeg:mi-eeg`), so keep it short (≤ 24 characters, lower case):

```toml
[project]
dependencies = ["concord-adapter-sdk>=1.0,<2", "numpy>=1.26"]

[project.entry-points."concord.sources"]
example-mi-eeg = "concord_example_adapter.plugin:MotorImageryEEGPlugin"
```

## 2. The manifest (2 minutes)

`plugin.py` declares who you are, which API you were written for and every role you may emit.
Options become a form in the Concord console:

```python
class MotorImageryEEGPlugin(SourcePlugin):
    manifest = PluginManifest(
        name="concord-example-adapter",       # your distribution name
        version="0.1.0",                       # semantic version
        api_version="1.0",                     # adapter SDK API you target
        display_name="Example: motor-imagery EEG generator",
        description="Declared-synthetic EEG ...",
        author="...", license="...",
        roles=frozenset({StreamRole.SIGNAL, StreamRole.BEHAVIOR, StreamRole.MARKERS}),
        options={
            "seed": OptionSpec("int", "Random seed (same seed, same signal)", default=1),
            "montage": OptionSpec("choice", "Channel set (10-20 labels)", default="8", choices=("8", "16")),
            ...
        },
    )
```

`discover(timeout_s)` lists what can be opened now; a generator always offers one device.
`open(device_key, options)` gets options already type-checked against your `OptionSpec`s (with
defaults filled in); check value ranges yourself and raise `InvalidOptions` with a readable
message.

## 3. The session (5 minutes)

`SourceSession.info` says exactly what you will deliver. Be honest: units you know, `None`
when you don't; `synthetic=True` for generated data; one clock for all streams.

```python
clock = ClockInfo("source", "generator sample clock: monotonic time at open() + index / 250 Hz")
SessionInfo(
    streams=(
        StreamSpec(
            "eeg",
            StreamRole.SIGNAL,
            tuple(Channel(lab, unit="microvolts", type="EEG") for lab in labels),
            250.0,
            clock,
            modality=Modality.EEG,
            invasive=False,
        ),
        StreamSpec(
            "cue", StreamRole.BEHAVIOR, (Channel("cue_class"),), 50.0, clock, quantity="class"
        ),
        StreamSpec("markers", StreamRole.MARKERS, (Channel("cue"),), 0.0, clock),
    ),
    primary_stream="eeg",
    synthetic=True,
    prerecorded=False,
    origin="concord-example-adapter:mi-eeg:seed=1",
)
```

`read(timeout_s)` returns what is available, waiting at most `timeout_s`:

```python
return [
    Chunk("eeg", eeg_float32[n, 16], timestamps_s[n], first_index),
    Chunk("cue", cue[::5, None], timestamps_s[::5], first_index // 5),
    MarkerChunk("markers", ("cue left",), np.array([t_onset])),
]
```

Rules Concord enforces (the full list with codes is in docs/ADAPTER_SDK.md §4): 2-D data with
exactly the declared channels, finite values, one timestamp per sample, timestamps ≥ 0 and
never decreasing (also across calls), `first_index` counting samples since `open()` (a jump is
reported as lost samples; going back stops the session). For a dropped device link raise
`LinkLost` — Concord reopens a fresh session. Invalid data stops the plugin with the reason.

## 4. Install and check (2 minutes)

From the Concord repository root:

```bash
.venv/bin/pip install -e examples/adapters/concord-example-adapter     # make setup does this
.venv/bin/python -m concord_adapter_sdk.host --check example-mi-eeg --option montage=16
```

`--check` runs your plugin in a real plugin host with Concord's validation and prints what
Concord will see:

```
plugin   concord-example-adapter 0.1.0 (API 1.0)
device   mi-eeg: Motor-imagery EEG generator
session  primary=eeg synthetic=True prerecorded=False origin=concord-example-adapter:mi-eeg:seed=1
  stream eeg          signal           16 ch @ 250 Hz clock=source units=['microvolts'] modality=eeg
  stream cue          behavior          1 ch @ 50 Hz clock=source units=['None'] modality=None
  stream markers      markers           1 ch @ 0 Hz clock=source units=['None'] modality=None
  read   eeg               500 samples in 2.00 s (249.9/s, nominal 250)
...
OK: all declarations and data passed validation
```

`python -m concord_adapter_sdk.host --list` shows every installed plugin as Concord discovers
it (each probed in its own process).

## 5. See it in Concord (2 minutes)

`make run`, open <http://127.0.0.1:8000>, *Connect a source* → **Plugins**. The plugin is listed
as `concord-example-adapter@0.1.0 · compatible` with the device *Motor-imagery EEG generator*;
*Options* opens the form generated from the manifest. *Connect*. The Acquisition row reads
`Plugin · concord-example-adapter@0.1.0 · isolated · EEG, noninvasive`, the source is labelled
*Simulated data*, and the signal, cue labels and markers flow like any other source: they can be
recorded, replayed, and fed to the processing pipeline (e.g. band power 8–12 Hz; at 250 Hz
set the bin to a whole number of samples such as 40 or 100 ms — the 50 ms default is refused).

If Concord was already running when you installed the package, press *Search again*.

## 6. Test (2 minutes)

`tests/test_example_mi_eeg.py` uses `concord_adapter_sdk.client.SyncHostClient`, which spawns the
same plugin host Concord uses — so a passing test means Concord will accept your declarations
and your data:

```python
with SyncHostClient("example-mi-eeg") as host:
    assert host.manifest()["compatible"]
    host.open("mi-eeg", {"seed": 5})
    chunks = host.read(0.2)  # validated by the host; invalid data raises HostError
```

Run with `pytest tests/` (the Concord repository also runs it in `make test`).

## Isolation, in one paragraph

Concord runs your plugin in its own process and validates everything twice, so a crash, hang
or `print()` in your code cannot take Concord down or corrupt its data path. That is fault
isolation, **not a security sandbox**: your code runs as the same user with the same file and
network access. See docs/ADAPTER_SDK.md §5.
