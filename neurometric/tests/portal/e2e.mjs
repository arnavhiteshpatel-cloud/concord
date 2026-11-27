#!/usr/bin/env node
// End-to-end + accessibility test for the sponsor evidence portal (/portal).
//
//   node tests/portal/e2e.mjs            (from the repository root: neurometric/)
//
// Seeds a fresh SYNTHETIC demo study in a temporary directory, starts the API server on a free
// port, signs in as every role through the real UI (Playwright, headless Chromium), checks that
// the right views render with data and that forbidden views are hidden, exercises key flows
// (export + manifest verification, signature with re-authentication, re-identification reveal,
// telemetry pause/resume, consent withdrawal, keyboard-only questionnaire), runs axe-core on
// every page (light and dark), checks for horizontal scrolling at 360px, saves screenshots to
// portal/screenshots/ and writes experiments/results/Q_accessibility/portal_axe.json.
//
// Environment: NEUROMETRIC_DEMO_PASSWORD (optional; random otherwise), AXE_CORE_PATH (path to
// axe.min.js; default: the scratch install described in portal/README.md, then node resolution),
// PYTHON (default python3). Exit code 1 on any failed check or serious/critical axe violation.
import { createRequire } from 'node:module';
import { spawn, spawnSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import net from 'node:net';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';

const require = createRequire(import.meta.url);
const { chromium } = require('playwright');

const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPO = path.resolve(HERE, '..', '..');
const SHOTS = path.join(REPO, 'portal', 'screenshots');
const RESULTS = path.join(REPO, 'experiments', 'results', 'Q_accessibility', 'portal_axe.json');
const PY = process.env.PYTHON || 'python3';

function findAxe() {
  const cands = [process.env.AXE_CORE_PATH,
    '/tmp/claude-0/-home-user-concord/e99cb831-573d-524c-a881-af97df967193/scratchpad/axe-portal/node_modules/axe-core/axe.min.js'];
  for (const c of cands) if (c && fs.existsSync(c)) return c;
  try { return require.resolve('axe-core/axe.min.js'); } catch { /* fallthrough */ }
  throw new Error('axe-core not found: set AXE_CORE_PATH to axe.min.js (npm install axe-core outside the repo)');
}

const freePort = () => new Promise((res) => { const s = net.createServer(); s.listen(0, '127.0.0.1', () => { const p = s.address().port; s.close(() => res(p)); }); });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// ------------------------------------------------------------------ results bookkeeping
const checks = [];
const pages = [];
function check(role, name, pass, detail = '') {
  checks.push({ role, check: name, pass: !!pass, detail: String(detail).slice(0, 300) });
  console.log(`${pass ? 'PASS' : 'FAIL'}  [${role}] ${name}${detail ? ` — ${String(detail).slice(0, 160)}` : ''}`);
}

async function main() {
  const axeSrc = fs.readFileSync(findAxe(), 'utf8');
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'nm-portal-e2e-'));
  const db = path.join(tmp, 'portal.sqlite');
  const pw = process.env.NEUROMETRIC_DEMO_PASSWORD || `demo-${crypto.randomBytes(9).toString('base64url')}`;
  const env = { ...process.env, NEUROMETRIC_DEMO_PASSWORD: pw, NEUROMETRIC_BACKUP_DIR: path.join(tmp, 'backups'), PYTHONPATH: path.join(REPO, 'src') + (process.env.PYTHONPATH ? `:${process.env.PYTHONPATH}` : '') };
  env.NEUROMETRIC_REID_KEY = spawnSync(PY, ['-m', 'neurometric.api', 'gen-key'], { env, encoding: 'utf8' }).stdout.trim();

  const seed = spawnSync(PY, ['-m', 'neurometric.api', 'seed-demo', '--db', db], { env, encoding: 'utf8', cwd: REPO });
  if (seed.status !== 0) throw new Error(`seed-demo failed: ${seed.stderr}`);
  const users = {};
  for (const line of seed.stdout.split('\n')) {
    const m = /^\s+(admin|coordinator|investigator|sponsor_analyst)\s+(\S+)/.exec(line);
    if (m) users[m[1]] = m[2];
  }
  const studyId = (/Study id:\s*(\S+)/.exec(seed.stdout) || [])[1];
  const port = await freePort();
  const base = `http://127.0.0.1:${port}`;
  const server = spawn(PY, ['-m', 'neurometric.api', 'serve', '--db', db, '--port', String(port)], { env, cwd: REPO, stdio: ['ignore', 'pipe', 'pipe'] });
  let serverLog = '';
  server.stdout.on('data', (d) => { serverLog += d; });
  server.stderr.on('data', (d) => { serverLog += d; });
  const stop = () => { try { server.kill('SIGTERM'); } catch { /* gone */ } };
  process.on('exit', stop);

  let browser;
  try {
    for (let i = 0; i < 100; i++) {
      try { const r = await fetch(`${base}/api/health`); if (r.ok) break; } catch { /* not yet */ }
      await sleep(150);
    }
    // ---------------------------------------------------------------- API set-up (synthetic)
    const apiAs = async (username) => {
      const r = await fetch(`${base}/api/auth/login`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ username, password: pw }) });
      const { token } = await r.json();
      return async (p, opts = {}) => {
        const res = await fetch(`${base}/api${p}`, { ...opts, headers: { authorization: `Bearer ${token}`, 'content-type': 'application/json', ...(opts.headers || {}) } });
        return { status: res.status, body: res.headers.get('content-type')?.includes('json') ? await res.json() : null };
      };
    };
    const admin = await apiAs(users.admin);
    const allUsers = (await admin('/users')).body;
    const partUsers = allUsers.filter((u) => u.role === 'participant');
    const participant = partUsers[0];
    const pid = participant.participant_id;
    const cpName = `demo-carepartner-e2e-${crypto.randomBytes(3).toString('hex')}`;
    const cpPw = pw.length >= 12 ? pw : `${pw}-padding-123`;
    const cp = await admin('/users', { method: 'POST', body: JSON.stringify({ username: cpName, password: cpPw, role: 'care_partner', display_name: 'Synthetic care partner', linked_participants: [pid] }) });
    check('setup', 'care-partner account created via admin API', cp.status === 201, cp.status);
    const coordApi = await apiAs(users.coordinator);
    const reid = await coordApi(`/participants/${pid}/reid`, { method: 'PUT', body: JSON.stringify({ identifier: 'SYNTHETIC-MRN-000001' }) });
    check('setup', 're-identification key stored (synthetic)', reid.status === 200, reid.status);

    // ---------------------------------------------------------------- headers
    const head = await fetch(`${base}/portal/`);
    check('setup', '/portal/ served with CSP + COOP/CORP', head.ok && head.headers.get('content-security-policy')?.includes("script-src 'self'") && head.headers.get('cross-origin-opener-policy') === 'same-origin' && head.headers.get('cross-origin-resource-policy') === 'same-origin',
      `coep=${head.headers.get('cross-origin-embedder-policy')}`);

    browser = await chromium.launch();
    const browserVersion = browser.version();

    const newPage = async (width, colorScheme = 'light') => {
      const ctx = await browser.newContext({ viewport: { width, height: 900 }, colorScheme, reducedMotion: 'reduce' });
      const page = await ctx.newPage();
      page.__errors = [];
      page.on('pageerror', (e) => page.__errors.push(e.message));
      // 401/403 resource errors are expected where the test probes forbidden endpoints or a wrong
      // re-authentication password; anything else logged as an error fails the run.
      page.on('console', (m) => { if (m.type() === 'error' && !/status of 40[13]/.test(m.text())) page.__errors.push(m.text()); });
      return page;
    };
    const login = async (page, username, password = pw) => {
      await page.goto(`${base}/portal/`);
      await page.getByLabel('Username').fill(username);
      await page.getByLabel('Password').fill(password);
      await page.getByRole('button', { name: 'Sign in' }).click();
      await page.waitForFunction(() => { const h = document.querySelector('main h1'); return h && h.textContent !== 'Sign in'; }, null, { timeout: 15000 });
    };
    const settle = async (page) => {
      await page.waitForFunction(() => !document.querySelector('[aria-busy="true"]') && !document.querySelector('main .loading'), null, { timeout: 20000 });
      await sleep(250);
    };
    const go = async (page, route) => { await page.evaluate((r) => { location.hash = r; }, `#/${route}`); await settle(page); };
    const runAxe = async (page, role, name) => {
      await page.evaluate(axeSrc);
      const res = await page.evaluate(async () => {
        // eslint-disable-next-line no-undef
        const r = await axe.run(document, { runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa', 'best-practice'] }, resultTypes: ['violations'] });
        return r.violations.map((v) => ({ id: v.id, impact: v.impact, help: v.help, nodes: v.nodes.length, targets: v.nodes.slice(0, 5).map((n) => n.target.join(' ')) }));
      });
      const count = (imp) => res.filter((v) => v.impact === imp).reduce((a, v) => a + v.nodes, 0);
      const vp = page.viewportSize();
      const scheme = await page.evaluate(() => (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'));
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
      const entry = { role, page: name, url: page.url().replace(base, ''), viewport: `${vp.width}x${vp.height}`, color_scheme: scheme,
        violations: { critical: count('critical'), serious: count('serious'), moderate: count('moderate'), minor: count('minor') },
        horizontal_overflow_px: overflow, details: res };
      pages.push(entry);
      const bad = entry.violations.critical + entry.violations.serious;
      check(role, `axe: no serious/critical violations on ${name} (${scheme}, ${vp.width}px)`, bad === 0, res.filter((v) => ['serious', 'critical'].includes(v.impact)).map((v) => `${v.id}:${v.targets[0]}`).join('; '));
      return entry;
    };
    const noScroll360 = async (page, role, name) => {
      const before = page.viewportSize();
      await page.setViewportSize({ width: 360, height: 800 });
      await sleep(400);
      const over = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
      check(role, `no horizontal scroll at 360px: ${name}`, over <= 0, `overflow ${over}px`);
      await page.setViewportSize(before);
      await sleep(250);
    };
    const navLabels = (page) => page.$$eval('#primary-nav a', (as) => as.map((a) => a.textContent.trim()));
    const forbidden = async (page, role, route, label) => {
      await go(page, route);
      const txt = await page.textContent('main h1');
      check(role, `forbidden view "${label}" shows not-available message`, txt.includes('Not available'), txt);
    };
    const banner = async (page, role) => check(role, 'DEMO banner visible', await page.isVisible('#demo-banner') && (await page.textContent('#demo-banner')).includes('DEMO — synthetic data, not patients'));

    // ================================================================ sponsor analyst
    {
      const role = 'sponsor_analyst';
      const page = await newPage(1280);
      await login(page, users.sponsor_analyst);
      await settle(page);
      await banner(page, role);
      check(role, 'lands on Study dashboard', (await page.textContent('main h1')) === 'Study dashboard');
      const nav = await navLabels(page);
      check(role, 'nav shows dashboard, queries, reports & exports only', nav.join('|') === 'Study dashboard|Data queries|Reports & exports', nav.join('|'));
      const nCharts = await page.locator('main figure.chart svg').count();
      check(role, 'dashboard renders >= 8 SVG charts', nCharts >= 8, nCharts);
      for (const sec of ['Study overview', 'Assessment completeness by visit', 'Functional performance over visits', 'Device-modality comparison', 'Task-level analysis', 'Home-use summary', 'Care-partner burden and patient-reported scores', 'Missing-data analysis', 'Protocol deviations', 'Data quality']) {
        check(role, `section "${sec}" present`, await page.getByRole('heading', { name: sec, level: 2 }).count() === 1);
      }
      check(role, 'site list shows DEMO-01', (await page.textContent('#sec-overview')).includes('DEMO-01'));
      check(role, 'completeness table lists visits', await page.locator('#sec-completeness tbody tr').first().isVisible());
      const firstChart = page.locator('#sec-trends figure.chart').first();
      await firstChart.locator('svg').hover();
      await sleep(150);
      check(role, 'hover shows chart tooltip', await firstChart.locator('.chart__tip').isVisible());
      await page.mouse.move(0, 0);
      await firstChart.locator('svg').focus();
      await page.keyboard.press('ArrowRight');
      check(role, 'keyboard focus + arrows show tooltip', await firstChart.locator('.chart__tip').isVisible(), await firstChart.locator('.chart__tip').textContent());
      await firstChart.getByRole('button', { name: 'Show as table' }).click();
      check(role, '"Show as table" reveals the data table', await firstChart.locator('table').isVisible());
      check(role, 'trend table includes 95% CI', (await firstChart.locator('table').textContent()).includes(' to '));
      await firstChart.getByRole('button', { name: 'Hide table' }).click();
      const pidOnPage = await page.evaluate((p) => document.body.innerText.includes(p), pid);
      check(role, 'no participant identifiers on the sponsor dashboard', !pidOnPage);
      await page.screenshot({ path: path.join(SHOTS, 'sponsor-dashboard-1280.png'), fullPage: true });
      await runAxe(page, role, 'dashboard');
      await noScroll360(page, role, 'dashboard');
      // backend enforcement + graceful 403
      const status403 = await page.evaluate(async (sid) => {
        const t = sessionStorage.getItem('nm.portal.token');
        return (await fetch(`/api/studies/${sid}/participants`, { headers: { Authorization: `Bearer ${t}` } })).status;
      }, studyId);
      check(role, 'backend returns 403 for participant list', status403 === 403, status403);
      await forbidden(page, role, 'participants', 'Participants');
      await forbidden(page, role, 'audit', 'Audit trail');
      await go(page, 'queries');
      const heads = await page.$$eval('main thead th', (ths) => ths.map((t) => t.textContent));
      check(role, 'queries table hides participant column for sponsor', heads.length > 0 && !heads.includes('Participant'), heads.join('|'));
      await runAxe(page, role, 'queries');
      await go(page, 'exports');
      check(role, 'only the sponsor package is offered', (await page.locator('#sec-export option').count()) === 1);
      await page.getByRole('button', { name: 'Generate export' }).click();
      await page.waitForSelector('text=Export ready and verified', { timeout: 30000 });
      const rows = await page.locator('table:has(caption:text("Manifest")) tbody tr').count();
      check(role, 'export manifest lists files with SHA-256', rows >= 10, `${rows} files`);
      const allMatch = await page.locator('table:has(caption:text("Manifest")) tbody tr:has-text("match")').count();
      check(role, 'every file hash re-verified in browser', allMatch === rows, `${allMatch}/${rows}`);
      const zipHash = (await page.locator('dd.hash').first().textContent()).trim();
      check(role, 'zip SHA-256 shown', /^[0-9a-f]{64}$/.test(zipHash), zipHash);
      check(role, 'report CLI command shown', (await page.textContent('#sec-reports')).includes('neurometric report demo'));
      await runAxe(page, role, 'exports');
      await noScroll360(page, role, 'exports');
      // dark mode pass on the dashboard
      const dark = await newPage(1280, 'dark');
      await login(dark, users.sponsor_analyst);
      await settle(dark);
      await runAxe(dark, role, 'dashboard');
      await dark.screenshot({ path: path.join(SHOTS, 'sponsor-dashboard-1280-dark.png'), fullPage: false });
      check(role, 'no page errors', page.__errors.length === 0 && dark.__errors.length === 0, [...page.__errors, ...dark.__errors].join('; '));
    }

    // ================================================================ coordinator
    {
      const role = 'coordinator';
      const page = await newPage(1280);
      await login(page, users.coordinator);
      await settle(page);
      await banner(page, role);
      const nav = await navLabels(page);
      check(role, 'nav: participants, visits, queries (no dashboard/exports/admin)', nav.join('|') === 'Participants|Visits due|Data queries', nav.join('|'));
      const ids = await page.$$eval('main tbody th a', (as) => as.map((a) => a.textContent));
      check(role, 'participant completeness lists pseudonymous IDs', ids.length === partUsers.length && ids.every((x) => /^NM-[A-Z0-9]+$/.test(x)), ids.join(','));
      check(role, 'enrollment state tiles shown', (await page.textContent('#sec-enrollment')).includes('Active'));
      await page.screenshot({ path: path.join(SHOTS, 'coordinator-participants-1280.png'), fullPage: true });
      await runAxe(page, role, 'participants');
      await noScroll360(page, role, 'participants');
      await go(page, 'visits');
      check(role, 'visits due view renders', await page.getByText('Overdue', { exact: true }).first().isVisible());
      await runAxe(page, role, 'visits');
      await go(page, `participants/${pid}`);
      check(role, 'participant detail shows sessions', (await page.locator('#sec-sessions tbody tr').count()) > 0);
      const before = await page.evaluate(() => document.body.innerText.includes('SYNTHETIC-MRN-000001'));
      check(role, 're-identification hidden by default', !before);
      await page.getByRole('button', { name: 'Reveal re-identification…' }).click();
      await page.getByLabel('Reason for re-identification').fill('E2E test of reveal flow (synthetic)');
      await page.getByRole('button', { name: 'Reveal', exact: true }).click();
      await page.waitForSelector('text=SYNTHETIC-MRN-000001');
      check(role, 'explicit reveal flow shows identifier', true);
      await page.getByRole('button', { name: 'Hide now' }).click();
      check(role, 'identifier hidden again', !(await page.evaluate(() => document.body.innerText.includes('SYNTHETIC-MRN-000001'))));
      await runAxe(page, role, 'participant detail');
      await go(page, 'queries');
      check(role, 'queries list shown', (await page.locator('main tbody tr').count()) >= 1);
      check(role, 'deviations list shown', (await page.textContent('#sec-deviations')).includes('Procedure'));
      await runAxe(page, role, 'queries');
      await forbidden(page, role, 'dashboard', 'Study dashboard');
      await forbidden(page, role, 'users', 'Users');
      check(role, 'no page errors', page.__errors.length === 0, page.__errors.join('; '));
    }

    // ================================================================ investigator
    {
      const role = 'investigator';
      const page = await newPage(1280);
      await login(page, users.investigator);
      await settle(page);
      await banner(page, role);
      const nav = await navLabels(page);
      check(role, 'nav: dashboard + coordinator views + review, exports, audit, integrity', nav.join('|') === 'Study dashboard|Participants|Visits due|Data queries|Review & sign-off|Reports & exports|Audit trail|System integrity', nav.join('|'));
      check(role, 'dashboard renders (investigator audience)', (await page.textContent('#sec-overview')).includes('Investigator view'));
      await go(page, 'review');
      const row = page.locator('main tbody tr').first();
      await row.getByRole('button', { name: /Sign/ }).click();
      await page.getByLabel('Password (re-authentication)').fill('wrong-password-123');
      await page.getByRole('button', { name: 'Sign', exact: true }).click();
      await page.waitForSelector('text=Re-authentication failed');
      check(role, 'wrong password: nothing signed, still signed in', (await page.textContent('main h1')) === 'Review & sign-off');
      await row.getByRole('button', { name: /Sign/ }).click();
      await page.getByLabel('Password (re-authentication)').fill(pw);
      await page.getByRole('button', { name: 'Sign', exact: true }).click();
      await page.waitForSelector('text=Signed: Approved');
      check(role, 'casebook signed with re-authentication', true);
      await page.getByRole('button', { name: 'Verify signature' }).click();
      await page.waitForSelector('text=Valid — record unchanged since signing');
      check(role, 'signature verifies', true);
      await page.screenshot({ path: path.join(SHOTS, 'investigator-review-1280.png'), fullPage: false });
      await runAxe(page, role, 'review');
      await go(page, 'exports');
      check(role, 'sponsor and full packages offered', (await page.locator('#sec-export option').count()) === 2);
      await go(page, 'system');
      await page.getByRole('button', { name: 'Run integrity check' }).click();
      await page.waitForSelector('text=All integrity checks passed');
      check(role, 'integrity check passes', true);
      check(role, 'backup controls hidden (no backup.run)', (await page.getByRole('button', { name: 'Run backup now' }).count()) === 0);
      await runAxe(page, role, 'system');
      await forbidden(page, role, 'users', 'Users');
      check(role, 'no page errors', page.__errors.length === 0, page.__errors.join('; '));
    }

    // ================================================================ admin
    {
      const role = 'admin';
      const page = await newPage(1280);
      await login(page, users.admin);
      await settle(page);
      await banner(page, role);
      const nav = await navLabels(page);
      check(role, 'nav: users, audit, integrity only', nav.join('|') === 'Users|Audit trail|System integrity', nav.join('|'));
      check(role, 'users table lists accounts', (await page.locator('main tbody tr').count()) >= 8);
      await runAxe(page, role, 'users');
      await go(page, 'audit');
      await page.getByRole('button', { name: 'Verify hash chain' }).click();
      await page.waitForSelector('text=Audit chain intact');
      check(role, 'audit chain verification result shown', true);
      check(role, 'audit entries listed (values withheld)', (await page.locator('#sec-entries tbody tr').count()) === 50);
      check(role, 'audit view shows no re-identification value', !(await page.evaluate(() => document.body.innerText.includes('SYNTHETIC-MRN'))));
      await page.screenshot({ path: path.join(SHOTS, 'admin-audit-1280.png'), fullPage: false });
      await runAxe(page, role, 'audit');
      await noScroll360(page, role, 'audit');
      await go(page, 'system');
      await page.getByRole('button', { name: 'Run integrity check' }).click();
      await page.waitForSelector('text=All integrity checks passed');
      check(role, 'integrity check passes', true);
      await page.getByRole('button', { name: 'Run backup now' }).click();
      await page.waitForSelector('text=Backup written');
      await page.getByRole('button', { name: 'Verify backup' }).click();
      await page.waitForSelector('text=Backup verified');
      check(role, 'backup + verify succeed', true);
      await runAxe(page, role, 'system');
      await forbidden(page, role, 'dashboard', 'Study dashboard');
      await forbidden(page, role, `participants/${pid}`, 'Participant');
      await forbidden(page, role, 'me', 'My study');
      check(role, 'no page errors', page.__errors.length === 0, page.__errors.join('; '));
    }

    // ================================================================ participant (390px)
    {
      const role = 'participant';
      const page = await newPage(390);
      await login(page, participant.username);
      await settle(page);
      await banner(page, role);
      check(role, 'lands on My study', (await page.textContent('main h1')) === 'My study');
      check(role, 'no staff navigation shown', !(await page.isVisible('#primary-nav')));
      await page.screenshot({ path: path.join(SHOTS, 'participant-390.png'), fullPage: true });
      await runAxe(page, role, 'my study');
      const small = await page.$$eval('.pv button, .pv summary, .pv .choice label, .pv input:not([type=radio]):not([type=checkbox]), .pv select', (els) =>
        els.filter((e) => e.offsetParent !== null).map((e) => ({ t: e.textContent.trim().slice(0, 30), h: e.getBoundingClientRect().height, w: e.getBoundingClientRect().width })).filter((r) => r.h < 44 || r.w < 44));
      check(role, 'all interactive targets >= 44x44px', small.length === 0, JSON.stringify(small));
      // telemetry: pause, resume, review
      await page.getByRole('button', { name: 'Pause sharing' }).click();
      await page.waitForSelector('text=Sharing is PAUSED');
      check(role, 'telemetry pause works', true);
      await page.getByRole('button', { name: 'Resume sharing' }).click();
      await page.waitForSelector('text=Sharing is ON');
      check(role, 'telemetry resume works', true);
      await page.locator('summary', { hasText: 'Review what was sent' }).click();
      await page.locator('summary', { hasText: 'Show exactly what was stored' }).first().click();
      check(role, '"review what was sent" shows stored payload', (await page.locator('#sec-telemetry pre').first().textContent()).includes('active_minutes'));
      // consent scope withdrawal
      await page.getByRole('button', { name: /Stop this.*Future research/ }).click();
      await page.getByRole('button', { name: 'Stop this', exact: true }).click();
      await page.waitForFunction(() => { const c = document.querySelector('#sec-consent'); return c && /Future research — •? ?No/.test(c.innerText.replace(/\s+/g, ' ')); });
      check(role, 'withdrawing one consent scope works', true);
      // keyboard-only questionnaire (NM-SESSION): Tab into each radio group, Space selects
      await page.getByRole('button', { name: /Fill in NeuroMetric post-session check/ }).focus();
      await page.keyboard.press('Enter');
      await page.waitForSelector('#questionnaire-area form');
      await sleep(200);
      check(role, 'questionnaire items rendered from instrument', (await page.locator('#questionnaire-area fieldset.q-item').count()) >= 5);
      await page.screenshot({ path: path.join(SHOTS, 'participant-questionnaire-390.png'), fullPage: false });
      await runAxe(page, role, 'questionnaire form');
      const groups = await page.locator('#questionnaire-area fieldset.q-item').count();
      for (let i = 0; i < groups; i++) { await page.keyboard.press('Tab'); await page.keyboard.press('Space'); }
      await page.keyboard.press('Tab');
      const focused = await page.evaluate(() => document.activeElement.textContent);
      check(role, 'Tab order reaches the send button', focused.includes('Send my answers'), focused);
      await page.keyboard.press('Enter');
      await page.waitForSelector('text=Thank you. Your answers were saved.');
      check(role, 'questionnaire submitted with keyboard only', true);
      const resp = await page.evaluate(async (p) => {
        const t = sessionStorage.getItem('nm.portal.token');
        const r = await (await fetch(`/api/participants/${p}/questionnaires`, { headers: { Authorization: `Bearer ${t}` } })).json();
        return r.filter((x) => x.instrument_id === 'NM-SESSION' && x.respondent_role === 'participant').length;
      }, pid);
      check(role, 'response stored by the backend', resp >= 1, resp);
      await noScroll360(page, role, 'my study');
      await forbidden(page, role, 'dashboard', 'Study dashboard');
      const dark = await newPage(390, 'dark');
      await login(dark, participant.username);
      await settle(dark);
      await runAxe(dark, role, 'my study');
      check(role, 'no page errors', page.__errors.length === 0 && dark.__errors.length === 0, [...page.__errors, ...dark.__errors].join('; '));
    }

    // ================================================================ care partner (390px)
    {
      const role = 'care_partner';
      const page = await newPage(390);
      await login(page, cpName, cpPw);
      await settle(page);
      await banner(page, role);
      check(role, 'care-partner page renders', (await page.textContent('main h1')) === 'The study you help with');
      check(role, 'care-partner questionnaire (NM-CPB) offered', (await page.textContent('#sec-questionnaires')).includes('care-partner'));
      check(role, 'no consent withdrawal controls for care partner', (await page.getByRole('button', { name: /Leave the study|Stop this/ }).count()) === 0);
      await page.locator('summary', { hasText: 'Review what was sent' }).click();
      check(role, 'telemetry review visible', (await page.locator('#sec-telemetry .big-list li').count()) > 0);
      await runAxe(page, role, 'my study');
      await noScroll360(page, role, 'my study');
      await forbidden(page, role, 'exports', 'Reports & exports');
      check(role, 'no page errors', page.__errors.length === 0, page.__errors.join('; '));
    }
  } finally {
    if (browser) await browser.close();
    stop();
    fs.rmSync(tmp, { recursive: true, force: true });
  }

  const sc = pages.reduce((a, p) => a + p.violations.serious + p.violations.critical, 0);
  const failed = checks.filter((c) => !c.pass);
  const out = {
    generated_at: new Date().toISOString(),
    tool: 'tests/portal/e2e.mjs (Playwright Chromium headless + axe-core)',
    axe_version: (/axe v([\d.]+)/.exec(axeSrc) || [])[1] || 'unknown',
    axe_tags: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa', 'best-practice'],
    data: 'SYNTHETIC demo study (seed-demo); no patient data',
    summary: {
      pages_scanned: pages.length,
      serious_critical_total: sc,
      moderate_total: pages.reduce((a, p) => a + p.violations.moderate, 0),
      minor_total: pages.reduce((a, p) => a + p.violations.minor, 0),
      checks_total: checks.length, checks_passed: checks.length - failed.length, checks_failed: failed.length,
    },
    pages, checks,
  };
  fs.mkdirSync(path.dirname(RESULTS), { recursive: true });
  fs.writeFileSync(RESULTS, `${JSON.stringify(out, null, 2)}\n`);
  console.log(`\n${checks.length - failed.length}/${checks.length} checks passed; ${pages.length} pages scanned; serious+critical axe violations: ${sc}`);
  console.log(`results: ${path.relative(REPO, RESULTS)}`);
  process.exit(failed.length || sc ? 1 : 0);
}

main().catch((e) => { console.error(e); process.exit(1); });
