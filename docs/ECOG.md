# Human ECoG in BrainOS (Milestone 5, workstream B)

A second, genuinely different neural modality, end to end: **raw-voltage electrocorticography
(ECoG) from a subdural grid** in a human, alongside the intracortical spike counts of FALCON H1
(docs/DATASETS.md). Same runtime, same contracts, same SDK-only application.

**Validation level** (docs/VALIDATION_LEVELS.md): software (level 1) plus **real-data
replay** — offline replay of recordings made during clinical epilepsy monitoring. Nothing here
is live acquisition, hardware validation or closed-loop control by a person.

## 1. Dataset choice

Candidates checked against the DANDI API on 2026-11-07 (sizes from DANDI metadata):

| Dandiset | Signal in the file | Behavior / labels | Size | Verdict |
| --- | --- | --- | --- | --- |
| **000055 AJILE12** (v 0.220127.0436) | raw ECoG `ElectricalSeries`, 500 Hz, µV declared; electrodes table with `good` flags | upper-body pose (9 keypoints, 30 Hz), curated wrist-movement (reach) events with features, coarse behavior labels | 788 GiB, 55 files of 7.8–18.6 GiB | **selected**: raw voltage + motor behavior; streamed in slices |
| 001535 (Natraj & Ganguly, ECoG BCI) | **features only**: "high gamma amplitude activity (70-150Hz) and low-frequency motor cortical potentials (<25Hz), down sampled … to 100Hz" (dandiset description) | imagined-movement targets (7 directions) | 4.4 GiB, 1 file | strong for feature-level decoding, but no raw voltage, so it cannot exercise a raw-signal importer or ECoG preprocessing. Good next dataset for a features-passthrough decoder. |
| 000019 (ECoG, CV syllables) | ECoG | spoken syllables | 51.8 GiB, 31 files | speech task; sequence decoding out of scope |
| 000465 / 000554 (PtNRGrids) | "multithousand-channel" grids (title), intraoperative | — | 120 GiB | channel counts beyond the contract's 1024-channel frame limit |
| 000623, 000576, 001613 | iEEG + single neurons | visual / movie tasks | 2–26 GiB | no motor behavior |

**License and terms (verified from DANDI metadata):** `spdx:CC-BY-4.0`, access
`dandi:OpenAccess`. Cite: Peterson SM, Singh SH, Dichter B, Scheid M, Rao RPN, Brunton BW
(2022) *AJILE12: Long-term naturalistic human intracranial neural recordings and pose*
(Version 0.220127.0436) [Data set]. DANDI archive. doi:10.48324/dandi.000055/0.220127.0436 —
described in Peterson et al., bioRxiv doi:10.1101/2021.07.26.453884; Peterson et al. (2021)
*Behavioral and neural variability of naturalistic arm movements*, eNeuro,
doi:10.1523/ENEURO.0007-21.2021; and *Mining naturalistic human behaviors in long-term video
and neural recordings*, J Neurosci Methods, doi:10.1016/j.jneumeth.2021.109199 (the DOIs DANDI
lists as `dcite:IsDescribedBy`). BrainOS never commits or re-hosts the data (`data/` is
git-ignored).

**Participant (chosen a priori):** `sub-07` — one 64-electrode grid (group `RFGRID`, described
in the file as "Right Frontal ECoG grid"; 63/64 marked good), contralateral (left) wrist reach
events, ≥ 190 curated reach events on days 5–7. Criteria: the smallest channel count (smallest
download) among participants with many reaches on three days. The authors' per-electrode
`high_freq_R2` / `low_freq_R2` columns were **not** consulted (they come from an analysis of
these very recordings).

## 2. Exactly what is read

Files are 10 GB each, so BrainOS streams only pinned **slices** with HTTP range requests
(`remfile` + `h5py`) from the pinned asset, then writes a local NWB extract
(`brainos/datasets/extract.py`). Pinned in `backend/src/brainos/datasets/ajile12.json`:

