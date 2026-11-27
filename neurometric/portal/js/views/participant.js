// Participant and care-partner page: large targets (>=56px), one linear focus order (works with
// switch scanning and keyboard only), plain language, no time limits.
import { get, post, put, explain } from '../api.js';
import { h, card, clear, announce, dialog, busy, notice, fmtDate, fmtDateTime, fmtNum, todayISO, nextId, shortHash } from '../ui.js';
import { labels } from '../labels.js';

const L = labels(null);
const SCOPE_TEXT = {
  task_battery: 'Doing the computer tasks (how quickly and accurately you select things).',
  questionnaires: 'Answering questionnaires.',
  home_telemetry: 'Sending daily usage summaries from the app at home. These are counts and minutes only, never what you wrote or looked at.',
  telemetry_app_categories: 'Including which kinds of apps you used (for example “communication”), not which apps.',
  free_text: 'Typing your own comments in free-text boxes.',
  audio_none: 'NeuroMetric never records sound. (Always true.)',
  sharing_with_sponsor: 'Sharing coded data (without your name) with the study sponsor.',
  future_research: 'Reusing coded data in future research.',
};
const SCOPE_TITLE = {
  task_battery: 'Computer tasks', questionnaires: 'Questionnaires', home_telemetry: 'Home usage summaries',
  telemetry_app_categories: 'App categories', free_text: 'Free-text comments', audio_none: 'No audio recording',
  sharing_with_sponsor: 'Sharing with the sponsor', future_research: 'Future research',
};

export async function myStudyView(root, ctx) {
  const pv = h('div', { class: 'pv' });
  root.appendChild(pv);
  const isCP = ctx.role === 'care_partner';
  const pids = isCP ? ctx.me.linked_participants : [ctx.me.participant_id].filter(Boolean);
  pv.appendChild(h('h1', null, isCP ? 'The study you help with' : 'My study'));
  if (!pids.length) {
    pv.appendChild(notice('warn', 'Your account is not linked to a study participant yet. Please contact your study team.'));
    return;
  }
  let pid = pids[0];
  const area = h('div');
  if (pids.length > 1) {
    const id = nextId('who');
    const sel = h('select', { id }, pids.map((p) => h('option', { value: p }, p)));
    sel.addEventListener('change', () => { pid = sel.value; render(); });
    pv.appendChild(h('div', { class: 'field' }, h('label', { for: id }, 'Person you support'), sel));
  }
  pv.appendChild(h('p', null, isCP ? 'Study ID of the person you support: ' : 'Your study ID: ', h('strong', null, pid),
    h('br'), h('span', { class: 'muted small' }, 'This code is used instead of your name.')));
  pv.appendChild(area);

  const render = async () => {
    clear(area).appendChild(h('p', { class: 'loading' }, 'Loading…'));
    const base = `/participants/${encodeURIComponent(pid)}`;
    const safe = (p) => p.then((v) => ({ ok: true, v }), (e) => ({ ok: false, e }));
    const [visits, asg, consent, tel, inst] = await Promise.all([
      safe(get(`${base}/visits`)), safe(get(`${base}/assignments`)), safe(get(`${base}/consent`)),
      safe(get('/telemetry/mine', { participant_id: pid })), safe(get('/instruments'))]);
    clear(area);
    const scopes = consent.ok && consent.v.active ? consent.v.active.scopes : {};
    const ctxP = { ctx, pid, isCP, scopes, instruments: inst.ok ? inst.v : [], rerender: render };
    area.appendChild(upcomingCard(ctxP, visits, asg));
    area.appendChild(questionnaireCard(ctxP, asg));
    area.appendChild(telemetryCard(ctxP, tel));
    area.appendChild(consentCard(ctxP, consent));
  };
  await render();
}

function canAnswer(isCP, respondentType) {
  return isCP ? respondentType === 'ObsRO' : respondentType === 'PRO';
}

