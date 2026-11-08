# Ecosystem integrations: BrainFlow and BCI2000

Milestone 4, workstream B. Two source plugins built on the public adapter SDK
(`concord_adapter_sdk.api`, API 1.0). They import only `concord_adapter_sdk` (never
`concord`), run in the plugin host, and are **receive-only**.

| | `concord-brainflow` | `concord-bci2000` |
| --- | --- | --- |
| Entry point (`concord.sources`) | `brainflow` | `bci2000` |
| External interface | BrainFlow's official acquisition API (`brainflow.board_shim.BoardShim`), BrainFlow 5.23.0 | BCI2000 App Connector protocol (`ConnectorOutput` filter, UDP), BCI2000 3.6 source |
| What Concord receives | Samples of noninvasive research/consumer biosensing boards (EEG/EMG/ECG/EOG and auxiliary sensors) | **Processed control information**: BCI2000's control signal and state values — not raw signal |
| Concord roles | `SIGNAL` | `DECODER_OUTPUT`, `BEHAVIOR`, `MARKERS` |
| Tested against | The official BrainFlow library: synthetic, playback-file and streaming boards; a real board driver's failure path | A genuine BCI2000 build (SignalGenerator + DummySignalProcessing + DummyApplication) sending through its own ConnectorOutput; a recorded capture of it; a byte-for-byte reproduction sender for edge cases |
| Validation level (docs/VALIDATION_LEVELS.md) | **2 — protocol-tested** (official software, no hardware) | **2 — protocol-tested** (genuine BCI2000 software, signal generator, no hardware) |

Neither plugin has been run with acquisition hardware or a person. Nothing here is level 3 or 4.

---

## 1. BrainFlow (`packages/concord-brainflow`)

### What it uses

BrainFlow 5.23.0 (`pip install brainflow`), Python binding of BrainFlow's C++ BoardController.
The plugin calls only `BoardShim.get_board_descr`, `BoardShim(board_id, BrainFlowInputParams)`,
`prepare_session`, `start_stream`, `get_board_data_count`, `get_board_data`, `stop_stream`,
`is_prepared` and `release_session`. It **never** calls `config_board`,
`config_board_with_bytes` or `insert_marker` (they send data to a board) and never adds
streamers. Only the DEFAULT preset is read (see "Not supported").

References used (fetched from the `5.23.0` tag of github.com/brainflow-dev/brainflow):
`docs/DataFormatDesc.rst`, `docs/SupportedBoards.rst`, `src/board_controller/board.cpp`,
`synthetic_board.cpp`, `playback_file_board.cpp`, `streaming_board.cpp`,
`src/data_handler/data_handler.cpp`.

### Devices (`discover`)

BrainFlow cannot enumerate hardware generically, so `discover()` returns configurable
entries, never detected devices:

| device key | board | required options |
| --- | --- | --- |
| `synthetic` | `SYNTHETIC_BOARD` (generated test signals; "not a real device") | — |
| `playback` | `PLAYBACK_FILE_BOARD` | `file`, `master_board` |
| `streaming` | `STREAMING_BOARD` | `ip_address`, `ip_port`, `master_board` |
| `board` | option `board` (any `BoardIds` name) | the `BrainFlowInputParams` fields BrainFlow documents for that board |

### Options

`board` (choice of all `BoardIds` names), `master_board`, and the `BrainFlowInputParams`
fields `serial_port`, `mac_address`, `ip_address`, `ip_port` (0-65535), `ip_protocol`
(`NO_IP_PROTOCOL`/`UDP`/`TCP`), `serial_number`, `file`, `other_info`, `timeout` (>= 0);
plugin options `stall_timeout_s` (default 5 s) and `package_num_modulus` (default 256).
Validation raises `InvalidOptions` with an actionable message: unknown keys (lists the valid
ones), wrong types, out-of-range ports, unknown board names (with "Did you mean ..."),
playback without an existing `file`, streaming without group/port, `master_board` missing
for playback/streaming or given for other boards, a fixed device key with a conflicting
`board`.

### Data mapping

