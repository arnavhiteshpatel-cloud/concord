// System administration: users, audit trail (with hash-chain verification), backup, integrity.
// The audit view shows who/what/when/why and the hash chain, but not old/new field values:
// administrators have no access to participant-level clinical data in this portal.
import { get, post, explain } from '../api.js';
import { h, card, table, tile, fmtNum, fmtDateTime, humanize, shortHash, load, clear, announce, dialog,
  busy, notice, status, nextId } from '../ui.js';

const ROLES = ['participant', 'care_partner', 'coordinator', 'investigator', 'sponsor_analyst', 'admin'];

// ------------------------------------------------------------------ users
export async function usersView(root, ctx) {
  root.appendChild(h('div', { class: 'page-head' }, h('h1', null, 'Users')));
  const body = h('div');
  const out = h('div', { 'aria-live': 'polite' });
  const add = h('button', { type: 'button' }, 'Add user…');
  root.appendChild(h('div', { class: 'actions' }, add));
  root.appendChild(out);
  root.appendChild(body);
  let sites = [];
  const reload = () => load(body, 'users', async () => {
    const [users, s] = await Promise.all([get('/users'), get('/sites').catch(() => [])]);
    sites = s;
    const counts = {};
    for (const u of users) if (u.active) counts[u.role] = (counts[u.role] || 0) + 1;
    return h('div', null,
      h('div', { class: 'tiles' }, ROLES.filter((r) => counts[r]).map((r) => tile(humanize(r), fmtNum(counts[r])))),
      table([
        { key: 'username', label: 'Username' },
        { key: 'display_name', label: 'Display name' },
        { key: 'role', label: 'Role', render: (r) => humanize(r.role) },
        { key: 'participant_id', label: 'Linked participant', render: (r) => r.participant_id || '—' },
        { key: 'active', label: 'Status', render: (r) => (r.active ? status('ok', 'Active') : status('info', 'Deactivated')) },
        { key: 'created_at', label: 'Created', render: (r) => fmtDateTime(r.created_at) },
        { key: 'act', label: 'Action', rowHeader: false, render: (r) => {
          if (!r.active || r.id === ctx.me.user_id) return '—';
          const b = h('button', { type: 'button', class: 'danger small' }, 'Deactivate', h('span', { class: 'visually-hidden' }, ` ${r.username}`));
          b.addEventListener('click', async () => {
            const v = await dialog({ title: `Deactivate ${r.username}?`, body: ['The account can no longer sign in. Its records and audit history are kept.'], fields: [{ name: 'reason', label: 'Reason', required: true }], confirm: 'Deactivate', danger: true });
            if (!v) return;
            try { await post(`/users/${r.id}/deactivate`, { reason: v.reason }); announce(`${r.username} deactivated.`); await reload(); } catch (e) { announce(explain(e, 'users'), true); }
          });
          return b;
        } },
      ], users, { caption: 'Accounts in your organization' }));
  });
  add.addEventListener('click', async () => {
    const v = await dialog({ title: 'Add user', fields: [
      { name: 'username', label: 'Username', required: true },
      { name: 'display_name', label: 'Display name' },
      { name: 'role', label: 'Role', type: 'select', value: 'coordinator', options: ROLES.map((r) => ({ value: r, label: humanize(r) })) },
      { name: 'password', label: 'Initial password', type: 'password', required: true, hint: 'At least 12 characters.', autocomplete: 'new-password' },
      { name: 'site', label: 'Site (site staff)', type: 'select', value: '', options: [{ value: '', label: 'None' }, ...sites.map((s) => ({ value: s.id, label: `${s.code} — ${s.name}` }))] },
      { name: 'participant', label: 'Participant ID (participant: own ID; care partner: linked participant)' },
    ], confirm: 'Create user' });
    if (!v) return;
    const body = { username: v.username.trim(), password: v.password, role: v.role, display_name: v.display_name };
    if (v.site && ['coordinator', 'investigator'].includes(v.role)) body.site_ids = [v.site];
    if (v.participant.trim() && v.role === 'participant') body.participant_id = v.participant.trim();
    if (v.participant.trim() && v.role === 'care_partner') body.linked_participants = [v.participant.trim()];
    clear(out);
    try { const u = await post('/users', body); out.appendChild(notice('ok', `Created ${u.username} (${humanize(u.role)}).`)); await reload(); } catch (e) { out.appendChild(notice('bad', explain(e, 'users'))); }
  });
  await reload();
}