| Asset (DANDI 000055) | asset id | size | SHA-256 (DANDI `dandi:sha2-256`) |
| --- | --- | ---: | --- |
| `sub-07/sub-07_ses-5_behavior+ecephys.nwb` | b33fadbb-a6b1-45aa-8dce-7179a4968fef | 10,409,046,599 B | dd7f25f8…b81d |
| `sub-07/sub-07_ses-6_behavior+ecephys.nwb` | 9cbcf6f1-1bb2-4054-bd7f-efe76e78caaf | 10,431,086,594 B | 08c9c121…f53b |
| `sub-07/sub-07_ses-7_behavior+ecephys.nwb` | fbb5c167-42a3-4de1-b89b-54f944998d8c | 10,389,089,705 B | 5caca10d…f70e |

| Slice | Role | `acquisition/ElectricalSeries` samples | Time (s since session start) | Duration | Reaches | Demo |
| --- | --- | --- | --- | ---: | ---: | :---: |
| s07-d5-052650 | train | [26,325,000, 26,662,500) | 52650–53325 | 11.25 min | 16 | ✓ |
| s07-d5-056193 | train | [28,096,875, 28,434,375) | 56193.75–56868.75 | 11.25 min | 12 | |
| s07-d5-065643 | train | [32,821,875, 33,159,375) | 65643.75–66318.75 | 11.25 min | 9 | |
| s07-d6-047925 | test (held-out session) | [23,962,500, 24,300,000) | 47925–48600 | 11.25 min | 15 | ✓ |
| s07-d6-065643 | test (held-out session) | [32,821,875, 33,159,375) | 65643.75–66318.75 | 11.25 min | 14 | |
| s07-d7-066825 | test (held-out session) | [33,412,500, 34,087,500) | 66825–68175 | 22.5 min | 19 | |

All 64 channels; the pose frames covering the same time (`pose_frames` in the manifest); the
epochs and reach intervals overlapping it; the complete electrodes table and groups. In total
78.75 min of 64-channel ECoG (≈ 577 MiB of float32 samples read; 549 MiB of local extracts).
The demo set (`make dataset-ecog`, used by the tests) is the two ✓ slices (≈ 157 MiB).
Slices are aligned to the source's HDF5 chunks (84,375 samples = 168.75 s) and were chosen as
the densest reach windows of each day (counts of the dataset's reach annotations only).

**Verification.** Before reading, the asset's DANDI metadata must still report the pinned
SHA-256 and size (DANDI blobs are content-addressed). The slice's stored values (float32,
little-endian, C order) must hash to the pinned `data_sha256`, the pose frames to
`pose_sha256`. At load time BrainOS recomputes `data_sha256` from the extract and checks the
pinned shape and start time; a changed sample or a shifted timeline makes it **unverified**
(tested). The console shows "Extract: SHA-256 of acquisition/ElectricalSeries samples […)
matches the slice pinned from DANDI 000055 asset …". The full 10 GB file's SHA-256 cannot be
recomputed without downloading it; it is checked through DANDI's metadata at fetch time.

## 3. NWB layout (verified on the files) and findings