All metadata comes from `BoardShim.get_board_descr(<board>, DEFAULT_PRESET)` (for
playback/streaming boards: of `master_board`, as BrainFlow's docs require). There are no
per-board tables except the documented unit exception below.

| Stream | Role | Rows | Channel type | Unit | Modality / invasive |
| --- | --- | --- | --- | --- | --- |
| `exg` (primary) | SIGNAL | every row listed under `eeg/emg/ecg/eog_channels` | all types the row is listed under, joined: `EEG`, or `EEG\|EMG\|ECG\|EOG` when ambiguous | `microvolts` if every type is EXG; else `None` | `EEG`/`False` only if every row is EEG-only; `EMG`/`False` if every row is EMG-only; ECG- or EOG-only rows → `OTHER`/`None`; mixed or ambiguous → `None`/`None` |
| `aux` | SIGNAL | every other typed row (`accel`, `gyro`, `magnetometer`, `ppg`, `optical`, `eda`, `temperature`, `resistance`, `battery`, `analog`, `rotation`, `other`, ...) | e.g. `ACCEL`, `OPTICAL\|PPG` | `None` | `OTHER` / `None` |

* **Ambiguous rows.** BrainFlow states: "For some boards like OpenBCI Cyton, OpenBCI
  Ganglion, etc we cannot separate EMG, EEG, EDA and ECG and in this case we return exactly
  the same array for all these methods" (`DataFormatDesc.rst`). The synthetic board lists
  rows 1-16 as EEG, EMG, ECG and EOG at once. The plugin does not guess: those channels
  have type `EEG|EMG|ECG|EOG` and the stream has modality `None` and invasive `None`.
  32 of the 64 board descriptions in BrainFlow 5.23.0 have such rows in their DEFAULT preset
  (e.g. Cyton, Ganglion, FreeEEG, Explore; ANT Neuro boards list EEG rows also as
  `resistance`).
* **Labels.** `eeg_names` where BrainFlow provides them and they match `eeg_channels`
  (e.g. `Fz, C3, ...` for the synthetic board); otherwise `<type><n>` for unambiguous rows
  (`accel1`) and `row<k>` for ambiguous rows without a name.
* **Units.** "For EXG channels BrainFlow returns uV wherever possible" (`DataFormatDesc.rst`)
  → EXG-only rows are `microvolts`. Exception from `SupportedBoards.rst`: gForcePro and
  gForceDual "returns ADC values instead uV" → `None`. BrainFlow documents no unit for any
  other channel type → `None` ("arbitrary"). "Wherever possible" is BrainFlow's own hedge;
  a board BrainFlow does not convert may be mislabelled — not verifiable without hardware.
* **Invasiveness.** BrainFlow boards are noninvasive research/consumer devices; Concord
  never presents them as implants. `invasive=False` only where the modality is one Concord
  treats as noninvasive (EEG, surface EMG); otherwise `None`.
* **No MARKERS stream.** BrainFlow's `Board::push_package` (`board.cpp`) overwrites the
  marker row of every sample with the next value queued by `insert_marker` *on the same
  session*, or 0. Markers stored in a playback file, or inserted by a streaming producer,
  therefore never arrive (verified: `test_bf_playback.py` writes markers into the file and
  they are 0 on playback; an ad-hoc run showed producer markers 5 and 6 arriving as 0 on the
  streaming board). Since the plugin never calls `insert_marker`, a markers stream could
  never carry data, so none is declared. The marker row is still counted
  (`stats()["marker_row_nonzero"]`) so a change in BrainFlow's behaviour would be visible.
* **Provenance.** `origin` = `brainflow:<BOARD>` or `brainflow:<BOARD>/<MASTER>`;
  `synthetic=True` when the data format is the synthetic board's (`SYNTHETIC_BOARD`, or a
  playback/stream whose `master_board` is `SYNTHETIC_BOARD` — only the synthetic board
  produces that format); `prerecorded=True` for `PLAYBACK_FILE_BOARD`. A streaming board
  cannot tell whether its producer is itself replaying a file: `prerecorded=False` there.

### Clock

BrainFlow's timestamp row: "UNIX timestamp ... Precision is microsecond, but for some boards
timestamps are generated on PC side as soon as packages were received"
(`DataFormatDesc.rst`) → `ClockInfo("unix")`. The playback board, by BrainFlow's default,
stamps samples with the time of replay (`new_timestamps`; the plugin does not change it, as
that requires `config_board`). Timestamps that go backwards (a stepped wall clock) are
clamped to the previous value and counted (`timestamp_regressions`).

### Loss

