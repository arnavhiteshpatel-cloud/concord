# SOP-NM-03 Security and data-integrity incident response (DRAFT)

Status: draft for adoption. Align with institutional IT security, IRB and (if applicable)
HIPAA breach-notification and state breach-law procedures [PK].

**Triggers.** Suspected unauthorised access; audit-chain verification failure; integrity-check
failure (raw-event hash, telemetry hash, signature changed); backup verification failure; lost
device/credentials; telemetry receipts showing content-like rejections at scale (possible
misconfigured client); data sent to the wrong recipient.

**Procedure.**
1. **Detect & report** within 1 hour to the system owner and security contact; open an incident
   record (time, reporter, symptoms).
2. **Contain:** deactivate affected accounts (`POST /api/users/{id}/deactivate`, which revokes
   tokens); rotate secrets (`NEUROMETRIC_REID_KEY` requires re-encryption - see gap list);
   isolate host; preserve the database file, WAL, logs and backups (copy, hash, store).
3. **Assess:** run `verify-audit` (with external anchors), `GET /api/admin/integrity`; compare
   with the last verified backup; determine data categories, participants and tenants affected
   using the audit trail.
4. **Eradicate & recover:** fix root cause under change control (SOP-NM-01, emergency path);
   restore from a verified backup if needed (SOP-NM-02).
5. **Notify:** per institutional policy, IRB reporting rules, sponsor contract, and applicable
   law (HIPAA breach rule if PHI; state breach laws; GDPR 72-hour rule if applicable) [PK].
   Decisions and timing documented.
6. **Review:** root-cause analysis and CAPA within 30 days; update RISK_ASSESSMENT.md.
