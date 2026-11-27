// E1 copy typing on an on-screen QWERTY keyboard (pointer, dwell, keyboard or switch scanning).
// Only the predefined phrases are ever typed or stored (no free text). Each key selection is
// recorded as the selection event (click / dwell_select / switch / select) followed by a
// text_input (letters, space) or key "Backspace" event, which the server scorer consumes.

import { useEffect, useRef, useState } from "react";
import { textEntryMetrics, BACKSPACE } from "../metrics/text";
import { ItemButton, fmt, type TaskApi, type TaskItem } from "./api";
import { limitN, mean } from "./common";
import type { ProvisionalSummary } from "./session";

const DONE: TaskItem = { id: "key-done", x: 1130, y: 724, w: 190, h: 90, row: 3, label: "Done" };

function keyLabel(k: string): string {
  return k === " " ? "Space" : k === "\b" ? "Backspace" : k;
}

export function TypingTask({ api }: { api: TaskApi }) {
  const stim = api.stim;
  const phrases = stim.phrases ?? [];
  const n = limitN(api, "trials", phrases.length, 2);
  const keys: TaskItem[] = [
    ...(stim.keys ?? []).map((k) => ({
      id: `key-${k.key === " " ? "space" : k.key === "\b" ? "backspace" : k.key}`,
      x: k.x, y: k.y, w: k.w, h: k.h,
      row: k.key === " " || k.key === "\b" ? 3 : k.y < 480 ? 0 : k.y < 580 ? 1 : 2,
      label: keyLabel(k.key),
      char: k.key,
    })),
    DONE,
  ];
  const [p, setP] = useState(0);
  const [typed, setTyped] = useState("");
  const [done, setDone] = useState(false);
  const stream = useRef<string[]>([]);
  const firstT = useRef<number | null>(null);
  const results = useRef<ReturnType<typeof textEntryMetrics>[]>([]);
  const textStream = api.session.rec.stream("in:text", api.session.modality);

  const summarize = (): ProvisionalSummary => {
    const r = results.current;
    const values = {
      phrases: r.length,
      wpm_mean: mean(r.map((x) => x.wpm)),
      ccpm_mean: mean(r.map((x) => x.ccpm)),
      msd_error_rate_mean: mean(r.map((x) => x.msd_error_rate)),
      total_error_rate_mean: mean(r.map((x) => x.total_error_rate)),
    };
    return {
      values,
      rows: [
        ["Phrases", String(r.length)],
        ["Words per minute", fmt(values.wpm_mean)],
        ["Correct characters per minute", fmt(values.ccpm_mean, 1)],
        ["Uncorrected error rate (MSD)", fmt(values.msd_error_rate_mean * 100, 1) + " %"],
        ["Total error rate", fmt(values.total_error_rate_mean * 100, 1) + " %"],
      ],
    };
  };

  const type = (ch: string, t: number, source: string) => {
    if (firstT.current === null) firstT.current = t;
    if (ch === "\b") {
      if (source !== "physical_keyboard") textStream.emit({ kind: "key", key: "Backspace", meta: { source } }, { t });
      stream.current.push(BACKSPACE);
      setTyped((s) => s.slice(0, -1));
      api.announce("Deleted");
    } else {
      if (source === "physical_keyboard") textStream.emit({ kind: "key", key: ch, meta: { source } }, { t });
      else textStream.emit({ kind: "text_input", text: ch, meta: { source } }, { t });
      stream.current.push(ch);
      setTyped((s) => s + ch);
    }
  };

  const finishPhrase = (t: number) => {
    const presented = phrases[p];
    api.session.marker("phrase_end", { phrase: p }, t);
    if (firstT.current !== null) results.current.push(textEntryMetrics(presented, stream.current, Math.max(0, t - firstT.current) / 1000));
    stream.current = [];
    firstT.current = null;
    setTyped("");
    if (p + 1 >= n) {
      setDone(true);
      api.finish(summarize());
    } else setP(p + 1);
  };

  api.handlers = {
    emptyEndsTrial: false,
    summarize,
    onSelect: (s) => {
      if (!api.session.inTrial || done || !s.item) return;
      if (s.item.id === DONE.id) {
        finishPhrase(s.t);
        return;
      }
      const ch = (s.item as TaskItem & { char?: string }).char;
      if (ch !== undefined) type(ch, s.t, s.via);
    },
    onKey: (name, ev, t) => {
      if (!api.session.inTrial || done) return false;
      // Direct typing on a physical keyboard (letters and space only) when the canvas has focus.
      if (ev.target !== ev.currentTarget) return false;
      if (/^[a-z]$/.test(ev.key)) {
        type(ev.key, t, "physical_keyboard");
        return true;
      }
      if (name === "Space") {
        type(" ", t, "physical_keyboard");
        return true;
      }
      if (name === "Backspace") {
        type("\b", t, "physical_keyboard");
        return true;
      }
      return false;
    },
    onSkip: () => {
      if (api.session.inTrial) finishPhrase(api.now());
    },
  };

  useEffect(() => {
    if (done) return;
    api.setItems(keys);
    api.setInstruction(`Phrase ${p + 1} of ${n}: type the phrase shown, then select Done.`);
    api.session.marker("phrase_start", { phrase: p, trial: p, presented: phrases[p] });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [p, done]);

  if (done) return <p className="cue-box">Task complete.</p>;
  return (
    <>
      <div style={{ position: "absolute", left: 80, top: 40, right: 80 }}>
        <p style={{ fontSize: 30, margin: "0 0 8px" }}>
          <span className="muted" style={{ fontSize: 20 }}>Copy this phrase: </span>
          <strong id="e1-presented">{phrases[p]}</strong>
        </p>
        <p className="typed" aria-live="polite" aria-label="Typed so far" id="e1-typed" style={{ borderBottom: "3px solid var(--canvas-line)", minHeight: 50, margin: 0 }}>
          {typed}
          <span aria-hidden="true">|</span>
        </p>
      </div>
      {keys.map((k) => (
        <ItemButton key={k.id} api={api} item={k}>
          {k.label}
        </ItemButton>
      ))}
    </>
  );
}
