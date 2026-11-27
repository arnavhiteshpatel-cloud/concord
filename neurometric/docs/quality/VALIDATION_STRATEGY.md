# Validation strategy (computerized system assurance) - DRAFT

Document status: DRAFT v0.1 (2026-11-27). **The system has not been validated.** This document
proposes how a deploying organization would validate a specific NeuroMetric release for its
intended use. Until that is executed and approved, NeuroMetric must not be described as Part 11
compliant or validated.

References (prior knowledge, verify current versions) [PK]: ISPE GAMP 5 *A Risk-Based Approach to
Compliant GxP Computerized Systems*, 2nd ed. (2022); FDA guidance *Computer Software Assurance
for Production and Quality System Software* (draft 2022; check final status) [UNR]; 21 CFR
Part 11 and FDA *Part 11, Scope and Application* (2003); ICH E6(R3) GCP (computerized systems
section); FDA *Electronic Systems, Electronic Records, and Electronic Signatures in Clinical
Investigations: Questions and Answers* (2024) [UNR].

## 1. Intended use and GxP determination

Capture and management of research data on functional performance of BCI / assistive-technology
users: functional task events and scores, questionnaires, consent, home usage aggregates,
exports for analysis. If records are submitted to or relied upon by FDA (e.g., device clinical
investigations under 21 CFR 812, or outcome data supporting a submission), the system is
GxP-relevant and the records are electronic records under Part 11 [PK]. Academic-only use may
not be GxP but the same approach is recommended for data integrity.

## 2. System categorisation (GAMP 5)

| Component | Category [PK] | Approach |
|---|---|---|
| Python runtime, SQLite, OS, uvicorn | 1 - infrastructure | qualified as platform (IQ: versions, configuration) |
| FastAPI, pydantic, numpy, cryptography (libraries) | 1/3 - used as supplied | version pinning, supplier reputation, covered by OQ of NeuroMetric functions |
| NeuroMetric study platform, scoring, instruments | 5 - custom application | full life cycle: URS, FS, risk assessment, design review, automated + manual testing, traceability |
| Instrument definitions (JSON), schedules (JSON) | configuration of category 5 | configuration verification per study (PQ) |

## 3. Risk-based approach

- Functions are ranked by the FMEA in [RISK_ASSESSMENT.md](RISK_ASSESSMENT.md). High-risk
  functions (audit trail, consent, access control, scoring, exports, telemetry allowlist) get
  scripted, documented testing with objective evidence; medium/low-risk functions rely on
  unscripted/exploratory testing and the automated suite (CSA "critical thinking" principle).
- Supplier (developer) testing - the automated pytest suite - is leveraged as OQ evidence when
  executed on the qualified environment from a tagged release, with the run log retained.
- Traceability: [TRACEABILITY.md](TRACEABILITY.md) maps every URS to FS and tests.

## 4. Life cycle deliverables

| Deliverable | Status |
|---|---|
| Validation plan (this document, finalised per deployment) | draft |
| URS / FS | draft ([USER_REQUIREMENTS.md](USER_REQUIREMENTS.md), [FUNCTIONAL_SPEC.md](FUNCTIONAL_SPEC.md)) |
| Risk assessment | draft |
| Design / code review records | not started (use PR reviews with checklist) |
| IQ / OQ / PQ protocols and reports | drafts below |
| Traceability matrix | generated, checked against the suite |
| SOPs (change control, backup/restore, incident response, access management, data correction) | drafts in this folder |
| Validation summary report | not started |
| Periodic review | yearly or on major change |

## 5. Installation Qualification (IQ) - draft protocol

| Step | Procedure | Acceptance criterion |
|---|---|---|
| IQ-01 | Record host OS, Python version, package versions (`pip freeze`), NeuroMetric git commit/tag. | Matches the release's approved environment list. |
| IQ-02 | Verify server clock synchronised (NTP) and timezone-independent UTC operation. | Offset < 1 s from reference; API time stamps end in `Z`. |
| IQ-03 | Set secrets via environment only: `NEUROMETRIC_REID_KEY` (if re-identification used), `NEUROMETRIC_TOKEN_TTL_MIN`; confirm no secrets in files under version control. | Secrets present in env; secret scan clean. |
| IQ-04 | Create database (`python -m neurometric.api create-admin ...`); check `schema_migrations`. | Schema version equals release; checksums recorded. |
| IQ-05 | Confirm TLS termination, HSTS, disk encryption and file permissions on database and backup directories. | Per site security baseline. |
| IQ-06 | Confirm backup destination (encrypted, off-host copy) and run `python -m neurometric.api backup` + `verify-backup`. | Verification `ok: true`. |
| IQ-07 | Confirm CORS configuration (`NEUROMETRIC_CORS_ORIGINS` empty unless approved) and docs disabled (`NEUROMETRIC_API_DOCS` unset). | As approved. |

