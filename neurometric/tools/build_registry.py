"""Generate EXPERIMENT_REGISTRY.md from experiments/results (numbers are read, never typed)."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
R = ROOT / "experiments" / "results"

H = {  # id: (title, hypothesis, model/dataset, limitations)
    "A_input_timing": ("Input adapter timing and consistency",
                       "Browser adapters preserve event order and timestamps without drops or duplicates under realistic and 1 kHz synthetic streams.",
                       "Headless Chromium via Playwright; injected pointer streams.",
                       "Headless timing is not physical device latency (no display, no USB polling)."),
    "B_noise": ("Target acquisition under increasing input noise",
                "Task scores degrade monotonically and detectably as decoder noise increases.",
                "Closed-loop BCI-like feedback users, bci_good base, white + AR(1) noise scaled 0-6x.", ""),
    "C_latency": ("Functional performance under increasing latency",
                  "Latency degrades closed-loop control; tracking lag and MT are most sensitive.",
                  "Total decoder output latency 0-700 ms on the bci_good base.", ""),
    "C2_latency_mouse": ("Latency with a position-control pointer",
                         "Position-control (mouse-like) users are less affected by latency than velocity users.",
                         "Submovement users; latency only.", ""),
    "D_dropout": ("Sensitivity to dropout", "Scores fall as dropout episodes become frequent.",
                  "Markov dropout 0-0.8 episodes/s, mean 500 ms.", ""),
    "E_drift": ("Cursor drift and calibration deterioration",
                "Calibration decay (drift, gain loss, noise growth over session time) degrades later tasks.",
                "Index k scales drift rate, gain decay and noise growth; session starts at minute 10.", ""),
    "F_false_activation": ("False activation sensitivity",
                           "Unintended selections lower accuracy and bitrate; empty-space selections reveal them.",
                           "Poisson false selections 0-16/min.", ""),
    "F2_missed_selection": ("Missed-selection sensitivity", "Missed selections lengthen time; accuracy is insensitive.",
                            "Selection miss probability 0-0.6.", ""),
    "B2_bias": ("Directional bias", "Users compensate small biases; large biases degrade path metrics first.",
                "Rotation 0-60 degrees.", ""),
    "B3_update_rate": ("Reduced update frequency", "Slow decoder updates degrade control.",
                       "Update interval 10-200 ms.", ""),
    "B4_gain": ("Gain mismatch (overshoot/undershoot)", "Performance is best near unit gain (non-monotone).",
                "Gain 0.4-2.0.", ""),
    "G_metric_comparison": ("Comparison of functional task metrics",
                            "Metrics differ in sensitivity, monotonicity, floor/ceiling and reliability; no single metric is best for all impairments.",
                            "Properties pooled over sweeps B-F.", ""),
    "H_adaptive": ("Fixed versus adaptive difficulty",
                   "An adaptive size staircase reduces floor/ceiling effects across a wide ability range.",
                   "Fixed 100 px and 40 px grids vs 2-down/1-up size staircase; 6 noise levels.",
                   "Adaptive scores are on a different scale; comparability requires locking the staircase rule."),
    "I_test_retest": ("Simulated test-retest reliability",
                      "Reliability rises with test length per Spearman-Brown; some metrics reach ICC >= 0.8.",
                      "60 virtual participants x 2 sessions x 4 lengths x 3 modalities; day-to-day variation.",
                      "Upper bounds: real users vary more between days than modelled."),
    "K_responsiveness": ("Measurement responsiveness",
                         "Change scores separate participants whose (simulated) decoder improved from stable ones.",
                         "100 virtual participants; half receive an improved decoder at session 2.",
                         "MDC is statistically detectable change, not an MCID."),
    "L_cross_modality": ("Cross-modality comparability (simulation)",
                         "The same tasks run across modalities; some metrics are undefined or unfair across selection methods.",
                         "8 simulated modalities incl. mouse, head pointer, gaze, BCI x3, switch scanning x2.",
                         "All modalities simulated; dwell time is inside MT; scanning has no throughput."),
    "M_user_variability": ("Virtual user variability vs device variability",
                           "Some metrics mostly reflect the device, others the user.",
                           "3 ability levels x 3 decoder profiles x 60 virtual participants.", ""),
    "N_missing_data": ("Missing data and incomplete sessions",
                       "Informative (MNAR) abandonment biases complete-case estimates; MCAR does not.",
                       "120 virtual participants, 24 ISO selections; MCAR, MAR (late trials), MNAR (abandon after slow trial).", ""),
    "O_telemetry_integrity": ("Telemetry data integrity",
                              "Duplicates, conflicts, overlaps, clock skew and forbidden content are handled; aggregates stay exact.",
                              "Fault-injection tests against the ingest service.", "Software verification, not field data."),
    "P_reproducibility": ("Reproducibility", "Identical seeds give bit-identical results regardless of process count.",
                          "One condition run in-process and in a pool.", ""),
    "Q_accessibility": ("Accessibility and interface performance",
                        "Web battery, portal and website have zero serious/critical automated violations.",
                        "axe-core via Playwright.", "Automated checks only; no testing with real assistive technology or users."),
    "R_statistical_verification": ("Statistical implementation verification",
                                   "Psychometric functions reproduce published values and independent libraries; CIs have nominal coverage.",
                                   "Shrout & Fleiss example, pingouin, scipy, Monte Carlo coverage.", ""),
    "S_event_latency": ("Real-time event processing latency",
                        "Server-side validation/scoring and browser event handling are fast enough for real-time recording.",
                        "Synthetic 60-trial session (Python); headless Chromium (browser).", "Machine-specific."),
    "X1_external_mc_rtt": ("Real public data: metric pipeline on macaque hand-cursor reaching",
                           "The pipeline ingests real behavioural data as canonical events and gives sane metrics.",
                           "NLB MC_RTT (DANDI:000129, CC-BY-4.0).",
                           "Able-bodied macaque, hand control, one session; target width unknown."),
}

SWEEPS = ["B_noise", "C_latency", "C2_latency_mouse", "D_dropout", "E_drift", "F_false_activation",
          "F2_missed_selection", "B2_bias", "B3_update_rate", "B4_gain"]
KEY = ["iso_tp_bps", "iso_mt_ms", "iso_path_efficiency", "grid_bitrate_bps", "grid_accuracy",
       "type_ccpm", "adl_completion_rate", "track_rms_px", "track_lag_ms"]


def fmt(v, d=2):
    if v is None or (isinstance(v, float) and not np.isfinite(v)):
        return "–"
    if isinstance(v, (int, np.integer)):
        return str(v)
    return f"{v:.{d}f}"


def table(df: pd.DataFrame, cols=None, d=2) -> str:
    cols = cols or list(df.columns)
    out = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for _, r in df.iterrows():
        out.append("| " + " | ".join(fmt(r[c], d) if isinstance(r[c], (float, int, np.floating, np.integer)) and not isinstance(r[c], bool) else str(r[c]) for c in cols) + " |")
    return "\n".join(out)


def sweep_section(e):
    d = R / e
    if not (d / "data.csv").exists():
        return "_Not yet run._\n"
    df = pd.read_csv(d / "data.csv")
    s = json.loads((d / "summary.json").read_text())
    m = df[df.rep == 0].groupby("level")[[k for k in KEY if k in df]].mean().reset_index()
    out = [f"Levels: {s['x']}; {s['n_participants']} virtual participants x {s['reps']} sessions per level; "
           f"runtime {s['runtime_s']} s; ~{s['n_trials_simulated']:,} simulated trials.\n",
           "Mean scores by level (session 1):\n", table(m), "\n"]
    p = pd.read_csv(d / "properties.csv")
    best = p.sort_values("rho").head(5)[["metric", "rho", "monotone_frac", "auc_adjacent", "min_detect_level"]]
    out += ["Most sensitive metrics (Spearman rho of oriented score with degradation; more negative = more sensitive):\n",
            table(best), "\n", f"![{e} sweep](experiments/results/{e}/sweep.png)\n"]
    return "\n".join(out)


def main():
    L = ["# EXPERIMENT REGISTRY", "",
         "Generated by `tools/build_registry.py` from `experiments/results/` — numbers are read from result files. "
         "All experiments are SIMULATIONS of virtual participants unless marked REAL DATA. Simulations show how the "
         "measurement system behaves under modelled input conditions; they do not establish clinical effectiveness, "
         "or reliability or validity in human users. Code version: results regenerated after the independent review "
         "fixes (docs/review/RESPONSE_TO_SCIENCE_CORE_REVIEW.md). Re-run: `python -m neurometric.experiments.registry`.", ""]
    L += ["| ID | Experiment | Status | Hypothesis |", "|---|---|---|---|"]
    for k, (t, h, _, _) in H.items():
        st = "done" if (R / k).exists() and any((R / k).iterdir()) else "pending"
        L.append(f"| {k} | {t} | {st} | {h} |")
    L.append("")
    for k, (t, h, model, lim) in H.items():
        L += [f"## {k} — {t}", "", f"**Hypothesis.** {h}", "", f"**Model / dataset.** {model}", ""]
        d = R / k
        if k in SWEEPS:
            L.append(sweep_section(k))
        elif (d / "summary.json").exists():
            s = json.loads((d / "summary.json").read_text())
            L.append(render_summary(k, s, d))
        elif d.exists():
            files = sorted(p.name for p in d.iterdir())
            L.append("Result files: " + ", ".join(files) + "\n")
            js = [p for p in d.glob("*.json")]
            for j in js[:2]:
                try:
                    L.append(f"`{j.name}`: " + json.dumps(json.loads(j.read_text()))[:900] + "\n")
                except Exception:
                    pass
        else:
            L.append("_Not yet run._\n")
        L += [f"**Limitations.** {lim or 'See docs/science/SIMULATOR.md (no physiology; one control law per modality; reliability estimates are upper bounds).'}", ""]
    (ROOT / "EXPERIMENT_REGISTRY.md").write_text("\n".join(L))
    print("ok")


def render_summary(k, s, d):
    out = []
    if k == "G_metric_comparison" and (d / "ranking.csv").exists():
        rk = pd.read_csv(d / "ranking.csv")
        out += ["Metric ranking across all degradation sweeps:\n",
                table(rk, ["metric", "mean_sensitivity", "min_sensitivity", "mean_monotone_frac",
                           "max_floor_frac", "max_ceiling_frac", "baseline_retest_icc", "max_undefined_frac"]),
                "\n![sensitivity heatmap](experiments/results/G_metric_comparison/sensitivity_heatmap.png)\n"]
    elif k == "I_test_retest" and (d / "reliability.csv").exists():
        r = pd.read_csv(d / "reliability.csv")
        out += [table(r, ["modality", "metric", "length", "icc_a1", "spearman_brown_pred", "sem", "mdc95"]),
                "\n![reliability](experiments/results/I_test_retest/reliability_vs_length.png)\n"]
    elif k == "K_responsiveness" and (d / "responsiveness.csv").exists():
        r = pd.read_csv(d / "responsiveness.csv")
        out += [table(r, ["metric", "srm_improved", "guyatt_ri", "auc_improved_vs_stable", "icc_stable", "mdc95",
                          "frac_improved_exceeding_mdc", "frac_stable_exceeding_mdc"]),
                "\n![responsiveness](experiments/results/K_responsiveness/responsiveness_auc.png)\n"]
    elif k == "L_cross_modality" and (d / "means.csv").exists():
        r = pd.read_csv(d / "means.csv")
        cols = [c for c in ["mod", "iso_tp_bps", "iso_error_rate", "grid_accuracy", "grid_bitrate_bps", "type_wpm",
                            "type_ccpm", "adl_completion_rate", "adl_time_s"] if c in r]
        out += [table(r, cols), f"\nRank concordance (Kendall tau): {json.dumps({a: round(b, 2) for a, b in s.get('rank_concordance_kendall_tau', {}).items()})}\n",
                "\n![modalities](experiments/results/L_cross_modality/modalities.png)\n"]
    elif k == "M_user_variability" and (d / "variance_decomposition.csv").exists():
        r = pd.read_csv(d / "variance_decomposition.csv")
        out += [table(r), "\n![variance](experiments/results/M_user_variability/variance_decomposition.png)\n"]
    elif k == "N_missing_data" and (d / "results.csv").exists():
        r = pd.read_csv(d / "results.csv")
        out += [table(r, ["mechanism", "missing_frac_target", "actual_missing_frac", "mt_bias_ms", "success_bias",
                          "mt_rank_corr_with_full"]),
                "\n![missing](experiments/results/N_missing_data/missing_bias.png)\n"]
    elif k == "H_adaptive" and (d / "comparison.csv").exists():
        r = pd.read_csv(d / "comparison.csv")
        out += [table(r), "\n![adaptive](experiments/results/H_adaptive/fixed_vs_adaptive.png)\n"]
    elif k == "X1_external_mc_rtt":
        out += [f"REAL DATA. Reaches: {s['n_reaches']}; median reach time {s['median_reach_time_ms']:.0f} ms; "
                f"median path efficiency {s['median_path_efficiency']:.3f}; effective throughput (mean over distance bins) "
                f"{s['pooled_TPe_bps_mean_of_bins']:.2f} bit/s; stream integrity {s['stream_integrity']}.\n",
                table(pd.DataFrame(s["throughput_by_distance"])),
                "\n![mc_rtt](experiments/results/X1_external_mc_rtt/mc_rtt_metrics.png)\n"]
    elif k == "P_reproducibility":
        out.append(f"In-process and 2-process pool hashes identical: **{s.get('identical')}**; different seed differs: {s.get('different_seed_differs')}.\n")
    elif k == "O_telemetry_integrity":
        out.append(f"{s['passed']}/{s['n_tests']} fault-injection tests passed. {s['design']}\n")
    elif k == "S_event_latency":
        med = s.get("median", {})
        out.append(f"Python pipeline on a {s['session']['events']:,}-event, {s['session']['trials']}-trial session: "
                   f"validation {med.get('validate_events_per_s', 0):,.0f} events/s; segmentation + scoring "
                   f"{med.get('segment_and_score_ms', 0):.0f} ms; JSON round trip identical: {s.get('all_roundtrips_identical')}; "
                   f"per-event validation p99 {s['per_event_validate_us']['p99']:.1f} µs.\n")
        for j in sorted(d.glob("browser_*.json"))[:2]:
            out.append(f"Browser (`{j.name}`): " + json.dumps(json.loads(j.read_text()))[:700] + "\n")
    else:
        out.append("```\n" + json.dumps({kk: v for kk, v in s.items() if kk not in ("software",)}, indent=1)[:2500] + "\n```\n")
    return "\n".join(out)


if __name__ == "__main__":
    main()
