// Task runner: owns the input pipeline for one task run (pointer / keyboard / dwell / switch
// scanning / gamepad -> canonical events), pause / resume, the assistance panel, the scaled
// 1280x800 task canvas and the hand-off of the finished run.

import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { PointerAdapter } from "../input/pointer";
import { KeyboardAdapter } from "../input/keyboard";
import { DwellSelector } from "../input/dwell";
import { GamepadAdapter } from "../input/gamepad";
import { recordScanAction, switchStream, type ScanTarget } from "../input/switch";
import { collectSessionMetadata } from "../input/metadata";
import { TASK_H, TASK_W } from "../input/space";
import type { StreamHandle } from "../input/recorder";
import type { Modality, AssistType } from "../input/types";
import { ASSIST_TYPES } from "../input/types";
import { prefersReducedMotion, type Settings } from "../a11y/settings";
import { scanBridge } from "../a11y/scanning";
import { hitTest, type Limits, type SelectVia, type TaskApi, type TaskItem } from "./api";
import { TaskSession, type ProvisionalSummary, type TaskRun } from "./session";
import type { Stimuli, TaskSpec } from "./stimuli";
import { TASK_COMPONENTS } from "./registry";

export function declaredModality(s: Settings): Modality {
  if (s.modality !== "auto") return s.modality;
  return s.selection === "scan" ? "switch" : s.selection === "keyboard" ? "keyboard" : s.selection === "gamepad" ? "gamepad" : "mouse";
}

const ASSIST_LABELS: Record<AssistType, string> = {
  setup: "Setup (positioning, equipment)",
  physical: "Physical help",
  verbal: "Verbal prompt or cue",
  troubleshooting: "Troubleshooting (device or software)",
  calibration: "Calibration / recalibration",
  task_completion: "Someone else completed the task step",
};

