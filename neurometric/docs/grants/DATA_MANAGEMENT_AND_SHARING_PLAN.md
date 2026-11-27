# NIH Data Management and Sharing (DMS) Plan: draft

> **DRAFT for the NIH STTR Phase I application (`NIH_STTR_PHASE1.md`).** Prepared 2026-11-27.
> Not reviewed by the partner research institution, its IRB, its privacy office or a repository.
> Follows the six elements of the NIH DMS Policy (effective 25 Jan 2023) and NIH's suggested
> two-page length [PK: confirm current format page and template]. The project's IRB-facing data
> management plan is planned at `docs/irb/data_management_plan.md` (not present at drafting); the
> two must agree before submission. Labels per `docs/research/CONVENTIONS.md`.

---

## Element 1. Data types

| Data type | Source | Approx. volume [HYP] | Shared? | Access |
|---|---|---|---|---|
| **Synthetic simulation outputs** (virtual-participant scores, sweep properties, figures; every row flagged `synthetic=True`) | Computational studies (`experiments/results/`) | Tens of MB | **Yes, all** | Open (Zenodo) |
| **Derived results from public data** (X1: canonical events and reach metrics from NLB MC_RTT, DANDI:000129, CC-BY-4.0) | Public macaque dataset | < 50 MB | Yes (derived tables only; the source stays at DANDI and is cited) | Open |
| **Participant task data**: canonical event streams (pointer samples, selections, keystrokes in the copy-typing task only, markers, ASSIST events), per-trial timing fields, per-task scores | Aims 1–3 (≈ 176 participants + 5 care partners) | ≈ 1–5 GB | Yes, de-identified | **Restricted** (controlled access) |
| **Questionnaires**: NASA-TLX, SUS, fatigue NRS, original NeuroMetric items, licensed instruments where licensed | Aims 1–3 | Small | De-identified scores yes; **licensed item text no** (licence terms) | Restricted |
| **Demographics and clinical descriptors**: age band, sex, handedness, diagnosis group, time since onset/injury (banded), AT type and settings | Aims 1–3 | Small | Yes, coarsened | Restricted |
| **Home data (Aim 3)**: daily aggregate telemetry (active minutes, interaction counts, number of characters typed, optional app-category minutes), diary help minutes and burden | 5 dyads × 14 days | Small | Yes, aggregate and de-identified | Restricted |
| **Bench timing data**: photodiode/actuator lag measurements per device class | Aim 1a (no participants) | Small | Yes | Open |
| **Interview notes** (Aim 3 closeout) | 5 dyads | Small | **No** (small n, re-identification risk); thematic summary published instead | — |
| **Identifiers, consent forms, payment records** | — | — | **Never shared** | Kept by the partner RI |

**Never collected** (so never shared): typed text outside the presented copy-typing phrases,
messages, URLs, window titles, screenshots, audio, video, camera images, gaze coordinates,
location, contacts, app names (`docs/clinical/HOME_USE_FEASIBILITY.md` §3; telemetry allowlist in
`src/neurometric/study/telemetry.py`).

**Rationale for what is shared.** Event-level data let others recompute every metric (all metrics
are computable from the stored canonical events; `docs/science/METRICS.md`). Small diagnostic
cohorts (≈ 15 per diagnosis) with AT type and settings are re-identifiable in combination, so
participant data go to a controlled-access repository rather than an open one.

## Element 2. Related tools, software and code

- **NeuroMetric analysis software** needed to read and score the data: the event schema, metric
  functions, psychometrics library and the exact analysis code frozen at each SAP lock (git commit
  hash recorded in the SAP). Each shared dataset states the software version and commit.
- **Release route.** Code for the published analyses is archived with a DOI (Zenodo) at
  publication. Which components are released under an open-source licence, and which remain
  company software available to researchers under a no-cost research licence, is decided by the
  allocation-of-rights agreement before the first publication (`STTR_STRUCTURE.md` §4) [INF].
  At minimum, the scoring and statistical code needed to reproduce published results is
  released.
- **Third-party software:** Python, numpy, scipy, pandas, statsmodels, matplotlib (versions pinned
  and recorded in each result file).

## Element 3. Standards

- **Event format:** NeuroMetric canonical event schema (versioned JSON; each event carries a
  sequence number, monotonic timestamp and provenance label simulated / replayed / live; streams
  carry a SHA-256). A JSON Schema and a data dictionary are deposited with the data.
- **Metric definitions:** `docs/science/METRICS.md` (Fitts throughput per ISO 9241-411 /
  Soukoreff & MacKenzie 2004; text-entry metrics per Soukoreff & MacKenzie 2003; achieved bitrate
  per Nuyujukian et al. 2015).
