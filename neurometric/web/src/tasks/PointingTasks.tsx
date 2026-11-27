// A1 single target, A5 time-constrained acquisition, A2 ISO multidirectional ring, A3 dwell ring.

import { useEffect, useRef, useState } from "react";
import { fittsThroughput, trialMetrics, type Trial } from "../metrics/pointing";
import { ItemButton, fmt, type Selection, type TaskApi, type TaskItem } from "./api";
import { TrialCollector, limitN, mean } from "./common";
import { inside } from "../input/space";
import type { ProvisionalSummary } from "./session";

// ----------------------------------------------------------------------------- A1 / A5
export function SingleTargetTask({ api }: { api: TaskApi }) {
  const stim = api.stim;
  const isA5 = stim.task_id === "A5";
  const trials = stim.trials ?? [];
  const n = limitN(api, "trials", trials.length, 4);
  const [i, setI] = useState(0);
  const [phase, setPhase] = useState<"start" | "target" | "done">("start");
  const col = useRef(new TrialCollector());
  const results = useRef<Trial[]>([]);
  const deadline = useRef<number>(Infinity);
  const tr = trials[i];
  const startItem: TaskItem = { id: "start", x: 640, y: 400, w: 100, h: 100, shape: "circle", label: "Start" };
  const targetItem: TaskItem | null = tr ? { id: "target", x: tr.x, y: tr.y, w: tr.w, h: tr.w, shape: "circle", label: "Target" } : null;

  const summarize = (): ProvisionalSummary => {
    const ms = results.current.map((t) => trialMetrics(t));
    const ok = ms.filter((m) => m.success);
    const values = {
      trials: ms.length,
      success_rate: ms.length ? ok.length / ms.length : NaN,
      movement_time_ms_mean: mean(ok.map((m) => m.movement_time_ms)),
      path_efficiency_mean: mean(ms.map((m) => m.path_efficiency)),
      endpoint_error_px_mean: mean(ms.map((m) => m.endpoint_error_px)),
    };
    return {
      values,
      rows: [
        ["Trials", String(values.trials)],
        [isA5 ? "Success within deadline" : "Success rate", fmt(values.success_rate * 100, 0) + " %"],
        ["Mean movement time (successful)", fmt(values.movement_time_ms_mean, 0) + " ms"],
        ["Mean path efficiency", fmt(values.path_efficiency_mean)],
      ],
    };
  };

  const endTrial = (outcome: "hit" | "miss" | "timeout" | "abandoned", s?: Selection) => {
    if (!tr) return;
    const sess = api.session;
    const t = s ? s.t : api.now();
    sess.marker("trial_end", { trial: i, outcome }, s?.t);
    if (outcome !== "abandoned") {
      results.current.push(
        col.current.end(sess.lastStimT, s ? s.t : null, s ? [s.x, s.y] : [api.pointer()?.x ?? 640, api.pointer()?.y ?? 400], outcome === "hit" ? 0 : outcome === "miss" ? -1 : -2),
      );
    } else col.current.active = false;
    api.announce(outcome === "hit" ? "Hit." : outcome === "miss" ? "Missed." : outcome === "timeout" ? "Time is up." : "Trial skipped.");
    void t;
    deadline.current = Infinity;
    if (i + 1 >= n) {
      setPhase("done");
      api.finish(summarize());
    } else {
      setI(i + 1);
      setPhase("start");
    }
  };

  api.handlers = {
    emptyEndsTrial: phase === "target",
    virtualCursor: true,
    summarize,
    onMove: (x, y, t) => col.current.add(x, y, t),
    onSelect: (s) => {
      if (phase === "start") {
        if (s.item?.id !== "start") return;
        api.session.marker("trial_start", { trial: i });
        setPhase("target");
        return;
      }
      if (phase !== "target" || !api.session.inTrial || !tr) return;
      endTrial(inside({ x: tr.x, y: tr.y, w: tr.w, h: tr.w }, s.x, s.y) ? "hit" : "miss", s);
    },
    onSkip: () => {
      if (phase === "target" && api.session.inTrial) endTrial("abandoned");
    },
    onPause: () => {
      if (phase === "target" && api.session.inTrial) {
        api.session.marker("trial_end", { trial: i, outcome: "abandoned", reason: "paused" });
        col.current.active = false;
        setPhase("start");
      }
    },
  };

  useEffect(() => {
    if (phase === "done" || !tr) return;
    api.setItems(phase === "start" ? [startItem] : [targetItem!]);
    if (phase === "start") {
      api.setInstruction(`Trial ${i + 1} of ${n}. Select the Start circle in the centre.`);
      return;
    }
    api.setInstruction(isA5 ? `Select the target before the time runs out (${tr.deadline_ms / 1000} s).` : "Select the blue target.");
    const p = api.pointer() ?? { x: 640, y: 400 };
    col.current.begin([tr.start.x, tr.start.y], [tr.x, tr.y], [tr.w / 2, tr.w / 2]);
    col.current.add(p.x, p.y, api.now());
    api.stimulusOnNextFrame({ trial: i, target: { x: tr.x, y: tr.y, w: tr.w }, start: tr.start, D: tr.D, W: tr.w, ...(isA5 ? { deadline_ms: tr.deadline_ms } : {}) });
    const limit = isA5 ? tr.deadline_ms * api.settings.timeMultiplier : api.timeLimit(stim.params.max_ms ?? 20000);
    deadline.current = api.now() + limit;
    const off = api.onFrame(() => {
      if (!api.paused() && api.session.inTrial && api.now() > api.session.lastStimT + limit) {
        off();
        endTrial("timeout");
      }
    });
    return off;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [phase, i]);

  if (!tr || phase === "done") return <p className="cue-box">Task complete.</p>;
  return (
    <>
      {phase === "start" ? <ItemButton api={api} item={startItem} className="target" /> : <ItemButton api={api} item={targetItem!} className="target" />}
    </>
  );
}

// ----------------------------------------------------------------------------- A2 / A3 (ISO)
export function IsoRingTask({ api }: { api: TaskApi }) {
  const stim = api.stim;
  const isA3 = stim.task_id === "A3";
  const allBlocks = (stim.blocks ?? []).map((b, bi) => ({ ...b, bi })).filter((b) => b.W >= api.settings.targetMinPx);
  const nBlocks = limitN(api, "blocks", allBlocks.length, 2);
  const blocks = allBlocks.slice(0, nBlocks);
  const [b, setB] = useState(0);
  const [k, setK] = useState(0); // index into ISO order
  // "start": the highlighted target must be selected once, unscored, to (re)start the sequence
  // (block start, or after a pause); then each later selection is a scored trial.
  const [phase, setPhase] = useState<"start" | "run">("start");
  const prevSel = useRef<{ x: number; y: number; t: number } | null>(null);
  const col = useRef(new TrialCollector());
  const perBlock = useRef<Map<number, Trial[]>>(new Map());
  const block = blocks[b];
  const nSel = block ? limitN(api, "n", block.targets.length, 7) : 0;
  const tgt = block?.targets[k];

  const summarize = (): ProvisionalSummary => {
    const rows: [string, string][] = [];
    const tps: number[] = [];
    let n = 0;
    let errs = 0;
    for (const bl of blocks) {
      const trials = perBlock.current.get(bl.bi) ?? [];
      if (!trials.length) continue;
      const r = fittsThroughput(trials, bl.D, bl.W, { dwell: isA3 });
      n += r.n;
      errs += r.error_rate * r.n;
      if (Number.isFinite(r.tp_effective_bps)) tps.push(r.tp_effective_bps);
      rows.push([`D=${bl.D}, W=${bl.W}`, `TPe ${fmt(r.tp_effective_bps)} bit/s, MT ${fmt(r.mt_ms, 0)} ms, errors ${fmt(r.error_rate * 100, 0)} %${r.valid ? "" : " (flagged: " + r.flags.join("; ") + ")"}`]);
    }
    const tp = mean(tps);
    return { values: { fitts_throughput_bps: tp, selections: n, error_rate: n ? errs / n : NaN }, rows: [["Effective throughput (mean of conditions)", fmt(tp) + " bit/s"], ["Error rate", fmt(n ? (errs / n) * 100 : NaN, 0) + " %"], ...rows] };
  };

  const advance = () => {
    if (k + 1 < nSel) {
      setK(k + 1);
      setPhase("run");
    } else if (b + 1 < blocks.length) {
      setB(b + 1);
      setK(0);
      setPhase("start");
      prevSel.current = null;
    } else api.finish(summarize());
  };

  const endTrial = (outcome: "hit" | "miss" | "timeout" | "abandoned", s?: Selection) => {
    if (!block || !tgt) return;
    const sess = api.session;
    sess.marker("trial_end", { block: block.bi, trial: k, outcome }, s?.t);
    if (outcome !== "abandoned") {
      const list = perBlock.current.get(block.bi) ?? [];
      list.push(col.current.end(sess.lastStimT, s ? s.t : null, s ? [s.x, s.y] : [api.pointer()?.x ?? tgt.x, api.pointer()?.y ?? tgt.y], outcome === "hit" ? 0 : outcome === "miss" ? -1 : -2));
      perBlock.current.set(block.bi, list);
    }
    prevSel.current = s ? { x: s.x, y: s.y, t: s.t } : { x: api.pointer()?.x ?? tgt.x, y: api.pointer()?.y ?? tgt.y, t: api.now() };
    advance();
  };

  api.handlers = {
    emptyEndsTrial: phase === "run",
    virtualCursor: true,
    summarize,
    onMove: (x, y, t) => col.current.add(x, y, t),
    onSelect: (s) => {
      if (!block || !tgt) return;
      const hit = inside({ x: tgt.x, y: tgt.y, w: tgt.w, h: tgt.w }, s.x, s.y);
      if (phase === "start") {
        if (!hit) return; // the unscored start selection must be on the highlighted target
        api.session.marker("sequence_start", { block: block.bi, trial: k }, s.t);
        prevSel.current = { x: s.x, y: s.y, t: s.t };
        advance();
        return;
      }
      if (isA3 && !hit && s.item) {
        // dwell completed on a non-target ring item: unintended (Midas touch) selection
        endTrial("miss", s);
        return;
      }
      endTrial(hit ? "hit" : "miss", s);
    },
    onSkip: () => {
      if (phase === "run") endTrial("abandoned");
    },
    onPause: () => {
      // the sequence restarts at the current target with a new unscored start selection
      if (phase === "run" && api.session.inTrial) {
        api.session.marker("trial_end", { block: block.bi, trial: k, outcome: "abandoned", reason: "paused" });
        col.current.active = false;
      }
      prevSel.current = null;
      setPhase("start");
    },
  };

  useEffect(() => {
    if (!block || !tgt) return;
    const ring: TaskItem[] = block.targets.map((t, j) => ({ id: `ring-${j}`, x: t.x, y: t.y, w: t.w, h: t.w, shape: "circle" }));
    api.setItems(isA3 ? ring : [ring[k]]);
    if (phase === "start") {
      if (k === 0) api.session.marker("block_start", { block: block.bi, D: block.D, W: block.W, n: nSel });
      api.setInstruction(`Block ${b + 1} of ${blocks.length}. ${isA3 ? "Hold the pointer still on" : "Select"} the highlighted circle to begin, then follow the highlight across the ring as quickly and accurately as you can.`);
      return;
    }
    api.setInstruction(`${isA3 ? "Dwell on" : "Select"} the highlighted circle (${k} of ${nSel - 1}).`);
    const p = prevSel.current ?? { x: tgt.x, y: tgt.y, t: api.now() };
    col.current.begin([p.x, p.y], [tgt.x, tgt.y], [tgt.w / 2, tgt.w / 2]);
    col.current.add(p.x, p.y, p.t);
    // ISO sequences: the next target's onset IS the previous selection (MT = time between selections)
    api.session.marker("stimulus_on", { block: block.bi, trial: k, target: { x: tgt.x, y: tgt.y, w: tgt.w }, start: { x: p.x, y: p.y }, D: block.D, W: block.W }, p.t);
    const limit = api.timeLimit(stim.params.max_ms ?? 15000);
    if (!Number.isFinite(limit)) return;
    const off = api.onFrame(() => {
      if (!api.paused() && api.session.inTrial && api.now() > api.session.lastStimT + limit) {
        off();
        endTrial("timeout");
      }
    });
    return off;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [b, k, phase]);

  if (!block) return <p className="cue-box">No conditions to administer (check the minimum target size setting).</p>;
  return (
    <>
      {block.targets.map((t, j) => (
        <div
          key={j}
          data-item-id={`ring-${j}`}
          className={`titem circle ${j === k ? "target" : "ghost"}`}
          style={{ left: t.x, top: t.y, width: t.w, height: t.w }}
          aria-hidden="true"
        />
      ))}
      <p className="sr-only" aria-live="polite">
        Target {k + 1} of {nSel} highlighted.
      </p>
    </>
  );
}
