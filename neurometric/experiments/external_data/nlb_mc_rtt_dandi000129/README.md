# MC_RTT (Neural Latents Benchmark), DANDI:000129, training file only

Downloaded 2026-11-27 for NeuroMetric behavioural-metric reproduction (cursor path, target
acquisition timing, effective-width throughput). Nothing from this directory has been executed.
The file was read once with h5py (read-only) to list its fields.

| Field | Value |
|---|---|
| File | `sub-Indy_desc-train_behavior+ecephys.nwb` (NWB 2 / HDF5) |
| Size | 49,764,168 bytes |
| SHA-256 (computed locally) | `2f78db62bd4d68b9bc737444f72bc2dfe475d7390dd7a54848aaf6a6a6ba8da5` |
| SHA-256 (DANDI asset metadata `dandi:sha2-256`) | `2f78db62bd4d68b9bc737444f72bc2dfe475d7390dd7a54848aaf6a6a6ba8da5` (matches) |
| Source | https://dandiarchive.org/dandiset/000129 (version 0.241017.1444), asset id `2ae6bf3c-788b-4ece-8c01-4b4a5680b25b`, download `https://api.dandiarchive.org/api/assets/2ae6bf3c-788b-4ece-8c01-4b4a5680b25b/download/` |
| Licence | CC-BY-4.0 (DANDI metadata `spdx:CC-BY-4.0`). Commercial use is allowed with attribution [V] |
| Required citation | O'Doherty, Joseph (2024) MC_RTT: macaque motor cortex spiking activity during self-paced reaching (Version 0.241017.1444) [Data set]. DANDI archive. https://doi.org/10.48324/dandi.000129/0.241017.1444 . Also cite the original recording dataset (O'Doherty, Cardoso, Makin, Sabes, Zenodo, https://doi.org/10.5281/zenodo.583331, CC-BY-4.0) and Makin et al. 2018, J Neural Eng, https://doi.org/10.1088/1741-2552/aa9e95 |
| Not downloaded | `sub-Indy_desc-test_ecephys.nwb` (1.2 MB). It holds held-out neural data only, with no behaviour |

## Contents (checked 2026-11-27) [V]

- Subject: one rhesus macaque ("Indy"). Session 2017-02-02. **Non-human primate, able-bodied,
  hand-controlled cursor.** This is not BCI control and not a clinical population.
- Task: self-paced random-target reaching on an 8x8 grid, with no gaps and no pre-movement delay
  (`general/experiment_description`).
- `processing/behavior/cursor_pos/data`: 649,100 x 2, sampled at 1000 Hz, in mm (conversion 0.001 to m).
  (0, 0) is the bottom centre of the screen.
- `processing/behavior/target_pos/data`: 649,100 x 2, at 1000 Hz, in mm. There are about 548 target
  changes and 52 unique target positions. 300 rows are NaN.
- `processing/behavior/finger_pos/data` (x 3) and `finger_vel/data` (x 2), at 1000 Hz.
- `intervals/trials`: 1,080 segments of about 600 ms each (810 train, 270 val). These are NLB
  segments, **not** task trials. Reconstruct reaches from the times at which `target_pos` changes.
- `units`: sorted spike times from a 96-channel M1 array. NeuroMetric does not need these.

## Caveats for Fitts-type analysis [INF]

- Target **width and the acceptance rule (hold time) are not stored in the file**, and the Zenodo
  description does not give them either [UNR]. Throughput can still be computed from effective
  width, We = 4.133 x SD of endpoint deviation along the task axis (Soukoreff & MacKenzie 2004).
  Nominal ID, error rate and target re-entry need the target size from Makin et al. 2018 or from
  the authors.
- The moment of target acquisition has to be inferred from the change of `target_pos` (the next
  target appears on acquisition). Movement-onset detection is up to the analyst.
- Reaches are continuous and self-paced, with no return to a home position. Each movement starts
  where the previous one ended, which makes the task close to ISO 9241-411 serial pointing.