// ------------------------------------------------------------------ upcoming
function upcomingCard(P, visits, asg) {
  const today = todayISO();
  const items = [];
  if (asg.ok) {
    for (const a of asg.v.filter((x) => x.status === 'pending').sort((x, y) => x.due_date.localeCompare(y.due_date))) {
      const meta = P.instruments.find((i) => i.id === a.instrument_id);
      const ok = meta && meta.items_loaded && canAnswer(P.isCP, meta.respondent_type);
      const start = ok ? h('button', { type: 'button' }, 'Start', h('span', { class: 'visually-hidden' }, ` ${meta.title}`)) : null;
      if (start) start.addEventListener('click', () => openQuestionnaire(P, a.instrument_id, a.visit_id));
      items.push(h('li', null, h('span', null, h('strong', null, meta ? meta.title : a.instrument_id), h('br'),
        h('span', { class: 'muted' }, `Questionnaire · please complete by ${fmtDate(a.due_date)}`),
        !ok ? h('span', { class: 'muted' }, ' · your study team will fill this in with you') : null), start));
    }
  }
  if (visits.ok) {
    for (const v of visits.v.filter((x) => x.status === 'scheduled' && x.window_end >= today).sort((a, b) => a.window_start.localeCompare(b.window_start))) {
      items.push(h('li', null, h('span', null, h('strong', null, `${L.visit(v.visit_code)} — ${v.visit_type === 'home' ? 'at home' : 'at the clinic'}`), h('br'),
        h('span', { class: 'muted' }, v.window_start <= today ? `Due now — any day until ${fmtDate(v.window_end)}` : `Between ${fmtDate(v.window_start)} and ${fmtDate(v.window_end)}`))));
    }
  }
  return card('Coming up', { id: 'sec-upcoming' },
    !visits.ok && !asg.ok ? notice('warn', explain(visits.e, 'your schedule')) : null,
    items.length ? h('ul', { class: 'big-list' }, items) : h('p', null, 'Nothing is due right now. Thank you!'));
}

// ------------------------------------------------------------------ questionnaires
function questionnaireCard(P) {
  const list = P.instruments.filter((i) => i.items_loaded && canAnswer(P.isCP, i.respondent_type));
  const box = h('div', { id: 'questionnaire-area' });
  const listView = () => {
    clear(box);
    if (!P.scopes.questionnaires) {
      box.appendChild(notice('warn', 'Questionnaires are switched off because consent for questionnaires is not active.'));
      return;
    }
    box.appendChild(h('p', null, P.isCP ? 'Questionnaires for care partners. There is no time limit; you can stop at any time.' : 'You can fill these in whenever you like. There is no time limit.'));
    box.appendChild(h('ul', { class: 'big-list' }, list.map((i) => {
      const b = h('button', { type: 'button', class: 'secondary' }, 'Fill in', h('span', { class: 'visually-hidden' }, ` ${i.title}`));
      b.addEventListener('click', () => openQuestionnaire(P, i.id, null));
      return h('li', null, h('span', null, h('strong', null, i.title), h('br'), h('span', { class: 'muted' }, `${i.n_items} questions`)), b);
    })));
  };
  P.showList = listView;
  P.qbox = box;
  listView();
  return card('Questionnaires', { id: 'sec-questionnaires' }, box);
}

