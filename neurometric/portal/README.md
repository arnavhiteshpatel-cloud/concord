# NeuroMetric sponsor evidence portal

A role-aware web UI over the NeuroMetric FastAPI backend (`/api`). Plain HTML, ES modules and
CSS: no build step, no third-party code, no CDN. Charts are inline SVG drawn by `js/charts.js`.
Served by the API at **`/portal/`** (mounted before the `/` web app in
`src/neurometric/api/app.py`; override the directory with `NEUROMETRIC_PORTAL_DIR`).

NeuroMetric is research software, not a medical device. Nothing here is a regulatory submission.

## Run it

```bash
cd neurometric
export NEUROMETRIC_DEMO_PASSWORD='choose-a-demo-password'   # optional; otherwise printed once
python -m neurometric.api seed-demo --db /tmp/nm-demo.sqlite  # prints the demo usernames
python -m neurometric.api serve --db /tmp/nm-demo.sqlite --port 8000
# open http://127.0.0.1:8000/portal/
```

The demo study is **synthetic**. Every page shows the banner “DEMO — synthetic data, not
patients” whenever the selected study has `is_demo` set. The seed creates no participant or
care-partner passwords you need to know beyond the shared demo password: participant usernames are
`demo-participant-<pseudonym in lower case>` (see **Users** as admin). Care-partner accounts can
be added by an admin (**Users → Add user**, role *care partner*, linked participant ID).

## Views by role

The backend enforces permissions. The portal reads `/api/permissions` and shows only what
the signed-in role may use. A hidden view opened by URL shows “Not available for your role”,
and API 403s are shown inline rather than breaking the page.

| Role | Pages |
|---|---|
| Sponsor analyst | **Study dashboard**: overview and sites, completeness by visit (table + bar chart), functional trends with 95% CIs, modality comparison, task-level analysis, home use, care-partner burden and PRO trends, missing data, deviations, data quality. **Data queries** (no participant column). **Reports & exports**: generate the sponsor package, list the manifest with SHA-256, re-hash every file in the browser, and download. Report CLI commands are listed because there is no report API. |
| Study coordinator | **Participants**: completeness by pseudonymous ID, enrollment state, consent. **Participant detail**: visits, consent, sessions, questionnaires, telemetry, and the re-identification reveal flow. **Visits due**: overdue, due now and upcoming, mark complete or missed. **Data queries**: answer queries, report deviations. |
| Clinical investigator | Everything the coordinator has, plus the dashboard (full-site audience) and **Review & sign-off**: casebook e-signature with password re-authentication, signature history from the audit trail, and verify. Also full and sponsor exports, the audit trail, and the integrity check. |
| System administrator | **Users**: list, add, deactivate. **Audit trail**: hash-chain verification and entries. Old and new values are withheld; only changed field names are shown. **System integrity**: integrity check, run backup, verify backup. |
| Participant / care partner | **My study**: upcoming assessments, questionnaires rendered from `/instruments/{id}` (PRO for participants, ObsRO for care partners), telemetry state with pause/resume/stop and “review what was sent” (`/telemetry/mine`, the exact stored payloads), and consent scopes. Participants can withdraw one scope or leave the study; care partners see consent read-only. |

Re-identification data appears only through **Reveal re-identification…**, available to roles
with `reid.read` (coordinator and investigator). The flow requires a reason, which the backend
audits. The identifier auto-hides after 60 seconds and is never stored in the page.

## Design and accessibility

- WCAG 2.2 AA target. The page has landmarks, a skip link, and focus moved to the page heading
  on navigation. It works with the keyboard alone, with visible 3px focus rings. Async results
  go to `aria-live` regions. Dialogs use `<dialog>`. `prefers-reduced-motion` and
  `forced-colors` are respected. Light and dark modes use `prefers-color-scheme` tokens on
  `:root`. Nothing scrolls sideways at 360px; wide tables scroll inside a focusable region.
- Participant pages use targets of 56px or more and one linear focus order, which suits switch
  scanning. Ten-point scales are rendered as radio tiles rather than sliders. There are no time
  limits. Free-text items appear only when the `free_text` consent scope is active.
- Charts use 2px lines, 8px or larger markers with a surface ring, a hairline grid and one
  y-axis. Charts with two or more series get a legend plus direct end labels, with leader lines
  where labels would collide. Series colours follow the fixed categorical order
  (`--s1…--s8`, with separate dark-mode steps); all text uses text tokens. Every chart has a
  hover tooltip, arrow-key reading when focused, and a **Show as table** toggle. 95% CIs are
  t-intervals computed from the dashboard's mean, SD and n.
- Security: same-origin only (CSP `script-src 'self'`, COOP/CORP/COEP compatible). DOM is built
  with `createElement` and `textContent`. The bearer token is kept in `sessionStorage` only.

## Tests

```bash
python -m pytest tests/test_portal_mount.py                       # /portal mount + self-containment
npm install --prefix "$SCRATCH/axe-portal" axe-core@4.10.2        # outside the repo
AXE_CORE_PATH="$SCRATCH/axe-portal/node_modules/axe-core/axe.min.js" node tests/portal/e2e.mjs
```

`tests/portal/e2e.mjs` seeds a fresh synthetic study in a temporary directory and starts the
server on a free port. It signs in through the UI as every role (a care partner is created via
the admin API). It checks views, data, hidden views and flows, and runs axe-core
(WCAG 2.0/2.1/2.2 A/AA + best practice) in light and dark modes. It writes screenshots to
`portal/screenshots/` and results to
`experiments/results/Q_accessibility/portal_axe.json`.

## Known gaps

- No API exists for listing signatures, listing backups, or generating reports. Signature
  history is read from the audit trail (investigator only), backups are verified by file name,
  and reports are generated with the CLI.
- `GET /studies/{sid}/queries` returns `participant_id` to sponsor analysts. The portal hides
  that column, but the API still sends the field; a backend fix is recommended.
- The login page cannot show the demo banner before sign-in, because no unauthenticated
  endpoint exposes `is_demo`.
- Raising new data queries and correcting records are not in the UI yet. Use the API.
- axe-core cannot judge SVG chart colour contrast. Light-mode series colours below 3:1
  (orange, aqua, yellow, pink) are mitigated by direct labels, tooltips and the table view.
