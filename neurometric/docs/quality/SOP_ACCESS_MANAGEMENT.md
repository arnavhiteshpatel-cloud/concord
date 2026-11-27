# SOP-NM-04 Access management (DRAFT)

Status: draft for adoption.

**Principles.** Unique named accounts; least privilege (permission matrix in
DATA_GOVERNANCE.md section 6); no shared accounts; site staff assigned only to their sites;
sponsor analysts never receive participant-level or re-identification access.

**Procedure.**
1. **Request:** supervisor requests an account with role and sites; for participants, the
   coordinator requests the participant account after enrollment; for care partners, the link
   to specific participants is documented with the participant's agreement.
2. **Approve:** system owner (or delegate) approves; training on relevant SOPs is completed
   before activation (training record).
3. **Provision:** admin creates the user (`POST /api/users`) with an initial password delivered
   out-of-band; user changes it at first use (procedural; forced change is a known gap). Password
   minimum 12 characters; no reuse of institutional passwords.
4. **Review:** quarterly access review - list users (`GET /api/users`), confirm roles, site
   assignments and care-partner links; remove stale access.
5. **Revoke:** on role change or departure, deactivate the same day
   (`POST /api/users/{id}/deactivate` with reason) - tokens are revoked immediately.
6. **Signatures:** before first e-signature use, the user signs a statement that their
   electronic signature is the legally binding equivalent of a handwritten signature (Part 11
   §11.100 certification to FDA is an organizational step) [PK].
7. **Re-identification access:** only coordinators/investigators of the participant's site;
   every reveal requires a reason and is audited; monthly review of `reidentify` audit entries.
