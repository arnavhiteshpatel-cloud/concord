# Stage 6 protocol template: NeuroMetric inside a partner's neural-interface or rehabilitation-device study

> **DRAFT. Not submitted. No partner, no agreement, no commitment exists.** This is a template
> for a protocol *module* or amendment to be written **with** a partner's study team and
> approved by the partner's IRB (and any relying IRBs). NeuroMetric is never the sponsor of an
> implanted-device study.

## 1. Possible partners (none contacted; see `docs/research/collaborators.md`)
- SRAlab DAI team (`SRALAB_APPROACH.md`).
- JNERL (UIUC/Carle) for stroke rehabilitation.
- BrainGate sites; Pittsburgh RNEL; UC Davis.
- Device sponsors under a data-use agreement (Tier 2 export).

## 2. Candidate questions (to be chosen with the partner)
1. Agreement and offset between in-clinic battery performance and home battery performance with
   the same device (Bland–Altman on log scale; within-person).
2. Feasibility of joining sponsor/device-side daily aggregates (decoder-on time, selections) with
   NeuroMetric scores on a pseudonymous study ID.
3. Within-person association of task performance with real-world use and care-partner assistance
   over time (`MEASUREMENT_CHAIN_STUDY.md`).
4. Comparison of NeuroMetric metrics against the partner's own performance outcomes on the same
   sessions (e.g. DAI metrics). This is possible only if the partner shares them under its IRB
   and data-sharing rules. **The DAI's IPD sharing is "No" on the registry [V]**, so this depends
   entirely on the partner.

## 3. Design principles
- **N-of-few:** implanted cohorts are 2–15 people (`clinical_trials.md`). Analysis is per person:
  individual trajectories, within-person mixed models, and descriptive agreement. There are no
  group-level validity or reliability claims unless n supports them.
- The partner's eligibility, consent, safety monitoring and AE reporting govern the study.
  NeuroMetric adds a consent section describing its data (`docs/irb/consent_home_telemetry.md`
  can be adapted).
- **Burden:** the NeuroMetric module adds ≤ 30 min per partner visit (a reduced core: A2, A4,
  E1 with 2 phrases, F3) unless the partner wants more.
- **Task procedures:** `stage1_protocol.md` §4. Accessibility: `stage4_protocol.md` §6. A BCI
  appears to NeuroMetric as an OS pointer or key source, or through an adapter. Decoder settings
  and recalibrations are recorded as AT settings and ASSIST(calibration) events.

## 4. Equipment
- Partner's device and computer.
- NeuroMetric web battery on a partner-approved host, or an offline build that exports
  pseudonymized files.
- No raw neural data are ingested by NeuroMetric. Only event-level interaction data, and
  aggregates under a DUA.

## 5. Approvals and agreements (all needed **before** any data flow)
- Partner IRB approval of the module, and UIUC reliance or determination of UIUC engagement via a
  Reliance Consultation Request [V route].
- For SRAlab: Northwestern University IRB oversight under the NU–SRAlab MOU [V].
- Data-use agreement; IP and licensing terms; publication rights (the partner's PI decides
  authorship; NeuroMetric gets no veto); confidentiality, including any device-company
  collaborator's rights. Neuralink is a registry collaborator on the DAI study [V].
- For IDE studies: the sponsor decides whether NeuroMetric data are study endpoints. If so, Part
  11-grade controls apply (`regulatory_landscape.md` §4).
- COI disclosure to the partner IRB (founder's interest).

## 6. Analysis
A pre-specified per-partner SAP from the template. Descriptive and within-person analyses only,
unless the partner's sample allows more. Never "validated in BCI users" from n < 10.