async function openQuestionnaire(P, iid, visitId) {
  const box = P.qbox;
  box.scrollIntoView({ block: 'start' });
  clear(box).appendChild(h('p', { class: 'loading' }, 'Opening questionnaire…'));
  let inst;
  try { inst = await get(`/instruments/${encodeURIComponent(iid)}`); } catch (e) {
    clear(box).appendChild(notice('bad', explain(e, 'this questionnaire')));
    return;
  }
  clear(box);
  const titleId = nextId('qt');
  const errBox = h('div', { tabindex: '-1' });
  const allowFree = !!P.scopes.free_text;
  const items = inst.items.filter((it) => it.type !== 'free_text' || allowFree);
  const getters = {};
  const form = h('form', { novalidate: true, 'aria-labelledby': titleId });
  form.appendChild(h('h3', { id: titleId, tabindex: '-1' }, inst.title));
  form.appendChild(h('p', { class: 'muted' }, `${items.length} questions${inst.recall_period ? ` · thinking about ${inst.recall_period}` : ''}. Questions marked “required” need an answer.`));
  if (!allowFree && inst.items.some((it) => it.type === 'free_text')) form.appendChild(h('p', { class: 'muted small' }, 'Comment boxes are hidden because you did not agree to free-text collection.'));
  form.appendChild(errBox);
  items.forEach((it, idx) => form.appendChild(renderItem(it, idx, items.length, getters)));
  const submit = h('button', { type: 'submit' }, 'Send my answers');
  const back = h('button', { type: 'button', class: 'secondary' }, 'Back without sending');
  back.addEventListener('click', () => { P.showList(); box.querySelector('button')?.focus(); });
  form.appendChild(h('div', { class: 'actions' }, submit, back));
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const answers = {};
    const missing = [];
    for (const it of items) {
      const v = getters[it.id]();
      if (v === undefined || v === null || v === '' || (Array.isArray(v) && !v.length)) { if (it.required) missing.push(it); } else answers[it.id] = v;
    }
    clear(errBox);
    if (missing.length) {
      errBox.appendChild(notice('bad', h('p', null, h('strong', null, `Please answer ${missing.length} more required question${missing.length > 1 ? 's' : ''}:`)),
        h('ul', null, missing.map((m) => h('li', null, h('a', { href: `#q-${m.id}` }, m.label || m.text))))));
      errBox.focus();
      return;
    }
    submit.setAttribute('aria-disabled', 'true');
    submit.textContent = 'Sending…';
    try {
      await post(`/participants/${encodeURIComponent(P.pid)}/questionnaires`, { instrument_id: inst.id, version: inst.version, answers, visit_id: visitId || null });
      clear(box).appendChild(h('div', { class: 'notice notice--ok', tabindex: '-1', id: 'q-done' },
        h('p', null, h('strong', null, 'Thank you. Your answers were saved.')),
        h('p', null, 'You can close this page or fill in another questionnaire.')));
      announce('Thank you. Your answers were saved.');
      const again = h('button', { type: 'button', class: 'secondary' }, 'Back to questionnaires');
      again.addEventListener('click', () => P.rerender());
      box.appendChild(h('div', { class: 'actions' }, again));
      box.querySelector('#q-done').focus();
    } catch (ex) {
      submit.removeAttribute('aria-disabled');
      submit.textContent = 'Send my answers';
      errBox.appendChild(notice('bad', explain(ex, 'questionnaires')));
      errBox.focus();
    }
  });
  box.appendChild(form);
  form.querySelector('h3').focus();
}

function renderItem(it, idx, total, getters) {
  const qid = `q-${it.id}`;
  const text = it.text || it.label;
  const req = it.required ? ' (required)' : ' (optional)';
  const progress = h('span', { class: 'q-progress' }, `Question ${idx + 1} of ${total}. `);
  const group = (inputs, cls = 'choices') => h('fieldset', { class: 'q-item', id: qid, tabindex: '-1' },
    h('legend', null, progress, text, h('span', { class: 'muted' }, req)), h('div', { class: cls }, inputs), anchors(it));
  const radios = (opts, cls) => {
    const name = nextId('r');
    const inputs = opts.map((o) => {
      const id = nextId('o');
      return h('div', { class: 'choice' }, h('input', { type: 'radio', id, name, value: String(o.value), dataset: { idx: String(opts.indexOf(o)) } }), h('label', { for: id }, o.label));
    });
    getters[it.id] = () => { const c = inputs.map((d) => d.querySelector('input')).find((i) => i.checked); return c ? opts[Number(c.dataset.idx)].value : undefined; };
    return group(inputs, cls);
  };
  switch (it.type) {
    case 'likert':
    case 'choice':
      return radios(it.options);
    case 'yes_no':
      return radios([{ value: true, label: 'Yes' }, { value: false, label: 'No' }]);
    case 'multi_choice': {
      const inputs = it.options.map((o) => {
        const id = nextId('o');
        return h('div', { class: 'choice' }, h('input', { type: 'checkbox', id, value: String(o.value) }), h('label', { for: id }, o.label));
      });
      getters[it.id] = () => inputs.map((d) => d.querySelector('input')).map((i, k) => (i.checked ? it.options[k].value : null)).filter((v) => v !== null);
      return group(inputs);
    }
    case 'numeric':
    case 'minutes': {
      const min = it.min ?? 0, max = it.max ?? (it.type === 'minutes' ? 1440 : 10), step = it.step || 1;
      if (it.type === 'numeric' && (max - min) / step <= 10) {
        const opts = [];
        for (let v = min; v <= max; v += step) opts.push({ value: v, label: String(v) });
        return radios(opts, 'choices scale');
      }
      return stepper(it, qid, progress, text, req, min, max, it.type === 'minutes' ? 5 : step, getters);
    }
    case 'free_text': {
      const id = nextId('t');
      const ta = h('textarea', { id, maxlength: it.max_length || 500 });
      getters[it.id] = () => ta.value.trim();
      return h('div', { class: 'q-item', id: qid }, h('label', { for: id }, progress, text, h('span', { class: 'muted' }, req)), ta);
    }
    default: {
      getters[it.id] = () => undefined;
      return h('p', { class: 'muted' }, `(${text} — this question type is not supported here)`);
    }
  }
}

