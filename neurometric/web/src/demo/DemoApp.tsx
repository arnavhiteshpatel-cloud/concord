// Live degradation demo: the viewer's own mouse / touch / keyboard movements pass through a
// TypeScript port of DegradedChannel in real time, on an ISO ring and a grid task, with a
// side-by-side table of results across conditions. "Watch a virtual user" replays trajectories
// pre-computed by the Python simulator, so the demo works without a mouse.
//
// SIMULATED input degradation - not a model of any specific BCI.

import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { DegradedChannel, PROFILES, type ControlMode, type DegradationConfig } from "./degraded";
import { Rng } from "./rng";
import { achievedBitrate, fittsThroughput, trialMetrics, type Trial } from "../metrics/pointing";
import { toTaskSpace } from "../input/pointer";
import { TASK_H, TASK_W } from "../input/space";
import type { Settings } from "../a11y/settings";

const DT = 10;
const ISO_D = 512;
const ISO_W = 64;

interface RingPt {
  x: number;
  y: number;
  w: number;
}

function isoRing(D: number, W: number, n = 13): RingPt[] {
  // same ordering as neurometric.tasks.battery.iso_ring (exported stimuli are used when loaded)
  const out: RingPt[] = [];
  let k = 0;
  for (let i = 0; i < n; i++) {
    const a = (2 * Math.PI * k) / n - Math.PI / 2;
    out.push({ x: Math.round((640 + (D / 2) * Math.cos(a)) * 100) / 100, y: Math.round((400 + (D / 2) * Math.sin(a)) * 100) / 100, w: W });
    k = (k + (n + 1) / 2) % n;
  }
  return out;
}

const GRID = Array.from({ length: 24 }, (_, id) => ({ id, x: 640 - 3 * 120 + 60 + (id % 6) * 120, y: 400 - 2 * 120 + 60 + Math.floor(id / 6) * 120, w: 100, h: 100 }));
const GRID_CUES = [3, 17, 8, 21, 0, 12, 5, 19, 10, 14];

interface ResultRow {
  condition: string;
  source: string;
  mode: string;
  task: string;
  tp: number;
  err: number;
  mt: number;
  eff: number;
  bitrate: number;
  n: number;
}

const PARAMS: { key: keyof DegradationConfig; label: string; min: number; max: number; step: number; unit: string; group: string }[] = [
  { key: "gain", label: "Gain", min: 0.2, max: 2, step: 0.05, unit: "×", group: "Continuous channel" },
  { key: "bias_deg", label: "Direction bias", min: -45, max: 45, step: 1, unit: "°", group: "Continuous channel" },
  { key: "asymmetry", label: "Left/right asymmetry", min: -0.8, max: 0.8, step: 0.05, unit: "", group: "Continuous channel" },
  { key: "white_noise", label: "White noise SD", min: 0, max: 200, step: 5, unit: "px/s or px", group: "Noise and drift" },
  { key: "correlated_noise", label: "AR(1) noise SD", min: 0, max: 200, step: 5, unit: "px/s or px", group: "Noise and drift" },
  { key: "correlated_tau_ms", label: "AR(1) time constant", min: 50, max: 2000, step: 50, unit: "ms", group: "Noise and drift" },
  { key: "drift", label: "Drift", min: 0, max: 100, step: 1, unit: "px/s or px", group: "Noise and drift" },
  { key: "smoothing_tau_ms", label: "Smoothing", min: 0, max: 400, step: 10, unit: "ms", group: "Decoder processing" },
  { key: "quantization", label: "Quantization step", min: 0, max: 100, step: 5, unit: "px/s or px", group: "Decoder processing" },
  { key: "direction_bins", label: "Direction bins (0 = off)", min: 0, max: 16, step: 1, unit: "", group: "Decoder processing" },
  { key: "update_hz", label: "Update rate (0 = every tick)", min: 0, max: 100, step: 5, unit: "Hz", group: "Decoder processing" },
  { key: "latency_ms", label: "Latency", min: 0, max: 500, step: 10, unit: "ms", group: "Timing" },
  { key: "latency_jitter_ms", label: "Latency jitter (mean)", min: 0, max: 200, step: 10, unit: "ms", group: "Timing" },
  { key: "dropout_enter_per_s", label: "Dropout rate", min: 0, max: 0.5, step: 0.01, unit: "/s", group: "Interruptions" },
  { key: "dropout_mean_ms", label: "Dropout duration", min: 0, max: 3000, step: 100, unit: "ms", group: "Interruptions" },
  { key: "loss_of_control_per_min", label: "Loss of control rate", min: 0, max: 5, step: 0.1, unit: "/min", group: "Interruptions" },
  { key: "loss_of_control_mean_ms", label: "Loss of control duration", min: 0, max: 5000, step: 100, unit: "ms", group: "Interruptions" },
  { key: "recovery_ms", label: "Recovery ramp", min: 0, max: 3000, step: 100, unit: "ms", group: "Interruptions" },
  { key: "select_miss_prob", label: "Selection miss probability", min: 0, max: 0.8, step: 0.05, unit: "", group: "Selection channel" },
  { key: "select_latency_ms", label: "Selection latency", min: 0, max: 500, step: 10, unit: "ms", group: "Selection channel" },
  { key: "false_select_per_min", label: "False activations", min: 0, max: 20, step: 0.5, unit: "/min", group: "Selection channel" },
];

