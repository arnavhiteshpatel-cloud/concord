# Datasets — selection, verification, and known pitfalls

## Selected dataset

| | |
| --- | --- |
| **Dataset** | FALCON Benchmark H1: Human 7DoF Reach and Grasp Motor BCI |
| **Identifier** | DANDI **000954**, version `draft` (no published version exists) |
| **URL** | https://dandiarchive.org/dandiset/000954/draft |
| **License** | CC-BY-4.0 |
| **Access** | Open access. Downloading implies agreeing to the Data Use Agreement in the dandiset description: no attempt to re-identify or contact the participant, no contact with PIs about individual results, **no redistribution**. BrainOS therefore never commits or re-hosts the files; it downloads them from DANDI. |
| **Citation** | Ye, Joel; Collinger, Jennifer L.; Gaunt, Robert (2024) FALCON Benchmark H1: Human 7DoF Reach and Grasp Motor BCI (Version draft) [Data set]. DANDI archive. https://dandiarchive.org/dandiset/000954/draft |
| **Participant / provenance** | One human participant (*Homo sapiens*) with two 96-channel intracortical microelectrode arrays in the motor-cortex hand knob, recorded under an FDA Investigational Device Exemption, University of Pittsburgh, ClinicalTrials.gov NCT01894802. Subject metadata is redacted (age range, sex unknown). |
| **Signals in the file** | NWB `units` table: 176 spike-time trains described by the dataset as *multi-unit spiking activity*; `OpenLoopKinematics(Velocity)`: 7-DoF cued kinematics (tx, ty, tz, rx, g1, g2, g3), arbitrary units, 50 Hz; `TrialNum`; `eval_mask`. No raw voltage, no electrode table. |
| **Files used** | 13 `held-in-calib` blocks (~66 MiB) for evaluation; 2 of them (~8.7 MiB) for the demo. All 26 held-in assets are pinned by DANDI asset id + SHA-256 in `backend/src/brainos/datasets/falcon_h1.json`. |

## Why this dataset

Candidates checked against the DANDI API on 2026-11-07:

| Dandiset | Human invasive? | Behavior? | Size | Verdict |
| --- | --- | --- | --- | --- |
| **000954 FALCON H1** | yes — intracortical arrays | continuous 7-DoF kinematics + eval masks | 97 MiB total, 1–6.5 MiB per file | **selected**: designed for decoder benchmarking, small, open, NWB |
| 000252 Finger_RL | yes — intracortical | trial-based attempted finger movements | 36 MiB | good alternative; trial classification rather than continuous kinematics |
| 000950 FALCON H2 | yes — intracortical | attempted handwriting (text) | 1.2 GiB | heavier; text decoding needs a sequence model |
| 000055 AJILE12 | yes — ECoG | pose | ~790 GiB | far too large for this milestone |
| 000019 | yes — ECoG | speech syllables | ~52 GiB | too large; speech task |

## How the files are verified

1. `make dataset` (or `python -m brainos.datasets.fetch`) downloads each asset from
   `https://api.dandiarchive.org/api/assets/<asset_id>/download/`.
2. Size and SHA-256 are compared with the pinned manifest, which was built from DANDI's own
   `digest["dandi:sha2-256"]` metadata. A mismatch deletes the download and fails.
3. At load time BrainOS re-hashes the file. The console shows
   "✓ SHA-256 matches DANDI 000954 asset …" only on an exact match. Any other NWB file is
   still loadable but labelled **unverified**, and its provenance origin is `file:<name>`.

## Findings while integrating (read before using this dataset)

These were verified against the files themselves and the dataset authors' reference code
(`snel-repo/falcon-challenge`, `falcon_challenge/dataloaders.py`):

1. **`TimeSeries.rate` holds the period, not the rate.** `OpenLoopKinematicsVelocity.rate = 0.02`.
   Read as Hz, 12,233 samples would span 170 hours. The spike times span 244.6 s, which matches
   12,233 × 20 ms. The authors' loader computes `timestamps = offset + i * rate`. BrainOS
   accepts the period interpretation only when it is the *unique* one consistent with the
   spike times, and records the correction in the source's metadata notes.
2. **`eval_mask` semantics.** The file describes it as "Timesteps to ignore covariates", but the
   authors' loader documents it as "True if should evaluate", and 97.5% of samples are True.
   BrainOS follows the loader and records the discrepancy.
3. **`held-in-minival` is a subset of `held-in-calib`.** The dandiset description says so, and
   we confirmed it: the minival file for session 19250108T110520 is exactly the first 1,691
   bins of the calib file (identical kinematics and spike times). **Training on calib and
   evaluating on minival is complete train/test leakage.** BrainOS never does this, and its
   decoder refuses to run on any file from its own training session.
