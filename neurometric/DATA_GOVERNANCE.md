# NeuroMetric data governance

Status: draft for the research team, sponsors and IRB/ethics review. Applies to the study data
platform in `src/neurometric/{study,api,instruments}` (schema version 2, battery 1.0.0).

> **Compliance statement.** NeuroMetric implements *technical controls* that are oriented to
> 21 CFR Part 11, HIPAA safeguards and common privacy-law requirements (audit trail, access
> control, encryption of the re-identification key, consent enforcement, retention). It is
> **NOT** Part 11 compliant or validated, **NOT** HIPAA compliant, has **no SOC 2** (or ISO
> 27001) attestation, and is research software that is **not a medical device** and never
> controls a device. Compliance depends on the deploying organisation's validation, procedures,
> training, contracts and infrastructure (see `docs/quality/` and `docs/security/`).

Evidence tags: **[PK]** prior knowledge (not re-verified in this session), **[UNR]** unverified
- must be checked by counsel before reliance, **[INF]** inference.

## 1. Principles

1. **Data minimisation.** Only data needed to measure functional performance and its burden are
   stored. No direct identifiers in study tables; participants are keyed by a random pseudonym
   (`NM-` + 10 random characters from a CSPRNG, never derived from any identifier).
2. **Consent first.** Every collection path checks an active consent scope at write time;
   withdrawal stops collection immediately (section 5).
3. **Purpose limitation.** Every table has a declared purpose and data category (section 4).
   Sponsor roles receive aggregates and pseudonymous exports only, restricted to participants who
   consented to `sharing_with_sponsor`; free text, re-identification data, deviation narratives
   and raw event streams never go to sponsors.
4. **Least privilege.** Six roles with a permission matrix (section 6) plus record scoping:
   tenant (organization) for everyone, site for site staff, self for participants, linked
   participants for care partners.
5. **Integrity and accountability.** Append-only, hash-chained audit trail with reasons for every
   change; e-signature records bound to record hashes; SHA-256 for raw events, telemetry batches,
   exports and backups.
6. **Synthetic data never mixes with real data.** Demo data live in demo organizations and demo
   studies; database triggers reject any record whose `is_demo` flag differs from its study's.

## 2. What is never collected

- Names, addresses, dates of birth, phone numbers, e-mail addresses, MRNs or other direct
  identifiers in study tables. The *only* place an identifier may exist is the optional,
  site-held, AES-256-GCM-encrypted re-identification table.
- Neural signals or raw device data. NeuroMetric stores canonical *input events* (pointer
  positions in task space, selections, task markers, assistance markers) only.
- Audio (`audio_none` is a fixed acknowledgement), video, camera images, screenshots.
- Keystroke content outside predefined copy-typing phrases. Typing tasks use NeuroMetric's own
  phrase set; text input in any other task is refused without the `free_text` scope. Home
  telemetry stores the *number* of text characters, never the characters.
- URLs, window titles, application names or bundle identifiers, message content, contacts,
  clipboard, file names, browsing history.
- Location / GPS, device serial numbers, IP addresses in study data (client addresses are used
  transiently, in memory, for login rate limiting only).
- Free text, unless the participant granted `free_text`; even then it is never exported to
  sponsors and is deleted on withdrawal of that scope with action `delete`.

## 3. Consent scopes

| Scope | Covers | Enforced at |
|---|---|---|
| `task_battery` | Functional task sessions (events + scores) | `upload_session` |
| `questionnaires` | Questionnaire responses | `submit_response` |
| `home_telemetry` | Aggregate home usage summaries | `ingest_telemetry`, telemetry state |
| `telemetry_app_categories` | Coarse app-category minutes (requires `home_telemetry`) | `ingest_telemetry` |
| `free_text` | Free-text answers; text input outside copy typing | `submit_response`, `upload_session` |
| `audio_none` | Acknowledgement that no audio is recorded (always true) | consent record |
| `sharing_with_sponsor` | Pseudonymous data in sponsor dashboards and exports | `dashboard`, `export_study` |
| `future_research` | Re-use for future research (recorded; reuse requires a separate protocol) | consent record |

Consent records are versioned (`consent_document_id`, `consent_version`); a new record
supersedes the previous one; the full history is kept. A participant must have an active
consent record before the `screening -> consented` transition.

## 4. Data inventory

Sensitivity levels: `public`, `internal` (no participant data), `pseudonymous` (participant
data keyed by pseudonym), `sensitive` (pseudonymous with elevated risk: raw input streams, free
text, device settings), `identifying` (encrypted re-identification key), `secret`
(credentials). A test (`tests/test_study_exports.py::test_every_schema_column_is_documented`)
fails if any column of the schema is missing from this inventory, so this section cannot drift
silently from the code. Retention values are defaults; per-study policies (section 5.3) override
them for the listed categories.

### 4.1 Tables (generated from the live schema + `neurometric.study.inventory`)

