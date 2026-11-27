# Public datasets for reproducing behavioural / input metrics

Accessed 2026-11-27. Labels follow `CONVENTIONS.md`. The full table is in `datasets.csv` (27 rows).

**How metadata was checked**
- Licences and sizes were taken from repository APIs: DANDI REST API, DataCite REST API (for
  Dryad, Zenodo, figshare and Edinburgh DataShare DOIs), Zenodo records API, figshare API, and the
  PhysioNet, Aalto and BBCI pages.
- The Dryad v2 API was **refused by the session proxy** (HTTP 403, "upstream denied the request:
  connection 'Dryad API access token'"). DataCite metadata was used for Dryad DOIs instead. These
  give the licence (CC0) and total size but not file-level listings.
- The session's web-search budget ran out during this part. Items not located by then are marked
  [UNR] and listed as follow-ups.

---

## 1. Usable now for behavioural-metric reproduction (cursor + targets + timing, permissive licence)

| Dataset | What it contains | Fitts / path usable? | Licence (commercial) | Size | Status |
|---|---|---|---|---|---|
| **NLB MC_RTT**, DANDI:000129 v0.241017.1444 [V] | Macaque (Indy) self-paced random-target reaching on an 8x8 grid. `cursor_pos`, `finger_pos` and `target_pos` at 1 kHz (mm), plus M1 spikes | **Yes.** Serial point-to-point reaches with no delay, close to ISO 9241-411 serial pointing. Target width is not stored, so use effective width | CC-BY-4.0 (yes) | 51.0 MB (train file 49.8 MB) | **Downloaded** |
| O'Doherty et al. RTT full set, Zenodo 10.5281/zenodo.3854034 [V] | Same task, 2 monkeys, 47 sessions (about 20,000 + 6,500 reaches); cursor and target at 250 Hz | Yes (multi-session: learning and test-retest analogues) | CC-BY-4.0 (yes) | 24.0 GB; per-session 84-500+ MB | Not downloaded |
| NLB MC_Maze_Small / Medium / Large / full (DANDI 000140/139/138/128) [V] | Center-out maze reaching with barriers; cursor, hand and eye position; delay/go timing | Path metrics yes. Fitts only partly (curved, obstructed paths) | CC-BY-4.0 (yes) | 29.9 / 77.3 / 149.4 / 694 MB | Not downloaded (Small qualifies under 50 MB if wanted) |
| Stieger, Engel & He 2021 EEG BCI dataset, figshare 10.6084/m9.figshare.13123148 [V] | 62 healthy adults, 7-11 sessions of SMR-BCI cursor control in 1D and 2D; 62-ch EEG; online success rates | Likely yes. Per-trial cursor position is in the files [PK, not verified] | CC BY 4.0 (yes) | 376.9 GB (599 files) | Not downloaded. Verify fields on one session |
| GazeBase, figshare 10.6084/m9.figshare.12912257 [V] | 12,334 eye-movement recordings from 322 adults; fixation, horizontal and random-oblique saccade tasks with target positions; reading, video, gaze game | Gaze accuracy, latency and test-retest. No dwell selection | CC BY 4.0 (yes) | 6.7 GB | Not downloaded |

**Downloaded:** `/home/user/concord/neurometric/experiments/external_data/nlb_mc_rtt_dandi000129/`
- File: `sub-Indy_desc-train_behavior+ecephys.nwb`, 49,764,168 bytes.
- SHA-256 `2f78db62bd4d68b9bc737444f72bc2dfe475d7390dd7a54848aaf6a6a6ba8da5`. This matches DANDI's
  `dandi:sha2-256` [V].
- The README there gives the licence, required citations, field inventory and caveats.

Fields were confirmed by a read-only h5py listing (no code from the dataset was executed) [V]:
- `processing/behavior/{cursor_pos, target_pos, finger_pos, finger_vel}` at 1000 Hz;
- `intervals/trials`: 1,080 x 600 ms NLB segments, which are **not** task trials;
- about 548 target changes and 52 unique target positions.

**Caveats [INF]**
- This is able-bodied macaque hand control of a cursor, not BCI control and not a clinical
  population. Use it to **validate the metric pipeline**: TP with effective width, path metrics,
  submovements and min-jerk deviation. It must not be used for clinical norms.
- Target size and the acceptance (hold) rule are missing [UNR]. They must come from Makin et al.
  2018 (https://doi.org/10.1088/1741-2552/aa9e95) or the authors before computing nominal ID or
  target re-entries.

## 2. Neural BCI datasets (decoder benchmarks, not behavioural metrics)

| Dataset | Content | Cursor/targets | Licence | Size |
|---|---|---|---|---|
| FALCON H1 (DANDI:000954, draft) [V] | Human with tetraplegia (Pitt iBCI, NCT01894802): open-loop 7-DoF reach/grasp calibration | Cued kinematics, not a cursor | CC-BY-4.0 | 102 MB |
| FALCON H2 (DANDI:000950) [V] | BrainGate T5 handwriting | Prompted characters | CC-BY-4.0 | 1.23 GB |
| FALCON M1 / M2 (DANDI:000941 / 000953) [V] | Macaque reach-to-grasp with EMG; finger movements | Object/finger targets | CC-BY-4.0 | 312 MB / 15.9 GB |
| Willett 2021 handwriting (Dryad 10.5061/dryad.wh70rxwmv) [V] | T5 (SCI) neural data + sentence/character prompts | No cursor | CC0 | 1.41 GB |
| Willett 2023 speech (Dryad 10.5061/dryad.x69p8czpq) [V] | T12 (ALS) attempted speech | No | CC0 | 130 GB |
| Card 2024 speech (Dryad 10.5061/dryad.dncjsxm85) [V] | T15 (ALS) attempted speech | No | CC0 | 11.6 GB |
| BrainGate closed-loop cursor/grid sessions [UNR] | — | — | — | Not located this session |

## 3. EEG BCI datasets

| Dataset | Content | Licence / commercial | Size |
|---|---|---|---|
| PhysioNet EEGMMIDB (10.13026/C28G6P) [V] | 109 volunteers, 64-ch BCI2000, motor execution and imagery cues. No cursor kinematics | ODC-By 1.0 (commercial OK with attribution) | 3.4 GB |
| BCI Competition IV (bbci.de) [V] | ds1 continuous MI; ds2a/2b MI; ds3 MEG wrist direction; ds4 ECoG finger flexion | Terms: cite the recording group and paper, and report publications. Commercial not addressed [UNR] | Moderate [PK] |
| MOABB [PK] | Aggregator of about 30+ public EEG datasets | Per-dataset licences; check each | Varies |
| Stieger 2021 (see section 1) | Cursor-control EEG | CC BY 4.0 | 377 GB |

## 4. Text entry, mouse dynamics, gaze typing, switch scanning

| Dataset | Content | Licence / commercial | Size |
|---|---|---|---|
| Dhakal et al. 2018, 136M keystrokes [V] | 168,000 volunteers transcribing sentences; key down/up timestamps | "Free to use for research and non-commercial use with attribution", so **no commercial use** | 1.4 GB zip / 16 GB |
| Palin et al. 2019 typing37k (mobile) [V size / UNR licence] | 37,000+ mobile typists (via typingtest.com) | See readme [UNR] | 4.7 GB zip / 43.4 GB |
| Balabit Mouse Dynamics Challenge [PK/UNR] | Mouse event streams for user identification. **No targets** | Licence not verified (GitHub API not enabled for this session) | Small [PK] |
| Human ISO 9241-411 / Fitts pointing datasets [UNR] | Not located before the search budget ran out | — | — |
| Switch-scanning timing logs [UNR] | None found | — | — |
| Eye-gaze dwell-typing logs [UNR] | None verified | — | — |

## 5. Rehabilitation / clinical outcome datasets

| Dataset | Content | Licence | Notes |
|---|---|---|---|
| International Stroke Trial database v2 (10.7488/ds/104) [V] | Variables at randomisation, 14 days and 6 months | ODC-By 1.0 (commercial OK) | Outcome-level only |
| PRO-ACT [V counts / UNR terms] | 13,717 anonymized ALS trial records from 44 trials; longitudinal ALSFRS-R, labs, etc. | Registration; terms page not retrieved (404 at tested URL) | Priors for ALSFRS-R decline and anchor studies |
| ODC-SCI [PK] | SCI data commons (mostly preclinical) | CC-BY after release [PK] | Not re-verified |
| NSCISC SCI Model Systems [PK] | US SCI longitudinal outcomes | Restricted application [PK] | Not re-verified |
| Neuralink Webgrid [V] | Public browser game only; participant data not released | — | Use for task-design comparison only |

---

## 6. Bottom line [INF]
- **Behavioural metric reproduction now**: MC_RTT (downloaded) for cursor TP, path and
  submovement metrics. If more sessions are needed, add O'Doherty Zenodo sessions selectively (CC
  BY 4.0, about 100 MB each).
- **Next to verify**: one Stieger 2021 EEG session (~600 MB) to confirm the cursor/target fields.
  That would give a human, non-invasive BCI cursor dataset under CC BY 4.0, the closest public
  analogue to NeuroMetric's use case.
- **Gaps**: no public human dataset with permissive licence was confirmed for ISO 9241-411 mouse
  pointing, eye-gaze dwell typing or switch scanning [UNR]. NeuroMetric should plan to collect its
  own reference data (able-bodied plus AT users) and consider releasing it openly.
- **Text-entry norms**: Dhakal 136M is research/non-commercial only. Use it for internal
  methodological comparison only, and do not ship norms derived from it in a commercial product
  without permission.

## Follow-ups (search budget exhausted)
1. Locate human Fitts/ISO 9241-411 datasets: Müller, Oulasvirta & Murray-Smith "Pointing
   Dynamics Dataset" [PK], GoFitts sample data, Wobbrock FittsStudy datasets.
2. Confirm the Balabit licence and the typing37k readme licence.
3. Check DANDI/Dryad for BrainGate closed-loop cursor sessions with targets.
4. Retrieve the PRO-ACT Terms & Conditions page.
5. Retry the Dryad API once the proxy token issue is fixed, to get file-level listings.
