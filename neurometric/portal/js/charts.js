// Inline-SVG charts (no libraries). Design rules:
// thin 2px lines, >=8px markers with a 2px surface ring, recessive hairline grid, one y-axis,
// legend whenever there are >=2 series plus direct end labels when they do not collide,
// categorical colours in fixed order (CSS classes s1..s8 -> tokens --s1..--s8, light/dark),
// text in text tokens only, hover + keyboard tooltip, and a "show as table" toggle on every chart.
import { h, s, nextId, fmtNum, clear, table } from './ui.js';

// ------------------------------------------------------------------ statistics
const T975 = [12.706, 4.303, 3.182, 2.776, 2.571, 2.447, 2.365, 2.306, 2.262, 2.228, 2.201, 2.179,
  2.160, 2.145, 2.131, 2.120, 2.110, 2.101, 2.093, 2.086, 2.080, 2.074, 2.069, 2.064, 2.060, 2.056,
  2.052, 2.048, 2.045, 2.042];
export function tCrit(df) {
  if (!(df >= 1)) return NaN;
  return df <= 30 ? T975[Math.floor(df) - 1] : 1.96 + 2.4 / df;
}
/** Two-sided 95% t-interval for a mean from (mean, sd, n); null when not estimable. */
export function ci95(mean, sd, n) {
  if (mean === null || mean === undefined || sd === null || sd === undefined || !(n >= 2)) return null;
  const hw = tCrit(n - 1) * sd / Math.sqrt(n);
  return [mean - hw, mean + hw];
}

function niceStep(range, count) {
  const raw = range / Math.max(count, 1);
  const p = 10 ** Math.floor(Math.log10(raw));
  const f = raw / p;
  return (f <= 1 ? 1 : f <= 2 ? 2 : f <= 2.5 ? 2.5 : f <= 5 ? 5 : 10) * p;
}
export function niceTicks(min, max, count = 5) {
  if (min === max) { max = min + 1; }
  const step = niceStep(max - min, count);
  const lo = Math.floor(min / step) * step;
  const hi = Math.ceil(max / step) * step;
  const out = [];
  for (let v = lo; v <= hi + step / 2; v += step) out.push(Math.round(v / step) * step);
  return out;
}
const tickFmt = (v) => (Math.abs(v) >= 10000 ? `${Math.round(v / 1000)}K` : fmtNum(v));

// ------------------------------------------------------------------ figure shell
function figureShell({ title, subtitle, legend, tableNode, draw, height }) {
  const titleId = nextId('ct');
  const tableId = nextId('ctab');
  const fig = h('figure', { class: 'chart', 'aria-labelledby': titleId });
  fig.appendChild(h('figcaption', null,
    h('p', { class: 'chart__title', id: titleId }, title),
    subtitle ? h('p', { class: 'chart__sub' }, subtitle) : null));
  if (legend && legend.length >= 2) {
    fig.appendChild(h('ul', { class: 'legend', 'aria-label': 'Legend' },
      legend.map((l) => h('li', null, h('span', { class: `swatch sw-${l.cls}`, 'aria-hidden': 'true' }), l.name))));
  }
  const plot = h('div', { class: 'chart__plot' });
  const tip = h('div', { class: 'chart__tip', hidden: true, 'aria-hidden': 'true' });
  const sr = h('p', { class: 'visually-hidden', 'aria-live': 'polite' });
  fig.appendChild(plot);
  fig.appendChild(sr);
  const tableBox = h('div', { id: tableId, hidden: true }, tableNode);
  const toggle = h('button', { type: 'button', class: 'secondary small', 'aria-expanded': 'false', 'aria-controls': tableId }, 'Show as table');
  toggle.addEventListener('click', () => {
    const open = toggle.getAttribute('aria-expanded') === 'true';
    toggle.setAttribute('aria-expanded', String(!open));
    toggle.textContent = open ? 'Show as table' : 'Hide table';
    tableBox.hidden = open;
  });
  fig.appendChild(h('div', { class: 'chart__controls' }, toggle));
  fig.appendChild(tableBox);

  let lastW = 0;
  const render = (w) => {
    if (!w || Math.abs(w - lastW) < 1) return;
    lastW = w;
    clear(plot);
    const svg = draw(Math.floor(w), { tip, plot, sr });
    plot.appendChild(svg);
    plot.appendChild(tip);
  };
  if (typeof ResizeObserver !== 'undefined') {
    const ro = new ResizeObserver((entries) => { for (const e of entries) render(e.contentRect.width); });
    ro.observe(plot);
  } else {
    requestAnimationFrame(() => render(plot.clientWidth || 600));
  }
  plot.style.minHeight = `${height || 200}px`;
  return fig;
}

