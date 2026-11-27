# SOP-NM-01 Change control (DRAFT)

Status: draft for adoption by the deploying organization. Not yet approved or trained.

**Purpose.** Ensure every change to the NeuroMetric study platform (code, schema, instrument
definitions, schedules, configuration, infrastructure) is assessed, tested, approved and
documented before use with study data.

**Scope.** `src/neurometric/{study,api,instruments}`, migrations, instrument JSON, deployment
configuration (environment variables, TLS, backup jobs).

**Roles.** Requester; system owner (approves); developer; independent reviewer; QA (approves
validation-impacting changes).

**Procedure.**
1. Raise a change request (issue) with description, reason, urgency and affected URS/FS ids.
2. Impact assessment: data integrity, privacy, GxP impact; risks from RISK_ASSESSMENT.md; need
   for a migration; need for re-scoring (scorer version) or instrument version change.
   Classify: minor (no validated-function impact), major (affects a URS item), emergency.
3. Implement on a branch. Rules: never edit an applied migration (add a new one); instrument
   changes create a new version (responses keep the version answered); scoring changes bump
   `SCORER_VERSION`; every new table/column documented in `study/inventory.py` (test-enforced).
4. Review: pull request reviewed by someone other than the author, including a checklist:
   tenant scoping (`org_id`) on every query, permission check, reason-for-change on updates,
   audit entry on writes, no secrets, no content-like telemetry fields.
5. Test: full automated suite; targeted OQ steps for affected functions; regenerate
   TRACEABILITY.md.
6. Approve (system owner; QA for major changes) and record the release tag.
7. Deploy: backup + verify (SOP-NM-02) before migration; apply; record schema version and
   migration checksums; smoke test (`/api/health`, `verify-audit`, integrity check).
8. Emergency changes: may deploy after step 5 with retrospective approval within 5 working days.

**Records.** Change request, review, test log (junit XML), approval, deployment record.