function anchors(it) {
  if (!it.anchors) return null;
  const e = Object.entries(it.anchors).sort((a, b) => Number(a[0]) - Number(b[0]));
  if (e.length < 2) return null;
  return h('p', { class: 'anchors' }, h('span', null, `${e[0][0]} = ${e[0][1]}`), h('span', null, `${e[e.length - 1][0]} = ${e[e.length - 1][1]}`));
}

function stepper(it, qid, progress, text, req, min, max, step, getters) {
  const id = nextId('n');
  const unit = it.type === 'minutes' ? 'minutes' : '';
  const input = h('input', { id, type: 'number', inputmode: 'numeric', min, max, step: it.step || 1, 'aria-describedby': `${id}-u` });
  const clamp = (v) => Math.max(min, Math.min(max, v));
  const minus = h('button', { type: 'button', class: 'secondary' }, `− ${step}`, h('span', { class: 'visually-hidden' }, ` ${unit}`));
  const plus = h('button', { type: 'button', class: 'secondary' }, `+ ${step}`, h('span', { class: 'visually-hidden' }, ` ${unit}`));
  minus.addEventListener('click', () => { input.value = clamp((Number(input.value) || 0) - step); announce(`${input.value} ${unit}`); });
  plus.addEventListener('click', () => { input.value = clamp((Number(input.value) || 0) + step); announce(`${input.value} ${unit}`); });
  getters[it.id] = () => (input.value === '' ? undefined : clamp(Number(input.value)));
  return h('div', { class: 'q-item', id: qid },
    h('label', { for: id }, progress, text, h('span', { class: 'muted' }, req)),
    h('div', { class: 'stepper' }, minus, input, plus),
    h('p', { class: 'muted small', id: `${id}-u` }, `${unit ? 'In minutes. ' : ''}From ${min} to ${max}.`), anchors(it));
}

// ------------------------------------------------------------------ telemetry
function telemetryCard(P, tel) {
  if (!tel.ok) return card('Home usage summaries', { id: 'sec-telemetry' }, notice('warn', explain(tel.e, 'home usage summaries')));
  const st = (tel.v.state && tel.v.state.state) || 'stopped';
  const text = { active: ['ok', 'Sharing is ON'], paused: ['warn', 'Sharing is PAUSED'], stopped: ['bad', 'Sharing is STOPPED'] }[st];
  const out = h('div', { 'aria-live': 'polite' });
  const set = (state, label) => {
    const b = h('button', { type: 'button', class: state === 'stopped' ? 'danger' : state === 'paused' ? 'secondary' : null }, label);
    b.addEventListener('click', busy(b, async () => {
      if (state === 'stopped') {
        const ok = await dialog({ title: 'Stop sending usage summaries?', body: ['The app will stop sending daily summaries. Summaries already sent are kept unless you withdraw consent. You can ask to restart later.'], confirm: 'Stop sending', danger: true });
        if (!ok) return;
      }
      try {
        await put(`/participants/${encodeURIComponent(P.pid)}/telemetry/state`, { state, reason: `${P.isCP ? 'care partner' : 'participant'} chose ${state} in portal` });
        announce(`${label}: done.`);
        await P.rerender();
        document.querySelector('#sec-telemetry h2')?.focus();
      } catch (e) { clear(out).appendChild(notice('bad', explain(e, 'home usage sharing'))); }
    }, { doing: 'Saving…' }));
    return b;
  };
  const buttons = [];
  if (st === 'active') buttons.push(set('paused', 'Pause sharing'), set('stopped', 'Stop sharing'));
  else if (st === 'paused') buttons.push(P.scopes.home_telemetry ? set('active', 'Resume sharing') : null, set('stopped', 'Stop sharing'));
  else if (P.scopes.home_telemetry) buttons.push(set('active', 'Start sharing again'));
  const batches = tel.v.batches || [];
  const recent = batches.slice(-30).reverse();
  const rejected = (tel.v.receipts || []).filter((r) => r.outcome !== 'accepted');
  return card('Home usage summaries', { id: 'sec-telemetry' },
    h('p', { class: 'state' }, h('span', { class: `status status--${text[0]}` }, text[1])),
    h('p', null, 'The NeuroMetric app at home sends one summary per day: minutes of use, number of selections, and breaks. It never sends what you typed, read or said.'),
    h('div', { class: 'actions' }, buttons),
    out,
    h('details', null,
      h('summary', null, `Review what was sent (${batches.length} summaries)`),
      batches.length ? h('ul', { class: 'big-list' }, recent.map((b) => h('li', null, h('div', null,
        h('strong', null, fmtDate(b.period_start)), ' — ',
        `${fmtNum(b.payload.active_minutes)} active minutes, ${fmtNum(b.payload.device_assisted_sessions)} sessions, ${fmtNum(b.payload.interruptions)} breaks`,
        h('br'), h('span', { class: 'muted small' }, `Received ${fmtDateTime(b.received_at)} · fingerprint ${shortHash(b.payload_sha256)}`),
        h('details', null, h('summary', null, 'Show exactly what was stored'), h('pre', { class: 'json' }, JSON.stringify(b.payload, null, 2)))))))
        : h('p', null, 'Nothing has been sent.'),
      batches.length > 30 ? h('p', { class: 'muted small' }, `Showing the latest 30 of ${batches.length}.`) : null,
      rejected.length ? h('p', null, `${rejected.length} summaries were refused by the server and not stored.`) : null));
}

