// C1 scroll to target: bring the cued row into the highlighted band and select it.
// Scrolling by wheel / touchpad, by the on-screen Scroll buttons (switch, dwell, click), or by
// arrow / Page keys. The list is app-controlled (not native scrolling) so geometry is identical
// on every device and every scroll step is recorded as a canonical `scroll` event.

import { useEffect, useRef, useState } from "react";
import { fmt, ItemButton, type TaskApi, type TaskItem } from "./api";
import { limitN, mean } from "./common";
import type { ProvisionalSummary } from "./session";
import type { StreamHandle } from "../input/recorder";

const VP = { x: 640, y: 450, w: 560 }; // viewport centre / width (height from params)

export function ScrollTask({ api }: { api: TaskApi }) {
  const p = api.stim.params;
  const ROWS = p.rows ?? 60;
  const RH = p.row_px ?? 60;
  const VH = p.viewport_px ?? 400;
  const top = VP.y - VH / 2;
  const maxOff = ROWS * RH - VH;
  const cues = api.stim.cues ?? [];
  const n = limitN(api, "trials", cues.length, 3);
  const [i, setI] = useState(0);
  const [off, setOff] = useState(0);
  const [done, setDone] = useState(false);
  const offRef = useRef(0);
  const passes = useRef({ inBand: false, entries: 0, reversals: 0, lastDir: 0 });
  const rows = useRef<{ time: number; passes: number; reversals: number; ok: boolean }[]>([]);
  const cue = cues[i];
  const bandRow = (o: number) => Math.round((o + VH / 2 - RH / 2) / RH); // row whose centre is in the band
  const ctlStream = api.session.rec.stream("in:scroll-buttons", api.session.modality);

  const summarize = (): ProvisionalSummary => {
    const r = rows.current;
    const values = { trials: r.length, success_rate: mean(r.map((x) => (x.ok ? 1 : 0))), time_to_select_ms_mean: mean(r.filter((x) => x.ok).map((x) => x.time)), band_passes_mean: mean(r.map((x) => x.passes)), reversals_mean: mean(r.map((x) => x.reversals)) };
    return { values, rows: [["Trials", String(r.length)], ["Success rate", fmt(values.success_rate * 100, 0) + " %"], ["Mean time to select", fmt(values.time_to_select_ms_mean, 0) + " ms"], ["Band passes (mean)", fmt(values.band_passes_mean, 1)], ["Reversals (mean)", fmt(values.reversals_mean, 1)]] };
  };

  const scrollBy = (dy: number) => {
    const o = Math.min(maxOff, Math.max(0, offRef.current + dy));
    const dir = Math.sign(o - offRef.current);
    if (dir && passes.current.lastDir && dir !== passes.current.lastDir) passes.current.reversals++;
    if (dir) passes.current.lastDir = dir;
    offRef.current = o;
    const inBand = bandRow(o) === cue;
    if (inBand && !passes.current.inBand) passes.current.entries++;
    passes.current.inBand = inBand;
    setOff(o);
  };

  const finishTrial = (ok: boolean, t: number, outcome: string) => {
    const time = t - api.session.lastStimT;
    rows.current.push({ time, passes: Math.max(passes.current.entries - 1, 0), reversals: passes.current.reversals, ok });
    api.session.marker("trial_end", { trial: i, outcome, offset_px: offRef.current, band_passes: Math.max(passes.current.entries - 1, 0), reversals: passes.current.reversals }, t);
    api.announce(ok ? "Correct." : "Not in the band.");
    if (i + 1 >= n) {
      setDone(true);
      api.finish(summarize());
    } else setI(i + 1);
  };

  const buttonScroll = (dy: number, t: number, stream: StreamHandle) => {
    stream.emit({ kind: "scroll", dy, meta: { source: "scroll_button" } }, { t });
    scrollBy(dy);
  };

  api.handlers = {
    emptyEndsTrial: false,
    summarize,
    selectMeta: (it) => (it && it.id.startsWith("row-") ? { correct: Number(it.id.slice(4)) === cue && bandRow(offRef.current) === cue } : {}),
    onWheel: (_dx, dy) => api.session.inTrial && scrollBy(dy),
    onKey: (name, _ev, t, stream) => {
      if (!api.session.inTrial) return false;
      const d = name === "ArrowDown" ? RH : name === "ArrowUp" ? -RH : name === "PageDown" ? VH - RH : name === "PageUp" ? -(VH - RH) : 0;
      if (!d) return false;
      stream.emit({ kind: "scroll", dy: d, meta: { source: "key" } }, { t });
      scrollBy(d);
      return true;
    },
    onSelect: (s) => {
      if (!api.session.inTrial || !s.item) return;
      const id = s.item.id;
      if (id === "scroll-up") return buttonScroll(-RH, s.t, ctlStream);
      if (id === "scroll-down") return buttonScroll(RH, s.t, ctlStream);
      if (id === "select-band") return finishTrial(bandRow(offRef.current) === cue, s.t, bandRow(offRef.current) === cue ? "hit" : "miss");
      if (id.startsWith("row-")) {
        const r = Number(id.slice(4));
        const ok = r === cue && bandRow(offRef.current) === cue;
        finishTrial(ok, s.t, ok ? "hit" : "miss");
      }
    },
    onSkip: () => api.session.inTrial && finishTrial(false, api.now(), "abandoned"),
  };

  // visible rows as items (clipped to the viewport)
  const first = Math.max(0, Math.floor(off / RH));
  const last = Math.min(ROWS - 1, Math.ceil((off + VH) / RH));
  const rowItems: TaskItem[] = [];
  for (let r = first; r <= last; r++) {
    const cy = top + r * RH + RH / 2 - off;
    if (cy - RH / 2 < top - 1 || cy + RH / 2 > top + VH + 1) continue; // only fully visible rows are selectable
    rowItems.push({ id: `row-${r}`, x: VP.x, y: cy, w: VP.w, h: RH - 6, label: `Item ${r + 1}`, row: 1 });
  }
  const controls: TaskItem[] = [
    { id: "scroll-up", x: 1080, y: top + 60, w: 200, h: 100, label: "Scroll up", row: 0 },
    { id: "scroll-down", x: 1080, y: top + VH - 60, w: 200, h: 100, label: "Scroll down", row: 0 },
    { id: "select-band", x: 1080, y: VP.y, w: 200, h: 100, label: "Select row in band", row: 0 },
  ];
  const items = [...controls, ...rowItems];

  useEffect(() => {
    api.setItems(items);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [off, i]);

  useEffect(() => {
    if (done || cue === undefined) return;
    const start = i % 2 === 0 ? 0 : maxOff; // alternate scrolling down / up
    offRef.current = start;
    passes.current = { inBand: bandRow(start) === cue, entries: bandRow(start) === cue ? 1 : 0, reversals: 0, lastDir: 0 };
    setOff(start);
    api.setInstruction(`Trial ${i + 1} of ${n}. Scroll until "Item ${cue + 1}" is inside the highlighted band, then select it.`);
    api.stimulusOnNextFrame({ trial: i, cue_row: cue, start_offset_px: start, direction: start === 0 ? "down" : "up", row_px: RH, viewport_px: VH });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [i, done]);

  if (done || cue === undefined) return <p className="cue-box">Task complete.</p>;
  return (
    <>
      <p className="cue-box" style={{ top: 40 }}>Find: Item {cue + 1}</p>
      <div aria-hidden="true" style={{ position: "absolute", left: VP.x - VP.w / 2 - 10, top: top - 4, width: VP.w + 20, height: VH + 8, border: "3px solid var(--canvas-line)" }} />
      <div aria-hidden="true" style={{ position: "absolute", left: VP.x - VP.w / 2 - 10, top: VP.y - RH / 2, width: VP.w + 20, height: RH, background: "color-mix(in srgb, var(--cue) 25%, transparent)", border: "3px solid var(--cue)" }} />
      {items.map((it) => (
        <ItemButton key={it.id} api={api} item={it} className={it.id === `row-${cue}` ? "cued" : ""} />
      ))}
    </>
  );
}