export function TaskRunner(props: { stim: Stimuli; spec: TaskSpec; settings: Settings; limits: Limits; onDone: (run: TaskRun) => void }) {
  const { stim, spec, settings } = props;
  const reducedMotion = prefersReducedMotion(settings);
  const modality = declaredModality(settings);
  const session = useMemo(() => new TaskSession(stim, settings, modality), [stim, settings, modality]);
  const [instruction, setInstruction] = useState("");
  const [feedback, setFeedback] = useState("");
  const [paused, setPaused] = useState(false);
  const [finished, setFinished] = useState(false);
  const [cursor, setCursor] = useState<{ x: number; y: number } | null>(null);
  const [dwell, setDwell] = useState<{ x: number; y: number; frac: number } | null>(null);
  const [scale, setScale] = useState(0.5);
  const [assistOpen, setAssistOpen] = useState(false);
  const [assistBy, setAssistBy] = useState("staff");
  const wrapRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLDivElement>(null);
  const barRef = useRef<HTMLDivElement>(null);
  const dialogRef = useRef<HTMLDialogElement>(null);
  const itemsRef = useRef<TaskItem[]>([]);
  const lastPos = useRef<{ x: number; y: number } | null>(null);
  const frameFns = useRef(new Set<(t: number, raf: number) => void>());
  const finishedRef = useRef(false);
  const streams = useRef<{ kb?: StreamHandle; sw?: StreamHandle; dwell?: StreamHandle; ptr?: StreamHandle }>({});
  const dwellRef = useRef<DwellSelector | null>(null);
  // A3 is by definition a dwell task; every other task uses the participant's selection method.
  const sel = stim.task_id === "A3" ? "dwell" : settings.selection;
  const [confirmStop, setConfirmStop] = useState(false);

  const doSelect = useCallback(
    (x: number, y: number, t: number, via: SelectVia, stream: StreamHandle | null, fixedItem?: TaskItem | null, extra?: Record<string, unknown>) => {
      if (session.rec.paused || finishedRef.current) return;
      const h = api.handlers;
      const item = fixedItem !== undefined ? fixedItem : hitTest(itemsRef.current, x, y);
      let ev = null;
      if (via !== "switch" && stream) {
        const kind = via === "click" ? "click" : via === "dwell" ? "dwell_select" : "select";
        const meta: Record<string, unknown> = item ? { item: item.id } : h.emptyEndsTrial ? {} : { empty: true };
        ev = stream.emit({ kind, x, y, button: via === "click" ? 0 : undefined, meta: { ...meta, ...(extra ?? {}), ...(h.selectMeta?.(item) ?? {}) } }, { t });
      }
      h.onSelect?.({ t, x, y, item, via, event: ev });
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [session],
  );

  const apiRef = useRef<TaskApi | null>(null);
  if (!apiRef.current || apiRef.current.session !== session) {
    apiRef.current = {
      session,
      stim,
      settings,
      reducedMotion,
      now: () => session.now(),
      paused: () => session.rec.paused,
      setInstruction: (s) => setInstruction(s),
      announce: (s) => setFeedback(s),
      setItems: (items) => {
        const prev = itemsRef.current;
        itemsRef.current = items;
        const same = prev.length === items.length && prev.every((p, i) => p.id === items[i].id);
        if (!same) {
          dwellRef.current?.reset(session.now());
          if (sel === "scan") queueMicrotask(() => scanBridge.scanner?.reset());
        }
      },
      handlers: {},
      finish: (summary) => finish(summary, true),
      pointer: () => lastPos.current,
      keyboardSelect: (item) => {
        const kb = streams.current.kb ?? session.rec.stream("in:keyboard", "keyboard");
        lastPos.current = { x: item.x, y: item.y };
        if (sel === "keyboard") setCursor({ x: item.x, y: item.y });
        doSelect(item.x, item.y, session.now(), "keyboard", kb, item);
      },
      onFrame: (fn) => {
        frameFns.current.add(fn);
        return () => frameFns.current.delete(fn);
      },
      stimulusOnNextFrame: (meta) => {
        let done = false;
        const fire = (rafTs?: number) => {
          if (done || finishedRef.current) return;
          done = true;
          session.marker("stimulus_on", { ...meta, ...(rafTs !== undefined ? { raf_ts_ms: session.rec.clock.fromTimeStamp(rafTs) } : {}) });
          canvasRef.current?.setAttribute("data-stimulus", String(meta.trial ?? ""));
          canvasRef.current?.setAttribute("data-stimulus-seq", String((Number(canvasRef.current?.getAttribute("data-stimulus-seq")) || 0) + 1));
        };
        requestAnimationFrame((ts) => fire(ts));
        setTimeout(() => fire(), 200); // rAF does not run in background tabs
      },
      timeLimit: (ms) => (settings.noTimePressure ? Infinity : ms * settings.timeMultiplier),
      limits: props.limits,
    };
  }
  const api = apiRef.current;

  const finish = useCallback(
    (summary: ProvisionalSummary | null, completed: boolean) => {
      if (finishedRef.current) return;
      finishedRef.current = true;
      session.completed = completed;
      if (session.rec.paused) session.resume();
      session.marker(completed ? "task_end" : "task_stopped", {});
      setFinished(true);
      props.onDone(session.toRun(summary));
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [session],
  );

  // ---- canvas scaling
  useLayoutEffect(() => {
    const wrap = wrapRef.current;
    if (!wrap) return;
    const fit = () => {
      const r = wrap.getBoundingClientRect();
      const s = Math.max(0.1, Math.min(r.width / TASK_W, r.height / TASK_H));
      setScale(s);
    };
    fit();
    const ro = new ResizeObserver(fit);
    ro.observe(wrap);
    return () => ro.disconnect();
  }, []);

  // ---- session metadata (timing self-checks) collected in the background
  useEffect(() => {
    // Test / lab hook (read-only use by tests/web): the active session and its recorder.
    (window as unknown as { __nmActive?: unknown }).__nmActive = { session, recorder: session.rec, api };
    canvasRef.current?.focus({ preventScroll: true });
    let live = true;
    collectSessionMetadata(scale).then((m) => {
      if (live) session.metadata = m;
    });
    session.marker("task_start", { task_id: stim.task_id, stimulus_hash: stim.stimulus_hash, selection: sel, declared_modality: modality });
    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session]);

  // ---- input adapters (attached to the task canvas only)
  useEffect(() => {
    const el = canvasRef.current!;
    const rec = session.rec;
    const pointerModality = settings.modality === "auto" ? "auto" : settings.modality;
    const observed = new Set<string>();
    const dwellStream = rec.stream("in:dwell", pointerModality === "auto" ? "mouse" : pointerModality);
    streams.current.dwell = dwellStream;
    let dwellSel: DwellSelector | null = null;
    if (sel === "dwell") {
      dwellSel = new DwellSelector({
        thresholdMs: settings.dwellMs,
        hitTest: (x, y) => {
          const it = hitTest(itemsRef.current, x, y);
          return it ? { id: it.id, x: it.x, y: it.y } : null;
        },
        onProgress: (hit, frac, px, py) => setDwell(hit && frac > 0 && frac < 1 ? { x: px, y: py, frac } : null),
        onSelect: (hit, t, px, py) => {
          const it = itemsRef.current.find((i) => i.id === hit.id) ?? null;
          doSelect(px, py, t, "dwell", dwellStream, it, { dwell_ms: settings.dwellMs });
        },
      });
      dwellRef.current = dwellSel;
    }
    const pa = new PointerAdapter({
      recorder: rec,
      element: el,
      declared: pointerModality,
      observed,
      onMove: (s) => {
        lastPos.current = { x: s.x, y: s.y };
        api.handlers.onMove?.(s.x, s.y, s.t);
        dwellSel?.update(s.x, s.y, s.t);
      },
      onDown: (s, stream) => {
        streams.current.ptr = stream;
        lastPos.current = { x: s.x, y: s.y };
        if (api.handlers.rawPointer) api.handlers.onPointerDown?.(s.x, s.y, s.t, stream);
        else if (sel === "click" && s.button === 0) doSelect(s.x, s.y, s.t, "click", stream);
      },
      onUp: (s, stream) => {
        if (api.handlers.rawPointer) api.handlers.onPointerUp?.(s.x, s.y, s.t, stream);
      },
      onWheel: (dx, dy, t, stream) => {
        if (!api.handlers.onWheel) return;
        stream.emit({ kind: "scroll", dx, dy }, { t });
        api.handlers.onWheel(dx, dy, t, stream);
      },
    }).attach();
    const kbModality: Modality = settings.modality === "auto" ? "keyboard" : settings.modality;
    const ka = new KeyboardAdapter({
      recorder: rec,
      element: el,
      modality: kbModality,
      onKey: (name, ev, t, stream) => {
        streams.current.kb = stream;
        if (name === "Escape") {
          ev.preventDefault();
          pauseRef.current();
          return;
        }
        if (session.rec.paused || finishedRef.current) return;
        if (api.handlers.onKey?.(name, ev, t, stream)) {
          ev.preventDefault();
          return;
        }
        if (sel === "keyboard" && api.handlers.virtualCursor) {
          const step = ev.shiftKey ? 40 : 10;
          const p = lastPos.current ?? { x: TASK_W / 2, y: TASK_H / 2 };
          let { x, y } = p;
          if (name === "ArrowLeft") x -= step;
          else if (name === "ArrowRight") x += step;
          else if (name === "ArrowUp") y -= step;
          else if (name === "ArrowDown") y += step;
          else if (name === "Enter" || name === "Space") {
            ev.preventDefault();
            doSelect(p.x, p.y, t, "keyboard", stream);
            return;
          } else return;
          ev.preventDefault();
          x = Math.min(TASK_W, Math.max(0, x));
          y = Math.min(TASK_H, Math.max(0, y));
          stream.emit({ kind: "pointer_move", x, y }, { t });
          lastPos.current = { x, y };
          setCursor({ x, y });
          api.handlers.onMove?.(x, y, t);
        }
      },
    }).attach();
    streams.current.kb = ka.stream;
    let gp: GamepadAdapter | null = null;
    if (sel === "gamepad") {
      gp = new GamepadAdapter({
        recorder: rec,
        cfg: settings.gamepad,
        onCursor: (x, y, t) => {
          lastPos.current = { x, y };
          setCursor({ x, y });
          api.handlers.onMove?.(x, y, t);
        },
        onSelect: (x, y, t, stream) => doSelect(x, y, t, "gamepad", stream),
      });
      gp.start();
      setCursor({ x: gp.x, y: gp.y });
      lastPos.current = { x: gp.x, y: gp.y };
    }
    if (sel === "keyboard") {
      lastPos.current = lastPos.current ?? { x: TASK_W / 2, y: TASK_H / 2 };
      setCursor(lastPos.current);
    }
    // switch scanning: the app-level scanner scans this task's items and controls
    if (sel === "scan") {
      const sw = switchStream(rec, settings.modality === "auto" ? "switch" : settings.modality);
      streams.current.sw = sw;
      scanBridge.fromTimeStamp = (ts) => rec.clock.fromTimeStamp(ts);
      scanBridge.onAction = (a) => {
        let extra: Record<string, unknown> = {};
        if (a.type === "select" && a.target.role === "task") {
          const it = itemsRef.current.find((i) => i.id === a.target.id) ?? null;
          extra = api.handlers.selectMeta?.(it) ?? {};
        }
        recordScanAction(sw, settings.switch, a, extra);
      };
      scanBridge.provider = () => {
        const controls: ScanTarget[] = [...(barRef.current?.querySelectorAll<HTMLButtonElement>("button[data-scan-control]") ?? [])]
          .filter((b) => !b.disabled && b.offsetParent !== null)
          .map((b) => ({ id: b.id, el: b, role: "control" as const, row: 1e6, label: b.textContent ?? "", activate: () => b.click() }));
        const overlayBtns: ScanTarget[] = [...(canvasRef.current?.querySelectorAll<HTMLButtonElement>(".overlay button") ?? [])].map((b) => ({
          id: b.id, el: b, role: "control" as const, row: 1e6 - 1, label: b.textContent ?? "", activate: () => b.click(),
        }));
        if (dialogRef.current?.open) {
          return [...dialogRef.current.querySelectorAll<HTMLButtonElement>("button")].map((b, i) => ({ id: b.id || `dlg${i}`, el: b, role: "control" as const, activate: () => b.click() }));
        }
        if (session.rec.paused || finishedRef.current) return [...overlayBtns, ...controls];
        const items: ScanTarget[] = itemsRef.current.map((it) => ({
          id: it.id,
          row: it.row,
          x: it.x,
          y: it.y,
          label: it.label,
          el: canvasRef.current?.querySelector<HTMLElement>(`[data-item-id="${CSS.escape(it.id)}"]`) ?? null,
          role: "task" as const,
          activate: (t: number) => doSelect(it.x, it.y, t, "switch", sw, it),
        }));
        return [...items, ...controls];
      };
      queueMicrotask(() => scanBridge.scanner?.reset());
    }
    // frame loop: dwell timing, task animation
    let raf = 0;
    const loop = (ts: number) => {
      raf = requestAnimationFrame(loop);
      const t = rec.clock.fromTimeStamp(ts);
      if (!rec.paused) dwellSel?.tick(rec.clock.now());
      for (const fn of frameFns.current) fn(t, ts);
    };
    raf = requestAnimationFrame(loop);
    return () => {
      cancelAnimationFrame(raf);
      pa.detach();
      ka.detach();
      gp?.stop();
      if (sel === "scan") {
        scanBridge.provider = null;
        scanBridge.onAction = null;
        scanBridge.fromTimeStamp = null;
      }
      (window as unknown as { __nmObservedPointerTypes?: string[] }).__nmObservedPointerTypes = [...observed];
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session]);

  // ---- pause / resume / stop / assistance
  const pause = useCallback(() => {
    if (session.rec.paused || finishedRef.current) return;
    session.pause();
    setPaused(true);
    setFeedback("Paused. Choose Resume when you are ready.");
    api.handlers.onPause?.();
    queueMicrotask(() => {
      scanBridge.scanner?.reset();
      canvasRef.current?.querySelector<HTMLButtonElement>(".overlay button")?.focus();
    });
  }, [session, api]);
  const pauseRef = useRef(pause);
  pauseRef.current = pause;
  const resume = useCallback(() => {
    if (!session.rec.paused) return;
    session.resume();
    setPaused(false);
    setFeedback("Resumed.");
    api.handlers.onResume?.();
    queueMicrotask(() => {
      scanBridge.scanner?.reset();
      canvasRef.current?.focus();
    });
  }, [session, api]);
  // Stopping needs an explicit second confirmation (in-app, so it works with switch scanning).
  const stop = useCallback(() => {
    setConfirmStop(true);
    queueMicrotask(() => {
      scanBridge.scanner?.reset();
      document.getElementById("btn-stop-confirm")?.focus();
    });
  }, []);
  const stopConfirmed = useCallback(() => {
    setConfirmStop(false);
    finish(api.handlers.summarize?.() ?? null, false);
  }, [api, finish]);
  const stopCancelled = useCallback(() => {
    setConfirmStop(false);
    queueMicrotask(() => {
      scanBridge.scanner?.reset();
      document.getElementById("btn-stop")?.focus();
    });
  }, []);
  const openAssist = () => {
    setAssistOpen(true);
    dialogRef.current?.showModal();
    queueMicrotask(() => scanBridge.scanner?.reset());
  };
  const closeAssist = () => {
    dialogRef.current?.close();
    setAssistOpen(false);
    queueMicrotask(() => scanBridge.scanner?.reset());
  };
  const recordAssist = (type: AssistType) => {
    session.assist(type, assistBy);
    setFeedback(`Assistance recorded: ${ASSIST_LABELS[type]}.`);
    closeAssist();
  };

  const TaskComp = TASK_COMPONENTS[stim.task_id];
  const pointerOnly = ["A1", "A2", "A3", "A5", "B1", "B2", "D1"].includes(stim.task_id);
  const scanUnsupported = sel === "scan" && pointerOnly;

  return (
    <div className="task-screen" data-task={stim.task_id}>
      <div className="task-bar" ref={barRef}>
        <div>
          <h2 id="task-title" style={{ margin: 0 }}>
            {spec.id}: {spec.name}
          </h2>
          <p className="instr" id="task-instruction" aria-live="polite">
            {instruction}
          </p>
        </div>
        <div className="row" role="toolbar" aria-label="Task controls">
          {!paused ? (
            <button id="btn-pause" data-scan-control type="button" onClick={pause} disabled={finished}>
              Pause
            </button>
          ) : (
            <button id="btn-resume" data-scan-control type="button" className="primary" onClick={resume}>
              Resume
            </button>
          )}
          <button id="btn-skip" data-scan-control type="button" onClick={() => api.handlers.onSkip?.()} disabled={finished || paused}>
            Skip trial
          </button>
          <button id="btn-assist" data-scan-control type="button" onClick={openAssist} disabled={finished}>
            Record assistance
          </button>
          {!confirmStop ? (
            <button id="btn-stop" data-scan-control type="button" className="danger" onClick={stop} disabled={finished}>
              Stop task
            </button>
          ) : (
            <span role="group" aria-label="Confirm stopping the task" className="row">
              <span>Stop and keep results so far (marked incomplete)?</span>
              <button id="btn-stop-confirm" data-scan-control type="button" className="danger" onClick={stopConfirmed}>
                Yes, stop
              </button>
              <button id="btn-stop-cancel" data-scan-control type="button" onClick={stopCancelled}>
                No, continue
              </button>
            </span>
          )}
        </div>
      </div>
      <p role="status" id="task-feedback" className="muted" style={{ minHeight: "1.5em", margin: "0 0 6px" }}>
        {feedback}
      </p>
      {scanUnsupported && (
        <p className="warn">
          This task measures continuous pointing and cannot be done with switch scanning. Choose Skip trial or Stop task, or change the selection
          method in Setup.
        </p>
      )}
      <div className="canvas-wrap" ref={wrapRef} style={{ height: undefined, aspectRatio: "1280 / 800", maxHeight: "calc(100vh - 190px)" }}>
        <div
          ref={canvasRef}
          className="task-canvas"
          id="task-canvas"
          tabIndex={0}
          role="group"
          aria-labelledby="task-title"
          aria-describedby="task-instruction"
          data-paused={paused ? "1" : "0"}
          style={{ transform: `scale(${scale})`, cursor: sel === "keyboard" || sel === "gamepad" ? "none" : "crosshair" }}
        >
          {TaskComp ? <TaskComp api={api} /> : <p>Task not implemented.</p>}
          {cursor && (sel === "keyboard" || sel === "gamepad") && <div className="cursor-dot" style={{ left: cursor.x, top: cursor.y }} aria-hidden="true" />}
          {dwell && (
            <svg className="dwell-ring" style={{ left: dwell.x, top: dwell.y }} viewBox="0 0 56 56" aria-hidden="true">
              <circle className="bg" cx="28" cy="28" r="24" />
              <circle className="fg" cx="28" cy="28" r="24" strokeDasharray={`${2 * Math.PI * 24}`} strokeDashoffset={`${2 * Math.PI * 24 * (1 - dwell.frac)}`} transform="rotate(-90 28 28)" />
            </svg>
          )}
          {paused && (
            <div className="overlay" role="dialog" aria-modal="false" aria-label="Task paused">
              <p>Paused</p>
              <button id="overlay-resume" type="button" className="primary" onClick={resume}>
                Resume
              </button>
            </div>
          )}
        </div>
      </div>
      <dialog ref={dialogRef} aria-labelledby="assist-title" onClose={() => setAssistOpen(false)}>
        <h2 id="assist-title">Record assistance</h2>
        <p>
          Record any help given during this task. Assisted trials are marked <strong>assisted</strong>, never failed.
        </p>
        <fieldset>
          <legend>Who helped</legend>
          <div className="row">
            {["staff", "care_partner", "participant_self"].map((b) => (
              <button key={b} type="button" aria-pressed={assistBy === b} onClick={() => setAssistBy(b)}>
                {b === "staff" ? "Study staff" : b === "care_partner" ? "Care partner" : "Participant (self-reported)"}
              </button>
            ))}
          </div>
        </fieldset>
        <fieldset>
          <legend>Type of assistance</legend>
          <div className="row">
            {ASSIST_TYPES.map((a) => (
              <button key={a} id={`assist-${a}`} type="button" onClick={() => recordAssist(a)}>
                {ASSIST_LABELS[a]}
              </button>
            ))}
          </div>
        </fieldset>
        <div className="row">
          <button type="button" id="assist-cancel" onClick={closeAssist}>
            Cancel (record nothing)
          </button>
        </div>
        {assistOpen && <span className="sr-only">Assistance dialog open</span>}
      </dialog>
    </div>
  );
}
