# User Requirements Specification (URS) - NeuroMetric study data platform

Document status: DRAFT v0.1 (2026-11-27). Scope: `neurometric.study`, `neurometric.api`,
`neurometric.instruments`. Intended use: research data capture and management for studies of
functional performance of BCI and assistive-technology users. Research software; not a medical
device; never controls a device. Regulatory posture: technical controls oriented to 21 CFR Part 11
and privacy law; **not** Part 11 compliant/validated, **not** HIPAA compliant, no SOC 2.

Priority: **H** = high (patient-rights, data-integrity or GxP-relevant), **M** = medium,
**L** = low. Each requirement is traced to functional specifications and tests in
[TRACEABILITY.md](TRACEABILITY.md).

## Access and identity

| ID | Requirement | Priority |
|---|---|---|
| URS-01 | Each organization's (tenant's) data shall be inaccessible to users of any other organization, including by guessing record identifiers. | H |
| URS-02 | Access shall be role-based with least privilege for participant, care partner, coordinator, investigator, sponsor analyst and administrator. | H |
| URS-03 | Site staff shall access only participants at their assigned sites; participants only their own record; care partners only linked participants. | H |
| URS-04 | Users shall authenticate with individually assigned credentials; passwords shall be stored using a memory-hard hash; sessions shall expire; repeated failed logins shall be throttled. | H |
| URS-05 | Participants shall be identified only by random, non-derivable pseudonyms; an optional re-identification key shall be encrypted, held per site and never visible to sponsor roles. | H |

## Study conduct

| ID | Requirement | Priority |
|---|---|---|
| URS-06 | The system shall track enrollment (screening, consented, enrolled, active, completed, withdrawn, lost) allowing only valid transitions, with reasons for terminal or adverse transitions. | H |
| URS-07 | Investigators shall configure assessment schedules (visits with windows; recurring home assessments); visits shall be generated per participant; out-of-window and missed visits shall be detected and recorded. | H |
| URS-08 | Device configurations (modality, make/model as text, settings, calibration state) shall be recorded as metadata linked to sessions. | M |
| URS-09 | Functional task sessions shall be uploaded as canonical input events, validated, stored unaltered with an integrity hash, linked to task, battery version and stimulus hash, and scored server-side. | H |
| URS-10 | Questionnaires shall be administered from versioned definitions with scoring rules, respondent types, schedules, reminders (records only), completion and missing-item tracking. | H |
| URS-11 | Licensed instruments shall be represented by metadata only (no copyrighted item text) until a licensee loads items; freely usable instruments (SUS, NASA-TLX) shall be scored correctly. | H |
| URS-12 | Protocol deviations and missing data (with reason codes) shall be recorded. | M |
| URS-13 | Data clarification queries (open / answered / closed) and review / sign-off workflows shall be supported. | M |

## Data integrity (ALCOA+ oriented)

| ID | Requirement | Priority |
|---|---|---|
| URS-14 | All creations, modifications and deletions shall be recorded in an append-only audit trail with user, role, action, old/new values, server time stamp and reason; tampering shall be detectable. | H |
| URS-15 | Every update of entered data shall require a reason for change; the correction history of a record shall be retrievable. | H |
| URS-16 | Electronic signature records shall capture signer, printed name, meaning, date/time, and the signed record's hash; signing shall require re-authentication. | H |
| URS-17 | Audit and record time stamps shall come from the server clock in UTC. | H |
| URS-18 | The database shall be backed up with integrity verification; restore shall refuse unverified backups; integrity checks shall cover raw data, telemetry and the audit chain. | H |

## Consent and privacy

| ID | Requirement | Priority |
|---|---|---|
| URS-19 | Consent shall be recorded per versioned consent document with explicit scopes and enforced at every collection point. | H |
| URS-20 | Consent withdrawal shall stop collection immediately and apply the protocol's action (retain or delete), recording the action taken. | H |
| URS-21 | Retention periods shall be configurable per data category with an auditable purge job. | H |
| URS-22 | A participant's data shall be exportable (JSON) and deletable on request. | H |
| URS-23 | Sponsor roles shall receive only aggregated or pseudonymous data of participants who consented to sharing; free text and identifiers shall never be shared. | H |
| URS-24 | Home telemetry shall be explicit opt-in, aggregate-only, pausable/stoppable by the participant, reviewable by the participant, and shall reject content (text, keystrokes, URLs, titles, screenshots). | H |
| URS-25 | Telemetry ingestion shall be idempotent and robust to duplicates, out-of-order delivery, overlapping periods and client clock skew, with batch integrity hashes. | H |

## Outputs

| ID | Requirement | Priority |
|---|---|---|
| URS-26 | Study data packages (CSV/JSON) shall include a data dictionary, analysis dataset, SDTM-inspired layouts, a FHIR QuestionnaireResponse structure, and a manifest with file hashes, software/battery/instrument versions and the audit-chain head, without claiming conformance. | H |
| URS-27 | Sponsor dashboards shall present aggregates only (completeness by visit, task-metric trends, modality comparison, missing data, deviations, queries) with small-cell suppression. | M |

## Platform

| ID | Requirement | Priority |
|---|---|---|
| URS-28 | Demonstration (synthetic) data shall be clearly labelled and impossible to mix with real study data. | H |
| URS-29 | The HTTP interface shall apply security headers, keep CORS disabled unless configured, limit request sizes and reject unknown request fields. | M |
| URS-30 | Schema changes shall be applied by tracked, checksummed migrations; every stored field shall be documented in the data inventory. | M |