function placeTip(tip, plot, x, y) {
  tip.hidden = false;
  const pw = plot.clientWidth;
  const tw = tip.offsetWidth;
  let left = x + 14;
  if (left + tw > pw) left = Math.max(0, x - tw - 14);
  tip.style.left = `${left}px`;
  tip.style.top = `${Math.max(0, y)}px`;
}

function tipContent(tip, heading, items) {
  clear(tip);
  tip.appendChild(h('h4', null, heading));
  tip.appendChild(h('ul', null, items.map((it) => h('li', null,
    it.cls ? h('span', { class: `swatch sw-${it.cls}`, 'aria-hidden': 'true' }) : null,
    h('span', null, it.text)))));
}

function describePoint(p, fmt, k) {
  if (p.suppressed) return `suppressed (n = ${p.n} < ${k ?? 'min cell'})`;
  if (p.y === null || p.y === undefined) return 'no data';
  let t = fmt(p.y);
  if (p.lo !== undefined && p.lo !== null) t += ` (95% CI ${fmt(p.lo)} to ${fmt(p.hi)})`;
  if (p.n !== undefined) t += `, n = ${p.n}`;
  return t;
}

// ------------------------------------------------------------------ line chart
/**
 * series: [{name, points: [{x, xl, y, lo, hi, n, suppressed}]}]  (x numeric, e.g. study day)
 * opts: {title, subtitle, xTitle(x, pts) -> string, xTick(x) -> string, fmt, minCell, yFromZero}
 */
