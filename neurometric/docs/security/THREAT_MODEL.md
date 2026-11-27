# Threat model (STRIDE) - NeuroMetric study data platform

Document status: DRAFT v0.1 (2026-11-27). Scope: `neurometric.api` (FastAPI), `neurometric.study`
(SQLite storage, audit, consent, telemetry, exports, backups), `neurometric.instruments`, and the
browser/app clients as untrusted callers.

> **Statement.** Technical security and integrity controls exist and are tested. NeuroMetric is
> **not** 21 CFR Part 11 compliant or validated, **not** HIPAA compliant, and has **no SOC 2**
> (or ISO 27001) attestation. Deployers are responsible for infrastructure security, validation,
> procedures, contracts and training.

## 1. Assets

| Asset | Sensitivity |
|---|---|
| Re-identification keys (encrypted identifiers) + `NEUROMETRIC_REID_KEY` | identifying - highest |
| Raw canonical event streams (may derive from neural decoding; BCI cursor events) | sensitive |
| Free-text answers (consented only) | sensitive |
| Questionnaire answers, scores, consent records, visits, deviations | pseudonymous |
| Telemetry aggregates | pseudonymous |
| Audit trail, e-signatures | integrity-critical |
| Credentials (password hashes, bearer tokens) | secret |
| Exports and backups | as their contents |

## 2. Actors and trust boundaries

```
[participant / care-partner device]  [staff browser]  [sponsor analyst browser]
            \                           |                     /
             --------- TLS (deployment) ---------------------
                                |
              [reverse proxy / TLS termination]   <- trust boundary 1 (internet)
                                |
              [FastAPI app: auth, middleware, routes] <- boundary 2 (authN/authZ)
                                |
              [StudyService + SQLite file + backups dir] <- boundary 3 (host / filesystem)
                                |
              [operators with shell access; backup storage] <- boundary 4 (privileged)
```

Adversaries: external attacker; malicious or curious authenticated user of another tenant;
curious sponsor analyst; compromised participant device/app; insider with server or backup
access; buggy client sending content in telemetry.

## 3. STRIDE analysis

### Spoofing

| Threat | Mitigation (implemented) | Residual / recommendation |
|---|---|---|
| Password guessing / credential stuffing | scrypt hashes, 12-char minimum, login rate limiting per user and address (429), generic errors, dummy hash for unknown users (timing) | No MFA/SSO; per-process limiter. Add OIDC/WebAuthn; proxy-level limits. |
| Token theft and replay | 256-bit random tokens, stored hashed, 30-min expiry, logout/deactivation revoke, `no-store` caching, CSP limits script injection | Bearer tokens are replayable until expiry; use TLS, short TTL, consider binding to client (DPoP) or cookie with SameSite + CSRF token in the web app. |
| Signing as someone else | Signatures require password re-entry at signing time; failures audited | No second factor at signing. |
| Telemetry from a spoofed participant | Ingest requires the participant's (or linked care partner's) token; payload pseudonym must match the token's participant | Compromised device can send plausible aggregates; aggregates are flagged, not trusted for safety. |

### Tampering

| Threat | Mitigation | Residual |
|---|---|---|
| Altering entered data without trace | All writes through the service; `_update` requires reason; audit old/new values | Direct DB edits by insiders bypass the app - detected only for hashed data (audit, raw events, telemetry, signed records). |
| Editing / deleting audit entries | SQLite triggers make `audit_log` and `e_signatures` append-only; SHA-256 hash chain; `verify_chain`; external anchors in export/backup manifests | An insider with file access can drop triggers and rewrite the *whole* chain consistently; only an off-system anchor (or HMAC key outside the DB) detects this. |
| Altering raw events / telemetry | SHA-256 stored at ingest; `integrity_check` | Same insider caveat (hash column could be rewritten) - anchor recommended. |
| Altering exports after generation | Per-file SHA-256 manifest, audit head in manifest, `verify_export` | Manifest itself unsigned; sign manifests (detached signature) in future. |
| Tampered backup restored | Manifest hash + `PRAGMA integrity_check` + audit chain vs manifest head; restore refuses unverified | Manifest stored next to backup; keep a copy of the head hash elsewhere. |
| Mass-assignment / unexpected fields | Pydantic models with `extra="forbid"`; correction allowlist per table | - |
| SQL injection | Parameterised queries; table names only from an allowlist | - |

### Repudiation

