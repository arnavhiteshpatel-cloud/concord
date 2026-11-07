# Open Ephys GUI — ZMQ Interface (read-only live source)

`brainos.adapters.openephys` reads the stream published by the Open Ephys GUI
**ZMQ Interface** plugin. BrainOS only *connects outward* to the GUI and never sends
data, commands or events to it. The only thing it sends is the plugin's heartbeat (application name +
random uuid), and you can turn that off.

**Validation level: protocol-tested.** The implementation has been tested against
BrainOS's own protocol-faithful test publisher and against the plugin's official Python
client. It has **not** been tested against a running Open Ephys GUI or against acquisition hardware.

## Source of the protocol facts

All protocol facts come from `open-ephys-plugins/zmq-interface` at commit `38513917`
(`38513917d6a7ee5791a47029d624a1b6110b01ee`). Two files were used:
`Source/ZmqInterface.cpp` (`sendData`, `sendEvent`, `sendSpikeEvent`, `process`, `run`) and
`Resources/python_client/plot_process_zmq.py`. The JSON formatting follows JUCE
`JSON::toString` (multi-line).

| Item | Fact |
| --- | --- |
| Sockets | PUB on `data_port` (default 5556); REP on `data_port + 1` for heartbeats |
| Envelope | `b"DATA\0"` for continuous data; `b"EVENT\0"` for TTL events **and** spikes (the NUL is part of the frame) |
| Header fields | Every header has `message_num`, `type` and `timestamp` (sender wall clock, ms). `message_num` goes up by 1 for every message, is reset when acquisition starts, and the first message is 1 |
| `data` message | `content{stream, channel_num, channel_name, num_samples, sample_num, sample_rate}` and `data_size = num_samples*4`. Payload: float32 samples. One message per selected channel per block, all with the same `sample_num` |
| `event` message | `content{stream, source_node, type, sample_num}` and `data_size`. A payload frame follows only if `data_size > 0`. TTL payload (type 3): line u8, state u8, word u64 LE |
| `spike` message | Fields are under the key `spike` (not `content`): `{stream, source_node, electrode, sample_num, num_channels, num_samples, sorted_id, threshold[]}`. There is no `data_size`. Payload: float32 waveform `[channel][sample]` |
| Order | Within a block, events and spikes are sent **before** the data |
| Heartbeat | JSON `{"application","uuid","type":"heartbeat"}`. The reply is `heartbeat received`, or `JSON message could not be read` if the JSON is invalid. The plugin marks a client dead after 5 s without a heartbeat |
| Units | **Not transmitted** |

## What the adapter does

1. **Learning in `open()`.** The adapter learns the stream layout from the stream itself:
   - stream name, sample rate, and the channel selection with names (from one complete
     block, i.e. all data messages that share one `sample_num`);
   - the spike electrodes seen during `learn_s`.

   The refined descriptor (kind `stream`, `synthetic=false`) declares:
   - `recording`, with `channel_count`, `sample_rate_hz`, `unit`, `channel_names`, `stream`
     and `frame_samples`;
   - `neural_features`, only if spike electrodes are known;
   - `device_status`.
2. **Frames.** Each complete block becomes one `recording.frame`, split at
   `max_frame_samples`:
   - `first_sample_index` is set to `sample_num`;
   - `device_timestamp_ns` is `round(sample_num / rate * 1e9)`;
   - provenance is `raw_signal`.

   If any channel message of a block is missing, the **whole block is discarded and
   counted**. The next frame is flagged `dropped_samples`. Samples are never fabricated.
3. **TTL events** become `recording.annotation` with label `ttl` and value
   `line=… state=… word=…`, with provenance `behavioral_label`. Each event is held until the
   frame that covers its sample has been emitted, so device timestamps stay monotonic.
4. **Spikes** become `features.binned` events with feature `spike_count`, one count per
   electrode, and provenance `processed_feature`.
   - Bins are `spike_bin_ms` long on the sample clock and are computed with exact
     rational arithmetic.
   - Spike detection is done by Open Ephys. The binning is done by BrainOS.
   - A bin is emitted only when the emitted frames cover its whole span. Bins that overlap a
     data gap are skipped, so `bin_index` jumps.
   - If messages were lost while a bin was open, the bin is flagged `dropped_samples`.
5. **Integrity accounting** (`adapter.counters`, `source_metadata()`):
   - `message_num` gaps (`missed_messages`);
   - per-channel `sample_num` gaps (`missing_samples`, counted as channel-samples);
   - incomplete and discarded blocks;
   - malformed messages, which are rejected with a specific reason and counted, and are
     also reported to the runtime as decode errors;
   - stalls, heartbeats, and the sender→local wall-clock offset (last and minimum).