| Table | Purpose | Category | Sensitivity | Retention | Who can see it |
|---|---|---|---|---|---|
| `assessment_schedules` | Visit schedule definitions. | study_setup | internal | life of study + archive | staff |
| `audit_log` | Append-only hash-chained audit trail. | audit | pseudonymous | life of study + archive (never purged by retention) | investigator, admin |
| `auth_tokens` | Session management. | security | secret | until expiry (default 30 min) | nobody (hash only) |
| `care_partner_links` | Care-partner access to a participant. | enrollment | pseudonymous | while linked | admin |
| `consent_records` | Consent scopes (versioned consent document). | consent | pseudonymous | life of study + archive | site staff, participant |
| `consent_withdrawals` | Evidence of withdrawal handling. | consent | pseudonymous | life of study + archive | site staff |
| `data_queries` | Data clarification workflow. | data_management | pseudonymous | life of study + archive | site staff, sponsor analysts |
| `device_configs` | Device context of functional sessions (metadata only). | device | sensitive | study retention period | site staff |
| `e_signatures` | Electronic signature records. | audit | pseudonymous | life of study + archive | staff |
| `enrollment_events` | Enrollment state history. | enrollment | pseudonymous | study retention period | site staff |
| `functional_sessions` | Functional task performance (primary outcome data). | functional_testing | sensitive | per retention policy | site staff, participant; sponsor: aggregates / pseudonymous metrics |
| `missing_data` | Missing-data tracking with reasons. | data_management | pseudonymous | life of study + archive | site staff; sponsor: counts |
| `organizations` | Tenant boundary. | administration | internal | life of deployment | members of the organization |
| `participants` | Pseudonymous enrollment record. | enrollment | pseudonymous | study retention period | site staff (assigned site), the participant |
| `protocol_deviations` | Protocol deviation log. | data_management | pseudonymous | life of study + archive | site staff; sponsor: counts |
| `protocol_versions` | Protocol version control. | study_setup | internal | life of study + archive | staff, sponsor analysts |
| `purge_log` | Evidence of retention purges. | governance | internal | life of deployment | admin |
| `questionnaire_assignments` | Questionnaire schedule and completion tracking. | questionnaires | pseudonymous | study retention period | site staff, participant |
| `questionnaire_responses` | Patient/observer/clinician-reported outcomes. | questionnaires | pseudonymous | per retention policy | site staff, respondent; sponsor: structured answers & scores only |
| `reidentification_keys` | Optional site-held link pseudonym -> identity. | identity | identifying | until study close-out per site SOP | site staff of the participant's site only; NEVER sponsor roles |
| `reminders` | Reminder records (no messages are sent by NeuroMetric). | questionnaires | pseudonymous | study retention period | site staff |
| `retention_policies` | Retention configuration. | governance | internal | life of study | investigator, admin |
| `schema_migrations` | Schema version control. | system | internal | life of database | admin |
| `sites` | Site management and site-scoped access. | study_setup | internal | life of study | staff, sponsor analysts |
| `sponsors` | Study sponsorship metadata. | study_setup | internal | life of study | staff, sponsor analysts |
| `studies` | Study definition. | study_setup | internal | life of study + archive | staff, sponsor analysts |
| `study_sites` | Sites participating in a study. | study_setup | internal | life of study | staff |
| `telemetry_batches` | Aggregate home usage summaries (no content). | telemetry | pseudonymous | per retention policy | participant (own), site staff; sponsor: aggregates |
| `telemetry_receipts` | Ingest outcome log (no payloads). | telemetry | pseudonymous | per retention policy | participant (own), admin |
| `telemetry_state` | Visible recording state (active/paused/stopped). | telemetry | pseudonymous | while enrolled | participant, care partner, site staff |
| `user_sites` | Site assignment of staff (scopes participant access). | administration | internal | account lifetime | admin |
| `users` | Authentication and role-based access. | administration | secret | account lifetime + audit retention | admin (no password hashes via API) |
| `visits` | Visit schedule and completion. | visits | pseudonymous | study retention period | site staff, participant |

### 4.2 Fields

**`assessment_schedules`** (internal)

| Field | Type | Description |
|---|---|---|
| `id` | TEXT | Random record identifier. |
| `org_id` | TEXT | Tenant (organization) owning the record; every query is scoped by it. |
| `study_id` | TEXT | Study the record belongs to. |
| `protocol_version_id` | TEXT | Protocol version. |
| `name` | TEXT | Schedule name. |
| `definition_json` | TEXT | Visits, windows and recurrence rules. |
| `is_demo` | INTEGER | 1 = synthetic demo record; must equal the study's flag (enforced by triggers). |
| `created_at` | TEXT | Server UTC time stamp of creation. |

**`audit_log`** (pseudonymous)

| Field | Type | Description |
|---|---|---|
| `id` | INTEGER | Random record identifier. |
| `org_id` | TEXT | Tenant (organization) owning the record; every query is scoped by it. |
| `at` | TEXT | UTC server time. |
| `actor_user_id` | TEXT | Acting user. |
| `actor_role` | TEXT | Role. |
| `action` | TEXT | Action. |
| `table_name` | TEXT | Table. |
| `record_id` | TEXT | Record. |
| `reason` | TEXT | Reason for change. |
| `old_json` | TEXT | Old values (sensitive values hashed). |
| `new_json` | TEXT | New values (sensitive values hashed). |
| `prev_hash` | TEXT | Previous entry hash. |
| `entry_hash` | TEXT | This entry's hash. |

**`auth_tokens`** (secret)

| Field | Type | Description |
|---|---|---|
| `token_hash` | TEXT | SHA-256 of bearer token. |
| `user_id` | TEXT | Token owner. |
| `org_id` | TEXT | Tenant (organization) owning the record; every query is scoped by it. |
| `created_at` | TEXT | Server UTC time stamp of creation. |
| `expires_at` | TEXT | UTC expiry. |
| `revoked` | INTEGER | 1 after logout. |

**`care_partner_links`** (pseudonymous)

| Field | Type | Description |
|---|---|---|
| `user_id` | TEXT | Care partner user. |
| `participant_id` | TEXT | Random participant pseudonym (not derived from any identifier). |
| `org_id` | TEXT | Tenant (organization) owning the record; every query is scoped by it. |

**`consent_records`** (pseudonymous)

| Field | Type | Description |
|---|---|---|
| `id` | TEXT | Random record identifier. |
| `org_id` | TEXT | Tenant (organization) owning the record; every query is scoped by it. |
| `study_id` | TEXT | Study the record belongs to. |
| `participant_id` | TEXT | Random participant pseudonym (not derived from any identifier). |
| `consent_document_id` | TEXT | Consent document. |
| `consent_version` | TEXT | Version. |
| `scopes_json` | TEXT | Scope -> granted. |
| `status` | TEXT | active / superseded / withdrawn. |
| `given_at` | TEXT | UTC. |
| `recorded_by` | TEXT | User. |
| `ended_at` | TEXT | UTC. |
| `is_demo` | INTEGER | 1 = synthetic demo record; must equal the study's flag (enforced by triggers). |