* `package_num` row → sample index. Step `k` (modulo the counter range) = `k-1` lost
  samples: `first_index` jumps and `dropped_packets` counts them; chunks are split at gaps.
  The counter range is not in `get_board_descr`; the default 256 matches the synthetic
  board (`unsigned char counter`, `synthetic_board.cpp`). Counter wrap is handled; a
  repeated number is counted (`package_num_repeats`) and treated as the next sample; a
  value outside `[0, modulus)` switches inference off (`package_num_unusable=1`) instead
  of inventing gaps. A gap of a whole multiple of the modulus is undetectable.
* BrainFlow's ring buffer (450 000 samples by default) overwrites old samples if the reader
  stalls; that shows up as a package-number gap.

### Errors and lifecycle

`prepare_session`/`start_stream` failure → `OpenFailed` with BrainFlow's exit-code name and
number (e.g. `UNABLE_TO_OPEN_PORT_ERROR (BrainFlow exit code 2)`), and the session is
released. `get_board_data(_count)` errors → `LinkLost`. No sample for `stall_timeout_s` →
`LinkLost` (device gone, producer stopped, or playback file ended — BrainFlow's playback
board idles at end of file rather than reporting it). `close()` stops and releases the
session, is idempotent and never raises; a released board can be opened again.

### What was tested (official library, no mocks) — `pytest packages/concord-brainflow/tests`: 41 tests

* `test_bf_synthetic.py` (5): manifest/discover rules; metadata equals
  `get_board_descr` (rate, `eeg_names`, ambiguous types, units, aux types); 3 s of streaming
  through the public API with every documented rule checked by `tests/bf_contract.py`
  (shapes, labels, roles, non-decreasing timestamps, `first_index` continuity); rate from
  BrainFlow timestamps within ±10 % of 250 Hz; unix timestamps within 5 s of `time.time()`;
  no gaps; close idempotent; reopen after release.
* `test_bf_playback.py` (2): a synthetic capture (BoardShim, 2.4 s, > 256 samples so the
  counter wraps) with 5 samples deleted, written by BrainFlow's own `DataFilter.write_file`.
  `write_file` prints `%lf` (6 decimals, `data_handler.cpp`); the test checks the file equals
  the capture rounded to 6 decimals, then that every value played back through the plugin
  is **bit-for-bit equal** to `DataFilter.read_file` of the same file (exg and aux), that the
  5 deleted samples appear as a 5-sample `first_index` gap and `dropped_packets == 5`, that
  the counter wrap is not taken as loss, that the session is `prerecorded`, and that the end
  of file is reported as `LinkLost` after `stall_timeout_s`.
* `test_bf_streaming.py` (1): a second official `BoardShim` session (synthetic) publishes
  with `add_streamer("streaming_board://225.1.1.1:<port>")`; the plugin's `STREAMING_BOARD`
  session receives it over multicast. Every received sample equals the producer's sample
  with the same timestamp **exactly** (the streamer sends raw doubles); rate within ±10 %;
  stopping the producer → `LinkLost`. Multicast worked in this container.
* `test_bf_options.py` (24): 20 invalid-option cases; unknown device key; a real BrainFlow
  board driver (`CYTON_BOARD`) on a nonexistent serial port → `OpenFailed` containing
  `UNABLE_TO_OPEN_PORT_ERROR`; an empty playback file → `OpenFailed`, released cleanly;
  host-filled defaults accepted.
* `test_bf_layout.py` (9): every `BoardIds` description shipped with BrainFlow 5.23.0 maps
  cleanly (unique labels, disjoint rows, never invasive=True); Cyton (ambiguous + names),
  Muse 2 (EEG-only → EEG/noninvasive), ANT Neuro EE-411 (`EEG|RESISTANCE` → unit None),
  gForcePro (EMG, ADC → unit None); package counter wrap/gap/repeat/out-of-range/off.

### Measurements (`packages/concord-brainflow/scripts/measure_brainflow.py --seconds 10`)

This container (x86_64 Linux, Python 3.12.3, BrainFlow 5.23.0), 2026-11-07. Latency = wall
time when `read()` returned minus the sample's BrainFlow timestamp (same machine, same
clock). Machine-dependent; not a hardware figure.

| Source | Samples | Rate from timestamps | Latency median / p95 / max | Loss |
| --- | --- | --- | --- | --- |
| `SYNTHETIC_BOARD` | 2 501 | 249.96 Hz | 1.18 / 2.17 / 8.78 ms | 0 |
| `STREAMING_BOARD` ← synthetic producer (multicast) | 2 502 | 249.96 Hz | 5.41 / 10.22 / 19.55 ms | 0 |
| Conversion step alone (`_convert`, 32 rows × 250 000 samples) | — | 3.17 M samples/s | — | — |

