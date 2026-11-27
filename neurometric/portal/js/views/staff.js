// Site-staff views (coordinator, investigator) plus the queries page shared with sponsor analysts.
// Participants are shown by pseudonymous study ID only. Re-identification is available solely via
// the explicit, reason-gated, audited reveal flow for roles holding reid.read.
import { get, post, explain } from '../api.js';
import { h, card, table, tile, fmtNum, fmtDate, fmtDateTime, humanize, shortHash, load, clear,
  announce, dialog, busy, notice, meter, status, todayISO, nextId, errorNotice } from '../ui.js';
import { barChart } from '../charts.js';
import { labels } from '../labels.js';

const L = labels(null);
const PRIMARY = { A1: 'movement_time_ms_mean', A2: 'fitts_throughput_bps', A3: 'fitts_throughput_bps', A4: 'achieved_bitrate_bps', A5: 'success_rate', E1: 'wpm_mean', E2: 'achieved_bitrate_bps' };

const settle = async (p) => { try { return { ok: true, value: await p }; } catch (e) { return { ok: false, error: e }; } };

function siteCode(ctx, id) {
  const s = ((ctx.study && ctx.study.sites) || []).find((x) => x.id === id);
  return s ? s.code : id;
}

/** Classify a scheduled visit relative to today. */
function visitTiming(v, today) {
  if (v.status !== 'scheduled') return null;
  if (v.window_end < today) return 'overdue';
  if (v.window_start <= today) return 'due';
  return 'upcoming';
}
const TIMING_LABEL = { overdue: ['bad', 'Overdue'], due: ['warn', 'Due now'], upcoming: ['info', 'Upcoming'] };

async function participantBundle(ctx) {
  const parts = await get(`/studies/${ctx.studyId}/participants`);
  const rows = await Promise.all(parts.map(async (p) => {
    const [visits, asg, consent] = await Promise.all([
      settle(get(`/participants/${p.id}/visits`)),
      settle(get(`/participants/${p.id}/assignments`)),
      settle(get(`/participants/${p.id}/consent`)),
    ]);
    return { p, visits: visits.ok ? visits.value : [], asg: asg.ok ? asg.value : [], consent: consent.ok ? consent.value : null };
  }));
  return rows;
}

// ------------------------------------------------------------------ participant completeness
export async function participantsView(root, ctx) {
  root.appendChild(h('div', { class: 'page-head' }, h('h1', null, 'Participants'),
    h('p', null, 'Pseudonymous study IDs only.')));
  const body = h('div');
  root.appendChild(body);
  await load(body, 'participants', async () => {
    const today = todayISO();
    const rows = (await participantBundle(ctx)).map(({ p, visits, asg, consent }) => {
      const live = visits.filter((v) => v.status !== 'cancelled');
      const done = live.filter((v) => v.status.startsWith('completed')).length;
      const dueSoFar = live.filter((v) => v.window_start <= today).length;
      const active = consent && consent.active;
      return {
        id: p.id, site: siteCode(ctx, p.site_id), modality: L.modality(p.primary_modality), state: p.enrollment_state,
        done, expected: live.length, completeness: dueSoFar ? Math.min(1, done / dueSoFar) : null,
        missed: live.filter((v) => v.status === 'missed').length,
        overdue: live.filter((v) => visitTiming(v, today) === 'overdue').length,
        pendingQ: asg.filter((a) => a.status === 'pending').length,
        consent: active ? 'active' : 'withdrawn',
        sponsor: active ? !!active.scopes.sharing_with_sponsor : false,
      };
    });
    const states = {};
    for (const r of rows) states[r.state] = (states[r.state] || 0) + 1;
    return h('div', null,
      card('Enrollment state', { id: 'sec-enrollment' },
        h('div', { class: 'tiles' }, tile('Participants', fmtNum(rows.length)), ...Object.entries(states).sort().map(([s, n]) => tile(humanize(s), fmtNum(n))))),
      card('Completeness by participant', { id: 'sec-completeness', intro: 'Completeness counts visits whose window has opened. Select a participant for visits, consent, sessions and sign-off.' },
        table([
          { key: 'id', label: 'Participant', render: (r) => h('a', { href: `#/participants/${encodeURIComponent(r.id)}` }, r.id) },
          { key: 'site', label: 'Site' },
          { key: 'modality', label: 'Primary modality' },
          { key: 'state', label: 'Enrollment', render: (r) => humanize(r.state) },
          { key: 'done', label: 'Visits done', num: true, render: (r) => `${r.done} / ${r.expected}` },
          { key: 'completeness', label: 'Completeness (to date)', render: (r) => meter(r.completeness) },
          { key: 'missed', label: 'Missed', num: true },
          { key: 'overdue', label: 'Overdue', num: true, render: (r) => (r.overdue ? status('bad', String(r.overdue)) : '0') },
          { key: 'pendingQ', label: 'Questionnaires pending', num: true },
          { key: 'consent', label: 'Consent', render: (r) => (r.consent === 'active' ? status('ok', 'Active') : status('bad', 'Withdrawn')) },
          { key: 'sponsor', label: 'Shared with sponsor', render: (r) => (r.sponsor ? 'Yes' : 'No') },
        ], rows, { caption: 'Participant completeness' })));
  });
}

