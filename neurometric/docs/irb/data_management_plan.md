# Data management plan

**DRAFT — not submitted — requires faculty PI and IRB review**

## 1. Data inventory
| Category | Content | Identifiable? | Where |
|---|---|---|---|
| Consent records | Signed forms, witness pages, consent version, choices | **Yes** | Paper: locked cabinet in the PI's lab. Electronic: the university-approved e-consent system *[REDCap or equivalent, UNR availability]* |
| Linking key | Name and contact ↔ pseudonym `NM-XXXXXXXXXX` | **Yes** | University-approved restricted storage, accessible to PI and coordinator only. Never on the NeuroMetric server; never on company systems |
| Screening log | Eligibility answers; identifiers only for enrolled people or those who consent to future contact | Yes | As the key; non-enrolled screening data deleted within 30 days [HYP] |
| Task data | Canonical input events within tasks, scores, timing diagnostics, AT settings, ASSIST events | Pseudonymous | University-hosted NeuroMetric study server (`src/neurometric/study`; SQLite/WAL per D-007, or Postgres) |
| Questionnaires | Structured answers | Pseudonymous | Same |
| Telemetry (Stage 5) | Daily aggregate counts and minutes only | Pseudonymous | Same; the allowlist validator rejects anything else |
| Care-partner diary | Minutes by help type; burden | Pseudonymous (linked to the dyad code) | Same |
| Equipment photos | Device and mount only, no people | Low | Same, attached to the AT-settings record |
| Payment records | Name, payment receipt | Yes | University business office per its rules; separate from research data |

**Excluded by design:** audio, video, images of people, gaze coordinates, free text (unless a
separate `free_text` scope is consented; not planned), keystroke content, URLs, app names.

## 2. Pseudonymization
- Pseudonyms come from the study module's generator (`new_pseudonym()`: random `NM-` plus 10
  characters, not derived from identifiers).
- Device-session IDs are random.
- Dates: visit dates are kept for scheduling. Analysis datasets carry days since enrolment, not
  calendar dates [INF].
- Small cells: the study module's `min_cell_size` setting suppresses group summaries below a
  threshold in exports (default to be set to 5 [HYP]).

## 3. Security
- The server is university-hosted under the faculty PI's unit IT. The university's data
  classification (likely "sensitive" or "high-risk" for health-related research data; exact
  category [UNR]) decides the controls.
- TLS in transit; encryption at rest; role-based access (`study/permissions.py`); hash-chained
  audit log (`study/audit.py`) of every create, update and delete.
- Accounts are individual. There are no shared logins. Access is removed within 1 business day
  of leaving the team.
- **The student founder's access:** pseudonymous data only, read-only, after the SAP lock, and
  only for roles approved in the COI plan. No access to the linking key, consent records or
  identifiable screening data.
- Laptops used for sessions: full-disk encryption; managed account; no local copies after upload
  and checksum verification.
- Backups: the study module's backup plus university backup, encrypted. A restore test is done
  before enrolment.

## 4. Retention and destruction
- OPRS: "University of Illinois policy varies based on the type of record"; HHS requires a
  three-year baseline; HIPAA records "must be kept for six years after completion" [V]
  https://oprs.research.illinois.edu/research-topics/record-retention.
- **Proposal [INF]:**
  - consent records: ≥ 3 years after study closure, or 6 years if a HIPAA authorization was used;
  - linking key: destroyed at study closure plus 3 years, unless a longitudinal extension is
    approved;
  - pseudonymous research data: retained ≥ 3 years. Longer retention, and a public
    de-identified dataset, only for participants who ticked the sharing choice.
  - Retention policies are configured in the study module (`retention_policies`; purge job), and
    purges are logged.

## 5. Withdrawal
Per-scope withdrawal is implemented (`study/consent.py`). Collection stops immediately. The
participant's recorded choice (retain or delete) is applied. Deletion is logged without
retaining the deleted content. Data already in a locked analysis dataset or a publication cannot
be withdrawn; the consent says so.

## 6. Sharing
- **Default:** no sharing outside the study team.
- **With consent (choice boxes) and IRB approval:**
  - a de-identified dataset in a public repository (e.g. OSF), following a disclosure review:
    remove rare combinations of diagnosis, access method and age band;
  - coded data to the NeuroMetric company under a university data-use agreement that forbids
    re-identification and onward sharing. **Only for consenting participants.**
- Code and the SAP are public (OSF / repository).

## 7. Breach response
Follow the OPRS breach guidance (a page exists: "Breaches of Confidentiality" [V title; content
not read]) and university IT incident procedures. Report to the IRB within the OPRS prompt
timeline (10 business days [V]) or sooner if university policy requires.

## 8. Responsibilities
| Role | Responsibility |
|---|---|
| Faculty PI | Overall data stewardship; access approvals; breach reporting |
| Study coordinator | Key custody; consent records; access provisioning |
| Independent statistician | Locked analyses from frozen code |
| Student founder | Software maintenance under change control (no changes to scoring code after the SAP lock without a logged deviation); no identifiable data |
