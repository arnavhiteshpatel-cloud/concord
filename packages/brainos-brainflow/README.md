# brainos-brainflow

BrainOS source plugin (adapter SDK API 1.0, entry point `brainos.sources:brainflow`) that
reads boards through BrainFlow's official `BoardShim` API. BrainFlow boards are
noninvasive research/consumer biosensing devices; this plugin never presents them as
implants and never sends commands to a board.

Devices offered by `discover()` (BrainFlow cannot enumerate hardware generically, so these
are configurable entries, not detected devices):

| device key | board | needs |
| --- | --- | --- |
| `synthetic` | `SYNTHETIC_BOARD` | nothing |
| `playback` | `PLAYBACK_FILE_BOARD` | `file`, `master_board` |
| `streaming` | `STREAMING_BOARD` | `ip_address`, `ip_port`, `master_board` |
| `board` | option `board` (any `BoardIds` name) | the `BrainFlowInputParams` fields BrainFlow documents for that board |

Streams: `exg` (EEG/EMG/ECG/EOG rows; primary), `aux` (other sensor rows), `markers`
(non-zero values of BrainFlow's marker row). Metadata comes from
`BoardShim.get_board_descr`. See `docs/ECOSYSTEMS.md` in the BrainOS repository for the
full mapping, what was tested, and what was not.

Tests run against the official BrainFlow library (no mocks): `pytest packages/brainos-brainflow/tests`.
