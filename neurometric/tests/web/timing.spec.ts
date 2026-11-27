// Experiment A "input adapter timing and consistency" and Experiment S part 1 "browser event
// processing latency" (headless Chromium). Results -> experiments/results/A_input_timing/ and
// experiments/results/S_event_latency/ (browser_*.csv / browser_*.json).
//
// IMPORTANT: headless Chromium timing is NOT physical device latency. Events injected via CDP or
// dispatchEvent never pass through USB/Bluetooth HID polling, the OS input stack or a display;
// these numbers characterise the software path inside the page only.
import { test, expect, type Page } from "@playwright/test";
import { writeFileSync } from "node:fs";
import path from "node:path";
import { RESULTS, ensureDir, pyValidate, quantiles, writeCsv } from "./helpers";

const CAVEAT =
  "Headless Chromium on a shared CI-class Linux container. Events are injected via CDP (page.mouse) or dispatchEvent, so USB/Bluetooth polling, OS input processing, compositor and display latency are NOT included. These figures characterise the in-page software path (adapter -> canonical event) only and must not be reported as physical end-to-end latency; see docs/research/browser_timing.md for the bench protocol.";

async function openTask(page: Page, hash: string) {
  await page.goto(hash);
  await expect(page.locator("#task-canvas")).toBeVisible();
  await page.waitForFunction(() => !!(window as any).__nmActive?.recorder);
  await page.waitForTimeout(300);
}

async function envInfo(page: Page) {
  return page.evaluate(() => ({
    user_agent: navigator.userAgent,
    cross_origin_isolated: (globalThis as any).crossOriginIsolated,
    device_pixel_ratio: devicePixelRatio,
    hardware_concurrency: navigator.hardwareConcurrency,
    timer_resolution_ms: (() => {
      let m = Infinity;
      let l = performance.now();
      for (let i = 0; i < 20000; i++) {
        const t = performance.now();
        if (t - l > 0 && t - l < m) m = t - l;
        l = t;
      }
      return m;
    })(),
  }));
}

