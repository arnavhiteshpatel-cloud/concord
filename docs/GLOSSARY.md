# Glossary

Terms used in the console and in these documents, in alphabetical order.

| Term | Meaning |
| --- | --- |
| **Acquisition source** | Where the data comes from: a simulated device, a recording replayed from a file, a live stream (LSL, Open Ephys) or a plugin. Chosen with **Connect a source**. |
| **Adapter** | The part of Concord that reads one kind of source and turns its data into standard events. Adapters only receive. Third parties write adapters as **source plugins** ([ADAPTER_SDK.md](ADAPTER_SDK.md)). |
| **Authorize (an application)** | Allow one application to receive decoded commands. Applications are not authorized by default, and authorization can be revoked at any time. |
| **`concord-hwval`** | The acquisition-verification toolkit: compares a Concord recording with a reference recording of the same signal ([HARDWARE_VALIDATION.md](HARDWARE_VALIDATION.md)). |
| **Calibration** | Fitting a decoder to recordings made with the same source, for example while a participant follows on-screen cues; the report gives held-out performance and controls. |
| **Capability** | A kind of data a source can provide or an application can ask for, such as `recording` (raw signal), `pointer_intent` (cursor movement) or `selection` (a click). Applications declare the capabilities they need; Concord grants those the current source provides ("negotiation"). |
| **Closed loop / open loop** | Closed loop: a person sees the result of their own brain activity and adjusts (real BCI use). Open loop: decoding recorded data afterwards, with no feedback to the person. All Concord decoding results are open loop. |
| **Command output** | The part of Concord (the "command router") that turns decoder output into commands for authorized applications. Off unless the operator starts it; **Stop control** turns it off. |
| **Communication board** | The participant-facing application included with Concord: tiles with words, selected with one of five input methods. Opened with **Open participant screen**. |
| **Console** | The operator's screen, in a web browser at http://127.0.0.1:8000. |
| **DANDI** | The DANDI archive (dandiarchive.org), a public archive of neurophysiology data in NWB format. Source of the FALCON H1 and AJILE12 datasets. |
| **Decoded intent** | Output of a decoder, e.g. intended cursor velocity. Always labelled with the model that produced it (`model_origin`: Concord, external, or historical). |
| **Decoder** | A model that turns neural features into intended movement or choices. |
| **Diagnostics** | Measured event rates, latencies, drops and errors (**Advanced → Diagnostics**). |
| **Dryad** | A public data repository (datadryad.org). Source of the T15 cursor + click dataset. |
| **ECoG** | Electrocorticography: signals from electrodes on the surface of the brain. |
| **Event / envelope** | One unit of data inside Concord, with its timestamps, capability, quality flags and provenance. The format is defined in [ARCHITECTURE.md](../ARCHITECTURE.md). |
| **Export bundle** | A zip of a research session (log, versions, settings, models, optionally recordings) that `concord reproduce` can verify and re-run elsewhere. |
| **Features** | Numbers computed from the raw signal per time bin, e.g. **threshold crossings** (spike counts) or **spike band power**, used by decoders. |
| **Held-out** | Data not used to train a decoder, used only to evaluate it. Concord never scores or shows a decoder on the data it was trained on ("leakage"). |
| **Historical** | Outputs of the original research system's decoders, recorded in a dataset and replayed; never presented as Concord output. |
| **Intracortical** | Recorded by microelectrode arrays inside the cortex (here: multi-unit spiking activity). |
| **LabRecorder** | The standard recorder of the Lab Streaming Layer ecosystem; writes XDF files. Used as a reference by `concord-hwval`. |
| **Lab Streaming Layer (LSL)** | A widely used protocol for streaming time series between programs on a lab network. |
| **NWB** | Neurodata Without Borders, a standard file format for neurophysiology data. |
| **Offline Replay** | Playing back recorded data from a file, labelled as such. Not live. |
| **Open Ephys GUI** | Open-source acquisition software. Concord reads its **ZMQ Interface** plugin; `concord-hwval` compares against its **Record Node**. |
| **Participant screen** | A second window (or screen) showing the communication board to the participant. |
| **Pipeline** | Signal processing (filters, feature extraction) followed by a decoder, run continuously on the connected source. |
| **Plugin** | Third-party code that adds a source (adapter SDK) or a decoder (decoder SDK); runs in its own process. |
| **Provenance** | Where an event came from: simulated, raw signal, processed feature, behavioural label, decoded intent… and whether it was replayed. Shown in the console and kept in recordings and exports. |
| **Raw signal** | Samples as acquired (e.g. microvolts per channel), as opposed to features. |
| **Recording** | A file of events Concord wrote while a source was connected; replayable through the same pipeline. |
| **Reference recording** | The recording made by the acquisition system's own software (LabRecorder, Open Ephys Record Node) at the same time as Concord's, for verification. |
| **Research session** | A named session that groups recordings, decoders and a log, and can be exported. |
| **Safe stop** | **Safe stop & disconnect**: command output off, recording closed, decoding stopped, source disconnected, in that order. Quitting the app does the same. |
| **Signal integrity** | Whether data arrives complete and on time: channels present, data received, delay, gaps. |
| **Simulated profile** | A built-in simulated device (Profile A or B) generating synthetic data; never brain data. |
| **Stop control** | The title-bar button that turns command output off immediately. |
| **Validation level** | How far a component has been validated: software, protocol, hardware, human participant ([VALIDATION_LEVELS.md](VALIDATION_LEVELS.md)). |
| **XDF** | The file format LabRecorder writes. |