export function lineChart(opts) {
  const { title, subtitle, series, fmt = fmtNum, xTick = (x) => String(x), xTitle, minCell,
    yFromZero = true, xAxisLabel = '' } = opts;
  const cls = series.map((_, i) => `s${(i % 8) + 1}`);
  const xs = [...new Set(series.flatMap((sr) => sr.points.map((p) => p.x)))].sort((a, b) => a - b);
  const rows = [];
  for (const x of xs) {
    for (const [i, sr] of series.entries()) {
      const p = sr.points.find((q) => q.x === x);
      if (p) rows.push({ series: sr.name, x: xTick(x), visit: p.xl || '', i, ...p });
    }
  }
  const tableNode = table([
    { key: 'series', label: 'Series' },
    { key: 'visit', label: 'Visit', render: (r) => r.visit || r.x },
    { key: 'x', label: xAxisLabel || 'x' },
    { key: 'y', label: 'Mean', num: true, render: (r) => (r.suppressed ? 'suppressed' : fmt(r.y)) },
    { key: 'lo', label: '95% CI', render: (r) => (r.lo === null || r.lo === undefined ? '—' : `${fmt(r.lo)} to ${fmt(r.hi)}`) },
    { key: 'n', label: 'n', num: true },
  ], rows, { caption: `${title} (data table)` });

  const H = 270;
  const draw = (W, { tip, plot, sr }) => {
    const narrow = W < 520;
    const multi = series.length > 1;
    const m = { l: 48, r: multi && !narrow ? 132 : 18, t: 14, b: 46 };
    const iw = Math.max(40, W - m.l - m.r);
    const ih = H - m.t - m.b;
    const vals = series.flatMap((sr) => sr.points.flatMap((p) => (p.suppressed || p.y === null ? [] : [p.y, p.lo, p.hi])))
      .filter((v) => v !== null && v !== undefined && Number.isFinite(v));
    let lo = vals.length ? Math.min(...vals) : 0;
    let hi = vals.length ? Math.max(...vals) : 1;
    if (yFromZero && lo > 0) lo = 0;
    if (hi === lo) hi = lo + 1;
    const ticks = niceTicks(lo, hi, 5);
    const y0 = ticks[0], y1 = ticks[ticks.length - 1];
    const xmin = xs[0] ?? 0, xmax = xs[xs.length - 1] ?? 1;
    const xspan = xmax - xmin || 1;
    const X = (x) => m.l + (xs.length === 1 ? iw / 2 : ((x - xmin) / xspan) * iw);
    const Y = (y) => m.t + ih - ((y - y0) / (y1 - y0)) * ih;

    const summary = series.map((sr) => {
      const pts = sr.points.filter((p) => !p.suppressed && p.y !== null);
      if (!pts.length) return `${sr.name}: no data`;
      return `${sr.name}: ${fmt(pts[0].y)} at ${xTick(pts[0].x)} to ${fmt(pts[pts.length - 1].y)} at ${xTick(pts[pts.length - 1].x)}`;
    }).join('; ');
    const svg = s('svg', { viewBox: `0 0 ${W} ${H}`, width: W, height: H, role: 'img', tabindex: '0',
      'aria-label': `${title}. ${summary}. Use left and right arrow keys to read values, or show as table.` });

    const g = s('g', { class: 'grid' });
    for (const t of ticks) g.appendChild(s('line', { x1: m.l, x2: m.l + iw, y1: Y(t), y2: Y(t) }));
    svg.appendChild(g);
    const ax = s('g', { class: 'axis', 'aria-hidden': 'true' });
    for (const t of ticks) ax.appendChild(s('text', { x: m.l - 8, y: Y(t) + 4, 'text-anchor': 'end' }, tickFmt(t)));
    ax.appendChild(s('line', { x1: m.l, x2: m.l + iw, y1: m.t + ih, y2: m.t + ih }));
    let lastX = -Infinity;
    for (const x of xs) {
      const px = X(x);
      ax.appendChild(s('line', { x1: px, x2: px, y1: m.t + ih, y2: m.t + ih + 4 }));
      const label = xTick(x);
      if (px - lastX >= label.length * 7 + 6) {
        ax.appendChild(s('text', { x: px, y: m.t + ih + 18, 'text-anchor': 'middle' }, label));
        lastX = px;
      }
    }
    if (xAxisLabel) ax.appendChild(s('text', { x: m.l + iw / 2, y: H - 6, 'text-anchor': 'middle' }, xAxisLabel));
    svg.appendChild(ax);

    const cross = s('line', { class: 'crosshair', y1: m.t, y2: m.t + ih, x1: -10, x2: -10, visibility: 'hidden' });
    svg.appendChild(cross);
    const dots = [];
    const ends = [];
    series.forEach((sr, i) => {
      const pts = sr.points.filter((p) => !p.suppressed && p.y !== null && p.y !== undefined).sort((a, b) => a.x - b.x);
      const withCi = pts.filter((p) => p.lo !== null && p.lo !== undefined);
      if (withCi.length >= 2) {
        const d = `M${withCi.map((p) => `${X(p.x)},${Y(p.hi)}`).join('L')}L${withCi.slice().reverse().map((p) => `${X(p.x)},${Y(p.lo)}`).join('L')}Z`;
        svg.appendChild(s('path', { class: `band ${cls[i]}`, d, 'aria-hidden': 'true' }));
      }
      if (withCi.length === 1) for (const p of withCi) { // a lone CI has no band: draw a whisker
        svg.appendChild(s('line', { class: `line ${cls[i]}`, x1: X(p.x), x2: X(p.x), y1: Y(p.lo), y2: Y(p.hi), 'stroke-width': 1, opacity: 0.5 }));
      }
      if (pts.length >= 2) {
        svg.appendChild(s('path', { class: `line ${cls[i]}`, d: `M${pts.map((p) => `${X(p.x)},${Y(p.y)}`).join('L')}` }));
      }
      for (const p of pts) {
        const c = s('circle', { class: `dot ${cls[i]}`, cx: X(p.x), cy: Y(p.y), r: 4.5 });
        dots.push({ el: c, x: p.x });
        svg.appendChild(c);
      }
      if (pts.length) ends.push({ name: sr.name, x: X(pts[pts.length - 1].x), y: Y(pts[pts.length - 1].y) });
    });
    // direct end labels in the right gutter (legend always present). Labels that would collide
    // are spaced apart and tied to their line end with a thin leader line, never left floating.
    if (multi && !narrow) {
      const gx = m.l + iw + 14;
      const placed = ends.map((e) => ({ ...e, ly: e.y })).sort((a, b) => a.y - b.y);
      for (let i = 1; i < placed.length; i++) placed[i].ly = Math.max(placed[i].ly, placed[i - 1].ly + 16);
      const overflow = placed.length ? placed[placed.length - 1].ly - (m.t + ih) : 0;
      if (overflow > 0) for (const p of placed) p.ly -= overflow;
      for (const e of placed) {
        if (Math.abs(e.ly - e.y) > 1 || gx - e.x > 16) {
          svg.appendChild(s('path', { class: 'crosshair', d: `M${e.x + 7},${e.y}L${gx - 10},${e.y}L${gx - 4},${e.ly}`, fill: 'none', 'aria-hidden': 'true' }));
        }
        svg.appendChild(s('text', { class: 'label', x: gx, y: e.ly + 4 }, e.name.length > 16 ? `${e.name.slice(0, 15)}…` : e.name));
      }
    }

    let active = -1;
    const show = (idx, fromKeyboard) => {
      if (idx < 0 || idx >= xs.length) return;
      active = idx;
      const x = xs[idx];
      cross.setAttribute('x1', X(x));
      cross.setAttribute('x2', X(x));
      cross.setAttribute('visibility', 'visible');
      for (const d of dots) d.el.classList.toggle('active', d.x === x);
      const items = series.map((sr, i) => {
        const p = sr.points.find((q) => q.x === x);
        return p ? { cls: cls[i], text: `${sr.name}: ${describePoint(p, fmt, minCell)}` } : null;
      }).filter(Boolean);
      const pts = series.map((sr) => sr.points.find((q) => q.x === x)).filter(Boolean);
      const heading = xTitle ? xTitle(x, pts) : xTick(x);
      tipContent(tip, heading, items);
      const scale = plot.clientWidth / W || 1;
      placeTip(tip, plot, X(x) * scale, m.t);
      if (fromKeyboard) sr.textContent = `${heading}. ${items.map((i) => i.text).join('. ')}`;
    };
    const hide = () => {
      tip.hidden = true;
      cross.setAttribute('visibility', 'hidden');
      for (const d of dots) d.el.classList.remove('active');
    };
    const overlay = s('rect', { class: 'hit', x: m.l - 10, y: m.t, width: iw + 20, height: ih });
    svg.appendChild(overlay);
    overlay.addEventListener('pointermove', (ev) => {
      const r = svg.getBoundingClientRect();
      const px = (ev.clientX - r.left) * (W / r.width);
      let best = 0;
      xs.forEach((x, i) => { if (Math.abs(X(x) - px) < Math.abs(X(xs[best]) - px)) best = i; });
      show(best, false);
    });
    overlay.addEventListener('pointerleave', hide);
    svg.addEventListener('focus', () => show(active < 0 ? 0 : active, true));
    svg.addEventListener('blur', hide);
    svg.addEventListener('keydown', (ev) => {
      const k = ev.key;
      if (k === 'ArrowRight' || k === 'ArrowDown') { show(Math.min(xs.length - 1, active + 1), true); ev.preventDefault(); }
      else if (k === 'ArrowLeft' || k === 'ArrowUp') { show(Math.max(0, active - 1), true); ev.preventDefault(); }
      else if (k === 'Home') { show(0, true); ev.preventDefault(); }
      else if (k === 'End') { show(xs.length - 1, true); ev.preventDefault(); }
      else if (k === 'Escape') hide();
    });
    return svg;
  };
  if (!xs.length) {
    return h('figure', { class: 'chart' }, h('figcaption', null, h('p', { class: 'chart__title' }, title)), h('p', { class: 'chart__empty' }, 'No data to chart yet.'));
  }
  return figureShell({ title, subtitle, legend: series.map((sr, i) => ({ name: sr.name, cls: cls[i] })), tableNode, draw, height: H });
}