The plugin returns as soon as BrainFlow has any sample (polling every 2 ms), so at 250 Hz
most chunks hold 1-2 samples; the streaming board receives BrainFlow's batches, hence the
higher latency.

### Not tested / not supported

* **No hardware.** No real board was connected; units, channel types and package counters of
  real boards are taken from BrainFlow's descriptions and docs only.
* Only the DEFAULT preset is read: boards that put sensors into the auxiliary/ancillary
  presets (e.g. Muse accelerometer/PPG) deliver only their DEFAULT rows.
* Board configuration (`config_board`, gain/channel settings, impedance modes) is not
  offered: it writes to the device.
* BrainFlow markers cannot reach the plugin (see above).
* `prerecorded` for a streaming board whose producer replays a file is not detectable.

### Researcher setup

1. `pip install concord-brainflow` (pulls `brainflow` and `concord-adapter-sdk`).
2. In the Concord console, open the BrainFlow plugin, choose `board` and set the
   connection options BrainFlow's "Supported Boards" page lists for your board (e.g.
   `serial_port=/dev/ttyUSB0` for a Cyton). Try `synthetic` first.
3. To replay a recording: device `playback`, `file=<BrainFlow file>`,
   `master_board=<board that recorded it>`. To share one board between programs: in the
   process that owns the board call `add_streamer("streaming_board://225.1.1.1:6677")`
   and open device `streaming` with `ip_address=225.1.1.1`, `ip_port=6677`,
   `master_board=<board>`.
4. If your board's package counter is not 0-255, set `package_num_modulus` (or 0 to turn
   loss inference off).

---

## 2. BCI2000 (`packages/concord-bci2000`)

### BCI2000's external interfaces

Determined from BCI2000's own source and documentation (sparse clone of a BCI2000 source
fork, `github.com/Personator01/bci2000` @ `40a2067`, BCI2000 3.6; bci2000.org was not
reachable from the build container).