// ------------------------------------------------------------------ visits due / overdue
export async function visitsView(root, ctx) {
  root.appendChild(h('div', { class: 'page-head' }, h('h1', null, 'Visits due and overdue')));
  const tools = h('div', { class: 'actions' });
  const body = h('div');
  root.appendChild(tools);
  root.appendChild(body);
  const filterId = nextId('flt');
  const filter = h('select', { id: filterId },
    [['open', 'Overdue and due now'], ['overdue', 'Overdue only'], ['due', 'Due now only'], ['upcoming', 'Upcoming'], ['all', 'All scheduled']].map(([v, l]) => h('option', { value: v }, l)));
  tools.appendChild(h('div', { class: 'field' }, h('label', { for: filterId }, 'Show'), filter));
  let all = [];
  const draw = () => {
    const f = filter.value;
    const rows = all.filter((r) => (f === 'all' ? true : f === 'open' ? r.timing === 'overdue' || r.timing === 'due' : r.timing === f));
    clear(body);
    const count = (t) => all.filter((r) => r.timing === t).length;
    body.appendChild(h('div', { class: 'tiles' }, tile('Overdue', fmtNum(count('overdue'))), tile('Due now', fmtNum(count('due'))), tile('Upcoming', fmtNum(count('upcoming')))));
    body.appendChild(table([
      { key: 'pid', label: 'Participant', render: (r) => h('a', { href: `#/participants/${encodeURIComponent(r.pid)}` }, r.pid) },
      { key: 'visit', label: 'Visit', render: (r) => `${L.visit(r.visit_code)} (${humanize(r.visit_type)})` },
      { key: 'target_date', label: 'Target date', render: (r) => fmtDate(r.target_date) },
      { key: 'window', label: 'Window', render: (r) => `${fmtDate(r.window_start)} – ${fmtDate(r.window_end)}` },
      { key: 'timing', label: 'Status', render: (r) => status(...TIMING_LABEL[r.timing]) },
      { key: 'act', label: 'Action', rowHeader: false, render: (r) => (ctx.can('visit.manage') ? completeButton(ctx, r, reload) : '—') },
    ], rows, { caption: 'Scheduled visits', empty: 'No visits match this filter.' }));
  };
  const reload = async () => {
    const ok = await load(body, 'visits', async () => {
      const today = todayISO();
      all = (await participantBundle(ctx)).flatMap(({ p, visits }) => visits.map((v) => ({ ...v, pid: p.id, timing: visitTiming(v, today) })))
        .filter((v) => v.timing)
        .sort((a, b) => a.window_end.localeCompare(b.window_end));
      return null;
    });
    if (ok) draw();
  };
  filter.addEventListener('change', () => { draw(); announce(`${body.querySelectorAll('tbody tr').length} visits shown.`); });
  if (ctx.can('visit.manage')) {
    const mm = h('button', { type: 'button', class: 'secondary' }, 'Mark overdue visits as missed');
    mm.addEventListener('click', busy(mm, async () => {
      try {
        const r = await post(`/studies/${ctx.studyId}/missed-visits`);
        announce(`${r.marked_missed} visits marked missed.`);
        await reload();
      } catch (e) { announce(explain(e, 'visits'), true); }
    }));
    tools.appendChild(mm);
  }
  await reload();
}

