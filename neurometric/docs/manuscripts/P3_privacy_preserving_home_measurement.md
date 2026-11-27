# Consented aggregate home telemetry for assistive-technology and BCI outcome research: an architecture and its verification (design paper)

> **OUTLINE + PARTIAL DRAFT v0.1 (2026-11-27). Design and software-verification paper only. No
> participant data exist and none are reported.** The home-use feasibility study that would test
> this architecture with people (`docs/clinical/HOME_USE_FEASIBILITY.md`) has not been approved or
> run. Experiment O (telemetry integrity) results: no `experiments/results/O_*` directory existed
> when this draft was finished, so they are marked `[RESULT PENDING]`. Authors and competing
> interests: `[AUTHORS]`.

---

## Working abstract
**Problem.** Regulators and the BCI field want evidence of real-world use and independence at home
(FDA iBCI guidance "Home Use" section [V]; iBCI-CC consensus 2026 [V]), but home measurement of
how people use computers through assistive technology (AT) risks capturing content (what people
type, read or watch) and creating surveillance. **Contribution.** We describe a tiered,
consent-gated architecture that collects only aggregate counts and minutes, enforces the
restriction at three independent layers (on-device aggregator, server allowlist validator,
consent and telemetry-state gates), detects duplicate, conflicting, overlapping and out-of-order
batches, and stores only a receipt for anything rejected. We map platform constraints on Windows,
macOS, Linux, Android, iOS and ChromeOS and show why only some platforms allow consented
cross-application telemetry without workarounds. **Verification.** [RESULT PENDING: experiments/results/O_*/summary.json — Experiment O: number of adversarial payload classes tested and rejected; duplicate/conflict/overlap handling outcomes]. Unit tests show that probes cannot report content keys, that pause and consent withdrawal drop data at the source, and that aggregate payloads pass the server allowlist (`tests/test_probe_contract.py`). **Status.** No human data; feasibility study pending IRB.

---

## 1. Introduction (outline)
1.1 Why home measurement matters for BCI and AT outcomes: FDA guidance asks to study devices "in
realistic, home use environments" and to measure caregivers' ability to assist [V]
(`docs/research/regulatory_landscape.md` §1); sponsors already use home-use hours as endpoints
(Utrecht; CortiCom-Utrecht; Cognixion NCT07871071 primary endpoint "voluntary daily use time") [V]
(`published_bci_functional_measures.md` §3.8); payers cite missing real-world use evidence [V].
1.2 Why "use time" alone is not function and device activity is not independence
(`docs/science/INDEPENDENCE_AND_CHAIN.md`): independence states range from device unavailable to
completed independently; assistance must be captured explicitly.
1.3 Privacy stakes: AT users often depend on one device for all communication; logging content would
capture private communication. Neural-data statutes are emerging (Colorado HB24-1058 [V];
California, Montana, Connecticut [PK]) and HIPAA may or may not apply depending on who deploys the
tool (`regulatory_landscape.md` §8).
1.4 Related work to review before submission [to do]: privacy-preserving mobile sensing and
digital phenotyping; differential privacy and federated analytics for usage statistics; AAC
language-sample logging (and its consent practices); research ethics of passive sensing in
disability research. (No systematic search done yet.)

## 2. Requirements (derived from the telemetry charter, `docs/research/platform_matrix.md`)
R1 Explicit, separate opt-in for any collection beyond the study task itself.
R2 Collect only session durations, interaction counts, modality and AT flags; **never** keystroke
content, screenshots, passwords, messages, browsing history, URLs, window titles, screen content,
audio, video, gaze coordinates, location, contacts or app names.
R3 No covert monitoring: a visible indicator, pause and withdraw controls.
R4 No bypassing operating-system permissions.
R5 Data minimisation on the device: aggregate to period totals (≤ 24 h) before transmission.
R6 Server-side enforcement independent of the client (assume a buggy or modified client).
R7 Integrity: detect duplicates, conflicting re-sends, overlaps and clock problems; hash every
stored batch.
R8 Auditability: every accepted or rejected batch leaves a receipt; rejected content is never stored.
R9 Participant control: withdrawal of consent stops ingestion immediately; per-scope consent
(home telemetry; app categories).

