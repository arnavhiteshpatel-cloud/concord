// A4 selection among distractors (grid) and E2 structured phrase selection (AAC-style board).
// Both work with click, dwell, keyboard (Tab + Enter) and switch scanning (row-column optional).

import { useEffect, useRef, useState } from "react";
import { achievedBitrate } from "../metrics/pointing";
import { ItemButton, fmt, type Selection, type TaskApi, type TaskItem } from "./api";
import { limitN, mean } from "./common";
import type { ProvisionalSummary } from "./session";

interface Row {
  outcome: string;
  mt: number;
}

function GridTask({ api, items, cues, nItems, cueText }: { api: TaskApi; items: TaskItem[]; cues: number[]; nItems: number; cueText: (it: TaskItem) => string }) {
  const n = limitN(api, "trials", cues.length, 6);
  const [i, setI] = useState(0);
  const [done, setDone] = useState(false);
  const rows = useRef<Row[]>([]);
  const empties = useRef(0);
  const cue = items[cues[i]];

  const summarize = (): ProvisionalSummary => {
    const r = rows.current;
    const nc = r.filter((x) => x.outcome === "hit").length;
    const ni = r.filter((x) => x.outcome === "miss").length;
    const secs = r.filter((x) => x.outcome !== "timeout").reduce((a, x) => a + x.mt, 0) / 1000;
    const br = achievedBitrate(nc, ni, nItems, secs);
    const mt = mean(r.filter((x) => x.outcome === "hit").map((x) => x.mt));
    return {
      values: { trials: r.length, correct: nc, wrong: ni, achieved_bitrate_bps: br, movement_time_ms_mean: mt, empty_selections: empties.current },
      rows: [
        ["Trials", String(r.length)],
        ["Correct / wrong selections", `${nc} / ${ni}`],
        ["Mean selection time (correct)", fmt(mt, 0) + " ms"],
        ["Achieved bitrate", fmt(br) + " bit/s"],
        ["Empty-space selections", String(empties.current)],
      ],
    };
  };

  const end = (outcome: "hit" | "miss" | "timeout" | "abandoned", s?: Selection, wrongItem?: string) => {
    const sess = api.session;
    const t0 = sess.lastStimT;
    sess.marker("trial_end", { trial: i, outcome, ...(wrongItem !== undefined ? { wrong_item: wrongItem } : {}) }, s?.t);
    if (outcome !== "abandoned") rows.current.push({ outcome, mt: (s ? s.t : api.now()) - t0 });
    api.announce(outcome === "hit" ? "Correct." : outcome === "miss" ? "That was not the cued item." : outcome === "timeout" ? "Time is up." : "Trial skipped.");
    if (i + 1 >= n) {
      setDone(true);
      api.finish(summarize());
    } else setI(i + 1);
  };

  api.handlers = {
    emptyEndsTrial: false,
    summarize,
    onSelect: (s) => {
      if (!api.session.inTrial || done) return;
      if (!s.item) {
        empties.current++;
        return;
      }
      if (s.item.id === cue.id) end("hit", s);
      else end("miss", s, s.item.id);
    },
    onSkip: () => api.session.inTrial && end("abandoned"),
    onPause: () => {
      if (api.session.inTrial) {
        api.session.marker("trial_end", { trial: i, outcome: "abandoned", reason: "paused" });
      }
    },
    onResume: () => {
      // re-present the same trial
      api.stimulusOnNextFrame({ trial: i, n_items: nItems, target: { x: cue.x, y: cue.y, w: cue.w, h: cue.h }, repeat: true });
    },
  };

  useEffect(() => {
    if (done || !cue) return;
    api.setItems(items);
    api.setInstruction(`Trial ${i + 1} of ${n}. ${cueText(cue)}`);
    api.stimulusOnNextFrame({ trial: i, n_items: nItems, target: { x: cue.x, y: cue.y, w: cue.w, h: cue.h }, cue: cue.id });
    const limit = api.timeLimit(api.stim.params.max_ms ?? 20000);
    if (!Number.isFinite(limit)) return;
    const off = api.onFrame(() => {
      if (!api.paused() && api.session.inTrial && api.now() > api.session.lastStimT + limit) {
        off();
        end("timeout");
      }
    });
    return off;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [i, done]);

  if (done) return <p className="cue-box">Task complete.</p>;
  return (
    <>
      {items.map((it) => (
        <ItemButton key={it.id} api={api} item={{ ...it, label: it.id === cue.id ? `${it.label} (cued)` : it.label }} className={it.id === cue.id ? "cued" : ""}>
          {api.stim.task_id === "E2" ? it.label : it.id === cue.id ? "★" : ""}
        </ItemButton>
      ))}
    </>
  );
}

export function GridSelectionTask({ api }: { api: TaskApi }) {
  const stim = api.stim;
  const cols = stim.params.cols ?? 6;
  const items: TaskItem[] = (stim.items ?? []).map((it) => ({
    id: String(it.id), x: it.x, y: it.y, w: it.w, h: it.h, row: Math.floor(it.id / cols),
    label: `Row ${Math.floor(it.id / cols) + 1}, column ${(it.id % cols) + 1}`,
  }));
  return <GridTask api={api} items={items} cues={stim.cues ?? []} nItems={items.length} cueText={(it) => `Select the starred item (${it.label}).`} />;
}

export function PhraseBoardTask({ api, phrases }: { api: TaskApi; phrases: string[] }) {
  const n = api.stim.params.n ?? 12;
  const board = phrases.slice(0, 12);
  // 3 columns x 4 rows of large tiles
  const items: TaskItem[] = board.map((p, j) => ({ id: `p${j}`, x: 640 + ((j % 3) - 1) * 400, y: 170 + Math.floor(j / 3) * 150, w: 380, h: 130, row: Math.floor(j / 3), label: p }));
  // Cue order: a fixed permutation (j * 5 mod 12), no browser-side randomness (DECISIONS D-004).
  const cues = Array.from({ length: n }, (_, j) => (j * 5) % board.length);
  return <GridTask api={api} items={items} cues={cues} nItems={items.length} cueText={(it) => `Select the phrase: “${it.label}”.`} />;
}