**`consent_withdrawals`** (pseudonymous)

| Field | Type | Description |
|---|---|---|
| `id` | TEXT | Random record identifier. |
| `org_id` | TEXT | Tenant (organization) owning the record; every query is scoped by it. |
| `study_id` | TEXT | Study the record belongs to. |
| `participant_id` | TEXT | Random participant pseudonym (not derived from any identifier). |
| `scopes_json` | TEXT | Withdrawn scopes. |
| `full_withdrawal` | INTEGER | 1 = full withdrawal. |
| `action` | TEXT | retain / delete. |
| `reason` | TEXT | Reason. |
| `deleted_counts_json` | TEXT | Records deleted per category. |
| `at` | TEXT | UTC. |
| `by_user` | TEXT | User. |
| `is_demo` | INTEGER | 1 = synthetic demo record; must equal the study's flag (enforced by triggers). |

**`data_queries`** (pseudonymous)

| Field | Type | Description |
|---|---|---|
| `id` | TEXT | Random record identifier. |
| `org_id` | TEXT | Tenant (organization) owning the record; every query is scoped by it. |
| `study_id` | TEXT | Study the record belongs to. |
| `participant_id` | TEXT | Random participant pseudonym (not derived from any identifier). |
| `record_table` | TEXT | Queried table. |
| `record_id` | TEXT | Queried record. |
| `field` | TEXT | Field. |
| `question` | TEXT | Question. |
| `status` | TEXT | open/answered/closed. |
| `answer` | TEXT | Answer. |
| `raised_by` | TEXT | User. |
| `raised_at` | TEXT | UTC. |
| `answered_by` | TEXT | User. |
| `answered_at` | TEXT | UTC. |
| `closed_by` | TEXT | User. |
| `closed_at` | TEXT | UTC. |
| `is_demo` | INTEGER | 1 = synthetic demo record; must equal the study's flag (enforced by triggers). |

**`device_configs`** (sensitive)

| Field | Type | Description |
|---|---|---|
| `id` | TEXT | Random record identifier. |
| `org_id` | TEXT | Tenant (organization) owning the record; every query is scoped by it. |
| `study_id` | TEXT | Study the record belongs to. |
| `participant_id` | TEXT | Random participant pseudonym (not derived from any identifier). |
| `modality` | TEXT | Access modality. |
| `make_model` | TEXT | Device make/model as free text (no serial numbers). |
| `settings_json` | TEXT | Settings relevant to measurement (gain, dwell...). |
| `calibration_state` | TEXT | Calibration state at configuration time. |
| `is_demo` | INTEGER | 1 = synthetic demo record; must equal the study's flag (enforced by triggers). |
| `created_at` | TEXT | Server UTC time stamp of creation. |

**`e_signatures`** (pseudonymous)

| Field | Type | Description |
|---|---|---|
| `id` | TEXT | Random record identifier. |
| `org_id` | TEXT | Tenant (organization) owning the record; every query is scoped by it. |
| `study_id` | TEXT | Study the record belongs to. |
| `signer_user_id` | TEXT | Signer. |
| `signer_username` | TEXT | Signer login. |
| `signer_display_name` | TEXT | Printed name. |
| `signer_role` | TEXT | Role. |
| `meaning` | TEXT | authored / reviewed / approved / verified. |
| `record_table` | TEXT | Signed table. |
| `record_id` | TEXT | Signed record. |
| `record_hash` | TEXT | SHA-256 of record at signing. |
| `reauth_method` | TEXT | Re-authentication used. |
| `signed_at` | TEXT | UTC. |
| `is_demo` | INTEGER | 1 = synthetic demo record; must equal the study's flag (enforced by triggers). |

**`enrollment_events`** (pseudonymous)

| Field | Type | Description |
|---|---|---|
| `id` | TEXT | Random record identifier. |
| `org_id` | TEXT | Tenant (organization) owning the record; every query is scoped by it. |
| `study_id` | TEXT | Study the record belongs to. |
| `participant_id` | TEXT | Random participant pseudonym (not derived from any identifier). |
| `from_state` | TEXT | Previous state. |
| `to_state` | TEXT | New state. |
| `reason` | TEXT | Reason (required for withdrawn/lost/completed). |
| `at` | TEXT | UTC time. |
| `by_user` | TEXT | Acting user. |
| `is_demo` | INTEGER | 1 = synthetic demo record; must equal the study's flag (enforced by triggers). |

**`functional_sessions`** (sensitive)

| Field | Type | Description |
|---|---|---|
| `id` | TEXT | Random record identifier. |
| `org_id` | TEXT | Tenant (organization) owning the record; every query is scoped by it. |
| `study_id` | TEXT | Study the record belongs to. |
| `participant_id` | TEXT | Random participant pseudonym (not derived from any identifier). |
| `visit_id` | TEXT | Visit. |
| `device_config_id` | TEXT | Device configuration. |
| `task_id` | TEXT | Battery task id. |
| `battery_version` | TEXT | Battery version. |
| `stimulus_seed` | INTEGER | Stimulus seed. |
| `performed_at` | TEXT | UTC time the assessment was performed (client-reported; used for visit windows). |
| `stimulus_hash` | TEXT | Hash identifying the exact stimuli. |
| `modality` | TEXT | Input modality. |
| `provenance` | TEXT | live / simulated / replayed. |
| `events_blob` | BLOB | zlib-compressed canonical input events (raw). |
| `events_sha256` | TEXT | SHA-256 of the uncompressed canonical events. |
| `n_events` | INTEGER | Number of events. |
| `raw_purged` | INTEGER | 1 when the raw blob was purged by retention. |
| `stream_report_json` | TEXT | Ordering / gap report of the event stream. |
| `metrics_json` | TEXT | Server-side scores. |
| `scorer_version` | TEXT | Scoring code version. |
| `status` | TEXT | valid / invalidated. |
| `is_demo` | INTEGER | 1 = synthetic demo record; must equal the study's flag (enforced by triggers). |
| `uploaded_at` | TEXT | UTC upload time. |
| `uploaded_by` | TEXT | Uploading user. |

