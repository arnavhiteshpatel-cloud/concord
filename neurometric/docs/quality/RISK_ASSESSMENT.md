# Risk assessment (FMEA) - NeuroMetric study data platform

Document status: DRAFT v0.1 (2026-11-27). Method: failure mode and effects analysis applied to
the functions in [FUNCTIONAL_SPEC.md](FUNCTIONAL_SPEC.md), in the spirit of ICH Q9(R1) quality
risk management and GAMP 5 (2nd ed.) risk-based computerized-system assurance [PK]. Scope: data
integrity, participant privacy/rights and decision-relevant evidence quality. NeuroMetric is not
a medical device and never controls a device, so direct patient-safety harms from device control
are out of scope by design; harms considered are privacy harms, loss of participant rights, and
wrong research conclusions.

Scales (1-5): **S** severity (5 = privacy breach of identifiable/sensitive data, or corrupted
primary outcome data used for decisions), **O** occurrence before controls, **D** detectability
(5 = unlikely to be detected). **RPN** = S x O x D (before controls). Residual risk is a judgement
after the listed controls and tests.

| # | Function | Failure mode | Effect | Cause | S | O | D | RPN | Controls (design / test) | Residual |
|---|---|---|---|---|---|---|---|---|---|---|
| R01 | Tenant isolation | Query returns another organization's records | Privacy breach, cross-sponsor leak | Missing `org_id` filter in a new query | 5 | 3 | 4 | 60 | FS-01 scoped `_get`, lists filtered; NotFound on foreign ids; `test_tenant_isolation`, `test_tenant_isolation_over_http`; code review checklist item | Low-Med (new code paths can regress; Postgres RLS recommended for hosted use) |
| R02 | Authorisation | Role performs action outside its permission | Unauthorised data access/modification | Matrix error, missing `require()` | 5 | 3 | 3 | 45 | FS-02/03 matrix + scope checks; `test_role_actions_enforced` (all roles), matrix test | Low |
| R03 | Re-identification | Identifier exposed to sponsor or wrong site | Identification of a participant | Missing scope check; key leak | 5 | 2 | 3 | 30 | FS-05 AES-GCM, AAD, reason + audit on read, no sponsor/admin permission; refuse without key; `test_reidentification_*` | Low (key management is a site SOP risk) |
| R04 | Authentication | Credential stuffing / brute force | Account takeover | Weak passwords, no throttling | 4 | 3 | 3 | 36 | scrypt, 12-char minimum, rate limiter, token expiry; `test_login_rate_limiting` | Med (no MFA; in-memory limiter per process) |
| R05 | Token handling | Stolen token reused | Session hijack | Token theft from client | 4 | 2 | 4 | 32 | 30-min expiry, hash-only storage, logout revocation, no-store caching, CSP | Med (bearer tokens in browser storage; recommend TLS + short TTL) |
| R06 | Session upload | Events scored against wrong stimuli | Wrong primary outcome | Seed/version mismatch | 4 | 3 | 4 | 48 | stimulus hash + battery version check; `test_upload_rejections`, `test_a1_target_geometry_from_stimuli` | Low |
| R07 | Session upload | Malformed / duplicated events silently stored | Biased metrics | Client bug, retries | 4 | 3 | 3 | 36 | canonical validation, duplicate seq + duplicate upload rejection, stream report stored | Low |
| R08 | Scoring | Server scoring defect | Wrong outcomes in all studies | Code defect in scorer | 5 | 2 | 4 | 40 | known-answer tests (A1, ISO TP formula, E1), scorer version stored per session, raw events kept for re-scoring | Low-Med (scorer v1 covers kinematics for A-tasks/E1 only; others generic) |
| R09 | Raw data | Raw events altered after upload | Undetected data falsification | DB edit outside app | 5 | 2 | 4 | 40 | SHA-256 per session, `integrity_check`, audit of every change; `test_integrity_check_detects_raw_event_tampering` | Low |
| R10 | Audit trail | Entries edited/deleted | Loss of attributable history | DB file access | 5 | 2 | 4 | 40 | append-only triggers, hash chain, `verify_chain`, external anchors in export/backup manifests; `test_tampering_is_detected`, truncation test | Low-Med (an attacker with file access can rewrite the whole chain consistently unless an anchor is kept off-system) |
| R11 | Corrections | Data changed without reason | Non-attributable change | Direct update path | 4 | 3 | 3 | 36 | `_update` requires reason; allowlisted correctable fields; `test_updates_require_reason_and_keep_history` | Low |
| R12 | E-signature | Signature applied without re-authentication or not bound to content | Repudiation; signature on altered data | Missing re-auth/hash | 4 | 2 | 3 | 24 | password re-auth, record hash, append-only, `verify_signature`; tests | Low (no biometric/2-component signing; Part 11 11.200 procedural controls needed) |
| R13 | Time stamps | Client-controlled audit times | Back-dated records | Trusting client clocks | 4 | 2 | 3 | 24 | server clock only; `performed_at` stored as data, not audit time; future values rejected | Low (server clock sync via NTP is an IQ item) |
| R14 | Consent | Data collected without/after consent | Rights violation | Missing check on a path | 5 | 2 | 3 | 30 | consent check at every collection path; withdrawal in one transaction; tests | Low |
| R15 | Withdrawal delete | Over- or under-deletion | Loss of retained data or retained deleted data | Scope mapping error | 4 | 2 | 3 | 24 | scope->category mapping, counts recorded, audited; tests for retain/delete/partial/free text | Low |
| R16 | Retention | Purge too early or never | Data loss / over-retention | Wrong cutoff, clock | 4 | 2 | 3 | 24 | server-time cutoffs, purge log, audit, dry run via policy review; `test_retention_purge` | Low |
| R17 | Sponsor access | Sponsor sees participant-level or non-consented data | Privacy breach, consent violation | Audience filter defect | 5 | 2 | 3 | 30 | `_participants_for`, aggregate dashboards, small-cell suppression, export content tests | Low |
| R18 | Telemetry | Content (text, URLs, titles) captured | Serious privacy breach | Client sends extra fields | 5 | 3 | 3 | 45 | allowlist validator, rejection without storage, local review; 20 forbidden-field tests | Low (application-scoped only; OS-level capture not implemented) |
| R19 | Telemetry | Double counting / wrong aggregates | Biased real-world outcome | Retries, overlaps, skew | 3 | 4 | 3 | 36 | idempotency, overlap rejection, out-of-order flags, skew handling; Experiment O test | Low |
| R20 | Exports | Export file altered or produced from tampered trail | Wrong evidence submitted | Post-export edits | 4 | 2 | 3 | 24 | per-file SHA-256 manifest, audit head anchor, `verify_export` | Low |
| R21 | Exports | Conformance over-claimed | Regulatory misrepresentation | Labelling | 3 | 2 | 2 | 12 | explicit disclaimers in manifest and MAPPING_NOTES | Low |
| R22 | Demo data | Synthetic data mixed with real data | Fabricated evidence | Seeding into real study | 5 | 2 | 3 | 30 | is_demo triggers, synthetic events refused in real studies, DEMO banner | Low |
| R23 | Backup/restore | Corrupt or tampered backup restored | Data loss/corruption | Storage fault, tampering | 5 | 2 | 3 | 30 | manifest hash, integrity_check, chain check vs manifest head, restore refuses unverified, never overwrites | Low (off-site copies and restore drills are SOP items) |
| R24 | Availability | Single SQLite file lost | Data loss | Disk failure | 5 | 2 | 2 | 20 | WAL, synchronous=FULL, backups (SOP-BR), restore test | Med (no HA; acceptable for single-lab deployment only) |
| R25 | Instruments | Copyrighted items reproduced | Licence infringement | Adding item text to stubs | 3 | 2 | 2 | 12 | stubs validated to contain no items; licensed items loaded only at run time with attestation | Low |
| R26 | Instruments | Wrong scoring of SUS/TLX/NM scales | Wrong secondary outcomes | Formula error | 4 | 2 | 3 | 24 | known-answer tests; responses keep instrument version | Low |
| R27 | Free text | Identifying free text shared | Privacy breach | Free text in exports | 5 | 2 | 3 | 30 | stored only with consent, excluded from sponsor/full exports and FHIR, deleted on withdrawal | Low |
| R28 | HTTP layer | XSS/clickjacking/CORS abuse in web client | Token theft | Missing headers | 4 | 2 | 3 | 24 | CSP, X-Frame-Options, CORS off, nosniff; tests | Low-Med (web client code outside this scope) |
| R29 | Large uploads | Memory exhaustion / DoS | Outage | Unbounded bodies | 3 | 3 | 2 | 18 | body size limits, event count cap | Low-Med (no global API rate limit) |

## Highest residual risks and recommended actions

1. **Whole-chain rewrite by an attacker with file access (R10).** Keep audit head anchors
   off-system (export/backup manifests to a WORM store; periodic signed anchor). Consider an
   HMAC key held outside the database.
2. **No multi-factor authentication (R04/R05).** Add TOTP/WebAuthn or institutional SSO (OIDC)
   before multi-site or hosted use.
3. **Single-node SQLite (R24).** Postgres with row-level security, PITR and HA for hosted
   deployments (repository layer prepared).
4. **Rate limiting is per process (R04/R29).** Use a shared store / reverse-proxy limits in
   multi-worker deployments.
5. **Scorer coverage (R08).** Task-specific kinematic scoring for B/C/D tasks is not implemented
   server-side (generic completion/time only); flagged in every such session's metrics.
