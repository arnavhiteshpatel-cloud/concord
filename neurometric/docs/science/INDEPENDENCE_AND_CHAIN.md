# Functional independence model and measurement chain (experimental)

## Independence states (per task attempt)
`device_unavailable < device_not_connected < not_used < abandoned < completed_other_input <
completed_with_assistance < completed_independently` (`chain/independence.py`).
Device activity alone never counts as independence. Assistance is captured as ASSIST events by
participant, care partner or staff: setup, physical, verbal, troubleshooting, calibration,
task_completion. Experimental score: assistance-weighted completion with a-priori, versioned
weights (setup 0.2, verbal 0.3, troubleshooting 0.4, calibration 0.4, physical 0.7,
task_completion 1.0). **Label: EXPERIMENTAL until validated** against external anchors
(care-partner diaries, observed assistance, licensed independence measures) in Stage 4–6.

## Measurement chain
Levels L1 device performance → L2 task performance → L3 real-world activity → L4 independence →
L5 care-partner assistance → L6 participation/QoL (`chain/chain.py`).
* Observations are long-form with provenance; any level may be missing.
* Associations are decomposed into **between-person** (person means; confounded by stable traits
  such as ability or care setting) and **within-person** (mixed model on person-mean-centred x
  with time) parts. The pooled correlation is reported as descriptive only.
* Mediation is an associational decomposition with listed, untestable assumptions.
* E-values quantify how strong unmeasured confounding would need to be.
* Verified on SYNTHETIC data with known structure: the within-person slope is recovered
  (−5 ± 1 assistance-minutes per unit) while the between-person association is strongly
  confounded (`tests/test_chain.py`).
Nothing in this module produces a causal claim or an economic claim automatically.