**`missing_data`** (pseudonymous)

| Field | Type | Description |
|---|---|---|
| `id` | TEXT | Random record identifier. |
| `org_id` | TEXT | Tenant (organization) owning the record; every query is scoped by it. |
| `study_id` | TEXT | Study the record belongs to. |
| `participant_id` | TEXT | Random participant pseudonym (not derived from any identifier). |
| `visit_id` | TEXT | Visit. |
| `item_type` | TEXT | visit/task/instrument/telemetry. |
| `item_ref` | TEXT | Missing item. |
| `reason_code` | TEXT | Reason code. |
| `note` | TEXT | Note (no identifiers). |
| `is_demo` | INTEGER | 1 = synthetic demo record; must equal the study's flag (enforced by triggers). |
| `recorded_at` | TEXT | UTC time. |
| `recorded_by` | TEXT | User. |

**`organizations`** (internal)

| Field | Type | Description |
|---|---|---|
| `id` | TEXT | Random record identifier. |
| `name` | TEXT | Organization name. |
| `is_demo` | INTEGER | 1 = synthetic demo record; must equal the study's flag (enforced by triggers). |
| `created_at` | TEXT | Server UTC time stamp of creation. |

**`participants`** (pseudonymous)

| Field | Type | Description |
|---|---|---|
| `id` | TEXT | Random record identifier. |
| `org_id` | TEXT | Tenant (organization) owning the record; every query is scoped by it. |
| `study_id` | TEXT | Study the record belongs to. |
| `site_id` | TEXT | Enrolling site. |
| `enrollment_state` | TEXT | Enrollment state. |
| `cohort` | TEXT | Protocol cohort label (no identifiers). |
| `primary_modality` | TEXT | Main access method (e.g. bci_cursor, eye_gaze). |
| `enrolled_on` | TEXT | Date enrolled (server date). |
| `is_demo` | INTEGER | 1 = synthetic demo record; must equal the study's flag (enforced by triggers). |
| `created_at` | TEXT | Server UTC time stamp of creation. |
| `updated_at` | TEXT | UTC time of last change. |

**`protocol_deviations`** (pseudonymous)

| Field | Type | Description |
|---|---|---|
| `id` | TEXT | Random record identifier. |
| `org_id` | TEXT | Tenant (organization) owning the record; every query is scoped by it. |
| `study_id` | TEXT | Study the record belongs to. |
| `participant_id` | TEXT | Random participant pseudonym (not derived from any identifier). |
| `visit_id` | TEXT | Visit. |
| `category` | TEXT | Category. |
| `description` | TEXT | Description (no identifiers). |
| `severity` | TEXT | minor / major. |
| `status` | TEXT | open / closed. |
| `is_demo` | INTEGER | 1 = synthetic demo record; must equal the study's flag (enforced by triggers). |
| `reported_at` | TEXT | UTC time. |
| `reported_by` | TEXT | User. |

**`protocol_versions`** (internal)

| Field | Type | Description |
|---|---|---|
| `id` | TEXT | Random record identifier. |
| `org_id` | TEXT | Tenant (organization) owning the record; every query is scoped by it. |
| `study_id` | TEXT | Study the record belongs to. |
| `version` | TEXT | Protocol version label. |
| `effective_date` | TEXT | Date the version takes effect. |
| `summary` | TEXT | Change summary. |
| `consent_document_id` | TEXT | Consent document approved with this version. |
| `is_demo` | INTEGER | 1 = synthetic demo record; must equal the study's flag (enforced by triggers). |
| `created_at` | TEXT | Server UTC time stamp of creation. |

**`purge_log`** (internal)

| Field | Type | Description |
|---|---|---|
| `id` | TEXT | Random record identifier. |
| `org_id` | TEXT | Tenant (organization) owning the record; every query is scoped by it. |
| `study_id` | TEXT | Study the record belongs to. |
| `policy_id` | TEXT | Policy. |
| `data_category` | TEXT | Category. |
| `cutoff` | TEXT | UTC cutoff. |
| `n_affected` | INTEGER | Records affected. |
| `run_at` | TEXT | UTC. |
| `run_by` | TEXT | User. |

**`questionnaire_assignments`** (pseudonymous)

| Field | Type | Description |
|---|---|---|
| `id` | TEXT | Random record identifier. |
| `org_id` | TEXT | Tenant (organization) owning the record; every query is scoped by it. |
| `study_id` | TEXT | Study the record belongs to. |
| `participant_id` | TEXT | Random participant pseudonym (not derived from any identifier). |
| `visit_id` | TEXT | Visit. |
| `instrument_id` | TEXT | Instrument. |
| `due_date` | TEXT | Due date. |
| `status` | TEXT | pending/completed/missed/cancelled. |
| `response_id` | TEXT | Completing response. |
| `is_demo` | INTEGER | 1 = synthetic demo record; must equal the study's flag (enforced by triggers). |
| `created_at` | TEXT | Server UTC time stamp of creation. |

**`questionnaire_responses`** (pseudonymous)