## 6. Operational Qualification (OQ) - draft protocol

| Step | Procedure | Acceptance criterion |
|---|---|---|
| OQ-01 | Run the automated suite on the qualified environment: `python -m pytest tests/test_study*.py tests/test_api*.py tests/test_instruments*.py tests/test_telemetry*.py -q -o addopts= -p no:cacheprovider --junitxml=oq.xml`. | All tests pass; junit XML retained as evidence. |
| OQ-02 | Scripted access-control challenge: for each role, attempt the actions of the permission matrix via the API (Postman/httpx script). | Allowed actions succeed; others return 403/404. |
| OQ-03 | Tenant isolation: two organizations, attempt cross-tenant reads/writes by id. | All 404. |
| OQ-04 | Audit trail: perform create/update/delete/sign; inspect `/api/audit`; tamper a copy of the database file; run `verify-audit` on the copy. | Entries complete (who/what/when/why/old/new); tamper detected. |
| OQ-05 | E-signature: sign with wrong then correct password; change the record; verify. | Wrong password refused and audited; status `record_changed_since_signing` after change. |
| OQ-06 | Consent withdrawal retain/delete: execute per protocol; attempt collection afterwards. | Collection refused; action and counts recorded. |
| OQ-07 | Telemetry challenge set: send each forbidden-field example and the Experiment O sequence. | Rejections with reason codes; aggregates equal expected sums; nothing forbidden stored. |
| OQ-08 | Scoring known answers: upload reference event files (A1/A2/E1) with known results. | Scores equal reference values within stated tolerance. |
| OQ-09 | Export: generate sponsor and full packages; verify hashes independently (`sha256sum`). | All hashes match; content restrictions met. |
| OQ-10 | Backup/restore drill: restore into a new file, run integrity check, compare record counts. | Integrity `ok`; counts equal; audit head equal to manifest. |
| OQ-11 | Retention: configure short policy on a test study, advance (test clock) or wait; run purge. | Only eligible records affected; purge log + audit present. |

## 7. Performance Qualification (PQ) - draft protocol

Executed per study in the production configuration with trained users:

| Step | Procedure | Acceptance criterion |
|---|---|---|
| PQ-01 | Configure the study (protocol version, schedule, instruments, retention, withdrawal default) from the approved protocol; second person verifies configuration against protocol. | Configuration matches protocol; review signed. |
| PQ-02 | Dry run with test participants (in a separate non-demo *test* study or the demo study) through every visit type, including out-of-window and missed visits. | Visits, deviations and missing data as expected. |
| PQ-03 | Compare scores of a pilot session computed server-side with an independent calculation. | Agreement within tolerance. |
| PQ-04 | Sponsor dashboard and export reviewed by data management against source. | No participant-level leakage; counts reconcile. |
| PQ-05 | Users trained on SOPs; training records filed. | 100% of active users trained. |

## 8. Change control and revalidation

Any change follows SOP_CHANGE_CONTROL.md: impact assessment against URS/FS/risks, regression
suite, targeted re-execution of affected OQ steps, migration verification (new
`schema_migrations` row, checksum recorded), updated traceability (generator) and data
inventory (test-enforced).

## 9. Known gaps blocking a validated state

- No MFA / SSO; no password expiry or reuse history (procedural controls required).
- Audit trail review tooling is basic (list + verify); no scheduled review reports.
- No electronic-signature "first signing in a session requires both components" logic beyond
  password re-entry; Part 11 §11.300 controls (identity code/password uniqueness, periodic
  checks, loss management) are procedural.
- No automated off-site anchor for the audit head.
- Scoring of B/C/D/F tasks server-side is generic (completion/time).
