#!/usr/bin/env python3
"""Regenerate site/results.html from the computational results in experiments/results/.

Usage (from the neurometric/ directory or anywhere):

    python site/build_results.py

What it does (standard library only; safe to re-run):
  * finds every experiments/results/<EXP>/summary.json (if a folder has no summary.json, it
    falls back to the first *.json in that folder whose top level has an "experiment" key);
  * copies the figures (*.png, *.svg, *.jpg, *.webp) of each experiment into
    site/assets/results/<EXP>/, removing stale copies;
  * writes site/results.html, reusing the header and footer of site/index.html (everything
    outside the <!-- BEGIN:main --> / <!-- END:main --> markers) so the page matches the site;
  * refreshes the screenshot block of site/demo.html (between <!-- BEGIN:demo-screenshots -->
    and <!-- END:demo-screenshots -->) from any screenshots found under web/ or experiments/
    (folders named screenshots/, or web/public/demo/), copied into site/assets/demo/.

Optional keys a summary.json may add to control the page: "title" (heading), "description"
(one paragraph), "figures" ({"file.png": "alt text"}). Everything else is rendered generically.
"""
from __future__ import annotations

import html
import json
import math
import re
import shutil
import sys
from pathlib import Path

SITE = Path(__file__).resolve().parent
ROOT = SITE.parent
RESULTS = ROOT / "experiments" / "results"
OUT_ASSETS = SITE / "assets" / "results"
DEMO_ASSETS = SITE / "assets" / "demo"
FIG_EXT = {".png", ".svg", ".jpg", ".jpeg", ".webp"}
MAX_OPEN_ROWS = 15  # longer tables are collapsed behind a <details> disclosure

# Human-readable titles for known experiment ids (from src/neurometric/experiments/registry.py).
KNOWN_TITLES = {
    "B_noise": "Sensitivity to added input noise",
    "B2_bias": "Sensitivity to directional bias",
    "B3_update_rate": "Sensitivity to decoder update rate",
    "B4_gain": "Sensitivity to gain mismatch",
    "C_latency": "Sensitivity to added latency (velocity control)",
    "C2_latency_mouse": "Sensitivity to latency (position-control pointer)",
    "D_dropout": "Sensitivity to signal dropouts",
    "E_drift": "Sensitivity to calibration deterioration",
    "F_false_activation": "Sensitivity to false selections",
    "F2_missed_selection": "Sensitivity to missed selections",
    "G_metric_comparison": "Comparison of metrics across all degradation sweeps",
    "H_adaptive": "Fixed versus adaptive task difficulty",
    "I_test_retest": "Simulated test-retest reliability versus test length",
    "K_responsiveness": "Responsiveness to a known simulated improvement",
    "L_cross_modality": "The same tasks across simulated input modalities",
    "M_user_variability": "Device versus user variance (crossed design)",
    "N_missing_data": "Effect of incomplete sessions",
    "P_reproducibility": "Bit-identical reproducibility across processes",
    "R_statistical_verification": "Monte-Carlo verification of statistical estimators",
    "S_event_latency": "Event-processing throughput and integrity",
    "X1_external_mc_rtt": "Real public data: NLB MC_RTT reaching dataset",
}

KNOWN_FIGURE_ALT = {
    ("X1_external_mc_rtt", "mc_rtt_metrics.png"):
        "Three panels from the real MC_RTT dataset (macaque hand cursor control): a histogram of "
        "reach times, mostly between about 900 and 1,500 ms; a histogram of path efficiency, "
        "concentrated between 0.8 and 1.0; and mean reach time rising from about 1,050 to 1,350 ms "
        "as effective index of difficulty increases from about 1.4 to 3.2 bits.",
}