| Interface | What it exposes | Direction | Concord uses it? |
| --- | --- | --- | --- |
| **App Connector — ConnectorOutput** (`src/shared/modules/application/ConnectorFilters.cpp`; `Technical_Reference:App_Connector`) | Per data block: every state value and every element of the signal reaching the end of the application module, i.e. the **control signal** from signal processing (FeedbackTask/StimulusTask pass their input through: `FeedbackTask.cpp` lines 100, 279; `StimulusTask.cpp` lines 188, 497). UDP, one ASCII line per datagram. | BCI2000 → client | **Yes** (this plugin) |
| App Connector — ConnectorInput (same file, lines 115-162) | Lets a client *set* states and control-signal elements | client → BCI2000 | No — write path |
| Operator scripting `ADD WATCH <expr...> AT ip:port` (`User_Reference:Operator_Module_Scripting`) | On every change of the watched states/expressions: one UDP datagram, one tab-separated line ending in CRLF, first field a timestamp in the SourceTime time base. The App Connector page names it the successor of ConnectorOutput. | BCI2000 → client, but the watch is created by an Operator command | No (not implemented). Usable read-only if the researcher's own BCI2000 script adds the watch; a candidate for a future plugin mode |
| Operator telnet / BCI2000Remote (C++ class, `BCI2000RemoteLib` C API, `OperatorLib`; `Technical_Reference:BCI2000Remote_Library`) | Full control of a BCI2000 instance: start/stop modules, set parameters, `SetStateVariable`, `GetStateVariable`, `GetControlSignal` (polling) | bidirectional control | No — controlling BCI2000 is outside Concord's read-only stance |
| FieldTripBuffer filter (`Contributions:FieldTripBuffer`, `src/contrib/SignalProcessing/FieldTripBuffer`) | Hosts a FieldTrip realtime buffer (TCP) and writes the filter's *input* into it — raw signal when placed first in signal processing, processed signal later — plus selected states as buffer events; can also read events back into states/output | BCI2000 → buffer ← client (bidirectional) | No. This is **the route for raw signal** out of BCI2000; a client would only read. Not built or tested |
| BCI2000 data files (`.dat`) | Raw signal + all states, offline | file | No (offline; Concord's offline path is NWB) |

### App Connector protocol (what the plugin implements)

From `ConnectorFilters.cpp` (BCI2000 3.6) and confirmed on the wire with a genuine build:

* `ConnectorOutput` default address: `localhost:20321` (line 167); `ConnectorInput`
  default `localhost:20320` (line 64). The plugin's default port is **20321**.
* `Process` (lines 217-234): once per block and per address, `Clear()` the buffer (line
  224), then `"<State> <value>\n"` for every state in StateList order (line 226), then
  `"Signal(<ch>,<el>) <value>\n"` channel-major, zero-based (lines 227-229).
* `Connection::OnExecute` (lines 243-264): each line is sent as its **own UDP datagram**.
* State values are `uint32_t` (`State.h`) taken at sample 0 of the block
  (`Environment.cpp`: `StateRef(pState, Statevector, 0)`); signal values are `double`
  printed by `std::ostream` defaults (6 significant digits).
* StateList order is definition order followed by padding states `__pad<N>`
  (`StateList::AddPadding`). Observed with SignalGenerator + DummySignalProcessing +
  DummyApplication: `Notes, Recording, SourceTime, StimulusTime, SourceChannel1, FilePart,
  Running, <added states>, __pad0..__pad3`.
* `Clear()` discards lines of the previous block not yet sent, and stopping a run
  (`StopRun` → `DeleteConnections`) cut the last block in our capture after its first line:
  blocks can be **truncated**, besides ordinary UDP loss/reordering.

**Block boundary rule** (`protocol.py`): a block starts with a state line; a new block
begins when a state line follows a Signal line, when a state or Signal element repeats
within the current block, or (once the layout is known) when the layout's first state
arrives. With a known layout a block is complete when its last Signal element arrives
(emitted immediately, no extra block of latency); otherwise it is finished by the next
block. **Layout learning:** `open()` receives until two consecutive blocks have the same
state list and a complete rectangular `Signal(ch,el)` grid; the first block seen is only
used to synchronise (the socket may have been bound mid-block). If nothing consistent
arrives within `open_timeout_s` (default 10 s) → `OpenFailed` telling the operator to set
`ConnectorOutputAddress` and start a run. Lines are parsed strictly (`[A-Za-z_][A-Za-z0-9_]*
<uint32>` or `Signal(<int>,<int>) <float>`, newline-terminated, ASCII); malformed lines and
unknown state names are counted, never fatal. A Signal element outside the layout, or 5
consecutive blocks carrying the same smaller set of elements → `ConfigurationChanged`.

### Mapping

| Stream | Role | Content |
| --- | --- | --- |
| `control_signal` (primary) | DECODER_OUTPUT, `quantity="control_signal"`, `model_id="bci2000-control-signal"` | one sample per block; channels `Signal(ch,el)`; unit `None` (App Connector carries no units). Becomes `intent.kinematics` with `decoded_intent` provenance in Concord and reaches apps as a command **only** if the operator enables the command router |
| `states` | BEHAVIOR, `quantity="bci2000_state"` | selected states (option `behavior_states`; `auto` = whichever of `TargetCode, ResultCode, Feedback` (FeedbackTask.cpp) and `StimulusCode, StimulusType` (StimulusTask.cpp) BCI2000 sends) |
| `state_changes` | MARKERS | transitions of selected states (`marker_states`, same default), e.g. `TargetCode 0->2` |

Element semantics depend on BCI2000's signal processing (e.g. cursor X/Y/Z per channel in the
cursor task; elements may be time samples or spectral bins), so they are labelled by index,
not interpreted. With DummySignalProcessing the "control signal" is the source signal passed
through; it is still labelled as control information, because that is what the interface
carries. Non-finite control values are not forwarded (Concord events require finite values;
counted as `nonfinite_blocks`). The manifest, the device entry and `SessionInfo.origin`
(`bci2000:<host>:<port> (processed control information, not raw signal)`) say this is
processed control information. App Connector does not reveal BCI2000's source module, so
`synthetic`/`prerecorded` are operator declarations (`declare_synthetic`,
`declare_prerecorded`, default false).

### Clock