| Threat | Mitigation | Residual |
|---|---|---|
| User denies having changed or signed data | Audit entries with user id, role, server UTC time, reason; signatures with meaning, printed name, record hash, re-auth method | Shared/compromised credentials undermine attribution - SOP-NM-04 (named accounts, reviews). |
| Client-controlled timestamps | Server clock for all audit/record times; client `performed_at` stored as data, future values rejected | Server clock must be NTP-synchronised (IQ-02). |

### Information disclosure

| Threat | Mitigation | Residual |
|---|---|---|
| Cross-tenant reads (IDOR) | `org_id` scoping on every query; foreign ids return 404 | Regression risk in new code - tests + review checklist; Postgres RLS for hosted use. |
| Sponsor sees participant-level or non-consented data | Aggregate-only dashboards, small-cell suppression, consent filter, sponsor exports without free text / narratives / identifiers / raw events | Small studies: even aggregates can disclose; set `min_cell_size` appropriately. Pseudonymous export rows + dates may allow linkage by a determined recipient (treat as limited data set). |
| Re-identification key exposure | AES-256-GCM, key in env, AAD binding, site-only access with reason, audited, never to sponsor/admin | Key on the same host as the database; use a KMS/HSM or separate secret store; key rotation tooling missing. |
| Content captured by telemetry | Allowlist validator, rejected payloads not stored, local review for participants | Only application-scoped telemetry exists; OS-level capture is out of scope by design. |
| Free text leakage | Only with consent; never exported to sponsors or in FHIR; hashed in audit | Staff can see free text; minimise collection. |
| Error messages leaking internals | Domain errors return codes/messages without stack traces | Uvicorn logs may contain request paths with pseudonyms - restrict log access. |
| Backups/exports copied off-site | Exports built in a temp dir and streamed (no server copy); backups are an operator responsibility | Encrypt backups at rest; restrict backup directory. |
| Browser-side attacks (XSS, clickjacking) | CSP (`default-src 'self'`, `frame-ancestors 'none'`), X-Frame-Options DENY, nosniff, no-referrer, CORS off by default | Web client code is outside this scope; review it separately. |

### Denial of service

| Threat | Mitigation | Residual |
|---|---|---|
| Large request bodies | Body size limits (16 MiB default; 64 KiB telemetry; 8 KiB auth), event count cap | No global per-user request rate limit; scoring of large sessions is CPU-bound (synchronous). Put a proxy with rate limits in front. |
| Login flooding | Rate limiter (429) | Per process only. |
| Telemetry flooding by a device | Per-batch validation; idempotency | Add per-participant quotas. |
| Database lock contention | Single connection with lock; WAL | Single-node SQLite suits single-lab deployments only. |

### Elevation of privilege

| Threat | Mitigation | Residual |
|---|---|---|
| Role escalation via API | Only admins create users; roles from a fixed enumeration; participant accounts must link to an existing participant of the same org | No admin approval workflow (4-eyes) - SOP. |
| Admin reads clinical data | Admin role lacks participant-level and re-identification permissions | Admins with shell access can read the DB file - insider control by SOP and OS permissions. |
| Care partner over-reach | Links to specific participants; cannot browse raw sessions or exports | - |
| Demo data used to fabricate evidence | is_demo triggers; synthetic events refused in non-demo studies; DEMO banners in dashboards/manifests | Operator could fabricate by sending non-synthetic-flagged events; provenance and audit trail support detection, not prevention. |

## 4. Security test coverage (automated)

Tenant isolation (service + HTTP), role matrix for all six roles, token expiry and revocation,
login rate limiting, request-size limits, unknown-field rejection, security headers, CORS off,
docs off, audit tamper detection (edit, delete, reorder, rehash, truncation with anchor),
append-only triggers, raw-event tamper detection, backup corruption/tamper detection, telemetry
forbidden-field rejection (20 cases), re-identification encryption and access restrictions.

## 5. Open items

1. MFA / SSO; forced password change at first login; password history.
2. Off-system audit anchors (WORM log or signed head hashes) and signed export manifests.
3. Key management for `NEUROMETRIC_REID_KEY` (KMS, rotation script, escrow).
4. Shared rate-limit store; per-user API quotas.
5. Postgres backend with row-level security for hosted multi-tenant deployments.
6. Dependency vulnerability scanning and SBOM in CI.
7. Penetration test before any internet-facing deployment.