| Field | Type | Description |
|---|---|---|
| `id` | TEXT | Random record identifier. |
| `org_id` | TEXT | Tenant (organization) owning the record; every query is scoped by it. |
| `study_id` | TEXT | Study the record belongs to. |
| `participant_id` | TEXT | Random participant pseudonym (not derived from any identifier). |
| `visit_id` | TEXT | Visit. |
| `instrument_id` | TEXT | Instrument id. |
| `instrument_version` | TEXT | Instrument version answered. |
| `respondent_type` | TEXT | PRO / ObsRO / ClinRO. |
| `respondent_role` | TEXT | Role of the submitting user. |
| `answers_json` | TEXT | Structured answers. |
| `free_text_json` | TEXT | Optional free text (consented only; never to sponsor). |
| `score_json` | TEXT | Scale scores and missing items. |
| `completion` | TEXT | complete / partial. |
| `language` | TEXT | Language. |
| `is_demo` | INTEGER | 1 = synthetic demo record; must equal the study's flag (enforced by triggers). |
| `submitted_at` | TEXT | UTC time. |
| `submitted_by` | TEXT | User. |

**`reidentification_keys`** (identifying)

| Field | Type | Description |
|---|---|---|
| `participant_id` | TEXT | Random participant pseudonym (not derived from any identifier). |
| `org_id` | TEXT | Tenant (organization) owning the record; every query is scoped by it. |
| `study_id` | TEXT | Study the record belongs to. |
| `site_id` | TEXT | Site holding the key. |
| `enc_scheme` | TEXT | Encryption scheme (aes-256-gcm/v1). |
| `enc_identifier` | BLOB | Encrypted identifier (AES-256-GCM, AAD = pseudonym). |
| `is_demo` | INTEGER | 1 = synthetic demo record; must equal the study's flag (enforced by triggers). |
| `created_at` | TEXT | Server UTC time stamp of creation. |
| `created_by` | TEXT | User who stored it. |

**`reminders`** (pseudonymous)

| Field | Type | Description |
|---|---|---|
| `id` | TEXT | Random record identifier. |
| `org_id` | TEXT | Tenant (organization) owning the record; every query is scoped by it. |
| `study_id` | TEXT | Study the record belongs to. |
| `participant_id` | TEXT | Random participant pseudonym (not derived from any identifier). |
| `assignment_id` | TEXT | Assignment. |
| `remind_on` | TEXT | Date. |
| `channel` | TEXT | record_only. |
| `status` | TEXT | scheduled / cancelled. |
| `is_demo` | INTEGER | 1 = synthetic demo record; must equal the study's flag (enforced by triggers). |
| `created_at` | TEXT | Server UTC time stamp of creation. |

**`retention_policies`** (internal)

| Field | Type | Description |
|---|---|---|
| `id` | TEXT | Random record identifier. |
| `org_id` | TEXT | Tenant (organization) owning the record; every query is scoped by it. |
| `study_id` | TEXT | Study the record belongs to. |
| `data_category` | TEXT | Category. |
| `retain_days` | INTEGER | Days. |
| `is_demo` | INTEGER | 1 = synthetic demo record; must equal the study's flag (enforced by triggers). |
| `created_at` | TEXT | Server UTC time stamp of creation. |

**`schema_migrations`** (internal)

| Field | Type | Description |
|---|---|---|
| `version` | INTEGER | Migration number. |
| `name` | TEXT | Migration name. |
| `checksum` | TEXT | SHA-256 of the migration SQL. |
| `applied_at` | TEXT | UTC time applied. |

**`sites`** (internal)

| Field | Type | Description |
|---|---|---|
| `id` | TEXT | Random record identifier. |
| `org_id` | TEXT | Tenant (organization) owning the record; every query is scoped by it. |
| `code` | TEXT | Short site code. |
| `name` | TEXT | Site name. |
| `is_demo` | INTEGER | 1 = synthetic demo record; must equal the study's flag (enforced by triggers). |
| `created_at` | TEXT | Server UTC time stamp of creation. |

**`sponsors`** (internal)

| Field | Type | Description |
|---|---|---|
| `id` | TEXT | Random record identifier. |
| `org_id` | TEXT | Tenant (organization) owning the record; every query is scoped by it. |
| `name` | TEXT | Sponsor name. |
| `is_demo` | INTEGER | 1 = synthetic demo record; must equal the study's flag (enforced by triggers). |
| `created_at` | TEXT | Server UTC time stamp of creation. |

**`studies`** (internal)

| Field | Type | Description |
|---|---|---|
| `id` | TEXT | Random record identifier. |
| `org_id` | TEXT | Tenant (organization) owning the record; every query is scoped by it. |
| `sponsor_id` | TEXT | Sponsor. |
| `code` | TEXT | Study code. |
| `title` | TEXT | Study title. |
| `is_demo` | INTEGER | 1 = synthetic demo record; must equal the study's flag (enforced by triggers). |
| `status` | TEXT | setup / active / closed. |
| `withdrawal_action_default` | TEXT | Protocol default on consent withdrawal: retain or delete. |
| `min_cell_size` | INTEGER | Smallest group reported in sponsor aggregates. |
| `created_at` | TEXT | Server UTC time stamp of creation. |
| `updated_at` | TEXT | UTC time of last change. |

**`study_sites`** (internal)

| Field | Type | Description |
|---|---|---|
| `study_id` | TEXT | Study the record belongs to. |
| `site_id` | TEXT | Site. |
| `org_id` | TEXT | Tenant (organization) owning the record; every query is scoped by it. |

**`telemetry_batches`** (pseudonymous)