// ------------------------------------------------------------------ horizontal bar chart
/**
 * rows: [{label, value, lo, hi, n, suppressed, note, cls}]; labels sit above each bar so the
 * chart works at 360px. opts: {title, subtitle, fmt, domainMax, minCell, valueLabel}
 */
export function barChart(opts) {
  const { title, subtitle, rows, fmt = fmtNum, domainMax, minCell, valueLabel = 'Value', tableCols } = opts;
  const tableNode = table(tableCols || [
    { key: 'label', label: 'Group' },
    { key: 'value', label: valueLabel, num: true, render: (r) => (r.suppressed ? 'suppressed' : fmt(r.value)) },
    { key: 'lo', label: '95% CI', render: (r) => (r.lo === null || r.lo === undefined ? '—' : `${fmt(r.lo)} to ${fmt(r.hi)}`) },
    { key: 'n', label: 'n', num: true },
  ], rows, { caption: `${title} (data table)` });
  const rowH = 50, barH = 16;
  const H = rows.length * rowH + 30;
  const draw = (W, { tip, plot, sr }) => {
    const m = { l: 2, r: 84, t: 4, b: 26 };
    const iw = Math.max(40, W - m.l - m.r);
    const max = domainMax ?? Math.max(1e-9, ...rows.map((r) => (r.suppressed ? 0 : Math.max(r.value ?? 0, r.hi ?? 0))));
    const ticks = domainMax ? niceTicks(0, domainMax, 4) : niceTicks(0, max, 4);
    const top = ticks[ticks.length - 1];
    const X = (v) => m.l + (Math.max(0, v) / top) * iw;
    const summary = rows.map((r) => `${r.label}: ${r.suppressed ? 'suppressed' : fmt(r.value)}`).join('; ');
    const svg = s('svg', { viewBox: `0 0 ${W} ${H}`, width: W, height: H, role: 'img', tabindex: '0',
      'aria-label': `${title}. ${summary}. Use up and down arrow keys to read values, or show as table.` });
    const g = s('g', { class: 'grid' });
    for (const t of ticks) g.appendChild(s('line', { x1: X(t), x2: X(t), y1: m.t, y2: H - m.b }));
    svg.appendChild(g);
    const ax = s('g', { class: 'axis', 'aria-hidden': 'true' });
    for (const t of ticks) ax.appendChild(s('text', { x: X(t), y: H - m.b + 16, 'text-anchor': 'middle' }, fmt === fmtNum ? tickFmt(t) : fmt(t)));
    svg.appendChild(ax);
    const marks = [];
    rows.forEach((r, i) => {
      const y = m.t + i * rowH;
      const by = y + 22;
      svg.appendChild(s('text', { class: 'label', x: m.l, y: y + 14 }, r.label));
      const cls = r.cls || 's1';
      let end = X(0);
      if (!r.suppressed && r.value !== null && r.value !== undefined) {
        const x0 = X(0), x1 = X(r.value);
        const w = x1 - x0;
        const d = w > 4
          ? `M${x0},${by}H${x1 - 4}Q${x1},${by} ${x1},${by + 4}V${by + barH - 4}Q${x1},${by + barH} ${x1 - 4},${by + barH}H${x0}Z`
          : `M${x0},${by}h${Math.max(w, 1)}v${barH}h${-Math.max(w, 1)}Z`;
        const bar = s('path', { class: `bar ${cls}`, d });
        svg.appendChild(bar);
        end = x1;
        if (r.lo !== null && r.lo !== undefined) {
          const cy = by + barH / 2;
          svg.appendChild(s('line', { class: 'whisker', x1: X(r.lo), x2: X(r.hi), y1: cy, y2: cy }));
          svg.appendChild(s('line', { class: 'whisker', x1: X(r.lo), x2: X(r.lo), y1: cy - 5, y2: cy + 5 }));
          svg.appendChild(s('line', { class: 'whisker', x1: X(r.hi), x2: X(r.hi), y1: cy - 5, y2: cy + 5 }));
          end = Math.max(end, X(r.hi));
        }
      }
      svg.appendChild(s('text', { class: 'value', x: end + 6, y: by + 12 },
        r.suppressed ? `suppressed (n<${minCell ?? 'k'})` : (r.display ?? fmt(r.value))));
      const hit = s('rect', { class: 'hit', x: 0, y, width: W, height: rowH });
      svg.appendChild(hit);
      marks.push({ hit, r, y });
    });
    let active = -1;
    const show = (i, kb) => {
      if (i < 0 || i >= marks.length) return;
      active = i;
      const { r, y } = marks[i];
      const items = [{ cls: r.cls || 's1', text: `${valueLabel}: ${describePoint({ y: r.value, lo: r.lo, hi: r.hi, n: r.n, suppressed: r.suppressed }, fmt, minCell)}` }];
      if (r.note) items.push({ text: r.note });
      tipContent(tip, r.label, items);
      const scale = plot.clientWidth / W || 1;
      placeTip(tip, plot, Math.min(X(r.value ?? 0), W * 0.6) * scale, (y + rowH) * scale);
      if (kb) sr.textContent = `${r.label}. ${items.map((x) => x.text).join('. ')}`;
    };
    const hide = () => { tip.hidden = true; };
    marks.forEach((mk, i) => {
      mk.hit.addEventListener('pointerenter', () => show(i, false));
      mk.hit.addEventListener('pointerleave', hide);
    });
    svg.addEventListener('focus', () => show(active < 0 ? 0 : active, true));
    svg.addEventListener('blur', hide);
    svg.addEventListener('keydown', (ev) => {
      if (ev.key === 'ArrowDown' || ev.key === 'ArrowRight') { show(Math.min(marks.length - 1, active + 1), true); ev.preventDefault(); }
      else if (ev.key === 'ArrowUp' || ev.key === 'ArrowLeft') { show(Math.max(0, active - 1), true); ev.preventDefault(); }
      else if (ev.key === 'Escape') hide();
    });
    return svg;
  };
  if (!rows.length) {
    return h('figure', { class: 'chart' }, h('figcaption', null, h('p', { class: 'chart__title' }, title)), h('p', { class: 'chart__empty' }, 'No data to chart yet.'));
  }
  return figureShell({ title, subtitle, tableNode, draw, height: H });
}
