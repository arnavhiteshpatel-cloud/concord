// NeuroMetric sponsor evidence portal: boot, sign-in, role-aware navigation and routing.
// The backend enforces every permission; this UI additionally hides what the signed-in role
// may not use (least privilege) and handles 401/403 gracefully.
import { get, post, setToken, hasToken, onUnauthorized, explain } from './api.js';
import { h, clear, announce, nextId } from './ui.js';
import { sponsorDashboard } from './views/dashboard.js';
import { exportsView } from './views/exports.js';
import { participantsView, participantDetailView, visitsView, queriesView, reviewView } from './views/staff.js';
import { usersView, auditView, systemView } from './views/admin.js';
import { myStudyView } from './views/participant.js';

const STAFF = new Set(['coordinator', 'investigator', 'sponsor_analyst', 'admin']);
const SELF = new Set(['participant', 'care_partner']);
const ROLE_LABEL = {
  sponsor_analyst: 'Sponsor analyst', coordinator: 'Study coordinator', investigator: 'Clinical investigator',
  admin: 'System administrator', participant: 'Participant', care_partner: 'Care partner',
};

// Each route: allow(ctx) decides visibility (mirrors the backend permission matrix).
const ROUTES = [
  { path: 'dashboard', label: 'Study dashboard', allow: (c) => c.can('dashboard.read'), view: sponsorDashboard },
  { path: 'participants', label: 'Participants', allow: (c) => STAFF.has(c.role) && c.can('participant.read'), view: participantsView },
  { path: 'visits', label: 'Visits due', allow: (c) => c.can('visit.manage'), view: visitsView },
  { path: 'queries', label: 'Data queries', allow: (c) => ['coordinator', 'investigator', 'sponsor_analyst'].includes(c.role), view: queriesView },
  { path: 'review', label: 'Review & sign-off', allow: (c) => c.can('signature.approve'), view: reviewView },
  { path: 'exports', label: 'Reports & exports', allow: (c) => c.can('export.sponsor') || c.can('export.full'), view: exportsView },
  { path: 'users', label: 'Users', allow: (c) => c.can('user.manage'), view: usersView },
  { path: 'audit', label: 'Audit trail', allow: (c) => c.can('audit.read'), view: auditView },
  { path: 'system', label: 'System integrity', allow: (c) => c.can('integrity.check') || c.can('backup.run'), view: systemView },
  { path: 'me', label: 'My study', allow: (c) => SELF.has(c.role), view: myStudyView },
];
const DETAIL = { prefix: 'participants/', allow: (c) => STAFF.has(c.role) && c.can('participant.read'), view: participantDetailView };

const main = document.getElementById('main');
const nav = document.getElementById('primary-nav');
const userArea = document.getElementById('user-area');
const banner = document.getElementById('demo-banner');

let ctx = null;

function storage(k, v) {
  try {
    if (v === undefined) return sessionStorage.getItem(k);
    if (v === null) sessionStorage.removeItem(k); else sessionStorage.setItem(k, v);
  } catch { /* storage unavailable */ }
  return null;
}