| Object | Content |
| --- | --- |
| `acquisition/ElectricalSeries` | float32 (samples × 64), gzip, chunks (84375, 1); `rate` 500 Hz, `starting_time` 0; `unit` volts, `conversion` 1e-6 → stored values **are µV** (the authors' converter: `conversion=1e-6  # data is in uV`) |
| `general/extracellular_ephys/electrodes` | x, y, z, imp, location, filtering (`250 Hz lowpass`), group / group_name, **good**, kurtosis, standard_deviation, median_deviation, low_freq_R2, high_freq_R2 |
| `processing/behavior/Position` | 9 `SpatialSeries` (L/R Ear, Elbow, Shoulder, Wrist, Nose), (frames × 2), 30 Hz, starting_time 0 |
| `processing/behavior/ReachEvents` | ndx-events `Events`, description `l_wrist`, onset timestamps |
| `intervals/reaches` | start/stop of each curated reach + magnitude (px), angle, onset speed (px/s), speech ratio, bimanual features |
| `intervals/epochs` | coarse behavior labels on the 30 Hz timeline, incl. `Blocklist (…)` entries |

Findings (all reported in the source's `notes`, never silently fixed):

1. **Channel names are not stored.** BrainOS labels channels `<group>/<electrode id>`
   (`RFGRID/0` … `RFGRID/63`).
2. **`location` is `unknown` for every electrode** (hard-coded by the converter); x/y/z are given
   without a coordinate space, so BrainOS makes no anatomical claim.
3. **Pose unit:** the SpatialSeries declare `meters` with `conversion` NaN; the reach features
   (`_px`) and the authors' code show they are **video pixel coordinates**. BrainOS reports
   `behavior.sample` unit `arbitrary`, values unscaled; NaN frames (untracked keypoints) are
   `valid: false`.
4. **Upstream filtering:** the stored signal already shows notch dips at **60, 120, 180 Hz**
   (power 0.07×, 0.16×, 0.30× the neighbouring frequencies on a training slice; a test asserts
   < 0.3 / 0.5 / 0.6 and no dip at 50 Hz), i.e. 60 Hz mains (US). This is the manifest's
   `line_hz: 60`.
5. **Data breaks:** `Blocklist (Data break)` epochs of 0.03–0.2 s recur about every 2 min.
   The samples there are not NaN. BrainOS passes them through unchanged, flags frames that
   overlap them `dropped_samples` (quality 0.5), and its evaluation excludes bins within 0.5 s.
6. `ReachEvents` timestamps equal `intervals/reaches.start_time` in every sliced session
   (checked at fetch time); the extract keeps the `reaches` table only.
7. **Dates are shifted** (sessions start at midnight UTC of days in January 2000) for
   de-identification; ECoG, pose and intervals share t = 0 (as in the authors' example code).
8. The authors' `high_freq_R2` / `low_freq_R2` columns are outcome information derived from
   these recordings; BrainOS never uses them for channel selection.

## 4. Importer (`adapters/nwb/ecog.py`)

`NWBElectricalSource` is a `ReplaySource` for the existing `ReplayAdapter`, listed by the NWB
catalog under the same `nwb:` ids (a file with an `ElectricalSeries` and no spike units goes
here; spike-time files still go to `NWBUnitsSource`). Descriptor: `kind = replay`,
`synthetic = false`, **`modality = ecog`, `invasive = true` — only because the pinned
manifest declares it** (an unverified ElectricalSeries file gets `modality = null`; nothing is
guessed), display name "Recorded Human ECoG — Offline Replay".

| Emitted | From | Provenance |
| --- | --- | --- |
| `recording.frame` (100 ms = 50 samples; `first_sample_index` = index in the source asset; device time = first sample; paced when the last sample exists) | `ElectricalSeries` × `conversion` (× `channel_conversion`) + `offset`, in **µV only when the unit is a voltage unit with a usable factor**, otherwise `arbitrary` | `raw_signal` |
| `behavior.sample` (30 Hz, 18 dims `L_Wrist.x` …) | Position SpatialSeries | `behavioral_label` |
| `recording.annotation` (`reaches`, `epoch` with the coarse label as value) | interval tables (rows starting inside the recording) | `behavioral_label` |

Recording capability parameters: `sample_rate_hz`, `channel_count`, `unit`, `frame_samples`,
`channel_labels`, `bad_channels` (from the file's `good`/`bad` column) and, from the manifest,
`line_hz`. `GET /devices/{id}/source` returns the electrode table, signal layout, interval
tables and the pinned slice (additive `SourceMetadata` fields), shown in the console.

## 5. Preprocessing (the pipeline's `ecog_high_gamma` preset)

| Stage | Choice | Why |
| --- | --- | --- |
| Line noise | IIR notch (Q 30) at the **source-declared** mains and harmonics below 0.45·fs: 60, 120, 180 Hz | AJILE12 is a 60 Hz recording (finding 4). Redundant with the authors' notches but harmless; required for sources that are not pre-filtered. An explicit request for a different notch frequency is refused (`line_hz: null` disables it). |
| Reference | common average over the electrodes the file marks **good**, subtracted from all channels | a broken electrode must not leak into every channel (tested with a 10⁴ µV artifact) |
| Band | 70–150 Hz Butterworth band-pass (order 4), log10 mean power per 100 ms bin | high-gamma power increases with movement over sensorimotor cortex (Crone et al. 1998, *Brain* 121:2301–2315; Miller et al. 2007, *J Neurosci* 27:2424–2432); 70–150 Hz is the band the 001535 ECoG BCI dataset uses. At 500 Hz with the file's 250 Hz anti-alias low-pass, 150 Hz is well below Nyquist. |
| Low-frequency / LMP | **not implemented** | the local motor potential (Schalk et al. 2007, *J Neural Eng* 4:264–275) is a signed low-pass amplitude, not a band power; the 1.4 contract has no feature name for it (needs a schema minor bump) |

All stages are causal and chunk-invariant (tests: random chunking == one block; changing the
future never changes past bins). The live pipeline's features equal the offline analysis
features bin for bin on the real held-out slice (`test_pipeline_features_equal_the_offline_analysis`).

## 6. Decoding: movement vs rest (`decoding/evaluate_ecog.py`, results in docs/ECOG_DECODING.md)

The labels permit a **binary movement-vs-rest** classifier; the participant was not trying to
control anything, so this is movement *detection*, not intention decoding.

* **Labels** (fixed before any held-out day was loaded): *move* = the bin ends inside a
  curated reach interval; *rest* = no reach within 2 s, both wrists tracked on every pose frame
  within ±1 s, both wrists' pose speed median < 20 px/s and max < 60 px/s in that window (the
  thresholds were set from the training day's wrist jitter, median ~8–11 px/s); everything else
  unlabelled (56–98 % of the bins of a slice). Excluded: the first 2 s of each slice (filter warm-up) and
  ±0.5 s around data breaks.
* **Split:** train on **day 5** (3 slices); score **days 6 and 7** — held-out *sessions*. The
  model records `training.session = "5"`; the pipeline refuses it on any day-5 stream and the
  evaluation refuses to score it on day 5 (tested).
* **Model:** the existing BrainOS LDA (causal exponential smoothing τ 300 ms, z-score with
  training statistics, Ledoit-Wolf shrinkage, priors from training labels) on the 63 good
  electrodes; the bad electrode gets zero weight (`input.excluded_channels`).
* **Controls:** chance (balanced accuracy and AUC 0.5), majority-class rate for accuracy, and a
  time-shift null (the same model on features circularly shifted at 20 offsets).

Results (`python -m brainos.decoding.evaluate_ecog`, deterministic; model
`move-vs-rest-lda-9f85d45365`, 393 move / 4985 rest training bins):

| Held-out session | Scored bins (move / rest) | Balanced accuracy | Time-shift null mean / max | AUC P(move) | AUC null mean / max | Reaches with P(move) > 0.5 | P(move) > 0.5 onsets per rest minute | All bins with P(move) > 0.5 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| day 6 (2 slices, 22.5 min) | 3482 (388 / 3094) | **0.938** | 0.511 / 0.540 | **0.992** | 0.526 / 0.602 | 29/29 | 3.68 | 15.2 % |
| day 7 (1 slice, 22.5 min) | 2939 (184 / 2755) | **0.861** | 0.501 / 0.550 | **0.939** | 0.502 / 0.568 | 16/19 | 6.10 | 11.4 % |

Context (not a held-out session): trained on the two earlier day-5 slices, scored on the latest
day-5 slice: balanced accuracy 0.875, AUC 0.970 (only 159 labelled bins).

Sanity check on the training day: the move–rest effect is **focal**, not grid-wide — median
per-electrode d′ 0.35, 4 of 63 electrodes above 1, all at the dorsal end of the grid (largest:
RFGRID/10, d′ 2.03, file coordinates x 26, y −22, z 77); correlation of d′ with z 0.48. A
grid-wide movement artifact would not look like that; the coordinate space is not stated in
the file, so no anatomical claim is made.

**How to read these numbers.** They are high because the task is easy by construction: curated
arm reaches against periods in which *both wrists are still*. The detector also fires in
unlabelled time (11–15 % of all bins have P(move) > 0.5, while curated reaches cover ~3 % of
the time), i.e. during other movements, eating or talking, and produces 3.7–6.1 false onsets per
minute of labelled rest at a 0.5 threshold. Day 7 is worse than day 6 (drift across days; no
recalibration). One participant, one grid, ~79 minutes of data: these results do not transfer
to other participants, implants or tasks, and say nothing about closed-loop control.

## 7. Same application interface across modalities

`test_unchanged_menu_app_gets_decoded_commands_from_ecog_after_authorization` (real server,
real held-out day-6 extract) runs the **unchanged, SDK-only** `examples/reference_app/menu_app.py`
— the same file that runs on the synthetic EEG plugin (`test_m4_demo.py`) and the synthetic
motor-imagery source (`test_control_e2e.py`):

1. The ECoG device is listed with `modality: ecog`; the menu app is `suspended` (no source
   provides `selection`).
2. A classifier cannot drive a pointer: requesting a pointer mapping is refused.
3. Pipeline `ecog_high_gamma` + the move-vs-rest LDA (trained on day 5) + a discrete router
   rule (`move` → `primary`, P > 0.8 held 200 ms, refractory 1.5 s), playback at 8×.
4. The router emits selections, but the app receives **none** until the operator authorizes
   `reference-menu` for `selection` (default deny).
5. After authorization the app acts on decoded `primary` commands (`decoded_intent` with the
   model id). In one observed run: 2 actions before the test's stop condition, highlight moved from "Messages" to "Music" (the count depends on wall-clock timing, not asserted beyond ≥ 2).
6. After `disconnect` the app is told commands stopped and receives nothing more.

Raw voltage, pose and reach labels never become commands: only the router, from the decoder's
`decoded_intent`, emits `intent.selection`.

## 8. Modality guards (`decoding/model.py`)

A model records its training modality in `input.modality` (models without it inherit the
modality the pinned manifest of their training dataset declares: FALCON H1 → `intracortical`,
AJILE12 → `ecog`). Loading a model on a stream of a **different declared modality is refused,
even with the cross-source override** (`incompatible_decoder`). Tested on real streams: the ECoG
LDA on FALCON spike counts, a FALCON ridge decoder on ECoG, and an EEG-declared copy of the
ECoG model on ECoG are all refused. An undeclared modality on either side is a warning, and a
model that uses a channel the stream marks bad gets a warning. Models calibrated from BrainOS
recordings now declare the recorded device's modality.

## 9. Limitations

* Offline replay only: no live ECoG source has been connected (an ECoG amplifier over LSL / Open
  Ephys / a plugin would use the same pipeline, but none was available).
* One participant (sub-07), 6 slices (78.75 min) from 3 days, chosen as the densest reach
  windows; performance on other periods (sleep, long inactivity) is not measured.
* Movement vs rest only. Reach direction (`Reach_angle_degrees`) and continuous wrist velocity
  were not attempted: ~37 training reaches are too few for direction classes, and pose is 2-D
  video pixels from one camera.
* LMP / low-frequency features are not implemented (§5).
* The data was notch- and low-pass-filtered upstream; BrainOS's notch was never tested on
  un-notched real ECoG.
* Channel names, anatomical locations and the coordinate space are not in the files.

## 10. Reproduce

```bash
make dataset-ecog        # 2 demo slices (~157 MiB) — enough for the tests
make dataset-ecog-all    # all 6 slices (~550 MiB)
make ecog-report         # model -> data/models/, reports/ecog_decoding.json, docs/ECOG_DECODING.md
cd backend && ../.venv/bin/pytest -q tests/test_ecog.py tests/test_ecog_real.py
```