function completeButton(ctx, v, reload) {
  const b = h('button', { type: 'button', class: 'secondary small' }, h('span', null, 'Mark complete'), h('span', { class: 'visually-hidden' }, ` ${v.pid} ${v.visit_code}`));
  b.addEventListener('click', async () => {
    const r = await dialog({ title: `Complete visit ${L.visit(v.visit_code)} for ${v.pid}`, fields: [{ name: 'reason', label: 'Reason / note', value: 'visit completed', required: true }], confirm: 'Mark complete' });
    if (!r) return;
    try { await post(`/visits/${v.id}/complete`, { reason: r.reason }); announce('Visit marked complete.'); await reload(); } catch (e) { announce(explain(e, 'this visit'), true); }
  });
  return b;
}

// ------------------------------------------------------------------ participant detail
export async function participantDetailView(root, ctx, pid) {
  root.appendChild(h('p', null, h('a', { href: '#/participants' }, '← All participants')));
  root.appendChild(h('div', { class: 'page-head' }, h('h1', null, `Participant ${pid}`), h('p', null, 'Pseudonymous study ID')));
  const body = h('div');
  root.appendChild(body);
  await load(body, 'the participant record', async () => {
    const p = await get(`/participants/${encodeURIComponent(pid)}`);
    const base = `/participants/${encodeURIComponent(pid)}`;
    const [visits, consent, hist, sessions, qs, tel, tstate] = await Promise.all([
      settle(get(`${base}/visits`)), settle(get(`${base}/consent`)), settle(get(`${base}/enrollment-history`)),
      settle(get(`${base}/sessions`)), settle(get(`${base}/questionnaires`)), settle(get(`${base}/telemetry/summary`)),
      settle(get(`${base}/telemetry/state`))]);
    const sec = (r, what, fn) => (r.ok ? fn(r.value) : errorNotice(r.error, what));
    const today = todayISO();
    return h('div', null,
      h('div', { class: 'tiles' },
        tile('Enrollment', humanize(p.enrollment_state)), tile('Site', siteCode(ctx, p.site_id)),
        tile('Primary modality', L.modality(p.primary_modality)), tile('Enrolled on', fmtDate(p.enrolled_on)),
        tile('Home telemetry', tstate.ok ? humanize(tstate.value.state) : '—')),
      ctx.can('signature.review') ? signoffCard(ctx, pid) : null,
      card('Visits', { id: 'sec-visits' }, sec(visits, 'visits', (vs) => table([
        { key: 'visit_code', label: 'Visit', render: (r) => L.visit(r.visit_code) },
        { key: 'visit_type', label: 'Type', render: (r) => humanize(r.visit_type) },
        { key: 'target_date', label: 'Target', render: (r) => fmtDate(r.target_date) },
        { key: 'window', label: 'Window', render: (r) => `${fmtDate(r.window_start)} – ${fmtDate(r.window_end)}` },
        { key: 'status', label: 'Status', render: (r) => { const t = visitTiming(r, today); return t ? status(...TIMING_LABEL[t]) : humanize(r.status); } },
        { key: 'completed_at', label: 'Completed', render: (r) => fmtDate(r.completed_at) },
      ], vs, { caption: `Visits for ${pid}` }))),
      card('Enrollment history', { id: 'sec-history' }, sec(hist, 'enrollment history', (hs) => table([
        { key: 'at', label: 'When', render: (r) => fmtDateTime(r.at) },
        { key: 'from_state', label: 'From', render: (r) => humanize(r.from_state) },
        { key: 'to_state', label: 'To', render: (r) => humanize(r.to_state) },
        { key: 'reason', label: 'Reason', render: (r) => r.reason || '—' },
      ], hs, { caption: 'Enrollment transitions' }))),
      card('Consent', { id: 'sec-consent' }, sec(consent, 'consent', (c) => h('div', null,
        c.active ? h('p', null, status('ok', 'Active consent'), ` ${c.active.consent_document_id} ${c.active.consent_version}, given ${fmtDate(c.active.given_at)}`) : h('p', null, status('bad', 'No active consent')),
        c.active ? table([{ key: 'scope', label: 'Scope', render: (r) => humanize(r.scope) }, { key: 'v', label: 'Agreed', render: (r) => (r.v ? 'Yes' : 'No') }],
          Object.entries(c.active.scopes).map(([scope, v]) => ({ scope, v })), { caption: 'Consent scopes' }) : null,
        c.withdrawals && c.withdrawals.length ? table([{ key: 'at', label: 'Withdrawn', render: (r) => fmtDateTime(r.withdrawn_at || r.at || r.created_at) }, { key: 'scopes', label: 'Scopes', render: (r) => (r.scopes || []).map(humanize).join(', ') }, { key: 'action', label: 'Data action', render: (r) => humanize(r.action) }], c.withdrawals, { caption: 'Withdrawals' }) : null))),
      card('Functional task sessions', { id: 'sec-sessions' }, sec(sessions, 'sessions', (ss) => table([
        { key: 'task_id', label: 'Task', render: (r) => L.task(r.task_id) },
        { key: 'visit_id', label: 'Visit', render: (r) => { const v = visits.ok && visits.value.find((x) => x.id === r.visit_id); return v ? L.visit(v.visit_code) : 'Unscheduled'; } },
        { key: 'performed_at', label: 'Performed', render: (r) => fmtDate(r.performed_at) },
        { key: 'modality', label: 'Modality', render: (r) => L.modality(r.modality) },
        { key: 'provenance', label: 'Provenance', render: (r) => humanize(r.provenance) },
        { key: 'status', label: 'Status', render: (r) => (r.status === 'valid' ? status('ok', 'Valid') : status('warn', humanize(r.status))) },
        { key: 'metric', label: 'Primary metric', render: (r) => { const m = PRIMARY[r.task_id]; return m && r.metrics ? `${fmtNum(r.metrics[m])} ${L.metric(m).replace(/^.*\(/, '(')}` : '—'; } },
        { key: 'events_sha256', label: 'Events SHA-256', render: (r) => h('span', { class: 'hash', title: r.events_sha256 }, shortHash(r.events_sha256)) },
      ], ss, { caption: 'Sessions', empty: 'No sessions uploaded.' }))),
      card('Questionnaires', { id: 'sec-questionnaires' }, sec(qs, 'questionnaires', (rs) => table([
        { key: 'instrument_id', label: 'Instrument' },
        { key: 'visit_id', label: 'Visit', render: (r) => { const v = visits.ok && visits.value.find((x) => x.id === r.visit_id); return v ? L.visit(v.visit_code) : 'Unscheduled'; } },
        { key: 'respondent_role', label: 'Entered by', render: (r) => humanize(r.respondent_role) },
        { key: 'completion', label: 'Completion', render: (r) => humanize(r.completion) },
        { key: 'scores', label: 'Scores', render: (r) => Object.entries(r.scores || {}).map(([k, v]) => `${humanize(k)} ${fmtNum(v.score)}`).join('; ') || '—' },
        { key: 'submitted_at', label: 'Submitted', render: (r) => fmtDate(r.submitted_at) },
      ], rs, { caption: 'Questionnaire responses', empty: 'No responses yet.' }))),
      card('Home telemetry summary', { id: 'sec-telemetry', intro: 'Aggregate counts only; NeuroMetric telemetry carries no content, keystrokes or audio.' }, sec(tel, 'telemetry', (t) => h('div', null,
        h('div', { class: 'tiles' }, tile('Batches', fmtNum(t.n_batches)), tile('Active minutes', fmtNum(t.active_minutes)), tile('Interruptions', fmtNum(t.interruptions)), tile('Flagged batches', fmtNum(t.flagged_batches))),
        Object.keys(t.days || {}).length ? barChart({ title: 'Active device minutes per day', subtitle: 'From the participant’s app (aggregate)', valueLabel: 'Active minutes',
          rows: Object.entries(t.days).map(([d, v]) => ({ label: fmtDate(d), value: v, cls: 's1' })) }) : h('p', { class: 'muted' }, 'No telemetry received.')))),
      ctx.can('reid.read') ? reidCard(pid) : null);
  });
}