`SourceTime` is a 16-bit state (`DataIOFilter.cpp`: `"SourceTime 16 0 0 0"`) set to
`PrecisionTime::Now()` when a block is acquired; `PrecisionTime::Now()` is BCI2000's
monotonic clock in ms truncated to 16 bits (`PrecisionTime.cpp`; on Linux
`clock_gettime(CLOCK_MONOTONIC)`, `TimeUtils.cpp`). When SourceTime is sent (default
`clock=auto`) timestamps are the unwrapped SourceTime in seconds, domain `source`. The number
of 65.536 s wraps between blocks is chosen so the SourceTime difference best matches the
receive-time difference, so pauses longer than 65 s (between runs) stay correct; a block whose
time would go backwards arrived out of order and is dropped (`out_of_order_blocks`). Without
SourceTime (or `clock=receive_time`), the timestamp is the receive time of the block's first
datagram on the plugin host's monotonic clock (domain `source`, described as such).
`nominal_rate_hz` is 0.0 (unknown) unless the operator enters BCI2000's `SamplingRate` and
`SampleBlockSize` (`sampling_rate_hz`, `sample_block_size`): then it is their ratio.

### Loss

A stream skips the index of a block in which its own lines were lost, so loss is a
`first_index` gap. `dropped_packets` counts datagrams missing from observed blocks (the
layout fixes how many lines a block has) plus lines of blocks discarded as out-of-order or
untimed. **A block whose datagrams were all lost cannot be detected**: App Connector carries no
block or sample counter, and SourceTime is an acquisition time, not a counter. An earlier
version inferred lost blocks from SourceTime steps; against genuine BCI2000 it reported a loss
that did not happen (one block had a 62 ms SourceTime step followed by ~0 ms, with every
datagram received), so that inference was removed. Such gaps remain visible in the timestamps.
The socket requests a 4 MiB receive buffer (one datagram per line).

### Receiver restarts stop BCI2000's output until the next run (measured)

Against the genuine BCI2000 3.6 build: while a run was active, the receiver socket was closed
and re-opened. Re-opened immediately, data kept flowing (2,881 datagrams in the next 3 s);
after a **1 s gap with nothing listening, BCI2000 sent nothing more** (0 datagrams in the
next 5 s) for the rest of the run. In BCI2000's source, `ConnectorOutput` opens its sending
sockets only in `StartRun` (`ConnectorFilters.cpp` lines 198–210) and the send loop ignores
write failures (lines 243–264), so a destination that becomes unreachable is not retried
until the next run. Consequences: start the Concord source **before** starting the BCI2000
run; after Concord reconnects (plugin host restart, Concord restart), stop and start the
BCI2000 run. The plugin's open error says this. It is also why `concord-certify`'s
`reconnect.host_killed` phase cannot pass against a live BCI2000 run (the certifier kills
the receiver mid-run on purpose); see docs/COMPATIBILITY.md.

### What was tested

**Against genuine BCI2000 (this happened, within the timebox).** BCI2000 3.6 was built from
the fork in this container in about 15 minutes: `apt-get install qtbase5-dev
qtbase5-dev-tools libqt5opengl5-dev portaudio19-dev libsndfile1-dev libavcodec-dev
libavformat-dev libavutil-dev libswscale-dev libswresample-dev libavdevice-dev
libavfilter-dev libsdl2-dev`; `cmake -S <fork>/build -B <dir> -DUSE_OPENMP=OFF
-DCMAKE_CXX_FLAGS=-I<dir with a one-line bcistream.h>`; `make SignalGenerator
DummySignalProcessing DummyApplication Operator BCI2000Shell OperatorLib`. Two local
workarounds, no source edits: `USE_OPENMP=OFF` (the build passes `-openmp`, which GCC 13
parses as `-o penmp`), and a `bcistream.h` → `#include "BCIStream.h"` shim (the fork's
`SourceDecimationFilter.cpp` includes the wrong case). The application framework links
`ConnectorFilters.cpp` (`build/cmake/frameworks/AppModuleLib/AppFiles.cmake`), so
DummyApplication contains the real ConnectorOutput. `BCI2000Shell` runs an Operator script
(Operator with `QT_QPA_PLATFORM=offscreen`): SourceCh 2, SampleBlockSize 8, SamplingRate
256 Hz, `ConnectorOutputAddress localhost:<port>`, states TargetCode/ResultCode/Feedback added
with `ADD STATE` and changed with `SET STATE(S)` during the run (`tests/bci2000_live.py`).

