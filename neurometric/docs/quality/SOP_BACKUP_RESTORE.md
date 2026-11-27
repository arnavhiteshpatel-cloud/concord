# SOP-NM-02 Backup and restore (DRAFT)

Status: draft for adoption.

**Purpose.** Protect study data against loss/corruption and prove that backups are restorable.

**Procedure - backup.**
1. Daily (and before every change deployment) run `POST /api/admin/backup` (admin) or
   `python -m neurometric.api backup --db <db> --out <dir>/neurometric-<UTC>.sqlite`. The SQLite
   online backup API produces a consistent copy while the service runs; a manifest
   (`.manifest.json`) records SHA-256, schema version, audit head hash and entry count.
2. Immediately verify: `python -m neurometric.api verify-backup <file>` (hash, integrity check,
   audit chain against manifest head). A failed verification is an incident (SOP-NM-03).
3. Copy backup + manifest to encrypted off-host storage with restricted access (same access
   class as the live database: backups contain all data incl. encrypted re-identification keys).
   Keep the manifest's `audit_head` in a separate log (external anchor for audit truncation
   detection).
4. Retention of backups follows the study retention policy; destroy expired backups securely
   and record destruction. Note: retention purges and subject deletions do not reach existing
   backups - document backup expiry in consent materials.

**Procedure - restore.**
1. Authorisation by system owner; record the reason (incident number).
2. `python -m neurometric.api restore <backup> <new-db-file>` - refuses unverified backups and
   never overwrites an existing file.
3. Verify: integrity check (`GET /api/admin/integrity`), `verify-audit --expected-head <manifest
   head>`, record counts vs. the backup manifest; switch the service to the restored file.
4. Data entered after the backup point must be re-entered from source with reason "restored from
   backup <id>, re-entry of <record>"; document the gap.

**Restore drill.** Quarterly, restore the latest backup into a scratch location and run step 3;
file the evidence.