- **Clinical descriptors:** NINDS Common Data Elements for ALS, SCI and stroke where they cover the
  variables collected [PK: check the current CDE versions]; PROMIS/Neuro-QoL scoring conventions
  where licensed.
- **Not applicable:** NWB and BIDS (no neural or imaging data are collected). This is also why
  **DANDI is not an appropriate repository** for this project's participant data: DANDI is an
  archive for cellular neurophysiology in NWB format, and NeuroMetric data are behavioural only
  [PK]. The X1 source data remain at DANDI.
- **Metadata:** DataCite metadata on every deposit; README with provenance, consent scope,
  synthetic/real flags and known limitations.

## Element 4. Data preservation, access and timelines

| Data | Repository | Timing |
|---|---|---|
| Synthetic simulation outputs, derived X1 tables, bench timing, code | **Zenodo** (DOI; versioned; CERN-hosted generalist repository) and/or **OSF** project linked to the OSF pre-registrations | At first publication that uses them, and no later than the end of the award |
| Pre-registrations and SAPs (with SHA-256 hashes) | **OSF Registries** | Before enrolment of each stage (time-stamped, frozen) |
| De-identified participant data (Aims 1–3) | **ICPSR** (controlled-access deposit with a data use agreement), or an equivalent NIH-listed repository offering controlled access; final choice with the partner RI's privacy office [INF] | At publication of each aim's main paper, and no later than the end of the performance period, per NIH policy [PK] |

Repositories are chosen to meet NIH's "desirable characteristics" (persistent identifiers,
long-term preservation, metadata, curation, access control) [PK]. Data are kept at least as long
as the repository's preservation commitment; the partner RI keeps the source records for the
period its record-retention policy and the IRB require.

## Element 5. Access, distribution and reuse considerations

- **Consent.** Every consent form includes an explicit, separately initialled choice about
  sharing de-identified data (§6 below). Participants who decline sharing are excluded from the
  deposit; their data are used only within the study.
- **De-identification.** HIPAA Safe Harbor identifiers removed; dates converted to study days;
  age, time since onset and AT settings banded; diagnosis kept at group level; small cells
  (< 5) suppressed or merged; re-identification review by the partner RI before deposit. Expert
  determination is used if Safe Harbor coarsening would destroy the analytic value [PK].
- **Controlled access.** ICPSR (or equivalent) restricted-use agreements: named researchers,
  research purpose, no re-identification attempts, no linkage to other datasets without approval,
  secure storage, destruction at the end of the agreement.
- **Certificate of Confidentiality.** NIH-funded research collecting identifiable, sensitive
  information is automatically covered by a Certificate of Confidentiality [PK]; consent forms
  describe it.
- **Licensed instruments.** Item text and item-level data of licensed questionnaires are shared
  only as the licence allows; scores are shared.
- **Neural-data laws.** No neural signals are collected. State neural-data laws (e.g. Colorado
  HB24-1058 [V]) are reviewed by the partner RI's counsel before any later phase that receives
  device-side data (`regulatory_landscape.md` §8).
- **Company access.** NeuroMetric receives only de-identified data under the same terms as any
  other user, or aggregate results, under a data-use agreement with the partner RI. The company
  has no publication veto.

## Element 6. Oversight of data management and sharing

The partner RI's PD/PI is responsible for compliance with this plan, with the research
coordinator managing deposits and the biostatistician checking that shared datasets reproduce the
published results with the archived code. Compliance is reviewed at each annual progress report
(RPPR). The company's technical lead maintains the schema, data dictionary and code archive.

---

## 6. Consent language for data sharing (draft for the IRB; to be adapted to OPRS templates)

> **Sharing your study information with other researchers (please initial one).**
>
> We would like to share the information collected in this study with other researchers so they
> can check our results and do new research. Before sharing, we remove your name, contact details
> and anything else that directly identifies you, and we make other details less specific (for
> example, we give your age as a range). Your information would be stored in a research data
> archive that only lets approved researchers see it after they sign an agreement not to try to
> find out who you are.
>
> What is shared: your task results (for example, how quickly and accurately you selected
> targets), the type of device or access method you used and its settings, your answers to the
> study questionnaires, and general information such as your age range and diagnosis group.
>
> What is never shared: your name, contact information, signed forms, payment records, and any
> notes from your interview. We never collect your messages, the content of what you type
> outside the study phrases, websites you visit, or screen images.
>
> Shared information cannot be taken back once other researchers have it, but you can ask us not
> to share it in future.
>
> ____ Yes, you may share my de-identified information in a controlled-access archive.
> ____ No, use my information only for this study.
>
> (Care partners: the same choice applies to your diary answers.)

Adaptation notes: the consent must be available in the participant's accessible format and
choice-making method (AAC, eye gaze, partner-assisted scanning; `CLINICAL_VALIDATION_PLAN.md`
§6.4), and the sharing choice must not affect eligibility or payment.