* `tests/test_bci_real_bci2000.py` (opt-in: `BCI2000_PROG_DIR=<BCI2000/prog>`; skipped
  otherwise because BCI2000 is not a package dependency): passed here — 131 control blocks of
  16 elements, SourceTime rate 31.996 Hz (nominal 32), 0 malformed, 0 dropped, the 5 state
  changes in order.
* `tests/fixtures/bci2000_connector_output.json`: 2 011 datagrams recorded from that build
  with `scripts/capture_app_connector.py`. `test_bci_plugin.py::test_replay_of_genuine_bci2000_output`
  replays them over UDP with their original timing (runs in CI): every complete block's 16
  values equal the transmitted text exactly, timestamps equal SourceTime, the truncated final
  block is not emitted, markers `TargetCode 0->2, Feedback 0->1, TargetCode 2->0,
  ResultCode 0->2, Feedback 1->0`.

**Against a reproduction.** `tests/connector_output.py` reproduces `ConnectorOutput::Process`
and `Connection::OnExecute` byte for byte (cited lines; its formatting is checked against
values from the genuine capture). `test_bci_protocol.py` (18, pure): strict line grammar
(14 malformed forms), boundaries, layout learning when joining mid-block, lost Signal and
state datagrams (exact `dropped_lines`), truncated blocks, lost first state line, reordered
lines, reordered blocks, SourceTime wrap, a 200 s pause (wrap count from receive time), no
invented whole-block loss, markers, malformed/unknown/non-ASCII lines, multi-line datagrams,
layout change, non-finite values, receive-time clock. `test_bci_plugin.py` (20 incl. the
replay): manifest/discover, values and stats over UDP, `ConfigurationChanged` on a grown and a
shrunk layout, close/port release, no data → `OpenFailed` with setup hint, port in use →
`OpenFailed`, unknown selected state → `InvalidOptions`, 10 invalid-option cases, unknown
device key.

Totals: `pytest packages/concord-bci2000/tests`: 38 passed, 1 skipped (the opt-in live test;
it passes with `BCI2000_PROG_DIR` set).

### Measurements (`scripts/measure_app_connector.py --prog-dir <BCI2000/prog> --seconds 10`)

Genuine BCI2000 (SignalGenerator → DummySignalProcessing → DummyApplication/ConnectorOutput),
same machine. Latency = `time.monotonic()` when `read()` returned minus the block's
SourceTime (both CLOCK_MONOTONIC; SourceTime has 1 ms resolution, so values below ~1 ms are
at the clock's resolution). Covers BCI2000's processing chain, ConnectorOutput's sender
thread, UDP and the plugin.

| Run | Blocks | Block rate from SourceTime | Latency median / p95 / max | Malformed / dropped |
| --- | --- | --- | --- | --- |
| 1 | 324 | 32.002 Hz (nominal 32) | 1.18 / 2.05 / 62.71 ms | 0 / 0 |
| 2 | 320 | 31.999 Hz | 0.64 / 2.40 / 63.27 ms | 0 / 0 |

The ~63 ms maxima coincide with the occasional late block seen in BCI2000's own SourceTime
sequence (a 62 ms step followed by ~0 ms).

### Not tested

* No EEG amplifier, no real BCI2000 source module other than SignalGenerator, no real
  application other than DummyApplication (CursorTask, P3Speller, StimulusPresentation not
  built), Windows/macOS BCI2000 not tested, BCI2000 on a different machine not tested.
* The official bci2000.org distribution was not reachable; the build is from a public fork's
  source at the commit above.
* WATCH, FieldTripBuffer and BCI2000Remote are documented only (table above).

### Researcher setup

1. `pip install concord-bci2000`.
2. In BCI2000 (Operator → Config → Connector, or a batch script):
   `Set parameter ConnectorOutputAddress localhost:20321` (or `<Concord machine>:20321` with
   the plugin's `address` set to that machine's address). Leave `ConnectorInputAddress`
   empty: Concord never sends.
3. In Concord, open the BCI2000 App Connector device (address/port as above). Optionally
   enter BCI2000's `SamplingRate` and `SampleBlockSize` for a nominal rate, choose
   `behavior_states`/`marker_states` (comma-separated BCI2000 state names), and tick
   `declare_synthetic`/`declare_prerecorded` if BCI2000 runs SignalGenerator or FilePlayback.
4. Start a BCI2000 run; `open()` waits up to `open_timeout_s` for the first blocks (BCI2000
   sends only while running).
