# DECISIONS

Architecture and scope decisions, newest last. Each has context, decision, consequences.

## D-001 (2026-11-27) NeuroMetric lives in `neurometric/` on branch `claude/neurometric-platform-vvzijh`
Context: the brief asks for a separate repository; this session can only push to
`arnavhiteshpatel-cloud/concord` and must not create repositories.
Decision: NeuroMetric is a self-contained directory (own pyproject, tests, web app, docs). No
Concord file outside `neurometric/` is modified. Concord's `main` is untouched.
Consequence: extract to its own repository with
`git subtree split -P neurometric -b neurometric-main` then push that branch to a new repo.

## D-002 Concord reuse: clean-room, reference only, importer provided
Context: audit (docs/research/concord_reuse_audit.md) found high-quality, well-tested code
(874 backend tests pass) but every package is marked "Proprietary (internal preview)"; there is no
LICENSE. The founder is the sole author, but UIUC IP policy may matter (see FOUNDER_HANDOFF).
Decision: NeuroMetric code is written fresh. Concord concepts reused with attribution:
provenance labels (simulated / replayed / live), "never fabricate confidence", read-only one-way
flow, achieved bitrate and false-activations-per-minute. A Concord recording importer
(`neurometric.adapters.concord`) maps `concord.recording/1` files into canonical events.
Concord has no degradation simulator, so the simulator is new.

## D-003 Python is the scoring source of truth
All authoritative metrics are computed in Python from canonical events. The browser records
events and shows provisional feedback; its small TypeScript metric subset is checked against
Python golden fixtures (cross-language parity test).

## D-004 Stimuli are generated once (Python, seeded) and exported as JSON
No cross-language PRNG. The browser and the simulator present byte-identical stimuli
(`stimulus_hash`).

## D-005 Simulation = closed loop with delayed perception
Virtual users perceive the *degraded* cursor with a feedback delay and correct for it, as real
users do. A pure open-loop noise model would overstate the harm of drift/bias and understate the
harm of latency. Basis: feedback-control models of BCI users (Willett et al. 2019) [PK].

## D-006 Observable-only metrics
Metric functions take only data a real deployment can record. Simulation ground truth
(intended selections, injected false activations, dropout ticks) is stored separately and used
only to validate the metrics.

## D-007 Storage: SQLite (stdlib) for local research deployment; Postgres-ready schema
Simpler to install for a student lab, single file backup, WAL mode. The data layer is a thin
repository class so a Postgres backend can be added for hosted deployments.

## D-008 Default telemetry is application-scoped only
No OS-level hooks ship enabled. Cross-application usage measurement is a documented design with
platform-specific contracts; sponsor-export import is the preferred route (see platform matrix).

## D-009 Sponsors see pseudonymous participant codes, never re-identification data
Context: the portal review noted that the data-query API returns `participant_id` to sponsor
analysts. Decision: keep. Coded subject identifiers are standard in sponsor-monitored research and
are needed to resolve data queries; they are random and non-derivable, and the re-identification
key table is site-scoped and never visible to sponsor roles. The portal hides the column where it
is not needed. Revisit if a study's data-sharing agreement requires aggregate-only sponsor access.

## D-010 Primary scores for human validation chosen from simulation evidence
Correct characters/min (E1), grid achieved bitrate (A4), movement time censored at timeout (A2) and
digital-ADL time (F) are the planned primary scores; Fitts throughput is secondary for BCI-like
users (undefined or unreliable under heavy degradation — EXPERIMENT_REGISTRY G, I). Accuracy and
error rates are reported as outcomes, not used as scores (ceiling, ICC ≈ 0).