| Field | Type | Description |
|---|---|---|
| `id` | TEXT | Random record identifier. |
| `org_id` | TEXT | Tenant (organization) owning the record; every query is scoped by it. |
| `study_id` | TEXT | Study the record belongs to. |
| `participant_id` | TEXT | Random participant pseudonym (not derived from any identifier). |
| `device_session_id` | TEXT | App session id (random). |
| `period_start` | TEXT | UTC period start. |
| `period_end` | TEXT | UTC period end. |
| `payload_json` | TEXT | Allowlisted aggregate payload as received. |
| `payload_sha256` | TEXT | SHA-256 of the payload. |
| `flags_json` | TEXT | Integrity flags (out_of_order, clock skew, overlap). |
| `received_at` | TEXT | UTC server time. |
| `is_demo` | INTEGER | 1 = synthetic demo record; must equal the study's flag (enforced by triggers). |

**`telemetry_receipts`** (pseudonymous)

| Field | Type | Description |
|---|---|---|
| `id` | TEXT | Random record identifier. |
| `org_id` | TEXT | Tenant (organization) owning the record; every query is scoped by it. |
| `participant_id` | TEXT | Random participant pseudonym (not derived from any identifier). |
| `outcome` | TEXT | accepted / duplicate / rejected. |
| `reason_codes_json` | TEXT | Reason / flag codes. |
| `batch_id` | TEXT | Stored batch. |
| `received_at` | TEXT | UTC. |

**`telemetry_state`** (pseudonymous)

| Field | Type | Description |
|---|---|---|
| `participant_id` | TEXT | Random participant pseudonym (not derived from any identifier). |
| `org_id` | TEXT | Tenant (organization) owning the record; every query is scoped by it. |
| `study_id` | TEXT | Study the record belongs to. |
| `state` | TEXT | active / paused / stopped. |
| `updated_at` | TEXT | UTC. |
| `updated_by` | TEXT | User. |
| `is_demo` | INTEGER | 1 = synthetic demo record; must equal the study's flag (enforced by triggers). |

**`user_sites`** (internal)

| Field | Type | Description |
|---|---|---|
| `user_id` | TEXT | Staff user. |
| `site_id` | TEXT | Assigned site. |
| `org_id` | TEXT | Tenant (organization) owning the record; every query is scoped by it. |

**`users`** (secret)

| Field | Type | Description |
|---|---|---|
| `id` | TEXT | Random record identifier. |
| `org_id` | TEXT | Tenant (organization) owning the record; every query is scoped by it. |
| `username` | TEXT | Login name. |
| `display_name` | TEXT | Name shown in signatures. |
| `password_hash` | TEXT | scrypt hash (salted); never exported. |
| `role` | TEXT | One of the six roles. |
| `participant_id` | TEXT | For participant accounts: own pseudonym. |
| `active` | INTEGER | Account enabled flag. |
| `is_demo` | INTEGER | 1 = synthetic demo record; must equal the study's flag (enforced by triggers). |
| `created_at` | TEXT | Server UTC time stamp of creation. |
| `password_changed_at` | TEXT | UTC time of last password change. |

**`visits`** (pseudonymous)

| Field | Type | Description |
|---|---|---|
| `id` | TEXT | Random record identifier. |
| `org_id` | TEXT | Tenant (organization) owning the record; every query is scoped by it. |
| `study_id` | TEXT | Study the record belongs to. |
| `participant_id` | TEXT | Random participant pseudonym (not derived from any identifier). |
| `schedule_id` | TEXT | Schedule used. |
| `visit_code` | TEXT | e.g. baseline, week_02, home_03. |
| `visit_type` | TEXT | clinic / home / remote. |
| `target_date` | TEXT | Target date. |
| `window_start` | TEXT | Window start date. |
| `window_end` | TEXT | Window end date. |
| `status` | TEXT | scheduled / completed / completed_out_of_window / missed / cancelled. |
| `completed_at` | TEXT | UTC completion time. |
| `tasks_json` | TEXT | Planned tasks. |
| `instruments_json` | TEXT | Planned questionnaires. |
| `notes` | TEXT | Operational notes (no identifiers). |
| `is_demo` | INTEGER | 1 = synthetic demo record; must equal the study's flag (enforced by triggers). |
| `created_at` | TEXT | Server UTC time stamp of creation. |

## 5. Lifecycle controls

### 5.1 Collection

- Functional sessions are accepted only while the participant is `enrolled` or `active`, with an
  active `task_battery` scope; the stimulus hash must match the server's stimuli for the task,
  seed and battery version; every event is validated against the canonical event contract;
  duplicate sequence numbers and duplicate uploads are refused. Raw events are stored
  zlib-compressed with the SHA-256 of their canonical JSON; scores are recomputed server-side.
- Synthetic (simulated) events are refused in non-demo studies.
- Questionnaire responses keep the instrument version; respondent type is enforced (PRO by the
  participant or staff entering on their behalf, ObsRO by a care partner or staff, ClinRO by
  staff); untranslated languages are refused (translations are placeholders marked
  "authorized translation required").

### 5.2 Withdrawal

`withdraw_consent` (participant, coordinator or investigator; reason mandatory) supports full or
per-scope withdrawal. Collection stops in the same transaction: consent record ended, telemetry
state `stopped`, enrollment `withdrawn` (full withdrawal), scheduled visits, questionnaire
assignments and reminders cancelled. The configurable action (study default
`withdrawal_action_default`, overridable per withdrawal as allowed by the protocol) is:

- `retain`: already collected data are kept for the purposes consented to;
- `delete`: data of the withdrawn scopes are deleted (sessions, questionnaire responses,
  telemetry batches, free-text answers), each deletion audited with the record hash.

The action, scopes, counts deleted, reason, actor and time are recorded in
`consent_withdrawals`.

### 5.3 Retention and purge

Per-study `retention_policies` for categories `raw_events` (blobs purged, metrics kept),
`functional_sessions`, `questionnaire_responses`, `questionnaire_free_text`, `telemetry`,
`telemetry_receipts`. The purge job (`POST /api/admin/retention/run`, admin) applies every
policy using server UTC time stamps, logs each run in `purge_log` and audits every affected
record. The audit trail, signatures, consent records and withdrawal evidence are never purged by
the job (archive per the sponsor's / institution's record-retention rules, e.g. FDA 21 CFR 312.62
two-year rule for IND studies [PK], institutional policy, or longer by contract).

