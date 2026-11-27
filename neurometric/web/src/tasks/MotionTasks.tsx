// B1 straight-line steering (tunnel), B2 continuous tracking, D1 drag and drop.

import { useEffect, useRef, useState } from "react";
import type { StreamHandle } from "../input/recorder";
import { fmt, type TaskApi, type TaskItem } from "./api";
import { limitN, mean } from "./common";
import type { ProvisionalSummary } from "./session";

// ----------------------------------------------------------------------------- B1 steering
export function SteeringTask({ api }: { api: TaskApi }) {
  const p = api.stim.params;
  const L = p.L ?? 600;
  const Ws: number[] = p.W ?? [40, 80];
  const n = limitN(api, "trials", p.n ?? 8, 2);
  const [i, setI] = useState(0);
  const [done, setDone] = useState(false);
  const W = Ws[i % Ws.length];
  const x0 = 640 - L / 2;
  const x1 = 640 + L / 2;
  const st = useRef({ phase: "wait" as "wait" | "ready" | "moving", tStart: 0, exits: 0, outside: false, dev2: 0, nDev: 0 });
  const rows = useRef<{ mt: number; exits: number; rms: number }[]>([]);

  const summarize = (): ProvisionalSummary => {
    const r = rows.current;
    const values = { trials: r.length, movement_time_ms_mean: mean(r.map((x) => x.mt)), tunnel_exits_mean: mean(r.map((x) => x.exits)), rms_path_deviation_px_mean: mean(r.map((x) => x.rms)) };
    return { values, rows: [["Trials", String(r.length)], ["Mean movement time", fmt(values.movement_time_ms_mean, 0) + " ms"], ["Mean tunnel exits", fmt(values.tunnel_exits_mean, 1)], ["RMS path deviation", fmt(values.rms_path_deviation_px_mean, 1) + " px"]] };
  };
  const next = () => {
    if (i + 1 >= n) {
      setDone(true);
      api.finish(summarize());
    } else setI(i + 1);
  };

  api.handlers = {
    virtualCursor: true,
    summarize,
    onMove: (x, y, t) => {
      const s = st.current;
      if (!api.session.inTrial) return;
      const inStart = x >= x0 - 80 && x < x0 && Math.abs(y - 400) <= W / 2 + 20;
      if (s.phase === "wait" && inStart) {
        s.phase = "ready";
        api.announce("In the start zone. Move right along the tunnel.");
      } else if (s.phase === "ready" && x >= x0) {
        s.phase = "moving";
        s.tStart = t;
        api.session.marker("movement_start", { trial: i }, t);
      } else if (s.phase === "ready" && !inStart && x < x0 - 80) s.phase = "wait";
      if (s.phase === "moving") {
        const out = Math.abs(y - 400) > W / 2 && x <= x1;
        if (out && !s.outside) s.exits++;
        s.outside = out;
        s.dev2 += (y - 400) ** 2;
        s.nDev++;
        if (x > x1) {
          const mt = t - s.tStart;
          const rms = Math.sqrt(s.dev2 / Math.max(1, s.nDev));
          rows.current.push({ mt, exits: s.exits, rms });
          api.session.marker("trial_end", { trial: i, outcome: "hit", movement_time_ms: mt, tunnel_exits: s.exits, rms_path_deviation_px: rms }, t);
          api.announce(`Done. ${s.exits} exits.`);
          next();
        }
      }
    },
    onSkip: () => {
      if (!api.session.inTrial) return;
      api.session.marker("trial_end", { trial: i, outcome: "abandoned" });
      next();
    },
    onPause: () => {
      if (api.session.inTrial) api.session.marker("trial_end", { trial: i, outcome: "abandoned", reason: "paused" });
    },
    onResume: () => {
      st.current = { phase: "wait", tStart: 0, exits: 0, outside: false, dev2: 0, nDev: 0 };
      api.stimulusOnNextFrame({ trial: i, tunnel: { x0, x1, y: 400, w: W }, L, W, repeat: true });
    },
  };

  useEffect(() => {
    if (done) return;
    st.current = { phase: "wait", tStart: 0, exits: 0, outside: false, dev2: 0, nDev: 0 };
    api.setItems([]);
    api.setInstruction(`Trial ${i + 1} of ${n}. Move into the green start zone on the left, then steer along the tunnel to the end zone without touching the edges.`);
    api.stimulusOnNextFrame({ trial: i, tunnel: { x0, x1, y: 400, w: W }, L, W });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [i, done]);

  if (done) return <p className="cue-box">Task complete.</p>;
  return (
    <svg width={1280} height={800} aria-hidden="true" style={{ position: "absolute", inset: 0 }}>
      <rect x={x0 - 80} y={400 - W / 2 - 20} width={80} height={W + 40} fill="var(--cue)" opacity={0.6} />
      <rect x={x0} y={400 - W / 2} width={L} height={W} fill="none" stroke="var(--fg)" strokeWidth={4} />
      <rect x={x1} y={400 - W / 2 - 20} width={80} height={W + 40} fill="var(--target)" opacity={0.6} />
    </svg>
  );
}

// ----------------------------------------------------------------------------- B2 tracking
interface Comp {
  f: number;
  ax: number;
  ay: number;
  px: number;
  py: number;
}

/** Target position at time s (seconds since onset); amplitudes scaled to stay on the canvas. */
export function trackingTarget(comps: Comp[], s: number, speed: number): { x: number; y: number; sx: number; sy: number } {
  const sumX = comps.reduce((a, c) => a + c.ax, 0);
  const sumY = comps.reduce((a, c) => a + c.ay, 0);
  const sx = Math.min(1, 520 / sumX);
  const sy = Math.min(1, 320 / sumY);
  let x = 640;
  let y = 400;
  for (const c of comps) {
    x += sx * c.ax * Math.sin(2 * Math.PI * c.f * s * speed + c.px);
    y += sy * c.ay * Math.sin(2 * Math.PI * c.f * s * speed + c.py);
  }
  return { x, y, sx, sy };
}

export function TrackingTask({ api }: { api: TaskApi }) {
  const p = api.stim.params;
  const comps = (api.stim.path ?? []) as Comp[];
  const R = p.radius ?? 40;
  const n = limitN(api, "trials", p.n ?? 3, 1);
  const duration = api.settings.short || api.limits.n ? Math.min(p.duration_ms ?? 30000, (api.limits.n ?? 8) * 1000) : p.duration_ms ?? 30000;
  const speed = api.reducedMotion ? 0.5 : 1; // reduced motion: slower path
  const [i, setI] = useState(0);
  const [running, setRunning] = useState(false);
  const [done, setDone] = useState(false);
  const tgtRef = useRef<HTMLDivElement>(null);
  const rows = useRef<{ rms: number; onTarget: number }[]>([]);
  const t0 = useRef(0);
  const samples = useRef<{ e: number }[]>([]);

  const summarize = (): ProvisionalSummary => {
    const r = rows.current;
    const values = { trials: r.length, rms_error_px_mean: mean(r.map((x) => x.rms)), time_on_target_mean: mean(r.map((x) => x.onTarget)) };
    return { values, rows: [["Trials", String(r.length)], ["RMS error", fmt(values.rms_error_px_mean, 1) + " px"], ["Time on target", fmt(values.time_on_target_mean * 100, 0) + " %"], ["Path speed", speed === 1 ? "standard" : "slower (reduced motion)"]] };
  };

  const startItem: TaskItem = { id: "track-start", x: 640, y: 400, w: 160, h: 90, label: "Start tracking" };

  const endTrial = (outcome: string) => {
    setRunning(false);
    const ss = samples.current.filter((_, k) => k * 16.7 >= 0);
    const e = ss.map((x) => x.e);
    const rms = Math.sqrt(mean(e.map((v) => v * v)));
    const onT = mean(e.map((v) => (v <= R ? 1 : 0)));
    if (outcome === "completed") rows.current.push({ rms, onTarget: onT });
    api.session.marker("trial_end", { trial: i, outcome, ...(outcome === "completed" ? { rms_error_px: rms, time_on_target: onT } : {}) });
    if (i + 1 >= n) {
      setDone(true);
      api.finish(summarize());
    } else setI(i + 1);
  };

  api.handlers = {
    virtualCursor: true,
    summarize,
    onSelect: (s) => {
      if (running || s.item?.id !== "track-start") return;
      setRunning(true);
    },
    onSkip: () => running && endTrial("abandoned"),
    onPause: () => running && endTrial("abandoned"),
  };

  useEffect(() => {
    if (done) return;
    if (!running) {
      api.setItems([startItem]);
      api.setInstruction(`Trial ${i + 1} of ${n}. Select Start, then keep the pointer inside the moving circle for ${Math.round(duration / 1000)} seconds.`);
      return;
    }
    api.setItems([]);
    samples.current = [];
    const s0 = trackingTarget(comps, 0, speed);
    api.stimulusOnNextFrame({ trial: i, duration_ms: duration, radius: R, speed_scale: speed, amp_scale: { x: s0.sx, y: s0.sy }, exclude_ms: 3000 });
    t0.current = api.now();
    const off = api.onFrame(() => {
      if (api.paused()) return;
      const el = (api.now() - t0.current) / 1000;
      const pos = trackingTarget(comps, el, speed);
      if (tgtRef.current) tgtRef.current.style.transform = `translate(${pos.x - R}px, ${pos.y - R}px)`;
      const c = api.pointer();
      if (c && el * 1000 >= 3000) samples.current.push({ e: Math.hypot(c.x - pos.x, c.y - pos.y) });
      if (el * 1000 >= duration) {
        off();
        endTrial("completed");
      }
    });
    return off;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [i, running, done]);

  if (done) return <p className="cue-box">Task complete.</p>;
  if (!running)
    return (
      <button type="button" data-item-id="track-start" className="titem target" style={{ left: 640, top: 400, width: 160, height: 90 }} tabIndex={api.settings.selection === "keyboard" ? 0 : -1} onClick={(e) => e.detail === 0 && api.keyboardSelect(startItem)}>
        Start tracking
      </button>
    );
  return <div ref={tgtRef} aria-hidden="true" style={{ position: "absolute", left: 0, top: 0, width: 2 * R, height: 2 * R, borderRadius: "50%", border: "4px solid var(--target)", background: "color-mix(in srgb, var(--target) 25%, transparent)" }} />;
}

// ----------------------------------------------------------------------------- D1 drag and drop
export function DragTask({ api }: { api: TaskApi }) {
  const p = api.stim.params;
  const trials = (api.stim.trials ?? []) as { zone: number; angle: number }[];
  const n = limitN(api, "trials", trials.length, 3);
  const D = p.D ?? 400;
  const [i, setI] = useState(0);
  const [obj, setObj] = useState({ x: 640, y: 400 });
  const [held, setHeld] = useState(false);
  const [done, setDone] = useState(false);
  const drops = useRef(0);
  const rows = useRef<{ time: number; drops: number; err: number }[]>([]);
  const grab = useRef({ dx: 0, dy: 0 });
  const tr = trials[i];
  // Zone centre: D px from the start in the stimulus direction (y compressed by 0.8 to stay on canvas)
  const zone = tr ? { x: 640 + D * Math.cos(tr.angle), y: 400 + D * Math.sin(tr.angle) * 0.8, s: tr.zone } : { x: 0, y: 0, s: 0 };
  const dragLock = api.settings.selection !== "click";
  const objItem: TaskItem = { id: "object", x: obj.x, y: obj.y, w: 60, h: 60, shape: "circle", label: held ? "Drop object here" : "Pick up object" };

  const summarize = (): ProvisionalSummary => {
    const r = rows.current;
    const values = { trials: r.length, time_ms_mean: mean(r.map((x) => x.time)), unintended_drops: r.reduce((a, x) => a + x.drops, 0), placement_error_px_mean: mean(r.map((x) => x.err)) };
    return { values, rows: [["Trials", String(r.length)], ["Mean time", fmt(values.time_ms_mean, 0) + " ms"], ["Drops outside the zone", String(values.unintended_drops)], ["Placement error", fmt(values.placement_error_px_mean, 1) + " px"]] };
  };

  const pick = (x: number, y: number, t: number, stream: StreamHandle) => {
    if (Math.abs(x - obj.x) > 30 || Math.abs(y - obj.y) > 30) return;
    grab.current = { dx: obj.x - x, dy: obj.y - y };
    stream.emit({ kind: "drag_start", x, y, meta: { mode: dragLock ? "drag_lock" : "hold" } }, { t });
    setHeld(true);
  };
  const drop = (x: number, y: number, t: number, stream: StreamHandle) => {
    const ox = x + grab.current.dx;
    const oy = y + grab.current.dy;
    const ok = Math.abs(ox - zone.x) <= zone.s / 2 && Math.abs(oy - zone.y) <= zone.s / 2;
    stream.emit({ kind: "drag_end", x, y, meta: { in_zone: ok, mode: dragLock ? "drag_lock" : "hold" } }, { t });
    setHeld(false);
    setObj({ x: ox, y: oy });
    if (!ok) {
      drops.current++;
      api.announce("Dropped outside the zone. Pick the object up again.");
      return;
    }
    const err = Math.hypot(ox - zone.x, oy - zone.y);
    rows.current.push({ time: t - api.session.lastStimT, drops: drops.current, err });
    api.session.marker("trial_end", { trial: i, outcome: "hit", unintended_drops: drops.current, placement_error_px: err }, t);
    api.announce("Placed in the zone.");
    if (i + 1 >= n) {
      setDone(true);
      api.finish(summarize());
    } else setI(i + 1);
  };

  api.handlers = {
    rawPointer: !dragLock,
    virtualCursor: true,
    emptyEndsTrial: false,
    summarize,
    onPointerDown: (x, y, t, s) => api.session.inTrial && !held && pick(x, y, t, s),
    onPointerUp: (x, y, t, s) => api.session.inTrial && held && drop(x, y, t, s),
    onMove: (x, y) => {
      if (held) setObj({ x: x + grab.current.dx, y: y + grab.current.dy });
    },
    onSelect: (s) => {
      if (!api.session.inTrial || !s.event) return;
      const stream = api.session.rec.stream(s.event.stream_id, s.event.modality);
      if (!held) pick(s.x, s.y, s.t, stream);
      else drop(s.x, s.y, s.t, stream);
    },
    onSkip: () => {
      if (!api.session.inTrial) return;
      api.session.marker("trial_end", { trial: i, outcome: "abandoned" });
      if (i + 1 >= n) {
        setDone(true);
        api.finish(summarize());
      } else setI(i + 1);
    },
  };

  useEffect(() => {
    if (done || !tr) return;
    drops.current = 0;
    setObj({ x: 640, y: 400 });
    setHeld(false);
    api.setInstruction(`Trial ${i + 1} of ${n}. ${dragLock ? "Select the object to pick it up, move it, and select again to drop it" : "Drag the object"} into the dashed zone.`);
    api.stimulusOnNextFrame({ trial: i, object: { x: 640, y: 400, w: 60 }, zone: { x: zone.x, y: zone.y, w: zone.s }, D });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [i, done]);

  useEffect(() => {
    // the object is the only selectable item; while held, selecting anywhere drops it
    api.setItems(held ? [] : [objItem]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [held, obj.x, obj.y]);

  if (done || !tr) return <p className="cue-box">Task complete.</p>;
  return (
    <>
      <div aria-hidden="true" style={{ position: "absolute", left: zone.x - zone.s / 2, top: zone.y - zone.s / 2, width: zone.s, height: zone.s, border: "5px dashed var(--cue)", borderRadius: 6 }} />
      <button
        type="button"
        data-item-id="object"
        className="titem circle target"
        aria-label={objItem.label}
        tabIndex={api.settings.selection === "keyboard" ? 0 : -1}
        style={{ left: obj.x, top: obj.y, width: 60, height: 60, pointerEvents: "none" }}
        onClick={(e) => e.detail === 0 && api.keyboardSelect(objItem)}
      />
    </>
  );
}