# Metric labels mirror LABELS in src/neurometric/experiments/analysis.py.
METRIC_LABELS = {
    "iso_tp_bps": "Fitts throughput (bit/s)", "iso_error_rate": "ISO error rate",
    "iso_timeout_rate": "ISO timeout rate", "iso_success_rate": "ISO success rate",
    "iso_mt_ms": "Movement time (ms)", "iso_path_efficiency": "Path efficiency",
    "iso_reentries": "Target re-entries", "iso_overshoot_px": "Overshoot (px)",
    "iso_movement_variability_px": "Movement variability (px)",
    "iso_endpoint_error_px": "Endpoint error (px)", "iso_dial_in_ms": "Dial-in time (ms)",
    "iso_submovements": "Submovements", "iso_onset_ms": "Movement onset (ms)",
    "grid_accuracy": "Grid accuracy", "grid_time_ms": "Grid selection time (ms)",
    "grid_bitrate_bps": "Achieved bitrate (bit/s)",
    "false_activations_per_min": "Empty-space selections /min",
    "type_wpm": "Typing WPM", "type_ccpm": "Correct chars /min",
    "type_total_error_rate": "Total error rate", "type_uncorrected_error_rate": "Uncorrected error rate",
    "type_kspc": "Keystrokes per char", "type_correction_burden": "Correction burden",
    "adl_completion_rate": "ADL completion", "adl_time_s": "ADL time (s)",
    "adl_wrong_selections": "ADL wrong selections", "track_rms_px": "Tracking RMS error (px)",
    "track_time_on_target": "Tracking time on target", "track_lag_ms": "Tracking lag (ms)",
}

COLUMN_LABELS = {
    "metric": "Metric",
    "rho": "Spearman ρ",
    "monotone_frac": "Monotone fraction",
    "d_first": "First-step d",
    "min_detect_level": "Min. detectable level",
    "auc_adjacent": "Adjacent-level AUC",
    "undefined_frac": "Undefined",
    "floor_frac": "At floor",
    "ceiling_frac": "At ceiling",
    "n": "n",
    "n_participants": "Virtual participants",
    "n_trials_simulated": "Trials simulated",
    "n_events": "Events",
    "n_reaches": "Reaches",
    "runtime_s": "Runtime (s)",
    "reps": "Repetitions",
    "x": "Degradation axis",
    "levels": "Levels",
    "modality": "Simulated modality",
    "base_profile": "Base profile",
    "dataset": "Dataset",
    "n_reps": "Monte-Carlo repetitions",
    "n_rows": "Checks",
    "n_pass": "Checks passed",
    "seed": "Seed",
    "median_retest_icc_by_metric": "Median simulated retest ICC by metric",
    "throughput_by_distance": "Throughput by reach distance",
    "properties": "Measurement properties across the sweep",
    "caveats": "Caveats",
    "failures": "Checks outside tolerance",
    "known_limitations": "Known limitations",
    "stream_integrity": "Event-stream integrity",
    "stream_check": "Event-stream integrity",
    "per_event_validate_us": "Per-event validation time (µs)",
    "median": "Medians",
    "machine": "Machine",
    "session": "Session",
    "note": "Note",
    "pooled_TPe_bps_mean_of_bins": "Pooled effective throughput (bit/s, mean of bins)",
    "median_reach_time_ms": "Median reach time (ms)",
    "median_path_efficiency": "Median path efficiency",
    "all_roundtrips_identical": "All round-trips identical",
}

HANDLED_KEYS = {"experiment", "generated_utc", "software", "synthetic", "disclaimer",
                "title", "description", "figures"}

esc = html.escape


def label(key: str) -> str:
    if key in COLUMN_LABELS:
        return COLUMN_LABELS[key]
    if key in METRIC_LABELS:
        return METRIC_LABELS[key]
    s = key.replace("_", " ").strip()
    return s[:1].upper() + s[1:]


def is_scalar(v) -> bool:
    return v is None or isinstance(v, (str, int, float, bool))