function f(v: number, d = 2): string {
  return Number.isFinite(v) ? v.toFixed(d) : "–";
}

export function DemoApp({ settings }: { settings: Settings }) {
  const [tab, setTab] = useState<"live" | "watch">("live");
  const [results, setResults] = useState<ResultRow[]>([]);
  return (
    <section aria-labelledby="demo-h">
      <h2 id="demo-h" tabIndex={-1}>
        Live input degradation demo
      </h2>
      <p className="sim-label" role="note">
        SIMULATED input degradation — not a model of any specific BCI
      </p>
      <p>
        Your own pointer movements are passed through an experimental model of a degraded control channel (gain, bias, noise, drift, smoothing,
        quantisation, update rate, latency, dropouts, loss of control and an unreliable selection channel). The same model is used by the
        NeuroMetric simulator. Results here are provisional demo numbers.
      </p>
      <div className="row" role="group" aria-label="Demo mode">
        <button type="button" aria-pressed={tab === "live"} onClick={() => setTab("live")} id="demo-tab-live">
          Try it yourself
        </button>
        <button type="button" aria-pressed={tab === "watch"} onClick={() => setTab("watch")} id="demo-tab-watch">
          Watch a virtual user
        </button>
      </div>
      {tab === "live" ? <LiveDemo settings={settings} onResult={(r) => setResults((x) => [...x, r])} /> : <WatchDemo onResults={(rs) => setResults((x) => [...x.filter((r) => r.source !== "virtual user"), ...rs])} />}
      <ResultsTable rows={results} />
    </section>
  );
}

function ResultsTable({ rows }: { rows: ResultRow[] }) {
  return (
    <div className="table-scroll" role="region" aria-labelledby="demo-results-cap" tabIndex={0}>
    <table style={{ marginTop: 16 }} id="demo-results">
      <caption id="demo-results-cap">Results across conditions (provisional; computed in the browser)</caption>
      <thead>
        <tr>
          <th scope="col">Condition</th>
          <th scope="col">Source</th>
          <th scope="col">Control mode</th>
          <th scope="col">Task</th>
          <th scope="col">Throughput (bit/s)</th>
          <th scope="col">Error rate</th>
          <th scope="col">Movement time (ms)</th>
          <th scope="col">Path efficiency</th>
          <th scope="col">Achieved bitrate (bit/s)</th>
          <th scope="col">Selections</th>
        </tr>
      </thead>
      <tbody>
        {rows.length === 0 && (
          <tr>
            <td colSpan={10}>No runs yet. Complete a run or open &ldquo;Watch a virtual user&rdquo;.</td>
          </tr>
        )}
        {rows.map((r, i) => (
          <tr key={i}>
            <th scope="row">{r.condition}</th>
            <td>{r.source}</td>
            <td>{r.mode}</td>
            <td>{r.task}</td>
            <td>{f(r.tp)}</td>
            <td>{f(r.err * 100, 0)} %</td>
            <td>{f(r.mt, 0)}</td>
            <td>{f(r.eff)}</td>
            <td>{f(r.bitrate)}</td>
            <td>{r.n}</td>
          </tr>
        ))}
      </tbody>
    </table>
    </div>
  );
}

