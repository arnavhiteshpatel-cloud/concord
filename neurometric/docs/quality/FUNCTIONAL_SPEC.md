# Functional Specification (FS) - NeuroMetric study data platform

Document status: DRAFT v0.1 (2026-11-27). Each FS item implements one or more URS items
([USER_REQUIREMENTS.md](USER_REQUIREMENTS.md)); tests are listed in
[TRACEABILITY.md](TRACEABILITY.md). Module paths are relative to `src/neurometric/`.

## Architecture

```
web client / scripts --HTTPS--> api/app.py (FastAPI)          [auth, hardening, routes]
                                   |
                                   v
                     study/service.py StudyService             [domain operations]
        core | clinical | collection | consent | telemetry | exports | backup
                                   |
                     study/db.py Database (SQLite, WAL, FK)     [thin repository]
                     study/audit.py AuditTrail                  [hash chain]
instruments/engine.py (definitions, scoring), instruments/fhir.py; study/scoring.py
(events -> neurometric.metrics); tasks/battery.py (stimuli); simulator (demo only)
```

## Specifications

| ID | Specification | Implements |
|---|---|---|
| FS-01 | Every tenant-owned table carries `org_id`; every service read uses `WHERE org_id = actor.org_id`; a record of another tenant raises `NotFound` (404), never revealing existence. (`study/core.py::_get`, all mixins) | URS-01 |
| FS-02 | Permission matrix `study/permissions.py::PERMISSIONS` (role -> permission); `require()` raises 403. Admins have no participant-level read; sponsor analysts no participant-level or re-identification access. | URS-02 |
| FS-03 | `_check_scope()`: participant = own pseudonym; care partner = `care_partner_links`; coordinator/investigator = `user_sites`; sponsor/admin = `aggregate_only` 403. Lists are filtered by the same rule. | URS-03 |
| FS-04 | `security.py`: scrypt (N=2^14, r=8, p=1, 16-byte salt), min 12-char passwords; tokens = 32 random bytes, SHA-256 stored, expiry `NEUROMETRIC_TOKEN_TTL_MIN` (default 30), revoked on logout/deactivation; constant-time compare and dummy hash for unknown users; `api/middleware.py::LoginRateLimiter` (failures per user and per address, attempts per address; 429 + Retry-After). | URS-04 |
| FS-05 | Pseudonym `NM-` + 10 CSPRNG characters. `reidentification_keys`: AES-256-GCM, key from `NEUROMETRIC_REID_KEY`, AAD = pseudonym; refused without key; read requires reason, site staff of the participant's site, audited (`reidentify`). | URS-05 |
| FS-06 | `clinical.py::TRANSITIONS` state machine; `consented` requires active consent; reasons required for `withdrawn`, `lost`, `completed`; each transition writes `enrollment_events` + audit; first session upload moves `enrolled -> active`. | URS-06 |
| FS-07 | `validate_schedule` / `expand_schedule`: visits (code, day, window_before/after, type, tasks, instruments) and recurrences (prefix, start_day, every_days, count or until_day); `generate_visits` is idempotent and creates questionnaire assignments and reminder records; completion outside the window -> `completed_out_of_window` + automatic deviation; `mark_missed_visits` -> `missed` + `missing_data` + assignments missed. Window compliance uses `performed_at` (not in the future). | URS-07, URS-12 |
| FS-08 | `device_configs` with calibration state enumeration; sessions may reference a device configuration of the same participant. | URS-08 |
| FS-09 | `collection.py::upload_session`: state and `task_battery` consent checks; battery version match; stimulus hash must equal `tasks.battery.stimuli(task, seed)`; each event through `InputEvent.from_dict` + `validate_event`; single session id; `check_stream` duplicate seq rejected; synthetic events only in demo studies; text input outside E1 requires `free_text`; zlib blob + SHA-256 of canonical JSON; duplicate upload rejected; `scoring.py::score_session` (pointing via `metrics.pointing`, typing via `metrics.text`, session summary via `metrics.session`). | URS-09, URS-28 |
| FS-10 | `instruments/engine.py`: JSON definitions validated on load; response types likert/numeric/minutes/yes_no/choice/multi_choice/free_text (sensitive); scoring sum/mean/reverse/min_answered/prorate, SUS, NASA-TLX raw/weighted; responses store `instrument_version`; respondent-type enforcement; translations other than the source language are refused ("authorized translation required"); assignments completed on submission and reminders cancelled. | URS-10 |
| FS-11 | License stubs (`license_required`) ship no items and cannot be answered; `load_licensed_items` attaches licensee-supplied items with an attestation; SUS: odd (x-1), even (5-x), sum x 2.5; TLX raw = mean of 6; weighted = sum(rating x weight)/15 with weights summing to 15. | URS-11 |
| FS-12 | `protocol_deviations` (category, severity, status) and `missing_data` (item type, reason code from a fixed list). | URS-12 |
| FS-13 | `data_queries` state machine open -> answered -> closed (answered -> open on re-open with reason; open -> closed needs a reason); sponsor analysts may raise/close on pseudonymous records; review = signature meaning `reviewed`, sign-off = `approved` on the participant casebook hash. | URS-13 |
| FS-14 | `audit.py`: entries (id, org, UTC time, user, role, action, table, record, reason, old/new JSON with sensitive fields replaced by SHA-256, prev_hash, entry_hash = SHA-256 of canonical JSON); SQLite triggers abort UPDATE/DELETE on `audit_log`; `verify_chain(expected_head)` reports edits, deletions, re-ordering and (with anchor) truncation. | URS-14 |
| FS-15 | `_update()` raises `ReasonRequired` for any update without a non-blank reason; `correct_record()` allowlists correctable fields per table and re-validates/re-scores questionnaire answers; `record_history()` returns the audit entries of a record. | URS-15 |
| FS-16 | `sign()`: meaning in {authored, reviewed, approved, verified} with role rules; password re-authentication (failure audited); signature row (signer id, username, display name, role, meaning, record table/id, record SHA-256, UTC time) append-only; `verify_signature()` reports `record_changed_since_signing`. | URS-16 |
| FS-17 | `Database.now()` from the server clock (injectable for tests only); ISO-8601 UTC with `Z`; naive datetimes rejected. | URS-17 |
| FS-18 | `backup.py`: SQLite online backup API to a new file + manifest (SHA-256, schema version, audit head, entry count); `verify_backup` (hash, `PRAGMA integrity_check`, audit chain against manifest head, read-only); `restore_database` refuses unverified backups and never overwrites; `integrity_check()` (page check, FK check, chain, raw-event hashes, telemetry hashes, signature status). | URS-18 |
| FS-19 | `consent.py::record_consent`: versioned document id/version, scopes from `CONSENT_SCOPES`; supersedes previous; `_require_consent` at session upload, questionnaire submission, telemetry ingest. | URS-19 |
| FS-20 | `withdraw_consent`: full or per-scope; same transaction: consent ended, telemetry stopped, enrollment withdrawn, visits/assignments/reminders cancelled; action `retain`/`delete` (study default or explicit); `consent_withdrawals` records scopes, action, counts, reason. | URS-20 |
| FS-21 | `retention_policies` per study/category; `run_retention_purge` (admin) computes cutoffs from server time, purges raw blobs / records / free text / telemetry, logs `purge_log`, audits each record. | URS-21 |
| FS-22 | `export_subject` (participant self / investigator) JSON of all records incl. raw events and own free text, never the identifier; `delete_subject` (investigator, reason) removes all participant rows and the key, deactivates the account, keeps audit tombstones. | URS-22 |
| FS-23 | `exports.py::_participants_for(audience="sponsor")` = latest consent allows `sharing_with_sponsor`; dashboards contain no participant ids; sponsor exports omit free text, deviation descriptions, raw events and identifiers. | URS-23, URS-27 |
| FS-24 | `telemetry.py::validate_payload` allowlist with reason codes (`forbidden_field`, `unknown_field`, `content_like_value`, `url_like_value`, `array_not_allowed`, `invalid_value`, `missing_field`); rejected payloads never stored (receipt only); consent + state `active` required; app categories need their own scope; `set_telemetry_state` pause/resume/stop; `review_own_telemetry` returns stored payloads and receipts. | URS-24 |
| FS-25 | Dedupe on (participant, device_session_id, period): identical -> `duplicate`, different -> `conflicting_duplicate`; overlap within device session rejected, across sessions flagged; out-of-order flagged; end > now + 5 min rejected, within tolerance flagged; period <= 24 h; minute sanity checks; batch SHA-256 stored and client `batch_sha256` verified; receipts for every outcome. | URS-25 |
| FS-26 | `export_study`: data dictionary (schema + inventory), participants, visits, sessions metadata, analysis dataset (participant x visit x task x metric, units, primary flag), `sdtm_like_qs_questionnaires.csv`, `sdtm_like_xf_functional.csv`, FHIR R4-shaped Bundle of QuestionnaireResponse, telemetry daily, deviations, missing data, queries, MAPPING_NOTES.md; manifest with SHA-256/bytes/records per file, software/battery/scorer/schema/instrument versions, audit head (after the export's own audit entry); `verify_export`. | URS-26 |
| FS-27 | `dashboard()`: enrollment counts, completeness by visit code, primary metric trends by visit, modality comparison, missing data, deviations, queries, questionnaire scale means, telemetry minutes/day; cells with n < `min_cell_size` suppressed. | URS-27 |
| FS-28 | `is_demo` on every study-level table; triggers (`*_demo_insert/update`) abort on mismatch with the study; demo org cannot hold non-demo studies; study demo flag immutable; `study/demo.py::seed_demo` creates "DEMO - synthetic data, not patients" via the simulator. | URS-28 |
| FS-29 | `SecurityHeadersMiddleware` (CSP, nosniff, DENY, no-referrer, permissions-policy, COOP/CORP, no-store for /api, HSTS on https); CORS only with `NEUROMETRIC_CORS_ORIGINS`; `BodySizeLimitMiddleware` (default 16 MiB, telemetry 64 KiB, auth 8 KiB) -> 413; pydantic models `extra="forbid"`; OpenAPI docs off by default. | URS-29 |
| FS-30 | `schema_migrations` (version, name, checksum, time); changed applied migration refused; `inventory.py` documents every table/column (test-enforced). | URS-30 |

## API surface (summary)

Public: `GET /api/health`, `GET /api/battery`, `GET /api/battery/{task_id}/stimuli?seed=`.
Auth: `POST /api/auth/login|logout`, `GET /api/auth/me`, `GET /api/permissions`.
Admin: `/api/users`, `/api/sites`, `/api/sponsors`, `/api/admin/{backup,backup/verify,retention/run,integrity}`.
Studies: `/api/studies[/{sid}]`, `/sites/{site}`, `/protocol-versions`, `/schedules`,
`/participants`, `/missed-visits`, `/dashboard`, `/deviations`, `/queries`, `/retention`, `/exports`.
Participants: `/api/participants/{pid}`, `/transition`, `/enrollment-history`, `/reid`,
`/reid/reveal`, `/consent`, `/consent/withdraw`, `/visits/generate`, `/visits`, `/devices`,
`/sessions`, `/questionnaires`, `/assignments`, `/missing`, `/telemetry/{summary,state}`,
`/export`, `DELETE`. Others: `/api/visits/{vid}/complete`, `/api/sessions/{id}`,
`/api/instruments[/{iid}[/score]]`, `/api/telemetry/{ingest,mine}`,
`/api/queries/{qid}/{answer,close,reopen}`, `/api/records/{table}/{rid}[/history]`,
`/api/signatures[/{id}/verify]`, `/api/audit[/verify]`.