test("Experiment A: input adapter timing and consistency (2000 CDP moves + 1000 Hz synthetic stream)", async ({ page }) => {
  await openTask(page, "/#/run/A1?autostart=1&selection=click");
  const env = await envInfo(page);
  const box = (await page.locator("#task-canvas").boundingBox())!;
  const N = 2000;
  const pts = Array.from({ length: N }, (_, i) => ({ x: box.x + 40 + (i % 500) * 2, y: box.y + 40 + Math.floor(i / 500) * 25 }));
  // page side: start the 1000 Hz synthetic pen stream (dispatchEvent on the canvas) and log it
  await page.evaluate((durationMs) => {
    const w = window as any;
    const el = document.getElementById("task-canvas")!;
    const rect = el.getBoundingClientRect();
    const log: { i: number; sched: number; disp: number; ts: number }[] = [];
    w.__synth = { log, done: false };
    const t0 = performance.now() + 20;
    const n = Math.floor(durationMs); // upper bound; the stream stops when the CDP stream ends
    let i = 0;
    const ch = new MessageChannel();
    const pump = () => {
      const now = performance.now();
      while (i < n && t0 + i <= now) {
        const x = rect.left + 30 + (i % 600) * 1.5;
        const y = rect.top + rect.height - 60 - Math.floor(i / 600) * 8;
        const ev = new PointerEvent("pointermove", { clientX: x, clientY: y, pointerType: "pen", isPrimary: true, pointerId: 7, bubbles: true });
        const disp = performance.now();
        el.dispatchEvent(ev);
        log.push({ i, sched: t0 + i, disp, ts: ev.timeStamp });
        i++;
      }
      if (i < n && !w.__synth.stop) ch.port2.postMessage(0);
      else w.__synth.done = true;
    };
    ch.port1.onmessage = pump;
    ch.port2.postMessage(0);
  }, 120_000);
  // node side: 2000 CDP mouse moves at known (node-clock) send times
  const sendT: number[] = [];
  const t0 = performance.now();
  for (const p of pts) {
    sendT.push(performance.now() - t0);
    await page.mouse.move(p.x, p.y);
  }
  await page.evaluate(() => ((window as any).__synth.stop = true));
  await page.waitForFunction(() => (window as any).__synth.done, null, { timeout: 60_000 });
  await page.waitForTimeout(200);
  const data = await page.evaluate(() => {
    const w = window as any;
    const rec = w.__nmActive.recorder;
    const evs = rec.merged().filter((e: any) => e.kind === "pointer_move");
    return { events: evs, synth: w.__synth.log, origin: rec.clock.origin, all: rec.merged() };
  });
  const box2 = (await page.locator("#task-canvas").boundingBox())!;
  const scale = box2.width / 1280;
  // map recorded task-space coordinates back to injected indices
  const mouse = data.events.filter((e: any) => e.stream_id === "in:pointer:mouse");
  const pen = data.events.filter((e: any) => e.stream_id === "in:pointer:pen");
  const idxMouse = (e: any) => {
    const cx = box2.x + e.x * scale;
    const cy = box2.y + e.y * scale;
    const i = Math.round((cx - box2.x - 40) / 2) + 500 * Math.round((cy - box2.y - 40) / 25);
    return i >= 0 && i < N && Math.abs(pts[i].x - cx) < 0.6 && Math.abs(pts[i].y - cy) < 0.6 ? i : -1;
  };
  const mouseIdx = mouse.map(idxMouse);
  const seen = new Map<number, number>();
  for (const i of mouseIdx) if (i >= 0) seen.set(i, (seen.get(i) ?? 0) + 1);
  const dupMouse = [...seen.values()].filter((c) => c > 1).length;
  const missingMouse = N - seen.size;
  const unmatchedMouse = mouseIdx.filter((i) => i < 0).length;
  // order preserved? (injected index sequence must be increasing)
  let orderViolations = 0;
  let last = -1;
  for (const i of mouseIdx) {
    if (i < 0) continue;
    if (i < last) orderViolations++;
    last = i;
  }
  const nonMono = (s: any[]) => s.reduce((a: number, e: any, k: number) => a + (k && e.t_ms < s[k - 1].t_ms ? 1 : 0), 0);
  const clamped = (s: any[]) => s.filter((e: any) => e.meta?.t_clamped_ms !== undefined).length;
  const ivl = (s: any[]) => s.slice(1).map((e: any, k: number) => e.t_ms - s[k].t_ms);
  const sendIvl = sendT.slice(1).map((t, k) => t - sendT[k]);
  // synthetic stream: recorded vs dispatched
  const penSeqOk = pen.every((e: any, k: number) => k === 0 || e.seq === pen[k - 1].seq + 1);
  const synthLog = data.synth as { i: number; sched: number; disp: number; ts: number }[];
  const synthLag = synthLog.map((s) => s.disp - s.sched);
  const penT = pen.map((e: any) => e.t_ms);
  const tsErr = synthLog.slice(0, pen.length).map((s, k) => penT[k] - (s.ts - data.origin));
  // cross-stream ordering in the merged timeline
  const merged = data.events;
  let mergeViolations = 0;
  for (let k = 1; k < merged.length; k++) {
    const a = merged[k - 1];
    const b = merged[k];
    if (a.t_ms > b.t_ms || (a.t_ms === b.t_ms && (a.stream_id > b.stream_id || (a.stream_id === b.stream_id && a.seq > b.seq)))) mergeViolations++;
  }
  let switches = 0;
  for (let k = 1; k < merged.length; k++) if (merged[k].stream_id !== merged[k - 1].stream_id) switches++;
  const [py] = pyValidate([{ task_id: "A1", stimulus_seed: 0, stimulus_hash: "x", events: data.all }], "expA_events");
  const summary = {
    experiment: "A_input_timing (browser part)",
    generated: new Date().toISOString(),
    caveat: CAVEAT,
    environment: env,
    canvas_scale: scale,
    cdp_mouse_stream: {
      injected: N,
      recorded_pointer_move: mouse.length,
      matched_unique: seen.size,
      missing_injected: missingMouse,
      duplicated_injected: dupMouse,
      unmatched_recorded: unmatchedMouse,
      order_violations: orderViolations,
      non_monotonic_t: nonMono(mouse),
      t_clamped_events: clamped(mouse),
      recorded_interval_ms: quantiles(ivl(mouse)),
      node_send_interval_ms: quantiles(sendIvl),
      injection_duration_ms: sendT[sendT.length - 1],
    },
    synthetic_1000hz_stream: {
      dispatched: synthLog.length,
      recorded_pointer_move: pen.length,
      dropped: synthLog.length - pen.length,
      seq_contiguous: penSeqOk,
      non_monotonic_t: nonMono(pen),
      t_clamped_events: clamped(pen),
      recorded_interval_ms: quantiles(ivl(pen)),
      dispatch_minus_schedule_ms: quantiles(synthLag),
      recorded_t_minus_event_timestamp_ms: quantiles(tsErr),
    },
    note_cdp_pacing: "Playwright page.mouse.move() resolves only after the renderer has handled the move, which headless Chromium aligns to animation frames, so CDP moves arrive at ~60 Hz regardless of how fast they are sent; the 1000 Hz stream is generated in-page with dispatchEvent and runs concurrently for the whole CDP injection.",
    two_streams_merged: {
      events: merged.length,
      merge_order_violations: mergeViolations,
      stream_switches_in_merged_timeline: switches,
      python_check_stream: py.stream_report,
      python_validation_errors: py.n_validation_errors,
      python_merge_order_matches: py.merge_order_matches_python,
    },
  };
  const dir = ensureDir(path.join(RESULTS, "A_input_timing"));
  writeFileSync(path.join(dir, "browser_summary.json"), JSON.stringify(summary, null, 1) + "\n");
  writeCsv(
    path.join(dir, "browser_events.csv"),
    ["stream_id", "seq", "t_ms", "interval_ms", "x_task", "y_task", "injected_index"],
    // all CDP mouse events + the first 4000 synthetic pen events (keeps the file small; the
    // summary JSON covers every event)
    (() => {
      const lastT = new Map<string, number>();
      const rows: (string | number)[][] = [];
      let penRows = 0;
      for (const e of merged) {
        const prev = lastT.get(e.stream_id);
        lastT.set(e.stream_id, e.t_ms);
        if (e.stream_id === "in:pointer:pen" && penRows++ >= 4000) continue;
        rows.push([e.stream_id, e.seq, e.t_ms.toFixed(4), prev !== undefined ? (e.t_ms - prev).toFixed(4) : "", e.x.toFixed(2), e.y.toFixed(2), e.stream_id === "in:pointer:mouse" ? idxMouse(e) : ""]);
      }
      return rows;
    })(),
  );
  writeCsv(path.join(dir, "browser_cdp_send_times.csv"), ["index", "node_send_ms"], sendT.map((t, i) => [i, t.toFixed(4)]));
  // assertions: integrity (timing magnitudes are reported, not asserted)
  expect(py.n_validation_errors).toBe(0);
  expect(py.stream_report.non_monotonic).toBe(0);
  expect(py.stream_report.duplicate_seq).toBe(0);
  expect(py.stream_report.seq_gaps).toBe(0);
  expect(mergeViolations).toBe(0);
  expect(pen.length).toBe(synthLog.length);
  expect(orderViolations).toBe(0);
  expect(dupMouse).toBe(0);
});

