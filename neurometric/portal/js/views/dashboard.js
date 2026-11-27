// Study dashboard (sponsor analyst: sponsor-shareable aggregates; investigator: full site view).
// Data: GET /studies/{sid}/dashboard (aggregates only, small cells suppressed server-side).
import { get } from '../api.js';
import { h, card, table, tile, fmtNum, fmtPct, humanize, load, nextId } from '../ui.js';
import { lineChart, barChart, ci95 } from '../charts.js';
import { labels } from '../labels.js';

export async function sponsorDashboard(root, ctx) {
  const sid = ctx.studyId;
  root.appendChild(h('div', { class: 'page-head' },
    h('h1', null, 'Study dashboard'),
    h('p', null, h('a', { href: '#/exports' }, 'Reports & data exports'))));
  const body = h('div');
  root.appendChild(body);
  await load(body, 'the study dashboard', async () => {
    const [d, battery] = await Promise.all([get(`/studies/${sid}/dashboard`), get('/battery').catch(() => null)]);
    const L = labels(battery);
    return render(d, ctx, L);
  });
}

function render(d, ctx, L) {
  const k = d.min_cell_size;
  const days = ctx.visitDays || {};
  const dayOf = (code) => (days[code] ? days[code].day : null);
  const typeOf = (code) => (days[code] ? days[code].type : (code.startsWith('home') ? 'home' : 'clinic'));
  const order = (a, b) => (dayOf(a) ?? 999) - (dayOf(b) ?? 999) || a.localeCompare(b);
  const withCi = (c) => {
    const ci = c.suppressed ? null : ci95(c.mean, c.sd, c.n);
    return { y: c.suppressed ? null : c.mean, lo: ci ? ci[0] : null, hi: ci ? ci[1] : null, n: c.n, suppressed: c.suppressed };
  };
  const xTick = (x) => `Day ${x}`;
  const xTitle = (x, pts) => `Study day ${x} · ${[...new Set(pts.map((p) => L.visit(p.xl)))].join(' / ')}`;
  const modalities = [...new Set(d.modality_comparison.map((r) => r.modality))].sort();
  const modCls = Object.fromEntries(modalities.map((m, i) => [m, `s${(i % 8) + 1}`]));
  const suppressedCells = [...d.task_trends, ...d.modality_comparison, ...d.questionnaire_scores].filter((c) => c.suppressed).length;

  const sections = [];
  const toc = [];
  const add = (id, title, node) => { toc.push({ id, title }); sections.push(node); };

  // ---------------------------------------------------------------- overview
  const enrollment = Object.entries(d.enrollment).sort();
  const totalExpected = d.completeness_by_visit.reduce((a, c) => a + c.expected, 0);
  const totalDone = d.completeness_by_visit.reduce((a, c) => a + c.completed, 0);
  const sites = (ctx.study && ctx.study.sites) || [];
  add('sec-overview', 'Study overview', card('Study overview', { id: 'sec-overview' },
    h('p', null, h('strong', null, d.study.code), ' — ', d.study.title),
    h('p', { class: 'muted small' }, d.audience === 'sponsor'
      ? `Sponsor view: pseudonymous aggregates of participants whose consent allows sharing with the sponsor. Groups smaller than ${k} are suppressed.`
      : `Investigator view: all participants at your sites. Groups smaller than ${k} are suppressed.`),
    h('div', { class: 'tiles' },
      tile('Participants in view', fmtNum(d.n_participants)),
      ...enrollment.map(([st, n]) => tile(`Enrollment: ${humanize(st)}`, fmtNum(n))),
      tile('Visits completed', `${fmtNum(totalDone)} / ${fmtNum(totalExpected)}`, fmtPct(totalExpected ? totalDone / totalExpected : null)),
      tile('Sites', fmtNum(sites.length))),
    h('h3', null, 'Sites'),
    table([{ key: 'code', label: 'Site code' }, { key: 'name', label: 'Site name' }], sites, { caption: 'Study sites', empty: 'No sites linked to this study.' })));

  // ---------------------------------------------------------------- completeness
  const comp = [...d.completeness_by_visit].sort((a, b) => order(a.visit_code, b.visit_code));
  add('sec-completeness', 'Assessment completeness', card('Assessment completeness by visit', { id: 'sec-completeness' },
    table([
      { key: 'visit_code', label: 'Visit', render: (r) => L.visit(r.visit_code) },
      { key: 'type', label: 'Type', render: (r) => humanize(typeOf(r.visit_code)) },
      { key: 'expected', label: 'Expected', num: true },
      { key: 'completed', label: 'Completed', num: true },
      { key: 'out_of_window', label: 'Out of window', num: true },
      { key: 'missed', label: 'Missed', num: true },
      { key: 'completeness', label: 'Completeness', num: true, render: (r) => fmtPct(r.completeness) },
    ], comp, { caption: 'Visits expected and completed' }),
    barChart({
      title: 'Completeness by visit',
      subtitle: 'Share of expected visits completed (in or out of window)',
      valueLabel: 'Completeness', fmt: fmtPct, domainMax: 1,
      rows: comp.map((c) => ({ label: L.visit(c.visit_code), value: c.completeness, n: c.expected, display: `${fmtPct(c.completeness)} (${c.completed}/${c.expected})`, cls: 's1' })),
    })));

  // ---------------------------------------------------------------- performance trends
  const tasks = [...new Set(d.task_trends.map((t) => t.task_id))].sort();
  const trendCharts = tasks.map((task) => {
    const rows = d.task_trends.filter((t) => t.task_id === task);
    const metric = rows[0].metric;
    const types = [...new Set(rows.map((r) => typeOf(r.visit_code)))].sort();
    const series = types.map((ty) => ({
      name: ty === 'home' ? 'Home sessions' : 'Clinic visits',
      points: rows.filter((r) => typeOf(r.visit_code) === ty && dayOf(r.visit_code) !== null)
        .map((r) => ({ x: dayOf(r.visit_code), xl: r.visit_code, ...withCi(r) })),
    }));
    return lineChart({
      title: `${L.task(task)}: ${L.metric(metric)}`,
      subtitle: `Mean with 95% CI (t-interval) by study day${series.length > 1 ? ', clinic vs home' : ''}`,
      series, xTick, xTitle, minCell: k, xAxisLabel: 'Study day',
    });
  });
  add('sec-trends', 'Functional performance', card('Functional performance over visits', { id: 'sec-trends',
    intro: 'Primary metric per task, all modalities pooled. Shaded bands are 95% confidence intervals for the mean.' },
  h('div', { class: 'grid' }, trendCharts.map((c) => h('div', null, c)))));

  // ---------------------------------------------------------------- modality comparison
  const modCharts = tasks.map((task) => {
    const rows = d.modality_comparison.filter((r) => r.task_id === task);
    if (!rows.length) return null;
    return barChart({
      title: `${L.task(task)}: ${L.metric(rows[0].metric)}`,
      subtitle: 'Mean across all sessions by access modality, with 95% CI',
      valueLabel: L.metric(rows[0].metric), minCell: k,
      rows: rows.map((r) => { const c = withCi(r); return { label: L.modality(r.modality), value: c.y, lo: c.lo, hi: c.hi, n: r.n, suppressed: r.suppressed, cls: modCls[r.modality] }; }),
    });
  }).filter(Boolean);
  add('sec-modality', 'Device-modality comparison', card('Device-modality comparison', { id: 'sec-modality',
    intro: 'Sessions are pooled across visits; participants contribute several sessions, so intervals are optimistic (not clustered by participant).' },
  h('div', { class: 'grid' }, modCharts.map((c) => h('div', null, c)))));

  // ---------------------------------------------------------------- task-level analysis
  const taskRows = tasks.map((task) => {
    const rows = d.task_trends.filter((t) => t.task_id === task && !t.suppressed).sort((a, b) => order(a.visit_code, b.visit_code));
    const clinic = rows.filter((r) => typeOf(r.visit_code) === 'clinic');
    const first = clinic[0] || rows[0];
    const last = clinic[clinic.length - 1] || rows[rows.length - 1];
    const mods = d.modality_comparison.filter((r) => r.task_id === task && !r.suppressed);
    const best = mods.reduce((a, b) => (a && a.mean > b.mean ? a : b), null);
    const worst = mods.reduce((a, b) => (a && a.mean < b.mean ? a : b), null);
    return {
      task: L.task(task), metric: L.metric(rows[0] ? rows[0].metric : ''),
      sessions: d.modality_comparison.filter((r) => r.task_id === task).reduce((a, r) => a + r.n, 0),
      first: first ? `${fmtNum(first.mean)} (${L.visit(first.visit_code)})` : '—',
      last: last ? `${fmtNum(last.mean)} (${L.visit(last.visit_code)})` : '—',
      change: first && last && first !== last ? last.mean - first.mean : null,
      range: best && worst ? `${L.modality(worst.modality)} ${fmtNum(worst.mean)} → ${L.modality(best.modality)} ${fmtNum(best.mean)}` : '—',
    };
  });
  add('sec-tasks', 'Task-level analysis', card('Task-level analysis', { id: 'sec-tasks' },
    table([
      { key: 'task', label: 'Task' }, { key: 'metric', label: 'Primary metric' },
      { key: 'sessions', label: 'Valid sessions', num: true },
      { key: 'first', label: 'First clinic visit' }, { key: 'last', label: 'Last clinic visit' },
      { key: 'change', label: 'Change (mean)', num: true, render: (r) => (r.change === null ? '—' : `${r.change >= 0 ? '+' : '−'}${fmtNum(Math.abs(r.change))}`) },
      { key: 'range', label: 'Modality range (lowest → highest)' },
    ], taskRows, { caption: 'Per-task summary' }),
    h('p', { class: 'muted small' }, 'Tasks without a primary metric in the scorer (for example simulated daily-living tasks) are listed in the export analysis dataset, not here.')));

  // ---------------------------------------------------------------- home use
  const q = (inst, scale) => d.questionnaire_scores.filter((r) => r.instrument_id === inst && r.scale === scale)
    .sort((a, b) => order(a.visit_code, b.visit_code));
  const tel = d.telemetry || {};
  const am = tel.active_minutes_per_day || {};
  const amCi = ci95(am.mean, am.sd, am.n);
  const indep = q('NM-DAU', 'independence');
  const homeA4 = d.task_trends.filter((t) => typeOf(t.visit_code) === 'home');
  add('sec-home', 'Home use', card('Home-use summary', { id: 'sec-home' },
    h('div', { class: 'tiles' },
      tile('Participants sending home telemetry', `${fmtNum(tel.participants_reporting ?? 0)} / ${fmtNum(d.n_participants)}`),
      tile('Active device minutes per day', am.suppressed ? 'suppressed' : fmtNum(am.mean), amCi ? `95% CI ${fmtNum(amCi[0])}–${fmtNum(amCi[1])}, n = ${am.n} participants` : null),
      tile('Home task sessions (valid)', fmtNum(homeA4.reduce((a, r) => a + r.n, 0)))),
    indep.length ? lineChart({
      title: 'Self-rated independence in digital activities (NM-DAU, 0–10)',
      subtitle: 'Mean with 95% CI at each home assessment; higher = more independent',
      series: [{ name: 'Independence', points: indep.map((r) => ({ x: dayOf(r.visit_code) ?? 0, xl: r.visit_code, ...withCi(r) })) }],
      xTick, xTitle, minCell: k, xAxisLabel: 'Study day',
    }) : h('p', { class: 'muted' }, 'No home-use questionnaire scores yet.')));

  // ---------------------------------------------------------------- care-partner burden
  const cpSeries = [
    { name: 'Care-partner help', rows: q('NM-DAU', 'care_partner_minutes') },
    { name: 'Any assistance', rows: q('NM-DAU', 'assisted_minutes') },
  ].filter((sr) => sr.rows.length);
  const cpb = d.questionnaire_scores.filter((r) => r.instrument_id === 'NM-CPB');
  const cpbScales = [...new Set(cpb.map((r) => r.scale))];
  const burden = ['session_burden', 'fatigue', 'satisfaction'].map((sc) => ({ name: humanize(sc), rows: q('NM-SESSION', sc) })).filter((sr) => sr.rows.length);
  add('sec-burden', 'Care-partner burden', card('Care-partner burden and patient-reported scores', { id: 'sec-burden' },
    h('div', { class: 'grid' },
      cpSeries.length ? h('div', null, lineChart({
        title: 'Assistance time per day (NM-DAU, minutes)',
        subtitle: 'Participant-reported minutes of care-partner help and of any assistance; mean with 95% CI',
        series: cpSeries.map((sr) => ({ name: sr.name, points: sr.rows.map((r) => ({ x: dayOf(r.visit_code) ?? 0, xl: r.visit_code, ...withCi(r) })) })),
        xTick, xTitle, minCell: k, xAxisLabel: 'Study day',
      })) : null,
      ...cpbScales.map((sc) => h('div', null, lineChart({
        title: `Care-partner strain (NM-CPB): ${humanize(sc)}`,
        subtitle: 'Care-partner-reported (ObsRO); mean with 95% CI',
        series: [{ name: humanize(sc), points: cpb.filter((r) => r.scale === sc).map((r) => ({ x: dayOf(r.visit_code) ?? 0, xl: r.visit_code, ...withCi(r) })) }],
        xTick, xTitle, minCell: k, xAxisLabel: 'Study day',
      }))),
      burden.length ? h('div', null, lineChart({
        title: 'Post-session check (NM-SESSION, 0–10)',
        subtitle: 'Participant-reported; burden and fatigue: higher = worse; satisfaction: higher = better',
        series: burden.map((sr) => ({ name: sr.name, points: sr.rows.map((r) => ({ x: dayOf(r.visit_code) ?? 0, xl: r.visit_code, ...withCi(r) })) })),
        xTick, xTitle, minCell: k, xAxisLabel: 'Study day',
      })) : null),
    cpbScales.length ? null : h('p', { class: 'muted small' }, 'No care-partner (NM-CPB) responses are in this view yet; burden is shown from participant-reported assistance minutes.'),
    h('details', null, h('summary', null, 'All questionnaire scale scores'),
      table([
        { key: 'instrument_id', label: 'Instrument' }, { key: 'scale', label: 'Scale', render: (r) => humanize(r.scale) },
        { key: 'visit_code', label: 'Visit', render: (r) => L.visit(r.visit_code) },
        { key: 'n', label: 'n', num: true },
        { key: 'mean', label: 'Mean', num: true, render: (r) => (r.suppressed ? 'suppressed' : fmtNum(r.mean)) },
        { key: 'ci', label: '95% CI', render: (r) => { const c = ci95(r.mean, r.sd, r.n); return c && !r.suppressed ? `${fmtNum(c[0])} to ${fmtNum(c[1])}` : '—'; } },
      ], [...d.questionnaire_scores].sort((a, b) => a.instrument_id.localeCompare(b.instrument_id) || a.scale.localeCompare(b.scale) || order(a.visit_code, b.visit_code)), { caption: 'Questionnaire scale scores by visit' }))));

  // ---------------------------------------------------------------- missing data
  const nByVisit = {};
  for (const t of d.task_trends) { (nByVisit[t.task_id] ||= {})[t.visit_code] = t.n; }
  const visitCodes = [...new Set(d.task_trends.map((t) => t.visit_code))].sort(order);
  add('sec-missing', 'Missing data', card('Missing-data analysis', { id: 'sec-missing' },
    table([
      { key: 'visit_code', label: 'Visit', render: (r) => L.visit(r.visit_code) },
      { key: 'expected', label: 'Expected', num: true },
      { key: 'completed', label: 'Completed', num: true },
      { key: 'missed', label: 'Missed', num: true },
      { key: 'open', label: 'Not yet done', num: true, render: (r) => fmtNum(Math.max(0, r.expected - r.completed - r.missed)) },
    ], comp, { caption: 'Visit-level missingness' }),
    h('h3', null, 'Valid task sessions per visit'),
    table([{ key: 'task', label: 'Task' }, ...visitCodes.map((vc) => ({ key: vc, label: L.visit(vc), num: true }))],
      Object.entries(nByVisit).map(([task, m]) => ({ task: L.task(task), ...Object.fromEntries(visitCodes.map((vc) => [vc, m[vc] ?? 0])) })),
      { caption: 'Number of participants with a valid scored session (attrition shows as falling counts)' }),
    h('h3', null, 'Recorded reasons for missing data'),
    table([{ key: 'item_type', label: 'Item type', render: (r) => humanize(r.item_type) }, { key: 'reason_code', label: 'Reason', render: (r) => humanize(r.reason_code) }, { key: 'count', label: 'Count', num: true }],
      d.missing_data, { caption: 'Missing-data reasons', empty: 'No missing-data reasons have been recorded.' })));

  // ---------------------------------------------------------------- deviations
  add('sec-deviations', 'Protocol deviations', card('Protocol deviations', { id: 'sec-deviations' },
    table([
      { key: 'category', label: 'Category', render: (r) => humanize(r.category) },
      { key: 'severity', label: 'Severity', render: (r) => h('span', { class: `status status--${r.severity === 'major' ? 'bad' : 'warn'}` }, humanize(r.severity)) },
      { key: 'status', label: 'Status', render: (r) => humanize(r.status) },
      { key: 'count', label: 'Count', num: true },
    ], d.deviations, { caption: 'Deviations by category, severity and status', empty: 'No protocol deviations reported.' }),
    d.audience === 'sponsor' ? h('p', { class: 'muted small' }, 'Deviation descriptions are free text and are not shared with the sponsor.') : null));

  // ---------------------------------------------------------------- data quality
  const qs = d.queries || {};
  const oow = comp.reduce((a, c) => a + c.out_of_window, 0);
  const openDev = d.deviations.filter((r) => r.status === 'open').reduce((a, r) => a + r.count, 0);
  add('sec-quality', 'Data quality', card('Data quality', { id: 'sec-quality' },
    h('div', { class: 'tiles' },
      tile('Open data queries', fmtNum((qs.open || 0) + (qs.reopened || 0))),
      tile('Answered, awaiting close', fmtNum(qs.answered || 0)),
      tile('Closed queries', fmtNum(qs.closed || 0)),
      tile('Out-of-window visits', fmtNum(oow)),
      tile('Open deviations', fmtNum(openDev)),
      tile('Suppressed cells', fmtNum(suppressedCells), `groups with n < ${k}`)),
    h('p', { class: 'small muted' }, 'Only sessions with status “valid” enter these aggregates. Full per-record quality flags (stream gaps, hash checks) are in the export package and the investigator integrity check.'),
    h('p', null, h('a', { href: '#/queries' }, 'Review data queries'))));

  const tocId = nextId('toc');
  return h('div', null,
    h('nav', { class: 'toc', 'aria-labelledby': tocId },
      h('h2', { id: tocId, class: 'visually-hidden' }, 'On this page'),
      h('ul', null, toc.map((t) => h('li', null, h('a', { href: `#${t.id}` }, t.title))))),
    ...sections);
}

