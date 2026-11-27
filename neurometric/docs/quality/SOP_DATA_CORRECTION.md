# SOP-NM-05 Data review and correction (DRAFT)

Status: draft for adoption.

**Principles (ALCOA+).** Original data are never overwritten without trace. Every change records
who, when (server UTC), what (old/new values) and why (reason for change) in the audit trail.

**Procedure.**
1. **Identify** a discrepancy via data review, monitoring, or a data query
   (`POST /api/studies/{sid}/queries`).
2. **Verify against source** (session notes, participant confirmation, device logs).
3. **Correct** only allowlisted fields via `PATCH /api/records/{table}/{id}` with a specific
   reason (e.g. "transcription error - participant confirmed rating 2, query Q-123"); generic
   reasons ("update", "fix") are not acceptable. Questionnaire corrections re-score
   automatically and keep the instrument version.
4. **Raw event streams are never edited.** If a session is invalid (device malfunction, wrong
   participant), set `status` to `invalidated` with the reason and re-collect if the protocol
   allows; the raw data and its hash remain.
5. **Answer/close the query** with a reference to the correction.
6. **Review & sign-off:** the coordinator signs records as `reviewed`; the investigator signs
   the participant casebook as `approved` (`POST /api/signatures` with password re-entry). Any
   later change shows the signature as `record_changed_since_signing` and requires re-review.
7. **Audit-trail review:** monthly, data management reviews corrections per participant
   (`GET /api/records/{table}/{id}/history`) and runs `GET /api/audit/verify`.