## 3. Architecture
### 3.1 Tiers (`platform_matrix.md` §1; `HOME_USE_FEASIBILITY.md` §3)
| Tier | What | Where | Default |
|---|---|---|---|
| 0 | In-battery events and scores from the periodic home battery; session duration; interaction counts; declared AT settings; timing self-checks | Browser (any platform) | On under study consent |
| 1 | Per-period totals from an opt-in activity agent: active minutes, device-assisted-session flags, counts of pointer/select/scroll/switch/dwell events, **number** of characters typed, interruptions; optional coarse app-category minutes (10 fixed categories) under a separate consent scope | Windows agent (signed build, visible indicator), Android app (UsageStats permission granted by the user), ChromeOS managed extension | Off unless opted in |
| 2 | Aggregate device-usage exports from BCI/AT manufacturers under a data-use agreement, joined on a pseudonymous study ID | Sponsor/manufacturer | Not in Phase I |

### 3.2 Platform verdicts (summary of `platform_matrix.md`)
Browser: yes (baseline). Windows: technically yes, ethically constrained (Raw Input and
`GetLastInputInfo` need no OS prompt, so the agent must supply consent, an indicator and a kill
switch; keyboard codes are never read) [V]. macOS: partial (global monitoring needs user TCC
grants; App Store sandbox excludes it) [V/PK]. Linux: no for cross-app on Wayland by design [V].
Android: yes, limited (UsageStatsManager with user-granted access; **AccessibilityService is not
used** for telemetry, per Play policy) [V]. iOS/iPadOS: no cross-app export (Screen Time report
extensions cannot make network requests) [V]. ChromeOS: yes on managed devices with explicit
consent [V API]. BCI devices: preferred route is Tier 2 export; no BCI telemetry is exposed to
third-party apps on Apple platforms [INF].

### 3.3 Enforcement layers
1. **On-device aggregator** (`src/neurometric/adapters/probes/contract.py`): accepts only
   `ProbeSample` objects with allowlisted interaction keys; raising an error for content-like keys
   (test `test_probe_cannot_report_content`); drops samples while paused or after consent is
   withdrawn (test `test_pause_and_consent_drop_at_source`); emits a period payload with totals.
2. **Server allowlist validator** (`src/neurometric/study/telemetry.py: validate_payload`): schema
   `nm.telemetry/1`; required fields (schema version, pseudonymous participant `NM-XXXXXXXXXX`,
   device session ID, ISO period start/end, active minutes, interaction counts); numeric ranges
   (active minutes 0–1440; counts 0–10⁷, integers; fatigue and burden 0–10); enumerated app
   categories and assistance types; semver client version and enumerated platform; any unknown key
   is rejected, and keys or values that *look like content* (hints such as text, url, title,
   window, screenshot, keystroke, clipboard, message, email, location, contact, file, path; URL-like
   strings; arrays where none are allowed) get explicit `forbidden_field`, `content_like_value`,
   `url_like_value` or `array_not_allowed` reason codes. App names, bundle IDs or window titles
   placed in the category map are rejected as forbidden.
3. **Service gates** (`ingest_telemetry`): role and ownership (participant or linked care partner
   only); active `home_telemetry` consent; telemetry state must be active (not paused/stopped);
   separate `telemetry_app_categories` consent for category minutes.
4. **Consistency and integrity rules**: period end after start; period ≤ 24 h; future periods
   beyond a 5-min skew tolerance rejected (smaller skew flagged); active minutes ≤ period length;
   self-reported assistance minutes ≤ period; app-category minutes ≤ active minutes; client-supplied
   `batch_sha256` must equal the SHA-256 of the canonical JSON; idempotent on (participant, device
   session, period): an identical re-send is acknowledged as a duplicate, a different payload for
   the same key is a conflict and rejected; overlapping periods within a device session are
   rejected; overlaps across device sessions and out-of-order arrival are accepted and flagged.