function reidCard(pid) {
  const out = h('div', { 'aria-live': 'polite' });
  const b = h('button', { type: 'button', class: 'danger' }, 'Reveal re-identification…');
  b.addEventListener('click', async () => {
    const r = await dialog({
      title: `Re-identify ${pid}?`,
      body: ['This shows the identifying key held by your site. Every reveal is recorded in the audit trail with your reason. Only reveal when there is a protocol-defined need (for example a safety contact).'],
      fields: [{ name: 'reason', label: 'Reason for re-identification', type: 'textarea', required: true }],
      confirm: 'Reveal', danger: true,
    });
    if (!r) return;
    clear(out);
    try {
      const res = await post(`/participants/${encodeURIComponent(pid)}/reid/reveal`, { reason: r.reason });
      const val = h('p', { class: 'hash' }, res.identifier);
      const hide = h('button', { type: 'button', class: 'secondary small' }, 'Hide now');
      const box = notice('warn', h('p', null, h('strong', null, 'Identifier (auto-hides in 60 seconds):')), val, hide);
      out.appendChild(box);
      const t = setTimeout(() => { clear(out).appendChild(h('p', { class: 'muted' }, 'Identifier hidden.')); }, 60000);
      hide.addEventListener('click', () => { clearTimeout(t); clear(out).appendChild(h('p', { class: 'muted' }, 'Identifier hidden.')); b.focus(); });
      hide.focus();
    } catch (e) {
      out.appendChild(notice(e.status === 404 ? 'info' : 'bad', e.status === 404 ? 'No re-identification key is stored for this participant.' : explain(e, 're-identification data')));
    }
  });
  return card('Re-identification', { id: 'sec-reid', intro: 'Hidden by default. Never copied into exports, dashboards or reports.' }, h('div', { class: 'actions' }, b), out);
}

