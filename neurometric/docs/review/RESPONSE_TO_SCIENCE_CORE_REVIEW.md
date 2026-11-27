# Response to the science-core review (2026-11-27)

All results in `experiments/results/` were regenerated **after** these fixes (the earlier partial
run was discarded). Regression tests: `tests/test_review_regressions.py`.

| ID | Finding | Resolution |
|---|---|---|
| C1 | Latent ability made velocity users worse (kp scaled with ability) | kp no longer scaled with ability; test: MT falls monotonically with ability |
| C2 | Invalid TP averaged; MT censored by timeouts | `iso_tp_bps` = mean of *valid* conditions (NaN otherwise); `iso_tp_all_bps` kept as diagnostic; `iso_mt_ms` counts timeouts at the limit; `iso_mt_completed_ms` separate |
| C3 | Tracking ran at minute 0; every task restarted the clock | one session clock across the battery (+30 s rest between tasks); tracking receives it; test added |
| C4 | Scanning ignored the population | per-person reaction-time scale from the population; test: between-person SD > 0 |
| C5 | WPM/CCPM clock started at phrase onset | clock from first to last keystroke; `phrase_time_s` kept separately |
| I | Tracking lag biased to 0 | lagged products averaged, not summed; test recovers 200 ms |
| I | `run_typing` could loop forever | attempt cap per phrase; `aborted` flag; test with total dropout |
| I | Adaptive vs fixed grid used different empty-click rules; staircase hit floor | same rule; floor 6 px, step ×1.4, 40 trials |
| I | Latency jitter realised < nominal | documented (outputs never reorder); report realised latency |
| I | Cross-modality unfairness (dwell in MT; scanning ground-truth false activations; empty scan cells; no ISO errors for position users) | `selection_method` column; scanning false activations = NaN (not observable), ground truth kept as `gt_*`; 4×7 frequency-ordered scanning layout without empty cells; position users click without verification with probability 0.6 (mouse) / 0.3 (head) → realistic ≈3% errors |
| I | Both ISO conditions had the same ID | conditions now ID 2.32 and 3.55 bits |
| I | Retest sessions differed only in noise | day-to-day within-person variation (log-normal SD 0.10) between sessions; ICCs still labelled upper bounds |
| I | SIMULATOR.md over-claimed tests and "learning" | corrected: untested parameters listed; learning not modelled |
| M1 | Adapter duplicated the selection sample | fixed; round-trip test now includes MV/ME/MO/TAC/submovements |
| M2 | Dwell timing one tick late | Reviewed: the counter measures time since the entry *sample*; kept, documented as sample-based (±1 tick, 10 ms) |
| M3 | Labels | C_latency axis says total latency; heatmap comment fixed; monotone mean excludes gain sweep |
| M4 | AR(1) noise started at 0 | initialised from the stationary distribution |
| M5 | Ring geometry varied with length in Exp I | ring fixed at 13 targets; `n_selections` continues around the ring |
| M6/M7 | Sampling-rate dependence of TAC/MDC/ODC; IF definition | documented in METRICS.md |
| M8 | Repeated PAUSE double-counted rest | fixed; test |
| M9 | ADL recovery errors uncounted; mistaken "back" did not navigate | fixed |
| M10 | No spatial-outlier rule for We | flagged (not excluded) per MacKenzie & Isokoski criterion |
| M11 | Test gaps | TRE/TAC known-count test added |