// ------------------------------------------------------------------ audit trail
function changedFields(e) {
  const keys = new Set();
  for (const j of [e.old_json, e.new_json]) {
    if (!j) continue;
    try { Object.keys(typeof j === 'string' ? JSON.parse(j) : j).forEach((k) => keys.add(k)); } catch { /* not json */ }
  }
  return [...keys].sort();
}

function verifyResult(v) {
  return v.ok
    ? notice('ok', h('p', null, status('ok', 'Audit chain intact'), ` — ${fmtNum(v.entries)} entries recomputed; head hash `, h('span', { class: 'hash' }, v.head)))
    : notice('bad', h('p', null, status('bad', 'Audit chain BROKEN'), ` — first bad entry ${v.first_bad_id}.`),
      h('ul', null, (v.problems || []).slice(0, 20).map((p) => h('li', null, typeof p === 'string' ? p : JSON.stringify(p)))));
}

export async function auditView(root, ctx) {
  root.appendChild(h('div', { class: 'page-head' }, h('h1', null, 'Audit trail')));
  const vout = h('div', { 'aria-live': 'polite' });
  const vb = h('button', { type: 'button' }, 'Verify hash chain');
  vb.addEventListener('click', busy(vb, async () => {
    clear(vout);
    try { const v = await get('/audit/verify'); vout.appendChild(verifyResult(v)); announce(v.ok ? 'Audit chain intact.' : 'Audit chain broken.', !v.ok); } catch (e) { vout.appendChild(notice('bad', explain(e, 'audit verification'))); }
  }, { doing: 'Verifying…' }));
  root.appendChild(card('Chain verification', { id: 'sec-verify', intro: 'Recomputes every entry’s SHA-256 and its link to the previous entry.' },
    ctx.can('audit.verify') ? h('div', { class: 'actions' }, vb) : null, vout));

  const tid = nextId('tbl');
  const tableSel = h('select', { id: tid }, ['', 'users', 'participants', 'consent_records', 'visits', 'functional_sessions', 'questionnaire_responses',
    'data_queries', 'protocol_deviations', 'e_signatures', 'telemetry_state', 'studies', 'reidentification_keys']
    .map((t) => h('option', { value: t }, t ? humanize(t) : 'All tables')));
  const list = h('div');
  const pager = h('div', { class: 'actions' });
  let offset = 0;
  const limit = 50;
  const reload = () => load(list, 'audit entries', async () => {
    const rows = await get('/audit', { table: tableSel.value || undefined, limit, offset });
    clear(pager);
    const prev = h('button', { type: 'button', class: 'secondary small', disabled: offset === 0 }, 'Newer');
    const next = h('button', { type: 'button', class: 'secondary small', disabled: rows.length < limit }, 'Older');
    prev.addEventListener('click', () => { offset = Math.max(0, offset - limit); reload().then(() => prev.focus()); });
    next.addEventListener('click', () => { offset += limit; reload().then(() => next.focus()); });
    pager.append(prev, next, h('span', { class: 'muted small' }, `Entries ${offset + 1}–${offset + rows.length}`));
    return table([
      { key: 'id', label: '#', num: true },
      { key: 'at', label: 'When', render: (r) => fmtDateTime(r.at) },
      { key: 'actor_role', label: 'Actor role', render: (r) => humanize(r.actor_role) },
      { key: 'action', label: 'Action', render: (r) => humanize(r.action) },
      { key: 'table_name', label: 'Table', render: (r) => humanize(r.table_name) },
      { key: 'record_id', label: 'Record', render: (r) => h('code', null, r.record_id || '—') },
      { key: 'reason', label: 'Reason', render: (r) => r.reason || '—' },
      { key: 'fields', label: 'Fields changed', render: (r) => changedFields(r).join(', ') || '—' },
      { key: 'entry_hash', label: 'Entry hash', render: (r) => h('span', { class: 'hash', title: r.entry_hash }, shortHash(r.entry_hash)) },
    ], rows, { caption: 'Audit entries (newest first; values withheld in this view)', empty: 'No entries.' });
  });
  tableSel.addEventListener('change', () => { offset = 0; reload(); });
  root.appendChild(card('Entries', { id: 'sec-entries' },
    h('div', { class: 'field' }, h('label', { for: tid }, 'Table'), tableSel), list, pager));
  await reload();
}