test("Experiment S part 1: event processing latency (dispatch -> canonical event -> next frame) and long-session stability", async ({ page }) => {
  await openTask(page, "/#/run/A1?autostart=1&selection=click");
  const env = await envInfo(page);
  // --- S1a/b: 1000 synthetic pointer moves at random phases relative to frames
  const lat = await page.evaluate(async (n) => {
    const w = window as any;
    const rec = w.__nmActive.recorder;
    const el = document.getElementById("task-canvas")!;
    const rect = el.getBoundingClientRect();
    const rows: { i: number; disp: number; ts: number; created: number; frame: number; raf_ts: number }[] = [];
    let pending: { created: number; row: number }[] = [];
    let current: { disp: number; ts: number; i: number } | null = null;
    const off = rec.onEvent((ev: any, createdAt: number) => {
      if (!current || ev.kind !== "pointer_move") return;
      rows.push({ i: current.i, disp: current.disp, ts: current.ts, created: createdAt, frame: NaN, raf_ts: NaN });
      pending.push({ created: createdAt, row: rows.length - 1 });
    });
    let running = true;
    const frameLoop = (rafTs: number) => {
      const now = performance.now();
      for (const p of pending) {
        rows[p.row].frame = now;
        rows[p.row].raf_ts = rafTs;
      }
      pending = [];
      if (running) requestAnimationFrame(frameLoop);
    };
    requestAnimationFrame(frameLoop);
    for (let i = 0; i < n; i++) {
      await new Promise((r) => setTimeout(r, 2 + Math.random() * 14));
      const ev = new PointerEvent("pointermove", { clientX: rect.left + 100 + (i % 400), clientY: rect.top + 200, pointerType: "mouse", isPrimary: true, bubbles: true });
      current = { disp: performance.now(), ts: ev.timeStamp, i };
      el.dispatchEvent(ev);
      current = null;
    }
    await new Promise((r) => setTimeout(r, 100));
    running = false;
    off();
    return rows;
  }, 1000);
  const toCreate = lat.map((r) => r.created - r.disp);
  const tsToCreate = lat.map((r) => r.created - r.ts);
  const toFrame = lat.map((r) => r.frame - r.created).filter(Number.isFinite);
  const dispToFrame = lat.map((r) => r.frame - r.disp).filter(Number.isFinite);

  // --- S1c: CDP-injected mouse moves: browser event.timeStamp -> canonical event creation
  const cdp = await page.evaluate(() => {
    const w = window as any;
    const rec = w.__nmActive.recorder;
    const out: number[] = [];
    w.__cdpLat = out;
    w.__cdpOff = rec.onEvent((ev: any, createdAt: number) => {
      if (ev.stream_id === "in:pointer:mouse" && ev.kind === "pointer_move") out.push(createdAt - (rec.clock.origin + ev.t_ms));
    });
    return true;
  });
  expect(cdp).toBe(true);
  const box = (await page.locator("#task-canvas").boundingBox())!;
  for (let i = 0; i < 500; i++) {
    await page.mouse.move(box.x + 50 + (i % 300) * 2, box.y + 300 + Math.floor(i / 300) * 10);
    if (i % 25 === 0) await page.waitForTimeout(5);
  }
  const cdpLat: number[] = await page.evaluate(() => {
    const w = window as any;
    w.__cdpOff();
    return w.__cdpLat;
  });

  // --- S2: long session, 10 minutes at 60 Hz fast-forwarded (36,000 DOM pointer events)
  const stab = await page.evaluate(async () => {
    const w = window as any;
    const rec = w.__nmActive.recorder;
    const el = document.getElementById("task-canvas")!;
    const rect = el.getBoundingClientRect();
    const mem = () => ((performance as any).memory ? (performance as any).memory.usedJSHeapSize : null);
    const gc = () => (typeof w.gc === "function" ? w.gc() : undefined);
    const before = rec.length;
    gc();
    const samples: { events: number; heap: number | null; t: number }[] = [{ events: 0, heap: mem(), t: performance.now() }];
    const TOTAL = 10 * 60 * 60; // 10 min at 60 Hz
    const PER_FRAME = 600; // 10 s of session per animation frame (fast-forward)
    let sent = 0;
    const frameGaps: number[] = [];
    let lastFrame = performance.now();
    while (sent < TOTAL) {
      await new Promise((r) => requestAnimationFrame(() => r(null)));
      const now = performance.now();
      frameGaps.push(now - lastFrame);
      lastFrame = now;
      for (let k = 0; k < PER_FRAME && sent < TOTAL; k++, sent++) {
        const a = (sent / 60) * 0.5;
        el.dispatchEvent(new PointerEvent("pointermove", { clientX: rect.left + rect.width / 2 + Math.cos(a) * 200, clientY: rect.top + rect.height / 2 + Math.sin(a) * 150, pointerType: "mouse", isPrimary: true, bubbles: true }));
      }
      if (sent % 6000 === 0) {
        gc();
        samples.push({ events: sent, heap: mem(), t: performance.now() });
      }
    }
    gc();
    samples.push({ events: sent, heap: mem(), t: performance.now() });
    const recorded = rec.merged().slice(before).filter((e: any) => e.kind === "pointer_move" && e.stream_id === "in:pointer:mouse").length;
    const json = JSON.stringify(rec.merged());
    return { sent, recorded, samples, frameGaps, serialized_bytes: json.length, has_memory_api: mem() !== null, has_gc: typeof w.gc === "function" };
  });
  const heap0 = stab.samples[0].heap ?? NaN;
  const heap1 = stab.samples[stab.samples.length - 1].heap ?? NaN;
  // steady-state growth per event (after the first sample) to separate warm-up from linear growth
  const s = stab.samples;
  const perEvent = s.length > 2 && s[1].heap !== null ? ((s[s.length - 1].heap! - s[1].heap!) / (s[s.length - 1].events - s[1].events)) : NaN;

  const summary = {
    experiment: "S_event_latency part 1 (browser)",
    generated: new Date().toISOString(),
    caveat: CAVEAT,
    environment: env,
    dispatch_to_canonical_event_ms: quantiles(toCreate),
    event_timestamp_to_canonical_event_ms: quantiles(tsToCreate),
    canonical_event_to_next_frame_callback_ms: quantiles(toFrame),
    dispatch_to_next_frame_callback_ms: quantiles(dispToFrame),
    cdp_mouse_event_timestamp_to_canonical_event_ms: quantiles(cdpLat),
    long_session: {
      simulated_minutes: 10,
      rate_hz: 60,
      mode: "fast-forward: 600 DOM pointermove events per animation frame (10 s of session per frame); event timestamps are therefore compressed",
      dispatched: stab.sent,
      recorded: stab.recorded,
      dropped: stab.sent - stab.recorded,
      heap_used_bytes_start: heap0,
      heap_used_bytes_end: heap1,
      heap_growth_bytes: heap1 - heap0,
      heap_growth_bytes_per_event_steady_state: perEvent,
      serialized_session_bytes: stab.serialized_bytes,
      memory_api_available: stab.has_memory_api,
      forced_gc_available: stab.has_gc,
      heap_samples: stab.samples,
      frame_gap_ms_during_fast_forward: quantiles(stab.frameGaps),
      note: "The recorder keeps every canonical event of the session in memory by design (it is the session log), so heap grows linearly with events; the test checks that growth per event is bounded and that no events are dropped.",
    },
  };
  const dir = ensureDir(path.join(RESULTS, "S_event_latency"));
  writeFileSync(path.join(dir, "browser_summary.json"), JSON.stringify(summary, null, 1) + "\n");
  writeCsv(
    path.join(dir, "browser_latency.csv"),
    ["i", "dispatch_to_event_ms", "event_timestamp_to_event_ms", "event_to_next_frame_ms", "dispatch_to_next_frame_ms"],
    lat.map((r) => [r.i, (r.created - r.disp).toFixed(4), (r.created - r.ts).toFixed(4), (r.frame - r.created).toFixed(4), (r.frame - r.disp).toFixed(4)]),
  );
  writeCsv(path.join(dir, "browser_cdp_latency.csv"), ["i", "event_timestamp_to_event_ms"], cdpLat.map((v, i) => [i, v.toFixed(4)]));
  writeCsv(path.join(dir, "browser_long_session_memory.csv"), ["events", "heap_used_bytes", "page_time_ms"], stab.samples.map((x) => [x.events, x.heap, x.t.toFixed(1)]));
  expect(stab.recorded).toBe(stab.sent);
  expect(lat.length).toBe(1000);
  if (Number.isFinite(perEvent)) expect(perEvent).toBeLessThan(4000); // bytes per retained event
});