### 5.4 Data-subject rights

- **Access / portability:** `GET /api/participants/{pid}/export` (participant self or
  investigator) returns every stored record (including raw events and the participant's own free
  text) as JSON; the identifier itself is never included (only whether a key exists).
- **Erasure:** `DELETE /api/participants/{pid}` (investigator, reason mandatory) deletes all
  participant-level records, the re-identification key and the participant account link.
- **Known tension:** the audit trail keeps pseudonymous tombstones (table, record id, SHA-256 of
  the deleted record, reason, actor, time) and the old/new values of corrected structured
  fields. Sensitive values (identifier, free text, raw events, payloads, passwords) are never
  copied into the audit trail (only their hashes). Whether these tombstones are acceptable under
  an applicable erasure right (e.g. GDPR Art. 17(3)(c)/(d) exemptions for legal obligations and
  research [PK]) must be decided per jurisdiction; crypto-shredding of audit values is a
  documented future option.

### 5.5 Re-identification table

Optional, site-held. Field-level encryption with AES-256-GCM (`cryptography` package), key from
the `NEUROMETRIC_REID_KEY` environment variable (32 random bytes, urlsafe base64;
`python -m neurometric.api gen-key`), the pseudonym bound as associated data so a ciphertext
cannot be moved between rows. Without the key (or the package) storing a re-identification key
is refused - there is no plaintext fallback. Reads require a stated reason, are restricted to
coordinators and investigators assigned to the participant's site, and are audited. Sponsor
analysts and administrators can never read it. Key management (generation, escrow, rotation,
destruction at study close-out) is the deploying site's responsibility (SOP gap: key rotation
requires a re-encryption script, not yet provided).

### 5.6 Home telemetry (privacy-preserving)

Explicit opt-in (`home_telemetry`), application-scoped (DECISIONS D-008), aggregate-only:
period (<= 24 h) counts and minutes. An allowlist validator rejects anything else - unknown keys,
content-like keys (`text`, `url`, `title`, `window`, `screenshot`, `keystrokes`, `clipboard`,
...), strings outside enumerated/patterned fields, URL-like values, arrays where none are
allowed. Rejected payloads are never stored: only a receipt with reason codes. The participant
controls a visible recording state (`active` / `paused` / `stopped`) and can review exactly what
was stored (`GET /api/telemetry/mine`), byte-for-byte, with all receipts. Integrity rules:
idempotent batches keyed by (participant, device session, period), conflicting re-sends and
overlapping periods rejected, out-of-order arrivals accepted and flagged, future periods beyond a
5-minute skew tolerance rejected, each batch hashed (client hash verified when supplied).

### 5.7 Sponsor access

Dashboards and exports for `sponsor_analyst` include only participants whose latest consent
record allows `sharing_with_sponsor`, contain no participant identifiers in dashboards (export
rows use the pseudonym), suppress groups smaller than the study's `min_cell_size` (default 3),
and exclude free text, deviation narratives, re-identification data and raw events. Sponsors may
raise data queries against pseudonymous record ids.

### 5.8 Security of data at rest and in transit

- SQLite with WAL, `foreign_keys=ON`, `synchronous=FULL`, `secure_delete=ON`. Disk encryption,
  OS hardening and TLS termination are deployment responsibilities (the app sends HSTS when
  served over HTTPS).
- Passwords: `hashlib.scrypt` (N=2^14, r=8, p=1, 16-byte salt), minimum 12 characters.
- Bearer tokens: 256-bit random, stored as SHA-256 only, absolute expiry
  (`NEUROMETRIC_TOKEN_TTL_MIN`, default 30 min), revoked on logout/deactivation.
- Secrets only from environment variables (`NEUROMETRIC_REID_KEY`,
  `NEUROMETRIC_ADMIN_PASSWORD`, `NEUROMETRIC_DEMO_PASSWORD`); none in the database or code.
- Backups: SQLite online backup API, sidecar manifest with file SHA-256 and audit head hash,
  verification before restore. Backups contain everything the database contains and must be
  stored encrypted with access restricted like the live database.

## 6. Roles and permission matrix

Generated from `neurometric.study.permissions`. Roles: P participant, CP care partner, CO coordinator, IN investigator, SA sponsor analyst, AD admin.