def fmt(v, key: str = "") -> str:
    """Format a scalar for display (escaped)."""
    if v is None:
        return "n/a"
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, int):
        return f"{v:,}" if key not in ("seed",) else str(v)
    if isinstance(v, float):
        if math.isnan(v):
            return "n/a"
        if math.isinf(v):
            return "∞" if v > 0 else "−∞"
        if v.is_integer() and abs(v) < 1e15 and key not in ("rho", "d_first"):
            return f"{int(v):,}"
        a = abs(v)
        if a != 0 and a < 0.001:
            s = f"{v:.1e}"
        elif a >= 1000:
            s = f"{v:,.0f}"
        elif a >= 100:
            s = f"{v:.1f}"
        else:
            s = f"{v:.3f}"
        return s.replace("-", "−")
    if isinstance(v, str):
        return esc(METRIC_LABELS.get(v, v)) if key == "metric" else esc(v)
    return esc(str(v))


def cell_is_num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


class Ids:
    def __init__(self):
        self.used: set[str] = set()
        self.ctx = ""

    def make(self, base: str) -> str:
        b = slug(base) or "x"
        i, s = 1, b
        while s in self.used:
            i += 1
            s = f"{b}-{i}"
        self.used.add(s)
        return s


def table_html(caption: str, columns: list[str], rows: list[list], ids: Ids, keys: list[str],
               row_header: bool = True) -> str:
    cap_id = ids.make("cap-" + caption)
    num_attr = ' class="num"'
    head = "".join(
        f'<th scope="col"{num_attr if i and any(cell_is_num(r[i]) for r in rows) else ""}>{esc(c)}</th>'
        for i, c in enumerate(columns))
    body = []
    for r in rows:
        cells = []
        for i, v in enumerate(r):
            k = keys[i] if i < len(keys) else ""
            txt = fmt(v, k) if is_scalar(v) else esc(json.dumps(v, allow_nan=True))
            cls = ' class="num"' if cell_is_num(v) else ""
            if i == 0 and row_header:
                cells.append(f'<th scope="row">{txt}</th>')
            else:
                cells.append(f"<td{cls}>{txt}</td>")
        body.append("<tr>" + "".join(cells) + "</tr>")
    ctx = f" {ids.ctx}" if ids.ctx else ""
    t = (f'<div class="table-wrap" role="region" aria-labelledby="{cap_id}{ctx}" tabindex="0">'
         f'<table class="compact"><caption id="{cap_id}">{esc(caption)}</caption>'
         f"<thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table></div>")
    if len(rows) > MAX_OPEN_ROWS:
        t = f"<details><summary>Show table: {esc(caption)} ({len(rows)} rows)</summary>{t}</details>"
    return t


def render_block(key: str, val, ids: Ids, depth: int = 0) -> str:
    """Render a non-scalar summary value."""
    title = label(key)
    if isinstance(val, list):
        if not val:
            return f"<p><strong>{esc(title)}:</strong> none.</p>"
        if all(is_scalar(x) for x in val):
            if all(isinstance(x, str) for x in val):
                items = "".join(f"<li>{esc(x)}</li>" for x in val)
                return f"<h3>{esc(title)}</h3><ul>{items}</ul>"
            return f"<p><strong>{esc(title)}:</strong> {', '.join(fmt(x) for x in val)}</p>"
        if all(isinstance(x, dict) for x in val):
            cols: list[str] = []
            for x in val:
                for k in x:
                    if k not in cols:
                        cols.append(k)
            rows = [[x.get(c) for c in cols] for x in val]
            return table_html(title, [label(c) for c in cols], rows, ids, cols)
    if isinstance(val, dict):
        if all(is_scalar(v) for v in val.values()):
            rows = [[label(k), v] for k, v in val.items()]
            return table_html(title, ["Item", "Value"], rows, ids, ["", key])
        if depth < 1:
            parts = [f"<h3>{esc(title)}</h3>"]
            scal = {k: v for k, v in val.items() if is_scalar(v)}
            if scal:
                parts.append(table_html(title + " (values)", ["Item", "Value"],
                                        [[label(k), v] for k, v in scal.items()], ids, ["", key]))
            for k, v in val.items():
                if not is_scalar(v):
                    parts.append(render_block(k, v, ids, depth + 1))
            return "".join(parts)
    dump = esc(json.dumps(val, indent=2, allow_nan=True))
    return f"<details><summary>{esc(title)} (raw JSON)</summary><pre><code>{dump}</code></pre></details>"