4. **Binning convention.** Bin *i* counts spikes in [tᵢ − 20 ms, tᵢ), where tᵢ is the bin's
   timestamp (a bin *end*), with `np.histogram`'s closed final edge. BrainOS's chunked binning is
   bit-identical to the authors' `bin_units` on all 14 downloaded files (tested).
5. **Dates are shifted** (sessions in 1925) for de-identification.
6. **No electrode table.** Physical electrode positions and array assignment are not in the
   file, so BrainOS identifies channels by unit id and reports the gap rather than inventing a
   mapping.

## Scientific limitations

- One participant, one cued open-loop task, ~2–4 minutes per block, 13 blocks over ~3 weeks.
- Kinematics are **cued** targets the participant attempted to follow, not measured limb motion
  (the participant has a spinal cord injury).
- Spike data is pre-processed (multi-unit spike times); raw broadband voltage is not available,
  so BrainOS's `recording.frame` (raw signal) capability is **not** offered for this source.
- Results from this dataset do not transfer to other participants, arrays or tasks.

## Suggested next dataset

For text/communication decoding, a natural next step is FALCON H2 (DANDI 000950, human
handwriting, 1.2 GiB), which needs a sequence model and character-error-rate evaluation. For
raw-signal ingestion, a smaller human intracranial dataset with an NWB `ElectricalSeries`
would exercise the `recording.frame` path. That requires a separate reader, since this reader
rejects raw-voltage-only files explicitly.

## Milestone 5, workstream B — human ECoG: AJILE12 (DANDI 000055)

Full write-up: docs/ECOG.md. Results: docs/ECOG_DECODING.md.

| | |
| --- | --- |
| **Dataset** | AJILE12: Long-term naturalistic human intracranial neural recordings and pose |
| **Identifier** | DANDI **000055**, published version **0.220127.0436** |
| **License / access** | CC-BY-4.0, `dandi:OpenAccess` (verified in DANDI metadata on 2026-11-07). Cite the dataset (doi:10.48324/dandi.000055/0.220127.0436) and its descriptor (doi:10.1101/2021.07.26.453884). |
| **Modality** | ECoG (subdural grids/strips during clinical epilepsy monitoring), 500 Hz, stored in µV (`conversion` 1e-6 V); manifest declares `modality: ecog`, `line_hz: 60` |
| **Behavior** | upper-body pose (9 keypoints, 30 Hz, video pixels), curated wrist-movement (reach) intervals with features, coarse behavior labels |
| **Files used** | participant `sub-07`, days 5 (train), 6 and 7 (held-out sessions): 6 pinned slices, 78.75 min of 64-channel ECoG, streamed with HTTP range requests (the source files are ~10 GB each) into local NWB extracts in `data/datasets/dandi-000055/`. Pinned in `backend/src/brainos/datasets/ajile12.json` by asset id + DANDI SHA-256 of each source file + SHA-256 of each slice's stored values. |

### Why this dataset (and why the M2 verdict "far too large" changed)

The M2 table above rejected 000055 because of its size (788 GiB). Milestone 5 adds slice
streaming: only the pinned sample ranges are read from the content-addressed DANDI blobs
(`remfile` + `h5py`), so a 22.5-minute demo costs ~157 MiB instead of two 10 GB files. Among the
ECoG dandisets on DANDI it is the one with raw voltage *and* motor behavior; 001535 (ECoG BCI,
imagined movements) only contains precomputed features (docs/ECOG.md §1).

### How slices are verified

1. `python -m brainos.datasets.fetch ajile12 [--all]` asks the DANDI API for the pinned asset id;
   the reported SHA-256 and size must equal the pinned ones, otherwise nothing is read.
2. The sliced `ElectricalSeries` values (stored dtype, little-endian, C order) must hash to the
   pinned `data_sha256`; the pose frames to `pose_sha256`.
3. The extract (an NWB file with the slice, the full electrodes table, the pose frames and the
   overlapping interval tables, on the original timeline) is re-hashed after writing and again
   whenever BrainOS loads it; its shape and start time must match the pinned slice. Anything
   else is "unverified" (origin `file:<name>`, no declared modality).

### Findings while integrating

See docs/ECOG.md §3: no channel names; `location` = `unknown` everywhere; coordinates without a
stated space; pose declared `meters` with `conversion` NaN (pixels); upstream 60/120/180 Hz
notches; recurring sub-second "data break" epochs; de-identified dates; `ReachEvents` equal to
`intervals/reaches.start_time`; electrode R² columns derived from these recordings (never used).