// ------------------------------------------------------------------ sign-in
function loginView(message) {
  ctx = null;
  banner.hidden = true;
  nav.hidden = true;
  clear(nav);
  clear(userArea);
  document.title = 'Sign in — NeuroMetric evidence portal';
  const err = h('div', { 'aria-live': 'assertive' });
  if (message) err.appendChild(h('p', { class: 'notice notice--warn' }, message));
  const uid = nextId('u'), pid = nextId('p');
  const user = h('input', { id: uid, name: 'username', type: 'text', autocomplete: 'username', required: true, autocapitalize: 'none', spellcheck: 'false' });
  const pass = h('input', { id: pid, name: 'password', type: 'password', autocomplete: 'current-password', required: true });
  const submit = h('button', { type: 'submit' }, 'Sign in');
  const form = h('form', { novalidate: true },
    h('div', { class: 'field' }, h('label', { for: uid }, 'Username'), user),
    h('div', { class: 'field' }, h('label', { for: pid }, 'Password'), pass),
    err,
    h('div', { class: 'actions' }, submit));
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    clear(err);
    if (!user.value.trim() || !pass.value) {
      err.appendChild(h('p', { class: 'notice notice--bad' }, 'Enter your username and password.'));
      (user.value.trim() ? pass : user).focus();
      return;
    }
    submit.setAttribute('aria-disabled', 'true');
    submit.textContent = 'Signing in…';
    try {
      const out = await post('/auth/login', { username: user.value.trim(), password: pass.value });
      setToken(out.token);
      pass.value = '';
      await boot();
    } catch (ex) {
      submit.removeAttribute('aria-disabled');
      submit.textContent = 'Sign in';
      const msg = ex.status === 401 ? 'Username or password not recognised.' : explain(ex, 'sign-in');
      err.appendChild(h('p', { class: 'notice notice--bad' }, msg));
      pass.focus();
    }
  });
  clear(main).appendChild(h('div', { class: 'login' },
    h('h1', { tabindex: '-1' }, 'Sign in'),
    h('p', { class: 'muted' }, 'Use the account your study team gave you. What you can see depends on your role.'),
    h('div', { class: 'card' }, form)));
  user.focus();
}

async function logout() {
  try { await post('/auth/logout'); } catch { /* ignore */ }
  setToken(null);
  storage('nm.portal.study', null);
  location.hash = '';
  loginView('You have signed out.');
  announce('Signed out.');
}

onUnauthorized(() => {
  setToken(null);
  loginView('Your session has ended. Please sign in again.');
});

// ------------------------------------------------------------------ boot
async function boot() {
  clear(main).appendChild(h('p', { class: 'loading' }, 'Loading your workspace…'));
  let me, perms, studies;
  try {
    [me, perms] = await Promise.all([get('/auth/me'), get('/permissions')]);
    studies = await get('/studies').catch(() => []);
  } catch (e) {
    if (e.status !== 401) loginView(explain(e, 'your account'));
    return;
  }
  ctx = {
    me, role: me.role, perms, studies,
    can: (p) => !!(perms[p] && perms[p][me.role]),
    study: null, studyId: null, logout,
  };
  const saved = storage('nm.portal.study');
  const chosen = studies.find((s) => s.id === saved) || studies[0] || null;
  await selectStudy(chosen);
  renderChrome();
  if (!location.hash.startsWith('#/')) {
    const first = ROUTES.find((r) => r.allow(ctx));
    location.replace(`#/${first ? first.path : 'none'}`);
  }
  route();
}

async function selectStudy(st) {
  ctx.study = st;
  ctx.studyId = st ? st.id : null;
  ctx.schedules = [];
  if (st) storage('nm.portal.study', st.id);
  if (st && ctx.can('study.read')) {
    try {
      const [full, schedules] = await Promise.all([get(`/studies/${st.id}`), get(`/studies/${st.id}/schedules`)]);
      ctx.study = full;
      ctx.schedules = schedules;
    } catch { /* keep the summary row */ }
  }
  ctx.visitDays = visitDays(ctx.schedules);
  banner.hidden = !(ctx.study && ctx.study.is_demo);
}

/** visit_code -> {day, type} from the study's schedule definitions. */
function visitDays(schedules) {
  const out = {};
  for (const sc of schedules || []) {
    const d = sc.definition || {};
    for (const v of d.visits || []) out[v.code] = { day: v.day, type: v.type || 'clinic' };
    for (const r of d.recurrences || []) {
      for (let k = 1; k <= (r.count || 0); k++) {
        out[`${r.code_prefix}_${String(k).padStart(2, '0')}`] = { day: r.start_day + (k - 1) * r.every_days, type: r.type || 'home' };
      }
    }
  }
  return out;
}