def find_summaries() -> list[tuple[str, Path, dict]]:
    found = []
    if not RESULTS.is_dir():
        return found
    for d in sorted(p for p in RESULTS.iterdir() if p.is_dir()):
        cand = d / "summary.json"
        data = None
        if cand.is_file():
            data = _load(cand)
        else:
            for j in sorted(d.glob("*.json")):
                obj = _load(j)
                if isinstance(obj, dict) and "experiment" in obj:
                    cand, data = j, obj
                    break
        if isinstance(data, dict):
            found.append((str(data.get("experiment") or d.name), cand, data))
    return found


def _load(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        print(f"  skipping {p}: {e}", file=sys.stderr)
        return None


def copy_figures(exp_dir: Path, exp_id: str) -> list[Path]:
    dest = OUT_ASSETS / slug(exp_id)
    if dest.exists():
        shutil.rmtree(dest)
    figs = sorted(p for p in exp_dir.iterdir() if p.is_file() and p.suffix.lower() in FIG_EXT)
    if figs:
        dest.mkdir(parents=True, exist_ok=True)
    out = []
    for f in figs:
        shutil.copy2(f, dest / f.name)
        out.append(dest / f.name)
    return out


def figure_alt(exp_id: str, name: str, summary: dict) -> str:
    custom = summary.get("figures")
    if isinstance(custom, dict) and isinstance(custom.get(name), str):
        return custom[name]
    if (exp_id, name) in KNOWN_FIGURE_ALT:
        return KNOWN_FIGURE_ALT[(exp_id, name)]
    stem = Path(name).stem.replace("_", " ")
    if summary.get("x") and summary.get("synthetic", True):
        return (f"Small-multiple line charts ({stem}): mean of each metric with 95% confidence "
                f"intervals over virtual participants, across levels of {summary['x']}. "
                "The measurement properties table on this page summarises the same data.")
    return f"Figure “{stem}” for experiment {exp_id}. Key values are given in the tables on this page."


def provenance(summary: dict) -> tuple[str, str, str]:
    syn = summary.get("synthetic")
    if syn is True:
        return ("badge-sim", "Simulation (synthetic data)",
                "Synthetic virtual users and simulated input. Not human or clinical data.")
    if syn is False:
        return ("badge-real", "Real public data (non-clinical)",
                "Real recorded data reprocessed by NeuroMetric. Read the caveats; not a clinical "
                "population unless stated.")
    return ("badge-human", "Provenance not recorded",
            "This result file does not state whether its data are synthetic. Treat it as "
            "computational output, not human or clinical data.")


def render_experiment(exp_id: str, src: Path, s: dict, ids: Ids) -> str:
    anchor = ids.make("exp-" + exp_id)
    ids.ctx = anchor + "-h"  # table regions are labelled by caption + experiment heading
    title = s.get("title") if isinstance(s.get("title"), str) else KNOWN_TITLES.get(exp_id, exp_id)
    badge_cls, badge_txt, prov_note = provenance(s)
    parts = [f'<article class="result" id="{anchor}" aria-labelledby="{anchor}-h">',
             '<div class="result-head">',
             f'<h2 id="{anchor}-h">{esc(title)}</h2>',
             f'<span class="badge {badge_cls}">{esc(badge_txt)}</span></div>',
             f'<p><code>{esc(exp_id)}</code>']
    if s.get("generated_utc"):
        parts.append(f" &middot; generated {esc(str(s['generated_utc']))}")
    sw = s.get("software")
    if isinstance(sw, dict) and sw:
        parts.append(" &middot; " + ", ".join(f"{esc(str(k))} {esc(str(v))}" for k, v in sw.items()))
    parts.append("</p>")
    if isinstance(s.get("description"), str):
        parts.append(f"<p>{esc(s['description'])}</p>")
    disc = s.get("disclaimer") if isinstance(s.get("disclaimer"), str) else prov_note
    parts.append(f'<p class="callout callout-warn">{esc(disc)}</p>')

    scalars = [(k, v) for k, v in s.items() if k not in HANDLED_KEYS and is_scalar(v)]
    if scalars:
        parts.append('<dl class="facts">')
        for k, v in scalars:
            parts.append(f"<dt>{esc(label(k))}</dt><dd>{fmt(v, k)}</dd>")
        parts.append("</dl>")

    figs = copy_figures(src.parent, exp_id)
    for f in figs:
        rel = f.relative_to(SITE).as_posix()
        alt = figure_alt(exp_id, f.name, s)
        parts.append(f'<figure class="result-figure"><img src="{esc(rel)}" alt="{esc(alt)}" '
                     f'loading="lazy" decoding="async">'
                     f"<figcaption>{esc(f.name)} ({esc(badge_txt.lower())}).</figcaption></figure>")

    for k, v in s.items():
        if k in HANDLED_KEYS or is_scalar(v):
            continue
        parts.append(render_block(k, v, ids))

    data_files = sorted(p.name for p in src.parent.iterdir()
                        if p.is_file() and p.suffix.lower() in {".csv", ".json"} and p != src)
    rel_dir = src.parent.relative_to(ROOT).as_posix()
    files_txt = (", ".join(f"<code>{esc(n)}</code>" for n in data_files)) or "none"
    parts.append(f"<p>Source: <code>{esc(rel_dir)}/{esc(src.name)}</code>. Other data files in the "
                 f"repository folder: {files_txt}.</p>")
    parts.append("</article>")
    return "\n".join(parts)


def page_shell() -> tuple[str, str]:
    idx = (SITE / "index.html").read_text(encoding="utf-8")
    try:
        pre, rest = idx.split("<!-- BEGIN:main -->", 1)
        _, post = rest.split("<!-- END:main -->", 1)
    except ValueError:
        sys.exit("site/index.html is missing the <!-- BEGIN:main --> / <!-- END:main --> markers")
    pre = re.sub(r"<title>.*?</title>", "<title>Computational results | NeuroMetric</title>", pre, flags=re.S)
    pre = re.sub(r'<meta name="description" content="[^"]*">',
                 '<meta name="description" content="Computational results from NeuroMetric: simulation '
                 'experiments, software verification and reprocessing of non-clinical public data. '
                 'Not clinical evidence.">', pre)
    pre = pre.replace(' aria-current="page"', "")
    pre = pre.replace('<a href="results.html">', '<a href="results.html" aria-current="page">', 1)
    return pre + "<!-- BEGIN:main -->\n  <main id=\"main\" tabindex=\"-1\">\n", "  </main>\n  <!-- END:main -->" + post


def build_results() -> int:
    OUT_ASSETS.mkdir(parents=True, exist_ok=True)
    summaries = find_summaries()
    ids = Ids()
    # remove figure folders for experiments that no longer exist
    live = {slug(e) for e, _, _ in summaries}
    for d in OUT_ASSETS.iterdir():
        if d.is_dir() and d.name not in live:
            shutil.rmtree(d)

    n_syn = sum(1 for _, _, s in summaries if s.get("synthetic") is True)
    n_real = sum(1 for _, _, s in summaries if s.get("synthetic") is False)
    n_other = len(summaries) - n_syn - n_real
    stamps = sorted(str(s["generated_utc"]) for _, _, s in summaries if s.get("generated_utc"))
    latest = stamps[-1] if stamps else "n/a"

    toc = "".join(
        f'<li><a href="#{slug("exp-" + e)}">{esc(s.get("title") if isinstance(s.get("title"), str) else KNOWN_TITLES.get(e, e))}</a> '
        f'<span class="visually-hidden">({esc(provenance(s)[1])})</span></li>'
        for e, _, s in summaries)

    body = [
        '    <div class="page-head"><div class="wrap">',
        '      <p class="eyebrow">Research &middot; Results</p>',
        "      <h1>Computational results</h1>",
        '      <p class="lead">Simulation experiments, software verification and reprocessing of '
        "non-clinical public data. This page is generated from the result files in the repository "
        "and lists whatever results exist; some experiments may still be running.</p>",
        "    </div></div>",
        '    <section class="section" aria-labelledby="res-lim"><div class="wrap">',
        '      <div class="callout callout-warn callout-strong">',
        '        <h2 id="res-lim" class="callout-title">Simulation is not clinical evidence</h2>',
        "        <p>Nothing on this page comes from people who use BCIs or assistive technology. "
        "Simulation results describe how the <em>measurement system</em> behaves under modelled input "
        "degradation with synthetic virtual users; simulated reliability reflects the model&rsquo;s "
        "assumptions, not human reliability. Real-data results use a non-human, non-BCI public dataset "
        "to check the processing pipeline. Read the "
        '<a href="research.html#limitations">limitations</a> and '
        '<a href="research.html#props-title">definitions of the summary statistics</a>.</p>',
        "      </div>",
        f"      <p>{len(summaries)} result set{'s' if len(summaries) != 1 else ''}: {n_syn} simulation, "
        f"{n_real} real public data, {n_other} without recorded provenance. Latest result generated "
        f"{esc(latest)}.</p>",
    ]
    if summaries:
        body.append(f'      <nav aria-label="Results on this page"><h2 class="visually-hidden">Contents</h2><ul class="toc">{toc}</ul></nav>')
        body.append("    </div></section>")
        body.append('    <section class="section" aria-label="Result sets"><div class="wrap">')
        for e, src, s in summaries:
            body.append(render_experiment(e, src, s, ids))
        body.append("    </div></section>")
    else:
        body.append("      <p>No result files were found in <code>experiments/results/</code>.</p>")
        body.append("    </div></section>")

    pre, post = page_shell()
    (SITE / "results.html").write_text(pre + "\n".join(body) + "\n" + post, encoding="utf-8")
    print(f"wrote site/results.html with {len(summaries)} result set(s)")
    for e, src, _ in summaries:
        print(f"  {e}: {src.relative_to(ROOT)}")
    return len(summaries)


def build_demo_screenshots() -> None:
    demo = SITE / "demo.html"
    if not demo.is_file():
        return
    text = demo.read_text(encoding="utf-8")
    m = re.search(r"(<!-- BEGIN:demo-screenshots -->)(.*?)(\s*<!-- END:demo-screenshots -->)", text, re.S)
    if not m:
        return
    shots = []
    for base in (ROOT / "web", ROOT / "experiments"):
        if not base.is_dir():
            continue
        for p in sorted(base.rglob("*")):
            if "node_modules" in p.parts or not p.is_file() or p.suffix.lower() not in FIG_EXT:
                continue
            rel = p.relative_to(ROOT).parts
            if "screenshots" in rel or rel[:3] == ("web", "public", "demo"):
                shots.append(p)
    if DEMO_ASSETS.exists():
        shutil.rmtree(DEMO_ASSETS)
    if shots:
        DEMO_ASSETS.mkdir(parents=True)
        items = []
        for i, p in enumerate(shots):
            name = f"{i:02d}-{p.name}"
            shutil.copy2(p, DEMO_ASSETS / name)
            stem = p.stem.replace("_", " ").replace("-", " ")
            items.append(
                f'\n        <figure class="result-figure"><img src="assets/demo/{esc(name)}" '
                f'alt="Screenshot of the NeuroMetric demo: {esc(stem)}" loading="lazy" decoding="async">'
                f"<figcaption>{esc(p.relative_to(ROOT).as_posix())} (synthetic demo data).</figcaption></figure>")
        inner = "".join(items)
    else:
        inner = ("\n        <p>No demo screenshots are available yet. Run <code>python site/build_results.py</code> "
                 "after screenshots are added to the web app to include them here.</p>")
    new = text[:m.start()] + m.group(1) + inner + m.group(3) + text[m.end():]
    if new != text:
        demo.write_text(new, encoding="utf-8")
    print(f"demo.html: {len(shots)} screenshot(s)")


if __name__ == "__main__":
    build_results()
    build_demo_screenshots()