// ------------------------------------------------------------------ signatures
function meaningOptions(ctx) {
  const o = [];
  if (ctx.can('signature.approve')) o.push({ value: 'approved', label: 'Approved — casebook reviewed and approved' });
  o.push({ value: 'reviewed', label: 'Reviewed' }, { value: 'verified', label: 'Verified (source data verified)' });
  return o;
}

async function signCasebook(ctx, pid, out) {
  const r = await dialog({
    title: `Sign casebook ${pid}`,
    body: ['Your electronic signature binds your name, the meaning, the time (UTC) and the SHA-256 of the current casebook content. Re-enter your password to sign.'],
    fields: [
      { name: 'meaning', label: 'Meaning of signature', type: 'select', options: meaningOptions(ctx), value: meaningOptions(ctx)[0].value },
      { name: 'password', label: 'Password (re-authentication)', type: 'password', required: true, autocomplete: 'current-password' },
    ],
    confirm: 'Sign',
  });
  if (!r) return null;
  clear(out);
  try {
    const sig = await post('/signatures', { record_table: 'casebook', record_id: pid, meaning: r.meaning, password: r.password });
    out.appendChild(signatureResult(sig));
    announce(`Signed: ${sig.meaning}.`);
    return sig;
  } catch (e) {
    out.appendChild(notice('bad', e.status === 401 ? 'Re-authentication failed: password not accepted. Nothing was signed.' : explain(e, 'signatures')));
    announce('Signature failed.', true);
    return null;
  }
}

function signatureResult(sig) {
  const vout = h('span', { 'aria-live': 'polite' });
  const vb = h('button', { type: 'button', class: 'secondary small' }, 'Verify signature');
  vb.addEventListener('click', busy(vb, async () => {
    clear(vout);
    try {
      const v = await get(`/signatures/${sig.id}/verify`);
      vout.appendChild(v.status === 'valid' ? status('ok', 'Valid — record unchanged since signing') : status('bad', humanize(v.status)));
    } catch (e) { vout.appendChild(status('bad', explain(e, 'signatures'))); }
  }));
  return notice('ok',
    h('p', null, status('ok', `Signed: ${humanize(sig.meaning)}`), ` by ${sig.signer_display_name} (${humanize(sig.signer_role)}) at ${fmtDateTime(sig.signed_at)}`),
    h('p', { class: 'small' }, 'Signature ', h('code', null, sig.id), ' · record SHA-256 ', h('span', { class: 'hash' }, sig.record_hash)),
    h('div', { class: 'actions' }, vb, vout));
}

function signoffCard(ctx, pid) {
  const out = h('div', { 'aria-live': 'polite' });
  const b = h('button', { type: 'button' }, 'Sign casebook…');
  b.addEventListener('click', () => signCasebook(ctx, pid, out));
  return card('Review & sign-off', { id: 'sec-signoff', intro: 'Electronic signature with password re-authentication (technical control; not a Part 11 compliance claim).' },
    h('div', { class: 'actions' }, b), out);
}

