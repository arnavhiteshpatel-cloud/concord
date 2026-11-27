"""Schema migrations (ordered, append-only list; never edit an applied migration).

Conventions
-----------
* Every tenant-owned table has ``org_id`` (tenant) and every query is scoped by it.
* Every study-level record carries ``study_id`` and ``is_demo``. Triggers make it impossible to
  write a record whose ``is_demo`` differs from its study's flag, or that references a
  participant from another study (defence in depth behind the service-layer checks).
* ``audit_log`` and ``e_signatures`` are append-only (UPDATE / DELETE abort).
* Time stamps are UTC ISO-8601 text produced by the server clock.
"""
from __future__ import annotations

_V1 = """
CREATE TABLE organizations (
  id TEXT PRIMARY KEY, name TEXT NOT NULL, is_demo INTEGER NOT NULL DEFAULT 0 CHECK (is_demo IN (0,1)),
  created_at TEXT NOT NULL);

CREATE TABLE users (
  id TEXT PRIMARY KEY, org_id TEXT NOT NULL REFERENCES organizations(id),
  username TEXT NOT NULL UNIQUE, display_name TEXT NOT NULL DEFAULT '',
  password_hash TEXT NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('participant','care_partner','coordinator','investigator','sponsor_analyst','admin')),
  participant_id TEXT, active INTEGER NOT NULL DEFAULT 1, is_demo INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL, password_changed_at TEXT NOT NULL);
CREATE INDEX ix_users_org ON users(org_id);

CREATE TABLE auth_tokens (
  token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  org_id TEXT NOT NULL, created_at TEXT NOT NULL, expires_at TEXT NOT NULL,
  revoked INTEGER NOT NULL DEFAULT 0);

CREATE TABLE sponsors (
  id TEXT PRIMARY KEY, org_id TEXT NOT NULL REFERENCES organizations(id), name TEXT NOT NULL,
  is_demo INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL);

CREATE TABLE sites (
  id TEXT PRIMARY KEY, org_id TEXT NOT NULL REFERENCES organizations(id), code TEXT NOT NULL,
  name TEXT NOT NULL, is_demo INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL,
  UNIQUE(org_id, code));

CREATE TABLE user_sites (
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  site_id TEXT NOT NULL REFERENCES sites(id), org_id TEXT NOT NULL,
  PRIMARY KEY (user_id, site_id));

CREATE TABLE studies (
  id TEXT PRIMARY KEY, org_id TEXT NOT NULL REFERENCES organizations(id),
  sponsor_id TEXT REFERENCES sponsors(id), code TEXT NOT NULL, title TEXT NOT NULL,
  is_demo INTEGER NOT NULL DEFAULT 0 CHECK (is_demo IN (0,1)),
  status TEXT NOT NULL DEFAULT 'setup' CHECK (status IN ('setup','active','closed')),
  withdrawal_action_default TEXT NOT NULL DEFAULT 'retain' CHECK (withdrawal_action_default IN ('retain','delete')),
  min_cell_size INTEGER NOT NULL DEFAULT 3,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(org_id, code));

CREATE TABLE study_sites (
  study_id TEXT NOT NULL REFERENCES studies(id), site_id TEXT NOT NULL REFERENCES sites(id),
  org_id TEXT NOT NULL, PRIMARY KEY (study_id, site_id));

CREATE TABLE protocol_versions (
  id TEXT PRIMARY KEY, org_id TEXT NOT NULL, study_id TEXT NOT NULL REFERENCES studies(id),
  version TEXT NOT NULL, effective_date TEXT NOT NULL, summary TEXT NOT NULL DEFAULT '',
  consent_document_id TEXT NOT NULL DEFAULT '', is_demo INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL, UNIQUE(study_id, version));

CREATE TABLE assessment_schedules (
  id TEXT PRIMARY KEY, org_id TEXT NOT NULL, study_id TEXT NOT NULL REFERENCES studies(id),
  protocol_version_id TEXT REFERENCES protocol_versions(id), name TEXT NOT NULL,
  definition_json TEXT NOT NULL, is_demo INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL);

CREATE TABLE participants (
  id TEXT PRIMARY KEY, org_id TEXT NOT NULL, study_id TEXT NOT NULL REFERENCES studies(id),
  site_id TEXT NOT NULL REFERENCES sites(id),
  enrollment_state TEXT NOT NULL DEFAULT 'screening' CHECK (enrollment_state IN
    ('screening','consented','enrolled','active','completed','withdrawn','lost')),
  cohort TEXT NOT NULL DEFAULT '', primary_modality TEXT NOT NULL DEFAULT '',
  enrolled_on TEXT, is_demo INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE INDEX ix_participants_study ON participants(org_id, study_id);

CREATE TABLE care_partner_links (
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  participant_id TEXT NOT NULL REFERENCES participants(id) ON DELETE CASCADE,
  org_id TEXT NOT NULL, PRIMARY KEY (user_id, participant_id));

CREATE TABLE reidentification_keys (
  participant_id TEXT PRIMARY KEY REFERENCES participants(id) ON DELETE CASCADE,
  org_id TEXT NOT NULL, study_id TEXT NOT NULL, site_id TEXT NOT NULL,
  enc_scheme TEXT NOT NULL, enc_identifier BLOB NOT NULL, is_demo INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL, created_by TEXT NOT NULL);

CREATE TABLE enrollment_events (
  id TEXT PRIMARY KEY, org_id TEXT NOT NULL, study_id TEXT NOT NULL,
  participant_id TEXT NOT NULL REFERENCES participants(id) ON DELETE CASCADE,
  from_state TEXT NOT NULL, to_state TEXT NOT NULL, reason TEXT NOT NULL DEFAULT '',
  at TEXT NOT NULL, by_user TEXT NOT NULL, is_demo INTEGER NOT NULL DEFAULT 0);

CREATE TABLE visits (
  id TEXT PRIMARY KEY, org_id TEXT NOT NULL, study_id TEXT NOT NULL,
  participant_id TEXT NOT NULL REFERENCES participants(id) ON DELETE CASCADE,
  schedule_id TEXT REFERENCES assessment_schedules(id), visit_code TEXT NOT NULL,
  visit_type TEXT NOT NULL DEFAULT 'clinic' CHECK (visit_type IN ('clinic','home','remote')),
  target_date TEXT NOT NULL, window_start TEXT NOT NULL, window_end TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'scheduled' CHECK (status IN
    ('scheduled','completed','completed_out_of_window','missed','cancelled')),
  completed_at TEXT, tasks_json TEXT NOT NULL DEFAULT '[]', instruments_json TEXT NOT NULL DEFAULT '[]',
  notes TEXT NOT NULL DEFAULT '', is_demo INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL,
  UNIQUE(participant_id, visit_code));

CREATE TABLE device_configs (
  id TEXT PRIMARY KEY, org_id TEXT NOT NULL, study_id TEXT NOT NULL,
  participant_id TEXT NOT NULL REFERENCES participants(id) ON DELETE CASCADE,
  modality TEXT NOT NULL, make_model TEXT NOT NULL DEFAULT '', settings_json TEXT NOT NULL DEFAULT '{}',
  calibration_state TEXT NOT NULL DEFAULT 'unknown', is_demo INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL);

CREATE TABLE functional_sessions (
  id TEXT PRIMARY KEY, org_id TEXT NOT NULL, study_id TEXT NOT NULL,
  participant_id TEXT NOT NULL REFERENCES participants(id) ON DELETE CASCADE,
  visit_id TEXT REFERENCES visits(id) ON DELETE SET NULL,
  device_config_id TEXT REFERENCES device_configs(id) ON DELETE SET NULL,
  task_id TEXT NOT NULL, battery_version TEXT NOT NULL, stimulus_seed INTEGER NOT NULL,
  performed_at TEXT NOT NULL,
  stimulus_hash TEXT NOT NULL, modality TEXT NOT NULL,
  provenance TEXT NOT NULL CHECK (provenance IN ('live','simulated','replayed')),
  events_blob BLOB, events_sha256 TEXT NOT NULL, n_events INTEGER NOT NULL,
  raw_purged INTEGER NOT NULL DEFAULT 0,
  stream_report_json TEXT NOT NULL, metrics_json TEXT NOT NULL, scorer_version TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'valid' CHECK (status IN ('valid','invalidated')),
  is_demo INTEGER NOT NULL DEFAULT 0, uploaded_at TEXT NOT NULL, uploaded_by TEXT NOT NULL);
CREATE INDEX ix_sessions_participant ON functional_sessions(org_id, participant_id);

CREATE TABLE questionnaire_assignments (
  id TEXT PRIMARY KEY, org_id TEXT NOT NULL, study_id TEXT NOT NULL,
  participant_id TEXT NOT NULL REFERENCES participants(id) ON DELETE CASCADE,
  visit_id TEXT REFERENCES visits(id) ON DELETE CASCADE, instrument_id TEXT NOT NULL,
  due_date TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','completed','missed','cancelled')),
  response_id TEXT, is_demo INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL);

CREATE TABLE reminders (
  id TEXT PRIMARY KEY, org_id TEXT NOT NULL, study_id TEXT NOT NULL,
  participant_id TEXT NOT NULL REFERENCES participants(id) ON DELETE CASCADE,
  assignment_id TEXT NOT NULL REFERENCES questionnaire_assignments(id) ON DELETE CASCADE,
  remind_on TEXT NOT NULL, channel TEXT NOT NULL DEFAULT 'record_only',
  status TEXT NOT NULL DEFAULT 'scheduled', is_demo INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL);

CREATE TABLE questionnaire_responses (
  id TEXT PRIMARY KEY, org_id TEXT NOT NULL, study_id TEXT NOT NULL,
  participant_id TEXT NOT NULL REFERENCES participants(id) ON DELETE CASCADE,
  visit_id TEXT REFERENCES visits(id) ON DELETE SET NULL,
  instrument_id TEXT NOT NULL, instrument_version TEXT NOT NULL, respondent_type TEXT NOT NULL,
  respondent_role TEXT NOT NULL, answers_json TEXT NOT NULL, free_text_json TEXT,
  score_json TEXT NOT NULL, completion TEXT NOT NULL CHECK (completion IN ('complete','partial')),
  language TEXT NOT NULL DEFAULT 'en', is_demo INTEGER NOT NULL DEFAULT 0,
  submitted_at TEXT NOT NULL, submitted_by TEXT NOT NULL);

CREATE TABLE protocol_deviations (
  id TEXT PRIMARY KEY, org_id TEXT NOT NULL, study_id TEXT NOT NULL REFERENCES studies(id),
  participant_id TEXT REFERENCES participants(id) ON DELETE CASCADE,
  visit_id TEXT REFERENCES visits(id) ON DELETE SET NULL,
  category TEXT NOT NULL, description TEXT NOT NULL,
  severity TEXT NOT NULL CHECK (severity IN ('minor','major')),
  status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','closed')),
  is_demo INTEGER NOT NULL DEFAULT 0, reported_at TEXT NOT NULL, reported_by TEXT NOT NULL);

CREATE TABLE missing_data (
  id TEXT PRIMARY KEY, org_id TEXT NOT NULL, study_id TEXT NOT NULL,
  participant_id TEXT NOT NULL REFERENCES participants(id) ON DELETE CASCADE,
  visit_id TEXT REFERENCES visits(id) ON DELETE CASCADE,
  item_type TEXT NOT NULL CHECK (item_type IN ('visit','task','instrument','telemetry')),
  item_ref TEXT NOT NULL, reason_code TEXT NOT NULL, note TEXT NOT NULL DEFAULT '',
  is_demo INTEGER NOT NULL DEFAULT 0, recorded_at TEXT NOT NULL, recorded_by TEXT NOT NULL);

CREATE TABLE data_queries (
  id TEXT PRIMARY KEY, org_id TEXT NOT NULL, study_id TEXT NOT NULL REFERENCES studies(id),
  participant_id TEXT REFERENCES participants(id) ON DELETE CASCADE,
  record_table TEXT NOT NULL, record_id TEXT NOT NULL, field TEXT NOT NULL DEFAULT '',
  question TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','answered','closed')),
  answer TEXT NOT NULL DEFAULT '', raised_by TEXT NOT NULL, raised_at TEXT NOT NULL,
  answered_by TEXT, answered_at TEXT, closed_by TEXT, closed_at TEXT,
  is_demo INTEGER NOT NULL DEFAULT 0);

CREATE TABLE consent_records (
  id TEXT PRIMARY KEY, org_id TEXT NOT NULL, study_id TEXT NOT NULL,
  participant_id TEXT NOT NULL REFERENCES participants(id) ON DELETE CASCADE,
  consent_document_id TEXT NOT NULL, consent_version TEXT NOT NULL, scopes_json TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('active','superseded','withdrawn')),
  given_at TEXT NOT NULL, recorded_by TEXT NOT NULL, ended_at TEXT,
  is_demo INTEGER NOT NULL DEFAULT 0);

CREATE TABLE consent_withdrawals (
  id TEXT PRIMARY KEY, org_id TEXT NOT NULL, study_id TEXT NOT NULL,
  participant_id TEXT NOT NULL, scopes_json TEXT NOT NULL, full_withdrawal INTEGER NOT NULL,
  action TEXT NOT NULL CHECK (action IN ('retain','delete')), reason TEXT NOT NULL,
  deleted_counts_json TEXT NOT NULL, at TEXT NOT NULL, by_user TEXT NOT NULL,
  is_demo INTEGER NOT NULL DEFAULT 0);

CREATE TABLE telemetry_state (
  participant_id TEXT PRIMARY KEY REFERENCES participants(id) ON DELETE CASCADE,
  org_id TEXT NOT NULL, study_id TEXT NOT NULL,
  state TEXT NOT NULL CHECK (state IN ('active','paused','stopped')),
  updated_at TEXT NOT NULL, updated_by TEXT NOT NULL, is_demo INTEGER NOT NULL DEFAULT 0);

CREATE TABLE telemetry_batches (
  id TEXT PRIMARY KEY, org_id TEXT NOT NULL, study_id TEXT NOT NULL,
  participant_id TEXT NOT NULL REFERENCES participants(id) ON DELETE CASCADE,
  device_session_id TEXT NOT NULL, period_start TEXT NOT NULL, period_end TEXT NOT NULL,
  payload_json TEXT NOT NULL, payload_sha256 TEXT NOT NULL, flags_json TEXT NOT NULL DEFAULT '[]',
  received_at TEXT NOT NULL, is_demo INTEGER NOT NULL DEFAULT 0,
  UNIQUE(participant_id, device_session_id, period_start, period_end));

CREATE TABLE telemetry_receipts (
  id TEXT PRIMARY KEY, org_id TEXT NOT NULL, participant_id TEXT,
  outcome TEXT NOT NULL CHECK (outcome IN ('accepted','duplicate','rejected')),
  reason_codes_json TEXT NOT NULL, batch_id TEXT, received_at TEXT NOT NULL);

CREATE TABLE retention_policies (
  id TEXT PRIMARY KEY, org_id TEXT NOT NULL, study_id TEXT NOT NULL REFERENCES studies(id),
  data_category TEXT NOT NULL, retain_days INTEGER NOT NULL CHECK (retain_days >= 0),
  is_demo INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL, UNIQUE(study_id, data_category));

CREATE TABLE purge_log (
  id TEXT PRIMARY KEY, org_id TEXT NOT NULL, study_id TEXT NOT NULL, policy_id TEXT,
  data_category TEXT NOT NULL, cutoff TEXT NOT NULL, n_affected INTEGER NOT NULL,
  run_at TEXT NOT NULL, run_by TEXT NOT NULL);

CREATE TABLE e_signatures (
  id TEXT PRIMARY KEY, org_id TEXT NOT NULL, study_id TEXT,
  signer_user_id TEXT NOT NULL, signer_username TEXT NOT NULL, signer_display_name TEXT NOT NULL,
  signer_role TEXT NOT NULL,
  meaning TEXT NOT NULL CHECK (meaning IN ('authored','reviewed','approved','verified')),
  record_table TEXT NOT NULL, record_id TEXT NOT NULL, record_hash TEXT NOT NULL,
  reauth_method TEXT NOT NULL, signed_at TEXT NOT NULL, is_demo INTEGER NOT NULL DEFAULT 0);

CREATE TABLE audit_log (
  id INTEGER PRIMARY KEY, org_id TEXT NOT NULL, at TEXT NOT NULL,
  actor_user_id TEXT NOT NULL, actor_role TEXT NOT NULL, action TEXT NOT NULL,
  table_name TEXT NOT NULL, record_id TEXT NOT NULL, reason TEXT NOT NULL DEFAULT '',
  old_json TEXT, new_json TEXT, prev_hash TEXT NOT NULL, entry_hash TEXT NOT NULL UNIQUE);
CREATE INDEX ix_audit_record ON audit_log(table_name, record_id);

CREATE TRIGGER audit_log_no_update BEFORE UPDATE ON audit_log
BEGIN SELECT RAISE(ABORT, 'audit_log is append-only'); END;
CREATE TRIGGER audit_log_no_delete BEFORE DELETE ON audit_log
BEGIN SELECT RAISE(ABORT, 'audit_log is append-only'); END;
CREATE TRIGGER e_signatures_no_update BEFORE UPDATE ON e_signatures
BEGIN SELECT RAISE(ABORT, 'e_signatures is append-only'); END;
CREATE TRIGGER e_signatures_no_delete BEFORE DELETE ON e_signatures
BEGIN SELECT RAISE(ABORT, 'e_signatures is append-only'); END;

CREATE TRIGGER studies_demo_org BEFORE INSERT ON studies
WHEN NEW.is_demo = 0 AND (SELECT is_demo FROM organizations WHERE id = NEW.org_id) = 1
BEGIN SELECT RAISE(ABORT, 'demo_mix: non-demo study in a demo organization'); END;
CREATE TRIGGER studies_demo_immutable BEFORE UPDATE OF is_demo ON studies
WHEN NEW.is_demo != OLD.is_demo
BEGIN SELECT RAISE(ABORT, 'demo_mix: is_demo of a study cannot change'); END;
"""

