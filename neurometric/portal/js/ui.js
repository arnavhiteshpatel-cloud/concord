// DOM helpers. Everything is built with createElement/textContent (never innerHTML with data),
// so server data can never inject markup.
import { ApiError, explain } from './api.js';

export function h(tag, attrs, ...children) {
  const el = document.createElement(tag);
  if (attrs) {
    for (const [k, v] of Object.entries(attrs)) {
      if (v === undefined || v === null || v === false) continue;
      if (k === 'class') el.className = v;
      else if (k === 'text') el.textContent = v;
      else if (k === 'dataset') Object.assign(el.dataset, v);
      else if (k.startsWith('on') && typeof v === 'function') el.addEventListener(k.slice(2), v);
      else if (v === true) el.setAttribute(k, '');
      else el.setAttribute(k, v);
    }
  }
  append(el, children);
  return el;
}

function append(el, children) {
  for (const c of children) {
    if (c === undefined || c === null || c === false) continue;
    if (Array.isArray(c)) append(el, c);
    else if (c instanceof Node) el.appendChild(c);
    else el.appendChild(document.createTextNode(String(c)));
  }
}

const SVGNS = 'http://www.w3.org/2000/svg';
export function s(tag, attrs, ...children) {
  const el = document.createElementNS(SVGNS, tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === undefined || v === null || v === false) continue;
    el.setAttribute(k, v);
  }
  for (const c of children) {
    if (c === undefined || c === null || c === false) continue;
    el.appendChild(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return el;
}

let uid = 0;
export const nextId = (p = 'id') => `${p}-${++uid}`;

export function clear(el) { while (el.firstChild) el.removeChild(el.firstChild); return el; }

export function announce(msg, assertive = false) {
  const el = document.getElementById(assertive ? 'live-assertive' : 'live-polite');
  if (!el) return;
  el.textContent = '';
  setTimeout(() => { el.textContent = msg; }, 30);
}

// ------------------------------------------------------------------ formatting
export function fmtNum(v, digits = 3) {
  if (v === null || v === undefined || Number.isNaN(v)) return '—';
  if (typeof v !== 'number') return String(v);
  if (Number.isInteger(v) && Math.abs(v) < 1e6) return v.toLocaleString('en-US');
  const a = Math.abs(v);
  if (a >= 100) return v.toLocaleString('en-US', { maximumFractionDigits: 0 });
  if (a >= 10) return v.toLocaleString('en-US', { maximumFractionDigits: 1 });
  return v.toLocaleString('en-US', { maximumSignificantDigits: digits });
}
export const fmtPct = (v) => (v === null || v === undefined ? '—' : `${Math.round(v * 100)}%`);
export function fmtDate(iso) {
  if (!iso) return '—';
  const d = new Date(iso.length === 10 ? `${iso}T00:00:00Z` : iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString('en-GB', { year: 'numeric', month: 'short', day: 'numeric', timeZone: 'UTC' });
}
export function fmtDateTime(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return `${d.toLocaleString('en-GB', { year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', timeZone: 'UTC' })} UTC`;
}
export const shortHash = (x) => (x ? `${x.slice(0, 12)}…` : '—');
export const humanize = (x) => (x ? String(x).replace(/_/g, ' ').replace(/^./, (c) => c.toUpperCase()) : '—');
export function todayISO() { return new Date().toISOString().slice(0, 10); }

// ------------------------------------------------------------------ components
export function status(kind, text) { return h('span', { class: `status status--${kind}` }, text); }

export function notice(kind, ...content) {
  return h('div', { class: `notice notice--${kind}`, role: kind === 'bad' ? 'alert' : null }, ...content.map((c) => (typeof c === 'string' ? h('p', null, c) : c)));
}

export function errorNotice(err, what) {
  const forbidden = err instanceof ApiError && err.forbidden;
  return h('div', { class: `notice ${forbidden ? 'notice--warn' : 'notice--bad'}` },
    h('p', null, h('strong', null, forbidden ? 'Not available for your role. ' : 'Could not load. '), explain(err, what)));
}

export function tile(label, value, note) {
  return h('div', { class: 'tile' },
    h('p', { class: 'tile__label' }, label),
    h('p', { class: 'tile__value' }, value),
    note ? h('p', { class: 'tile__note' }, note) : null);
}

/**
 * Accessible data table. columns: [{key, label, num?, render?(row) => Node|string}]
 */
export function table(columns, rows, { caption, empty = 'No records.', label } = {}) {
  if (!rows || rows.length === 0) return h('p', { class: 'muted' }, empty);
  const t = h('table', null,
    caption ? h('caption', null, caption) : null,
    h('thead', null, h('tr', null, columns.map((c) => h('th', { scope: 'col', class: c.num ? 'num' : null }, c.label)))),
    h('tbody', null, rows.map((r) => h('tr', null, columns.map((c, i) => {
      const v = c.render ? c.render(r) : (c.num ? fmtNum(r[c.key]) : (r[c.key] ?? '—'));
      return h(i === 0 && c.rowHeader !== false ? 'th' : 'td', { scope: i === 0 && c.rowHeader !== false ? 'row' : null, class: c.num ? 'num' : null }, v);
    })))));
  return h('div', { class: 'table-wrap', tabindex: '0', role: 'region', 'aria-label': label || caption || 'Data table' }, t);
}

export function card(title, { id, level = 2, intro } = {}, ...children) {
  const hid = id ? `${id}-h` : nextId('h');
  return h('section', { class: 'card section-anchor', id, 'aria-labelledby': hid },
    h(`h${level}`, { id: hid }, title),
    intro ? h('p', { class: 'muted' }, intro) : null,
    ...children);
}

/** Render async content into a container: loading text, then content or an error. */
export async function load(container, what, fn) {
  clear(container);
  container.setAttribute('aria-busy', 'true');
  container.appendChild(h('p', { class: 'loading' }, `Loading ${what}…`));
  try {
    const out = await fn();
    clear(container);
    if (out) append(container, [out]);
    return true;
  } catch (e) {
    clear(container);
    container.appendChild(errorNotice(e, what));
    if (!(e instanceof ApiError)) console.error(e);
    return false;
  } finally {
    container.removeAttribute('aria-busy');
  }
}

export function meter(frac) {
  const pct = frac === null || frac === undefined ? 0 : Math.max(0, Math.min(1, frac));
  return h('span', null,
    h('span', { class: 'meter', 'aria-hidden': 'true' }, h('span', { style: `width:${Math.round(pct * 100)}%` })),
    fmtPct(frac));
}

/**
 * Modal dialog built on <dialog>. fields: [{name, label, type, value, required, hint, options}]
 * Resolves with the field values, or null when cancelled.
 */
export function dialog({ title, body, fields = [], confirm = 'Confirm', danger = false, cancel = 'Cancel' }) {
  return new Promise((resolve) => {
    const titleId = nextId('dlg');
    const err = h('div', { 'aria-live': 'assertive' });
    const inputs = {};
    const form = h('form', { method: 'dialog', novalidate: true },
      h('h2', { id: titleId }, title),
      ...(Array.isArray(body) ? body : [body]).filter(Boolean).map((b) => (typeof b === 'string' ? h('p', null, b) : b)),
      ...fields.map((f) => {
        const id = nextId('f');
        let input;
        if (f.type === 'select') {
          input = h('select', { id, name: f.name }, f.options.map((o) => h('option', { value: o.value, selected: o.value === f.value }, o.label)));
        } else if (f.type === 'textarea') {
          input = h('textarea', { id, name: f.name, required: f.required, 'aria-describedby': f.hint ? `${id}-hint` : null });
          input.value = f.value || '';
        } else {
          input = h('input', { id, name: f.name, type: f.type || 'text', required: f.required, autocomplete: f.autocomplete || 'off', 'aria-describedby': f.hint ? `${id}-hint` : null });
          input.value = f.value || '';
        }
        inputs[f.name] = input;
        return h('div', { class: 'field' }, h('label', { for: id }, f.label, f.hint ? h('span', { class: 'hint', id: `${id}-hint` }, f.hint) : null), input);
      }),
      err,
      h('div', { class: 'actions' },
        h('button', { type: 'submit', value: 'ok', class: danger ? 'danger' : null }, confirm),
        h('button', { type: 'button', class: 'secondary', onclick: () => dlg.close('cancel') }, cancel)));
    const dlg = h('dialog', { 'aria-labelledby': titleId }, form);
    const opener = document.activeElement;
    form.addEventListener('submit', (e) => {
      const missing = fields.filter((f) => f.required && !String(inputs[f.name].value).trim());
      if (missing.length) {
        e.preventDefault();
        clear(err).appendChild(h('p', { class: 'status status--bad' }, `Please fill in: ${missing.map((m) => m.label).join(', ')}`));
        inputs[missing[0].name].focus();
      }
    });
    dlg.addEventListener('close', () => {
      const ok = dlg.returnValue === 'ok';
      const vals = {};
      for (const [k, el] of Object.entries(inputs)) vals[k] = el.value;
      dlg.remove();
      if (opener && opener.isConnected) opener.focus();
      resolve(ok ? vals : null);
    });
    document.body.appendChild(dlg);
    dlg.showModal();
    const first = fields.length ? inputs[fields[0].name] : form.querySelector('button');
    first.focus();
  });
}

/** Wrap a button's async action: disables it, announces outcome in the live region. */
export function busy(button, fn, { doing = 'Working…' } = {}) {
  return async (...args) => {
    // aria-disabled (not disabled) so keyboard focus stays on the button while it works
    if (button.getAttribute('aria-disabled') === 'true') return undefined;
    const label = button.textContent;
    button.setAttribute('aria-disabled', 'true');
    button.setAttribute('aria-busy', 'true');
    button.textContent = doing;
    try { return await fn(...args); } finally {
      button.removeAttribute('aria-disabled');
      button.removeAttribute('aria-busy');
      button.textContent = label;
    }
  };
}