function useScale(wrap: React.RefObject<HTMLDivElement>): number {
  const [s, setS] = useState(0.5);
  useLayoutEffect(() => {
    const el = wrap.current;
    if (!el) return;
    const fit = () => {
      const r = el.getBoundingClientRect();
      setS(Math.max(0.1, Math.min(r.width / TASK_W, r.height / TASK_H)));
    };
    fit();
    const ro = new ResizeObserver(fit);
    ro.observe(el);
    return () => ro.disconnect();
  }, [wrap]);
  return s;
}

// ----------------------------------------------------------------------------- live demo
function LiveDemo({ settings, onResult }: { settings: Settings; onResult: (r: ResultRow) => void }) {
  const [cfg, setCfg] = useState<DegradationConfig>(PROFILES.bci_good);
  const [preset, setPreset] = useState("bci_good");
  const [mode, setMode] = useState<ControlMode>("velocity");
  const [task, setTask] = useState<"iso" | "grid">("iso");
  const [status, setStatus] = useState("");
  const [cursor, setCursor] = useState({ x: 640, y: 400 });
  const [k, setK] = useState(0);
  const wrapRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLDivElement>(null);
  const scale = useScale(wrapRef);
  const ring = useMemo(() => isoRing(ISO_D, ISO_W), []);
  const eng = useRef({
    ch: new DegradedChannel(cfg, DT, mode, new Rng(7)),
    ptr: null as { x: number; y: number } | null,
    prevPtr: null as { x: number; y: number } | null,
    keys: new Set<string>(),
    selIntent: false,
    cursor: { x: 640, y: 400 },
    last: 0,
    simT: 0,
    k: 0,
    trials: [] as Trial[],
    samples: [] as { t: number; x: number; y: number }[],
    trialStart: { x: 640, y: 400, t: 0 },
    grid: { nc: 0, ni: 0, secs: 0, empty: 0 },
  });

  const reset = (c: DegradationConfig = cfg, m: ControlMode = mode) => {
    const e = eng.current;
    e.ch = new DegradedChannel(c, DT, m, new Rng(7));
    e.k = 0;
    e.trials = [];
    e.samples = [];
    e.grid = { nc: 0, ni: 0, secs: 0, empty: 0 };
    e.cursor = { x: 640, y: 400 };
    e.prevPtr = null;
    setK(0);
    setStatus(task === "iso" ? "Move the cursor onto the highlighted circle and click (or press Space) to start." : "Select the starred item.");
  };
  useEffect(() => reset(), [task]); // eslint-disable-line react-hooks/exhaustive-deps

  const applyPreset = (name: string) => {
    setPreset(name);
    setCfg(PROFILES[name]);
    reset(PROFILES[name]);
  };
  const setParam = (key: keyof DegradationConfig, v: number) => {
    const c = { ...cfg, [key]: v } as DegradationConfig;
    setPreset("custom");
    setCfg(c);
    reset(c);
  };

  const condName = preset === "custom" ? "custom" : preset;

  const onSelectAt = (x: number, y: number) => {
    const e = eng.current;
    if (task === "iso") {
      const tg = ring[e.k];
      const hit = Math.abs(x - tg.x) <= tg.w / 2 && Math.abs(y - tg.y) <= tg.w / 2;
      if (e.k === 0) {
        if (!hit) return;
        e.trialStart = { x, y, t: e.simT };
        e.samples = [{ t: e.simT, x, y }];
        e.k = 1;
        setK(1);
        setStatus("Follow the highlight across the ring.");
        return;
      }
      const s = e.samples.filter((p) => p.t >= e.trialStart.t);
      e.trials.push({
        t_ms: s.map((p) => p.t - e.trialStart.t), xy: s.map((p) => [p.x, p.y]), start: [e.trialStart.x, e.trialStart.y], target: [tg.x, tg.y],
        half: [tg.w / 2, tg.w / 2], sel_t: e.simT - e.trialStart.t, sel_pos: [x, y], sel_item: hit ? 0 : -1,
      });
      e.trialStart = { x, y, t: e.simT };
      e.samples = [{ t: e.simT, x, y }];
      e.k++;
      setK(e.k);
      if (e.k >= ring.length) {
        const r = fittsThroughput(e.trials, ISO_D, ISO_W);
        const eff = e.trials.map((t) => trialMetrics(t).path_efficiency).filter(Number.isFinite);
        onResult({ condition: condName, source: "you (live)", mode, task: "ISO ring", tp: r.tp_effective_bps, err: r.error_rate, mt: r.mt_ms, eff: eff.reduce((a, b) => a + b, 0) / (eff.length || 1), bitrate: NaN, n: r.n });
        setStatus(`Run complete: throughput ${f(r.tp_effective_bps)} bit/s. Change the condition or start again.`);
        e.k = 0;
        e.trials = [];
        setK(0);
      }
    } else {
      const cue = GRID_CUES[e.k];
      const it = GRID.find((g) => Math.abs(x - g.x) <= g.w / 2 && Math.abs(y - g.y) <= g.h / 2);
      if (!it) {
        e.grid.empty++;
        return;
      }
      if (it.id === cue) e.grid.nc++;
      else e.grid.ni++;
      e.grid.secs += (e.simT - e.trialStart.t) / 1000;
      e.trialStart = { x, y, t: e.simT };
      e.k++;
      setK(e.k);
      setStatus(it.id === cue ? "Correct." : "Wrong item.");
      if (e.k >= GRID_CUES.length) {
        const br = achievedBitrate(e.grid.nc, e.grid.ni, GRID.length, e.grid.secs);
        onResult({ condition: condName, source: "you (live)", mode, task: "Grid 4×6", tp: NaN, err: e.grid.ni / GRID_CUES.length, mt: (e.grid.secs * 1000) / GRID_CUES.length, eff: NaN, bitrate: br, n: GRID_CUES.length });
        setStatus(`Run complete: achieved bitrate ${f(br)} bit/s.`);
        e.k = 0;
        e.grid = { nc: 0, ni: 0, secs: 0, empty: 0 };
        setK(0);
      }
    }
  };
  const selectRef = useRef(onSelectAt);
  selectRef.current = onSelectAt;

  // fixed-step simulation loop (10 ms ticks) driven by requestAnimationFrame
  useEffect(() => {
    let raf = 0;
    const e = eng.current;
    e.last = performance.now();
    const loop = (now: number) => {
      raf = requestAnimationFrame(loop);
      let n = Math.min(20, Math.floor((now - e.last) / DT));
      if (n <= 0) return;
      e.last += n * DT;
      const kv = { x: 0, y: 0 };
      if (e.keys.has("ArrowLeft")) kv.x -= 400;
      if (e.keys.has("ArrowRight")) kv.x += 400;
      if (e.keys.has("ArrowUp")) kv.y -= 400;
      if (e.keys.has("ArrowDown")) kv.y += 400;
      const ch = e.ch;
      // pointer displacement since the last frame, spread over the ticks of this frame
      const ptr = e.ptr;
      const dPtr = ptr && e.prevPtr ? { x: (ptr.x - e.prevPtr.x) / n, y: (ptr.y - e.prevPtr.y) / n } : { x: 0, y: 0 };
      e.prevPtr = ptr ? { ...ptr } : null;
      while (n-- > 0) {
        e.simT += DT;
        let intent: [number, number];
        if (ch.mode === "velocity") intent = [(dPtr.x * 1000) / DT + kv.x, (dPtr.y * 1000) / DT + kv.y];
        else {
          const base = ptr ?? e.cursor;
          intent = [base.x + (kv.x * DT) / 1000, base.y + (kv.y * DT) / 1000];
          if (!ptr && (kv.x || kv.y)) e.ptr = { x: intent[0], y: intent[1] };
        }
        const { out, select } = ch.step(intent, e.selIntent);
        if (ch.mode === "velocity") e.cursor = { x: e.cursor.x + (out[0] * DT) / 1000, y: e.cursor.y + (out[1] * DT) / 1000 };
        else e.cursor = { x: out[0], y: out[1] };
        e.cursor = { x: Math.min(TASK_W, Math.max(0, e.cursor.x)), y: Math.min(TASK_H, Math.max(0, e.cursor.y)) };
        e.samples.push({ t: e.simT, x: e.cursor.x, y: e.cursor.y });
        if (e.samples.length > 3000) e.samples.splice(0, 1000);
        if (select) selectRef.current(e.cursor.x, e.cursor.y);
      }
      setCursor(e.cursor);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, []);

  // pointer + keyboard on the demo canvas only
  const onPointer = (ev: React.PointerEvent) => {
    const rect = canvasRef.current!.getBoundingClientRect();
    eng.current.ptr = toTaskSpace(rect, ev.clientX, ev.clientY);
  };

  const groups = [...new Set(PARAMS.map((p) => p.group))];
  return (
    <div>
      <div className="row" role="group" aria-label="Presets" style={{ margin: "12px 0" }}>
        {Object.keys(PROFILES).map((n) => (
          <button key={n} type="button" aria-pressed={preset === n} onClick={() => applyPreset(n)} id={`preset-${n}`}>
            {n}
          </button>
        ))}
        <span className="muted">Same values as the Python simulator&apos;s PROFILES.</span>
      </div>
      <div className="row" style={{ marginBottom: 12 }}>
        <div role="group" aria-label="Control mode" className="row">
          {(["velocity", "position"] as ControlMode[]).map((m) => (
            <button key={m} type="button" aria-pressed={mode === m} onClick={() => { setMode(m); reset(cfg, m); }}>
              {m === "velocity" ? "Velocity control (BCI-like)" : "Position control (pointer-like)"}
            </button>
          ))}
        </div>
        <div role="group" aria-label="Task" className="row">
          <button type="button" aria-pressed={task === "iso"} onClick={() => setTask("iso")}>ISO ring</button>
          <button type="button" aria-pressed={task === "grid"} onClick={() => setTask("grid")}>Grid</button>
        </div>
        <button type="button" onClick={() => reset()}>Restart run</button>
      </div>
      <p role="status" aria-live="polite">{status}</p>
      <div className="grid2" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(min(300px, 100%), 1fr))" }}>
        <div ref={wrapRef} className="canvas-wrap" style={{ aspectRatio: "1280 / 800", height: "auto" }}>
          <div
            ref={canvasRef}
            className="task-canvas"
            tabIndex={0}
            role="group"
            aria-label="Demo canvas. Move the mouse or use the arrow keys to steer the degraded cursor; click or hold Space to select."
            style={{ transform: `scale(${scale})`, cursor: "crosshair" }}
            onPointerMove={onPointer}
            onPointerDown={(ev) => { onPointer(ev); eng.current.selIntent = true; }}
            onPointerUp={() => { eng.current.selIntent = false; }}
            onPointerLeave={() => { eng.current.ptr = null; eng.current.prevPtr = null; eng.current.selIntent = false; }}
            onKeyDown={(ev) => {
              if (ev.key.startsWith("Arrow")) { eng.current.keys.add(ev.key); ev.preventDefault(); }
              if (ev.key === " " || ev.key === "Enter") { eng.current.selIntent = true; ev.preventDefault(); }
            }}
            onKeyUp={(ev) => {
              eng.current.keys.delete(ev.key);
              if (ev.key === " " || ev.key === "Enter") eng.current.selIntent = false;
            }}
            onBlur={() => { eng.current.keys.clear(); eng.current.selIntent = false; }}
          >
            <p className="sim-label" style={{ position: "absolute", left: 12, top: 8, margin: 0, background: "var(--bg)" }} aria-hidden="true">SIMULATED degradation</p>
            {task === "iso"
              ? ring.map((t, j) => <div key={j} className={`titem circle ${j === k ? "target" : "ghost"}`} style={{ left: t.x, top: t.y, width: t.w, height: t.w }} aria-hidden="true" />)
              : GRID.map((g) => <div key={g.id} className={`titem ${g.id === GRID_CUES[k] ? "cued" : ""}`} style={{ left: g.x, top: g.y, width: g.w, height: g.h }} aria-hidden="true">{g.id === GRID_CUES[k] ? "★" : ""}</div>)}
            <div className="cursor-dot" style={{ left: cursor.x, top: cursor.y }} aria-hidden="true" />
          </div>
        </div>
        <div style={{ maxHeight: "70vh", overflowY: "auto" }}>
          {groups.map((g) => (
            <fieldset key={g}>
              <legend>{g}</legend>
              {PARAMS.filter((p) => p.group === g).map((p) => (
                <div key={p.key} style={{ marginBottom: 8 }}>
                  <label htmlFor={`p-${p.key}`}>
                    {p.label}: <output htmlFor={`p-${p.key}`}>{String(cfg[p.key])}</output> {p.unit}
                  </label>
                  <input id={`p-${p.key}`} type="range" min={p.min} max={p.max} step={p.step} value={Number(cfg[p.key])} onChange={(e) => setParam(p.key, Number(e.target.value))} />
                </div>
              ))}
            </fieldset>
          ))}
          <p className="muted">Velocity mode integrates the decoded velocity (like most intracortical BCI cursor decoders); position mode degrades pointer displacements. Settings: {settings.selection} selection is not used here; the demo uses click / Space.</p>
          <button type="button" onClick={() => applyPreset("identity")}>Reset to identity (no degradation)</button>
        </div>
      </div>
    </div>
  );
}

// ----------------------------------------------------------------------------- watch mode
interface TraceStep {
  xy: [number | null, number | null][];
  dt_ms: number;
  sel_t: number | null;
  sel_pos: [number, number];
  sel_item: number;
  target: [number, number];
  half: [number, number];
  start: [number, number];
  cue?: number;
  sel_item_id?: number;
}
interface TraceCond {
  name: string;
  modality: string;
  profile: string;
  control_mode: string;
  iso_steps: TraceStep[][];
  grid_steps: TraceStep[];
  python_metrics: { iso: { tp_effective_bps: number; error_rate: number; mt_ms: number; path_efficiency: number }[]; grid: { achieved_bitrate_bps: number } };
}
interface Traces {
  label: string;
  iso: { D: number; W: number; ring: RingPt[] };
  grid: { items: { id: number; x: number; y: number; w: number; h: number }[]; cues: number[] };
  conditions: TraceCond[];
}

function stepToTrial(s: TraceStep): Trial {
  const xy = s.xy.filter((p) => p[0] !== null) as [number, number][];
  return { t_ms: xy.map((_, i) => i * s.dt_ms), xy, start: s.start, target: s.target, half: s.half, sel_t: s.sel_t, sel_pos: s.sel_pos, sel_item: s.sel_item };
}

export function traceMetrics(c: TraceCond, D: number, W: number, nItems: number): ResultRow[] {
  const trials = c.iso_steps.map((st) => stepToTrial(st[0]));
  const r = fittsThroughput(trials, D, W);
  const eff = trials.map((t) => trialMetrics(t).path_efficiency).filter(Number.isFinite);
  const g = c.grid_steps;
  const nc = g.filter((s) => s.sel_item === 0).length;
  const ni = g.filter((s) => s.sel_item > 0).length;
  const secs = g.filter((s) => s.sel_t !== null).reduce((a, s) => a + (s.sel_t ?? 0), 0) / 1000;
  return [
    { condition: c.name, source: "virtual user", mode: c.control_mode, task: "ISO ring", tp: r.tp_effective_bps, err: r.error_rate, mt: r.mt_ms, eff: eff.reduce((a, b) => a + b, 0) / (eff.length || 1), bitrate: NaN, n: r.n },
    { condition: c.name, source: "virtual user", mode: c.control_mode, task: "Grid 4×6", tp: NaN, err: g.length ? ni / g.length : NaN, mt: g.length ? (secs * 1000) / g.length : NaN, eff: NaN, bitrate: achievedBitrate(nc, ni, nItems, secs), n: g.length },
  ];
}

function WatchDemo({ onResults }: { onResults: (r: ResultRow[]) => void }) {
  const [data, setData] = useState<Traces | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [ci, setCi] = useState(0);
  const [task, setTask] = useState<"iso" | "grid">("iso");
  const [playing, setPlaying] = useState(false);
  const [frame, setFrame] = useState<{ step: number; x: number; y: number } | null>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const scale = useScale(wrapRef);
  useEffect(() => {
    fetch("demo/traces.json")
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((d: Traces) => {
        setData(d);
        onResults(d.conditions.flatMap((c) => traceMetrics(c, d.iso.D, d.iso.W, d.grid.items.length)));
      }, (e) => setErr(String(e)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  useEffect(() => {
    if (!playing || !data) return;
    const c = data.conditions[ci];
    const steps = task === "iso" ? c.iso_steps.map((s) => s[0]) : c.grid_steps;
    let raf = 0;
    const t0 = performance.now();
    const loop = (now: number) => {
      let el = now - t0;
      for (let s = 0; s < steps.length; s++) {
        const dur = steps[s].xy.length * steps[s].dt_ms;
        if (el < dur) {
          const p = steps[s].xy[Math.min(steps[s].xy.length - 1, Math.floor(el / steps[s].dt_ms))];
          setFrame({ step: s, x: p[0] ?? 0, y: p[1] ?? 0 });
          raf = requestAnimationFrame(loop);
          return;
        }
        el -= dur;
      }
      setPlaying(false);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, [playing, ci, task, data]);
  if (err) return <p className="warn" role="alert">Could not load the virtual-user traces: {err}</p>;
  if (!data) return <p role="status">Loading virtual-user traces…</p>;
  const c = data.conditions[ci];
  const st = frame ? (task === "iso" ? c.iso_steps[frame.step]?.[0] : c.grid_steps[frame.step]) : null;
  return (
    <div>
      <p>
        Pre-computed by the Python simulator (closed-loop virtual users perceiving the degraded cursor with a delay). Python&apos;s own scores for this
        condition: throughput {f(c.python_metrics.iso[0].tp_effective_bps)} bit/s (virtual user 1), grid achieved bitrate {f(c.python_metrics.grid.achieved_bitrate_bps)} bit/s.
      </p>
      <div className="row" role="group" aria-label="Condition">
        {data.conditions.map((cc, i) => (
          <button key={cc.name} type="button" aria-pressed={ci === i} onClick={() => { setCi(i); setPlaying(false); setFrame(null); }}>
            {cc.name}
          </button>
        ))}
      </div>
      <div className="row" role="group" aria-label="Task" style={{ marginTop: 8 }}>
        <button type="button" aria-pressed={task === "iso"} onClick={() => { setTask("iso"); setFrame(null); }}>ISO ring</button>
        <button type="button" aria-pressed={task === "grid"} onClick={() => { setTask("grid"); setFrame(null); }}>Grid</button>
        <button type="button" className="primary" onClick={() => setPlaying(!playing)} id="watch-play">
          {playing ? "Stop playback" : "Play"}
        </button>
      </div>
      <p role="status" aria-live="polite">{frame ? `Selection ${frame.step + 1}` : "Press Play to watch the virtual user."}</p>
      <div ref={wrapRef} className="canvas-wrap" style={{ aspectRatio: "1280 / 800", height: "auto", maxWidth: 960 }}>
        <div className="task-canvas" style={{ transform: `scale(${scale})` }} aria-hidden="true">
          <p className="sim-label" style={{ position: "absolute", left: 12, top: 8, margin: 0, background: "var(--bg)" }}>SIMULATED virtual user</p>
          {task === "iso"
            ? data.iso.ring.map((t, j) => <div key={j} className={`titem circle ${st && Math.abs(st.target[0] - t.x) < 0.5 && Math.abs(st.target[1] - t.y) < 0.5 ? "target" : "ghost"}`} style={{ left: t.x, top: t.y, width: t.w, height: t.w }} />)
            : data.grid.items.map((g) => <div key={g.id} className={`titem ${st && st.cue === g.id ? "cued" : ""}`} style={{ left: g.x, top: g.y, width: g.w, height: g.h }} />)}
          {frame && <div className="cursor-dot" style={{ left: frame.x, top: frame.y }} />}
        </div>
      </div>
    </div>
  );
}