#: Study-scoped tables: is_demo must equal the study's flag.
DEMO_SCOPED = [
    "protocol_versions", "assessment_schedules", "participants", "reidentification_keys",
    "enrollment_events", "visits", "device_configs", "functional_sessions",
    "questionnaire_assignments", "reminders", "questionnaire_responses", "protocol_deviations",
    "missing_data", "data_queries", "consent_records", "consent_withdrawals", "telemetry_state",
    "telemetry_batches", "retention_policies",
]
#: Tables whose participant must belong to the same study.
PARTICIPANT_SCOPED = [
    "reidentification_keys", "enrollment_events", "visits", "device_configs",
    "functional_sessions", "questionnaire_assignments", "reminders", "questionnaire_responses",
    "protocol_deviations", "missing_data", "data_queries", "consent_records", "telemetry_state",
    "telemetry_batches",
]


def _demo_triggers() -> str:
    out = []
    for t in DEMO_SCOPED:
        for ev in ("INSERT", "UPDATE"):
            out.append(
                f"CREATE TRIGGER {t}_demo_{ev.lower()} BEFORE {ev} ON {t}\n"
                f"WHEN NEW.is_demo != (SELECT is_demo FROM studies WHERE id = NEW.study_id)\n"
                f"BEGIN SELECT RAISE(ABORT, 'demo_mix: record is_demo differs from its study'); END;")
    for t in PARTICIPANT_SCOPED:
        for ev in ("INSERT", "UPDATE"):
            out.append(
                f"CREATE TRIGGER {t}_pstudy_{ev.lower()} BEFORE {ev} ON {t}\n"
                f"WHEN NEW.participant_id IS NOT NULL AND NEW.study_id != "
                f"(SELECT study_id FROM participants WHERE id = NEW.participant_id)\n"
                f"BEGIN SELECT RAISE(ABORT, 'participant belongs to another study'); END;")
    return "\n".join(out)


MIGRATIONS: list[tuple[int, str, str]] = [
    (1, "initial_schema", _V1),
    (2, "demo_and_participant_scope_triggers", _demo_triggers()),
]