5. **Receipts**: rejected payloads are never stored; a receipt with reason codes is kept
   (`telemetry_receipts`), allowing audit of the privacy-integrity criterion (F5 in the feasibility
   protocol: zero accepted batches with a disallowed field).

### 3.4 Care-partner assistance capture
Assistance is recorded two ways: ASSIST events during home batteries (setup, physical, verbal,
troubleshooting, calibration, task completion; by participant, care partner or staff) and a daily
2-minute care-partner diary (help minutes by type; burden 0–10). Self-reported assistance can also
travel in the telemetry payload (type, minutes). An experimental assistance-weighted completion
score with a-priori weights exists but is labelled experimental until validated
(`INDEPENDENCE_AND_CHAIN.md`).

## 4. Verification (software; no participants)
### 4.1 Unit and contract tests (exist)
- `tests/test_probe_contract.py`: aggregate payload passes the server allowlist; pause and consent
  withdrawal drop data at the source; probes cannot report content keys.
- `tests/test_study_core.py`: role permissions for `telemetry.ingest`; a participant of one
  organisation cannot ingest telemetry for another organisation's participant.
Counts of tests and pass status should be cited from a test run log at submission [not run for
this draft].

### 4.2 Experiment O: adversarial and integrity evaluation (planned/pending)
Design to report (from the module's documented integrity rules):
- adversarial payload corpus: content-like keys, URL-like values, keystroke arrays, app names in the
  category map, out-of-range numbers, NaN/inf, wrong types, nested objects, missing fields;
- integrity scenarios: identical re-send, conflicting re-send, overlap within and across device
  sessions, out-of-order arrival, clock skew within and beyond tolerance, hash mismatch;
- consent scenarios: no consent, withdrawn consent, paused telemetry, app categories without the
  extra scope.
[RESULT PENDING: experiments/results/O_*/summary.json — counts accepted/rejected per class and the reason codes; false-rejection rate on valid synthetic payloads]

### 4.3 Accessibility of the participant-facing battery
Automated axe-core scan of 58 screens: 0 violations (`experiments/results/Q_accessibility/axe_summary.json`);
manual testing with screen readers, switch hardware and eye trackers not yet done (same file,
caveat).

## 5. Planned human evaluation (protocol only)
Two-week feasibility with 5 AT-user/care-partner dyads, success criteria F1–F7 (usable logs ≥ 4/5;
≥ 80% participant-days complete; burden limits; zero privacy breaches; support load; retention)
(`docs/clinical/HOME_USE_FEASIBILITY.md` §5). It cannot show reliability, validity or benefit.

## 6. Discussion points
- Trade-off between minimisation and scientific value (counts cannot tell *what* was
  communicated — by design).
- Platform asymmetry creates selection bias (macOS/iOS users get Tier 0 only); report as a stratum.
- Aggregates are still personal data; pseudonymous IDs, university hosting, controlled-access
  sharing (`docs/grants/DATA_MANAGEMENT_AND_SHARING_PLAN.md`).
- Tier 2 manufacturer exports may be more accurate for BCI use than OS-level counts but bring
  sponsor data-rights questions.
- The server validator is a necessary but not sufficient control: a malicious client could still
  encode information in allowed numbers; mitigations (period granularity, rate limits, plausibility
  checks) and their limits.

## 7. Limitations
No participant data; platform verdicts partly [PK]; legal analysis (HIPAA, state neural-data laws)
not performed by counsel; the agent builds for Windows and Android are specified as contracts and
were not run on real devices (`BLOCKERS.md` X-7).

## 8. Candidate venues
ACM ASSETS or CHI (accessibility and privacy design; full paper requires a user evaluation for most
tracks [PK] — likely after the feasibility study), *JMIR* family (digital health methods [PK]),
*Assistive Technology* (RESNA), RESNA conference paper (design + verification) as the first
outlet. See `VENUES.md`.
