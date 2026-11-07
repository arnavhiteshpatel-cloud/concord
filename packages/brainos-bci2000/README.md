# brainos-bci2000

BrainOS source plugin (adapter SDK API 1.0, entry point `brainos.sources:bci2000`) that
receives BCI2000's **App Connector** output: the UDP datagrams BCI2000's `ConnectorOutput`
filter sends once per data block. This is **processed control information** — the control
signal computed by BCI2000's signal processing module and BCI2000 state values — not raw
brain signal. The plugin only receives; it never sends anything to BCI2000.

Setup in BCI2000: set the parameter `ConnectorOutputAddress` (Connector section) to the
plugin's address, e.g. `localhost:20321` (BCI2000's default), and start a run. BrainOS
learns the state list and the control-signal layout from the first blocks it receives.

Streams: `control_signal` (DECODER_OUTPUT, labels `Signal(ch,el)`, model id
`bci2000-control-signal`), `states` (BEHAVIOR: selected states, default the standard
`TargetCode`, `ResultCode`, `Feedback`, `StimulusCode`, `StimulusType` that are present),
`state_changes` (MARKERS such as `TargetCode 0->2`).

See `docs/ECOSYSTEMS.md` in the BrainOS repository for the protocol analysis (with source
citations), clocks, loss handling, and how this was tested.