6. **Link errors** (`DeviceLinkError`, so the runtime reconnects and learns the layout again):
   - no message for `stall_timeout_s`;
   - `message_num` reset (acquisition restarted);
   - a change of stream, sample rate, channel set or channel name;
   - a learned channel missing from 3 consecutive blocks;
   - a new spike electrode. The electrode is kept, so the next descriptor includes it.
     This does not apply if the electrodes were declared with `spike_electrodes`.
7. **Pause.** While paused, the adapter keeps reading and discarding messages (it counts
   them). On resume it waits for the next block start, so the first frame after a pause is
   not reported as a loss.

### Units policy

The protocol carries no physical unit. With `unit="unknown"` (the default), frames have
`unit: "arbitrary"` and the values are passed through unscaled. They must not be
interpreted as microvolts. If the operator states the unit configured in the GUI
(`uV`, `mV` or `V`), the values are converted to µV in float64 by multiplying by 1, 1e3 or
1e6.

### Configuration (`OpenEphysConfig`)

| Field | Default | Meaning |
| --- | --- | --- |
| `host` | `127.0.0.1` | GUI machine (hostname or IPv4) |
| `data_port` | `5556` | The plugin's Data Port; the heartbeat port is `data_port + 1` |
| `unit` | `unknown` | `unknown` / `uV` / `mV` / `V` |
| `open_timeout_s` | `4.0` | How long `open()` waits for a complete block (the runtime caps `open()` at 5 s) |
| `learn_s` | `0.5` | Minimum time `open()` listens, so it can see spike electrodes |
| `stall_timeout_s` | `2.0` | How long without any message before a link error is raised |
| `heartbeat` | `true` | Send heartbeats (lazy-pirate REQ, as the official client does) |
| `spike_bin_ms` | `20` | Spike-count bin length |
| `spike_electrodes` | learned | Declares the electrode names explicitly; spikes from other electrodes are only counted |
| `max_frame_samples` | `10000` | Frame split size (the contract maximum) |

## Setting up the Open Ephys GUI

1. Add **ZMQ Interface** to the signal chain, after the source and any filters or spike
   detector whose output you want.
2. In the plugin editor, choose the **stream**, set the **Data Port** (default 5556), and
   **select the channels** to send.
3. Start acquisition. When BrainOS heartbeats reach the plugin, BrainOS appears in the
   plugin's client list.

When connection fails, `open()` reports which of these cases applies:

| Case | What it means |
| --- | --- |
| No heartbeat reply and no data | Wrong host or port, the plugin is not in the signal chain, or a firewall is blocking it |
| Heartbeat replied but no data | Acquisition is not running, or no channels are selected |
| Events/spikes but no data | No continuous channels are selected |

## Limitations

- Not tested against a real GUI or real hardware. BrainOS cannot tell whether the GUI is
  reading hardware, a file or a simulator.
- The plugin's sample rate and channel count must fit the contract: ≤ 100 kHz and
  ≤ 1024 channels.
- Only the plugin's selected stream is sent. TTLs from other streams are filtered out by the
  plugin itself.
- Data that arrives while `open()` is learning the layout (at least `learn_s`, plus up to
  one block while it waits for the next block start) is not emitted. The same happens on
  every reconnect.
- The plugin writes the JSON header with `s.length()` characters, not UTF-8 bytes. A
  non-ASCII channel or electrode name would therefore be truncated by the plugin. The test
  publisher sends the complete UTF-8 header. JUCE's scientific-notation number formatting
  (|x| ≥ 1e6 or ≤ 1e-5) is reproduced only on a best-effort basis.

## Tests (`backend/tests/test_openephys.py`)

- **Protocol:**
  - byte-exact header for a data message;
  - round trips of data, TTL, payload-less event and spike messages;
  - 29 malformed cases, each rejected with a specific reason;
  - plugin heartbeat replies.
- **Adapter over real ZMQ sockets against `OpenEphysTestPublisher`** (a test publisher,
  *not* Open Ephys):
  - layout learning;
  - bit-exact values, both unscaled and unit-converted;
  - continuity;
  - message and block loss;
  - TTL and spike binning;
  - configuration change, deselection, restart and stall;
  - the different open-failure messages;
  - heartbeat registration;
  - pause and resume;
  - frame splitting.
- **Conformance** (`test_official_client_parses_publisher`):
  - The test downloads the official client at the pinned commit and checks its SHA-256. The
    client is GPL-3, so it is downloaded only into a temp directory and never committed.
  - It runs the client against the publisher on its hard-coded ports 5556/5557. The client
    parses the data (bit-exact), TTL line/state/word and spikes, and reports no
    "missing a message".
  - The test is skipped, with a reason, if there is no network or the ports are in use.