export async function reviewView(root, ctx) {
  root.appendChild(h('div', { class: 'page-head' }, h('h1', null, 'Review & sign-off')));
  root.appendChild(h('p', null, 'Sign each participant casebook after review. Signing requires your password again. Verification recomputes the casebook hash and reports whether it changed since signing.'));
  const body = h('div');
  root.appendChild(body);
  await load(body, 'casebooks', async () => {
    const [bundle, sigs] = await Promise.all([participantBundle(ctx), ctx.can('audit.read') ? settle(get('/audit', { table: 'e_signatures', limit: 1000 })) : Promise.resolve({ ok: false })]);
    const last = {};
    if (sigs.ok) {
      for (const e of sigs.value) {
        let row = null;
        try { row = typeof e.new_json === 'string' ? JSON.parse(e.new_json) : e.new_json; } catch { row = null; }
        if (row && row.record_table === 'casebook' && (!last[row.record_id] || last[row.record_id].signed_at < row.signed_at)) last[row.record_id] = row;
      }
    }
    const out = h('div', { 'aria-live': 'polite' });
    const rows = bundle.map(({ p, visits }) => ({
      id: p.id, state: p.enrollment_state,
      done: visits.filter((v) => v.status.startsWith('completed')).length, expected: visits.filter((v) => v.status !== 'cancelled').length,
      sig: last[p.id] || null,
    }));
    return h('div', null,
      out,
      table([
        { key: 'id', label: 'Participant', render: (r) => h('a', { href: `#/participants/${encodeURIComponent(r.id)}` }, r.id) },
        { key: 'state', label: 'Enrollment', render: (r) => humanize(r.state) },
        { key: 'done', label: 'Visits completed', render: (r) => `${r.done} / ${r.expected}` },
        { key: 'sig', label: 'Latest signature', render: (r) => (r.sig ? `${humanize(r.sig.meaning)} by ${r.sig.signer_display_name}, ${fmtDateTime(r.sig.signed_at)}` : status('warn', 'Not signed')) },
        { key: 'act', label: 'Action', rowHeader: false, render: (r) => {
          const b = h('button', { type: 'button', class: 'small' }, h('span', null, 'Sign'), h('span', { class: 'visually-hidden' }, ` casebook ${r.id}`));
          b.addEventListener('click', async () => { const sig = await signCasebook(ctx, r.id, out); if (sig) { const cell = b.closest('tr').children[3]; clear(cell).appendChild(document.createTextNode(`${humanize(sig.meaning)} by ${sig.signer_display_name}, ${fmtDateTime(sig.signed_at)}`)); out.scrollIntoView({ block: 'nearest' }); } });
          return b;
        } },
      ], rows, { caption: 'Participant casebooks' }),
      sigs.ok ? null : h('p', { class: 'muted small' }, 'Signature history is read from the audit trail, which your role cannot read.'));
  });
}

// ------------------------------------------------------------------ data queries (+ deviations)
export async function queriesView(root, ctx) {
  const sponsor = ctx.role === 'sponsor_analyst';
  root.appendChild(h('div', { class: 'page-head' }, h('h1', null, 'Data queries'),
    sponsor ? h('p', null, 'Sponsor view: participant identifiers are not shown.') : null));
  const fid = nextId('qf');
  const filter = h('select', { id: fid }, [['', 'All statuses'], ['open', 'Open'], ['answered', 'Answered'], ['closed', 'Closed']].map(([v, l]) => h('option', { value: v }, l)));
  root.appendChild(h('div', { class: 'field' }, h('label', { for: fid }, 'Status'), filter));
  const body = h('div');
  root.appendChild(body);
  const reload = () => load(body, 'data queries', async () => {
    const qs = await get(`/studies/${ctx.studyId}/queries`, { status: filter.value || undefined });
    const cols = [
      { key: 'question', label: 'Question' },
      { key: 'record', label: 'Record', render: (r) => h('span', null, humanize(r.record_table), ' ', h('code', null, shortHash(r.record_id))) },
    ];
    if (!sponsor) cols.push({ key: 'participant_id', label: 'Participant', render: (r) => (r.participant_id ? h('a', { href: `#/participants/${encodeURIComponent(r.participant_id)}` }, r.participant_id) : '—') });
    cols.push(
      { key: 'status', label: 'Status', render: (r) => status(r.status === 'closed' ? 'ok' : r.status === 'answered' ? 'info' : 'warn', humanize(r.status)) },
      { key: 'raised_at', label: 'Raised', render: (r) => fmtDate(r.raised_at) },
      { key: 'answer', label: 'Answer', render: (r) => r.answer || '—' },
      { key: 'act', label: 'Actions', rowHeader: false, render: (r) => queryActions(ctx, r, reload) },
    );
    return table(cols, qs, { caption: 'Data queries', empty: 'No data queries match.' });
  });
  filter.addEventListener('change', reload);
  await reload();
  if (ctx.can('deviation.manage')) root.appendChild(await deviationsCard(ctx));
}