// ------------------------------------------------------------------ backup & integrity
export async function systemView(root, ctx) {
  root.appendChild(h('div', { class: 'page-head' }, h('h1', null, 'System integrity')));
  if (ctx.can('integrity.check')) {
    const out = h('div', { 'aria-live': 'polite' });
    const b = h('button', { type: 'button' }, 'Run integrity check');
    b.addEventListener('click', busy(b, async () => {
      clear(out);
      try {
        const r = await get('/admin/integrity');
        const tel = r.telemetry || {};
        out.appendChild(r.ok ? notice('ok', h('p', null, status('ok', 'All integrity checks passed'))) : notice('bad', h('p', null, status('bad', 'Integrity problems found'))));
        out.appendChild(table([{ key: 'check', label: 'Check' }, { key: 'result', label: 'Result', render: (x) => status(x.ok ? 'ok' : 'bad', x.result) }], [
          { check: 'SQLite integrity_check', ok: r.sqlite_integrity === 'ok', result: r.sqlite_integrity },
          { check: 'Foreign-key violations', ok: r.foreign_key_violations === 0, result: String(r.foreign_key_violations) },
          { check: 'Audit hash chain', ok: r.audit_chain.ok, result: r.audit_chain.ok ? `intact (${fmtNum(r.audit_chain.entries)} entries)` : `broken at ${r.audit_chain.first_bad_id}` },
          { check: 'Session event hashes', ok: !(r.sessions_with_bad_hash || []).length, result: (r.sessions_with_bad_hash || []).length ? `${r.sessions_with_bad_hash.length} mismatched` : 'all match' },
          { check: 'Telemetry payload hashes', ok: tel.ok !== false, result: tel.ok === false ? `${(tel.bad_batches || []).length} mismatched` : 'all match' },
          { check: 'Signatures', ok: !Object.values(r.signatures || {}).some((v) => v !== 'valid'), result: Object.keys(r.signatures || {}).length ? `${Object.keys(r.signatures).length} checked` : 'none to check' },
        ], { caption: 'Integrity check results' }));
        announce(r.ok ? 'Integrity check passed.' : 'Integrity check found problems.', !r.ok);
      } catch (e) { out.appendChild(notice('bad', explain(e, 'the integrity check'))); }
    }, { doing: 'Checking…' }));
    root.appendChild(card('Integrity check', { id: 'sec-integrity', intro: 'Database integrity, foreign keys, audit chain, and stored hashes of sessions, telemetry and signatures.' }, h('div', { class: 'actions' }, b), out));
  }
  if (ctx.can('backup.run')) {
    const out = h('div', { 'aria-live': 'polite' });
    const vid = nextId('bk');
    const name = h('input', { id: vid, type: 'text', placeholder: 'neurometric-YYYYMMDDTHHMMSSZ.sqlite', autocomplete: 'off', spellcheck: 'false' });
    const run = h('button', { type: 'button' }, 'Run backup now');
    const verify = h('button', { type: 'button', class: 'secondary' }, 'Verify backup');
    run.addEventListener('click', busy(run, async () => {
      clear(out);
      try {
        const m = await post('/admin/backup');
        name.value = m.file;
        out.appendChild(notice('ok', h('p', null, status('ok', 'Backup written'), ' ', h('code', null, m.file)),
          h('p', { class: 'small' }, `${fmtNum(Math.round(m.size_bytes / 1024))} KB · SHA-256 `, h('span', { class: 'hash' }, m.sha256)),
          h('p', { class: 'small' }, `Audit head at backup `, h('span', { class: 'hash' }, m.audit_head), ` (${fmtNum(m.audit_entries)} entries)`)));
        announce('Backup written.');
      } catch (e) { out.appendChild(notice('bad', explain(e, 'backups'))); }
    }, { doing: 'Backing up…' }));
    verify.addEventListener('click', busy(verify, async () => {
      clear(out);
      if (!name.value.trim()) { out.appendChild(notice('warn', 'Enter a backup file name, or run a backup first.')); name.focus(); return; }
      try {
        const v = await post('/admin/backup/verify', { name: name.value.trim() });
        out.appendChild(v.ok ? notice('ok', h('p', null, status('ok', 'Backup verified')), h('pre', { class: 'json' }, JSON.stringify(v, null, 2)))
          : notice('bad', h('p', null, status('bad', 'Backup verification failed')), h('pre', { class: 'json' }, JSON.stringify(v, null, 2))));
        announce(v.ok ? 'Backup verified.' : 'Backup verification failed.', !v.ok);
      } catch (e) { out.appendChild(notice('bad', explain(e, 'backups'))); }
    }, { doing: 'Verifying…' }));
    root.appendChild(card('Backup', { id: 'sec-backup', intro: 'Online SQLite backup with a manifest (SHA-256, schema version, audit head). Verification re-hashes the file and checks the audit chain inside it.' },
      h('div', { class: 'actions' }, run),
      h('div', { class: 'field' }, h('label', { for: vid }, 'Backup file name'), name),
      h('div', { class: 'actions' }, verify), out));
  }
}