// ------------------------------------------------------------------ consent
function consentCard(P, consent) {
  if (!consent.ok) return card('My consent', { id: 'sec-consent' }, notice('warn', explain(consent.e, 'consent')));
  const active = consent.v.active;
  const canWithdraw = !P.isCP && P.ctx.can('consent.withdraw');
  const out = h('div', { 'aria-live': 'polite' });
  const withdraw = async (scope) => {
    const full = scope === null;
    const r = await dialog({
      title: full ? 'Leave the study?' : `Stop: ${SCOPE_TITLE[scope]}?`,
      body: [full ? 'All data collection stops now, and future visits are cancelled. The study protocol decides whether data already collected is kept or deleted; your study team will explain.' : `${SCOPE_TEXT[scope]} This stops now.`,
        'You do not have to give a reason, but one is recorded. You can change the text below.'],
      fields: [{ name: 'reason', label: 'Reason', value: 'participant choice', required: true }],
      confirm: full ? 'Leave the study' : 'Stop this', danger: true,
    });
    if (!r) return;
    try {
      await post(`/participants/${encodeURIComponent(P.pid)}/consent/withdraw`, full ? { reason: r.reason } : { reason: r.reason, scopes: [scope] });
      announce(full ? 'You have left the study.' : `${SCOPE_TITLE[scope]} stopped.`);
      await P.rerender();
      document.querySelector('#sec-consent h2')?.focus();
    } catch (e) { clear(out).appendChild(notice('bad', explain(e, 'consent'))); }
  };
  if (!active) {
    return card('My consent', { id: 'sec-consent' }, notice('warn', 'There is no active consent. No new data is being collected.'));
  }
  return card(P.isCP ? 'Consent' : 'My consent', { id: 'sec-consent' },
    h('p', null, `Consent form ${active.consent_document_id} (${active.consent_version}), given ${fmtDate(active.given_at)}.`),
    P.isCP ? h('p', { class: 'muted' }, 'Only the participant or the study team can change consent.') : null,
    h('ul', { class: 'big-list' }, Object.entries(active.scopes).map(([k, v]) => {
      const b = canWithdraw && v && k !== 'audio_none' ? h('button', { type: 'button', class: 'secondary small' }, 'Stop this', h('span', { class: 'visually-hidden' }, `: ${SCOPE_TITLE[k] || k}`)) : null;
      if (b) b.addEventListener('click', () => withdraw(k));
      return h('li', null, h('span', null, h('strong', null, SCOPE_TITLE[k] || k), ' — ',
        h('span', { class: `status status--${v ? 'ok' : 'info'}` }, v ? 'Yes' : 'No'), h('br'), h('span', { class: 'muted' }, SCOPE_TEXT[k] || '')), b);
    })),
    out,
    canWithdraw ? h('div', { class: 'actions' }, (() => { const b = h('button', { type: 'button', class: 'danger' }, 'Leave the study…'); b.addEventListener('click', () => withdraw(null)); return b; })()) : null);
}