function queryActions(ctx, q, reload) {
  const box = h('div', { class: 'actions' });
  const act = (label, fn) => { const b = h('button', { type: 'button', class: 'secondary small' }, label, h('span', { class: 'visually-hidden' }, ` query ${q.id}`)); b.addEventListener('click', fn); box.appendChild(b); };
  const run = async (p, body, msg) => { try { await post(p, body); announce(msg); await reload(); } catch (e) { announce(explain(e, 'this query'), true); } };
  if (ctx.can('query.answer') && q.status === 'open') {
    act('Answer', async () => { const r = await dialog({ title: 'Answer query', body: [q.question], fields: [{ name: 'answer', label: 'Answer', type: 'textarea', required: true }], confirm: 'Submit answer' }); if (r) run(`/queries/${q.id}/answer`, { answer: r.answer }, 'Answer submitted.'); });
  }
  if (ctx.can('query.close') && q.status !== 'closed') {
    act('Close', async () => { const r = await dialog({ title: 'Close query', body: [q.question], fields: [{ name: 'reason', label: q.status === 'open' ? 'Reason (required for unanswered queries)' : 'Reason (optional)', required: q.status === 'open' }], confirm: 'Close query' }); if (r) run(`/queries/${q.id}/close`, { reason: r.reason }, 'Query closed.'); });
  }
  if (ctx.can('query.close') && q.status === 'answered') {
    act('Send back', async () => { const r = await dialog({ title: 'Reopen query', body: ['The answer did not resolve the query; it returns to the site as open.'], fields: [{ name: 'reason', label: 'Reason', required: true }], confirm: 'Reopen' }); if (r) run(`/queries/${q.id}/reopen`, { reason: r.reason }, 'Query reopened.'); });
  }
  return box.childNodes.length ? box : '—';
}

async function deviationsCard(ctx) {
  const list = h('div');
  const reload = () => load(list, 'protocol deviations', async () => table([
    { key: 'reported_at', label: 'Reported', render: (r) => fmtDate(r.reported_at) },
    { key: 'participant_id', label: 'Participant', render: (r) => r.participant_id || 'Study-level' },
    { key: 'category', label: 'Category', render: (r) => humanize(r.category) },
    { key: 'severity', label: 'Severity', render: (r) => status(r.severity === 'major' ? 'bad' : 'warn', humanize(r.severity)) },
    { key: 'status', label: 'Status', render: (r) => humanize(r.status) },
    { key: 'description', label: 'Description' },
  ], await get(`/studies/${ctx.studyId}/deviations`), { caption: 'Protocol deviations', empty: 'No deviations reported.' }));
  const b = h('button', { type: 'button', class: 'secondary' }, 'Report a deviation…');
  b.addEventListener('click', async () => {
    const r = await dialog({ title: 'Report a protocol deviation', fields: [
      { name: 'category', label: 'Category', type: 'select', value: 'procedure', options: ['procedure', 'visit_window', 'consent', 'eligibility', 'device', 'data_collection', 'other'].map((v) => ({ value: v, label: humanize(v) })) },
      { name: 'severity', label: 'Severity', type: 'select', value: 'minor', options: [{ value: 'minor', label: 'Minor' }, { value: 'major', label: 'Major' }] },
      { name: 'participant_id', label: 'Participant ID (optional)', hint: 'Leave empty for a study-level deviation' },
      { name: 'description', label: 'Description', type: 'textarea', required: true, hint: 'Do not include names or other identifying details.' },
    ], confirm: 'Report deviation' });
    if (!r) return;
    try {
      await post(`/studies/${ctx.studyId}/deviations`, { category: r.category, severity: r.severity, description: r.description, participant_id: r.participant_id.trim() || null });
      announce('Deviation reported.');
      await reload();
    } catch (e) { announce(explain(e, 'deviations'), true); }
  });
  const c = card('Protocol deviations', { id: 'sec-deviations' }, h('div', { class: 'actions' }, b), list);
  await reload();
  return c;
}