| Permission | P | CP | CO | IN | SA | AD |
|---|---|---|---|---|---|---|
| `audit.read` | - | - | - | yes | - | yes |
| `audit.verify` | - | - | - | yes | - | yes |
| `backup.run` | - | - | - | - | - | yes |
| `consent.read` | yes | yes | yes | yes | - | - |
| `consent.record` | - | - | yes | yes | - | - |
| `consent.withdraw` | yes | - | yes | yes | - | - |
| `dashboard.read` | - | - | - | yes | yes | - |
| `data.correct` | - | - | yes | yes | - | - |
| `deviation.manage` | - | - | yes | yes | - | - |
| `device.manage` | - | - | yes | yes | - | - |
| `enrollment.transition` | - | - | yes | yes | - | - |
| `export.full` | - | - | - | yes | - | - |
| `export.sponsor` | - | - | - | yes | yes | - |
| `instrument.load_licensed` | - | - | - | yes | - | - |
| `instrument.read` | yes | yes | yes | yes | yes | yes |
| `integrity.check` | - | - | - | yes | - | yes |
| `missing.record` | - | - | yes | yes | - | - |
| `participant.create` | - | - | yes | yes | - | - |
| `participant.read` | yes | yes | yes | yes | - | - |
| `protocol.manage` | - | - | - | yes | - | - |
| `query.answer` | - | - | yes | yes | - | - |
| `query.close` | - | - | - | yes | yes | - |
| `query.raise` | - | - | - | yes | yes | - |
| `questionnaire.read` | yes | yes | yes | yes | - | - |
| `questionnaire.respond` | yes | yes | yes | yes | - | - |
| `record.history` | - | - | yes | yes | - | yes |
| `reid.read` | - | - | yes | yes | - | - |
| `reid.write` | - | - | yes | yes | - | - |
| `retention.manage` | - | - | - | yes | - | yes |
| `retention.run` | - | - | - | - | - | yes |
| `schedule.manage` | - | - | - | yes | - | - |
| `session.read` | yes | - | yes | yes | - | - |
| `session.upload` | yes | yes | yes | yes | - | - |
| `signature.approve` | - | - | - | yes | - | - |
| `signature.review` | - | - | yes | yes | - | - |
| `site.manage` | - | - | - | - | - | yes |
| `sponsor.manage` | - | - | - | - | - | yes |
| `study.create` | - | - | - | yes | - | yes |
| `study.read` | - | - | yes | yes | yes | yes |
| `study.update` | - | - | - | yes | - | yes |
| `subject.delete` | - | - | - | yes | - | - |
| `subject.export` | yes | - | - | yes | - | - |
| `telemetry.control` | yes | yes | yes | yes | - | - |
| `telemetry.ingest` | yes | yes | - | - | - | - |
| `telemetry.review_own` | yes | yes | - | - | - | - |
| `user.manage` | - | - | - | - | - | yes |
| `visit.manage` | - | - | yes | yes | - | - |
| `visit.read` | yes | yes | yes | yes | - | - |

Record scope applied on top of the matrix: tenant for everyone; participants only themselves;
care partners only linked participants (upload, questionnaires, telemetry control - not raw
session browsing); coordinators and investigators only participants at their assigned sites;
sponsor analysts and admins never participant-level records.

## 7. Legal and regulatory applicability (to be confirmed by counsel)

### 7.1 HIPAA

HIPAA applies to *covered entities* (health plans, clearinghouses, providers conducting standard
electronic transactions) and their *business associates* [PK]. Whether NeuroMetric data are PHI
depends on who operates it:

- A university research lab that is not part of a covered component of a hybrid entity, collecting
  data directly from consented research participants, is generally not subject to HIPAA for those
  data (the Common Rule / IRB and state law apply instead) [PK/INF].
- If a covered entity (e.g. an academic medical centre's clinic) operates NeuroMetric, or the
  data are created from its patients' records, the data are PHI; research use then requires an
  authorization, IRB/privacy-board waiver, limited data set with a data use agreement, or
  de-identification (Safe Harbor or Expert Determination) [PK].
- A vendor hosting NeuroMetric for a covered entity would be a business associate and needs a
  BAA [PK].
- Pseudonymised data are **not** de-identified under HIPAA if a re-identification key exists
  that the recipient could access; the sponsor never receives the key, but dates (visit dates,
  time stamps) are retained in exports, so sponsor exports are best treated as a *limited data
  set* at most, not Safe Harbor de-identified data [INF].

NeuroMetric is not HIPAA compliant by itself: the administrative and physical safeguards, risk
analysis, BAAs, breach notification and workforce training are organisational obligations.

### 7.2 State neural-data and consumer-privacy laws [UNR]

Several US states have amended consumer-privacy laws to cover "neural data". The following are
recalled from prior knowledge and are **unverified** - check current text, definitions,
effective dates and research exemptions before relying on them:

- **Colorado** - HB24-1058 (2024) adds "neural data" / biological data to "sensitive data" under
  the Colorado Privacy Act (consent required for processing) [UNR].
- **California** - SB 1223 (2024) adds "neural data" to "sensitive personal information" under
  the CCPA/CPRA [UNR].
- **Montana** - 2025 amendments extending the Genetic Information Privacy Act to neurotechnology
  data [UNR].
- **Connecticut** and other states have considered or passed similar amendments in 2025 [UNR].
- Many consumer-privacy statutes exempt HIPAA-covered data and/or research conducted under the
  Common Rule; the scope of such exemptions differs by state [UNR].

Open question [INF]: NeuroMetric does not store neural signals, but BCI cursor events are
*derived from* decoded neural activity. Some statutory definitions cover information "generated
by measuring the activity of" the nervous system and may or may not reach derived control
outputs. Until counsel advises otherwise, treat BCI-derived event streams as potentially
sensitive neural data: explicit consent (already enforced), purpose limitation, no sale, and
deletion on request (already supported).

### 7.3 Other frameworks

- **21 CFR Part 11 / ICH E6(R3)**: audit trail, e-signature records and access controls are
  technical controls only; validation and procedures are required (see
  `docs/quality/VALIDATION_STRATEGY.md`) [PK].
- **Common Rule (45 CFR 46)** and IRB requirements: consent document versioning and withdrawal
  handling support, not replace, the IRB-approved consent process [PK].
- **GDPR / UK GDPR** (if EU/UK sites): data concerning health are special-category data;
  pseudonymised data remain personal data; a DPIA, lawful basis and Art. 9 condition, data
  processing agreements and international-transfer safeguards are required [PK].

## 8. Demo / synthetic data

`python -m neurometric.api seed-demo` creates a demo organization and a study titled
"DEMO - synthetic data, not patients", populated by the NeuroMetric simulator. All records have
`is_demo = 1`, all events `synthetic = true`, provenance `simulated`; triggers prevent demo and
non-demo records from being combined; dashboards and export manifests carry the DEMO banner.
Demo data must never be presented as patient data or used as evidence of clinical performance.

## 9. Change control of this document

This document is updated with any schema change (the inventory test fails otherwise) and
reviewed at each protocol amendment. Owner: data governance lead (TBD).