function renderChrome() {
  clear(userArea);
  const name = ctx.me.display_name || ctx.me.username;
  userArea.appendChild(h('span', null, h('span', { class: 'visually-hidden' }, 'Signed in as '), name, ' ', h('span', { class: 'role' }, `(${ROLE_LABEL[ctx.role] || ctx.role})`)));
  if (ctx.studies.length > 1) {
    const id = nextId('study');
    const sel = h('select', { id }, ctx.studies.map((s) => h('option', { value: s.id, selected: ctx.studyId === s.id }, `${s.code} — ${s.title}`)));
    sel.addEventListener('change', async () => {
      await selectStudy(ctx.studies.find((s) => s.id === sel.value));
      announce(`Study changed to ${ctx.study.code}.`);
      route();
    });
    userArea.appendChild(h('span', null, h('label', { for: id, class: 'visually-hidden' }, 'Study'), sel));
  }
  userArea.appendChild(h('button', { type: 'button', class: 'secondary small', onclick: logout }, 'Sign out'));
  clear(nav);
  const items = ROUTES.filter((r) => r.allow(ctx));
  nav.appendChild(h('ul', null, items.map((r) => h('li', null, h('a', { href: `#/${r.path}`, 'data-route': r.path }, r.label)))));
  nav.hidden = items.length <= 1 && SELF.has(ctx.role);
}

function setCurrent(path) {
  for (const a of nav.querySelectorAll('a')) {
    if (a.dataset.route === path) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current');
  }
}

let renderSeq = 0;
async function route() {
  if (!ctx) return;
  const path = location.hash.replace(/^#\//, '');
  const seq = ++renderSeq;
  let def = ROUTES.find((r) => r.path === path);
  let arg = null;
  if (!def && path.startsWith(DETAIL.prefix)) { def = { ...DETAIL, label: 'Participant', path: 'participants' }; arg = decodeURIComponent(path.slice(DETAIL.prefix.length)); }
  clear(main);
  if (!def) {
    setCurrent(null);
    document.title = 'Page not found — NeuroMetric evidence portal';
    main.appendChild(h('h1', { tabindex: '-1' }, 'Page not found'));
    main.appendChild(h('p', null, 'There is no page at this address. Use the navigation above.'));
  } else if (!def.allow(ctx)) {
    setCurrent(null);
    document.title = 'Not available — NeuroMetric evidence portal';
    main.appendChild(h('h1', { tabindex: '-1' }, 'Not available for your role'));
    main.appendChild(h('p', { class: 'notice notice--warn', 'data-testid': 'forbidden' },
      `The page “${def.label}” is not available to the ${ROLE_LABEL[ctx.role] || ctx.role} role. `,
      'Access follows the study’s least-privilege permission matrix.'));
  } else {
    setCurrent(def.path);
    document.title = `${def.label} — NeuroMetric evidence portal`;
    if (!ctx.studyId && def.path !== 'users' && def.path !== 'audit' && def.path !== 'system') {
      main.appendChild(h('h1', { tabindex: '-1' }, def.label));
      main.appendChild(h('p', { class: 'notice' }, 'No study is available to your account yet.'));
    } else {
      try {
        await def.view(main, ctx, arg);
      } catch (e) {
        console.error(e);
        if (seq === renderSeq) main.appendChild(h('p', { class: 'notice notice--bad', role: 'alert' }, explain(e, def.label)));
      }
    }
  }
  if (seq !== renderSeq) return;
  const h1 = main.querySelector('h1');
  if (h1) { h1.setAttribute('tabindex', '-1'); h1.focus({ preventScroll: false }); }
}

window.addEventListener('hashchange', () => { if (location.hash.startsWith('#/')) route(); });

// In-page anchors (skip link, tables of contents) must not trigger the hash router.
document.addEventListener('click', (e) => {
  const a = e.target.closest && e.target.closest('a[href^="#"]');
  if (!a) return;
  const href = a.getAttribute('href');
  if (href.startsWith('#/')) return;
  e.preventDefault();
  const target = document.getElementById(href.slice(1));
  if (!target) return;
  const focusEl = target.matches('section') ? (target.querySelector('h2, h3') || target) : target;
  if (!focusEl.hasAttribute('tabindex')) focusEl.setAttribute('tabindex', '-1');
  focusEl.focus({ preventScroll: true });
  target.scrollIntoView({ block: 'start', behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' });
});

export { ROLE_LABEL };

if (hasToken()) boot(); else loginView();
