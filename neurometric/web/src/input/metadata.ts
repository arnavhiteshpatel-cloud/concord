// Session metadata and in-session timing self-checks (docs/research/browser_timing.md §5.3, §6).
// No fingerprinting beyond what timing interpretation needs; no text, no screen content.

export interface TimingEstimate {
  timer_resolution_ms: number | null;
  refresh_interval_ms_median: number | null;
  refresh_interval_ms_p95: number | null;
  refresh_hz_est: number | null;
  frames_over_1_5x: number;
  frames_sampled: number;
}

export interface SessionMetadata {
  app: string;
  schema_version: string;
  user_agent: string;
  ua_brands: string | null;
  platform: string | null;
  device_pixel_ratio: number;
  viewport_css_px: [number, number];
  screen_css_px: [number, number];
  canvas_scale: number | null;
  cross_origin_isolated: boolean;
  time_origin_epoch_ms: number;
  pointer_events: boolean;
  coalesced_events: boolean;
  gamepad_api: boolean;
  prefers_reduced_motion: boolean;
  prefers_contrast_more: boolean;
  prefers_color_scheme_dark: boolean;
  timing: TimingEstimate;
  /** PointerEvent.pointerType values actually seen (the declared modality is stored separately). */
  observed_pointer_types?: string[];
}

/** Smallest non-zero difference between successive performance.now() readings. */
export function estimateTimerResolution(samples = 20000): number | null {
  let min = Infinity;
  let last = performance.now();
  for (let i = 0; i < samples; i++) {
    const t = performance.now();
    const d = t - last;
    if (d > 0 && d < min) min = d;
    last = t;
  }
  return Number.isFinite(min) ? min : null;
}

function quantile(sorted: number[], q: number): number {
  if (!sorted.length) return NaN;
  const pos = (sorted.length - 1) * q;
  const lo = Math.floor(pos);
  const hi = Math.ceil(pos);
  return sorted[lo] + (sorted[hi] - sorted[lo]) * (pos - lo);
}

/** Display refresh estimate from rAF timestamps (median interval over `frames` frames). */
export function estimateRefresh(frames = 120, timeoutMs = 4000): Promise<{ intervals: number[] }> {
  return new Promise((resolve) => {
    const ts: number[] = [];
    let done = false;
    const finish = () => {
      if (done) return;
      done = true;
      const intervals: number[] = [];
      for (let i = 1; i < ts.length; i++) intervals.push(ts[i] - ts[i - 1]);
      resolve({ intervals });
    };
    const tick = (t: number) => {
      ts.push(t);
      if (ts.length > frames) finish();
      else if (!done) requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
    setTimeout(finish, timeoutMs); // rAF is paused in background tabs
  });
}

export function summariseIntervals(intervals: number[]): Omit<TimingEstimate, "timer_resolution_ms"> {
  const s = [...intervals].sort((a, b) => a - b);
  const med = s.length ? quantile(s, 0.5) : NaN;
  return {
    refresh_interval_ms_median: Number.isFinite(med) ? med : null,
    refresh_interval_ms_p95: s.length ? quantile(s, 0.95) : null,
    refresh_hz_est: Number.isFinite(med) && med > 0 ? 1000 / med : null,
    frames_over_1_5x: Number.isFinite(med) ? intervals.filter((d) => d > 1.5 * med).length : 0,
    frames_sampled: intervals.length,
  };
}

function mq(q: string): boolean {
  try {
    return typeof matchMedia === "function" && matchMedia(q).matches;
  } catch {
    return false;
  }
}

/** Everything that can be read synchronously (refresh-rate fields are filled in later). */
export function syncMetadata(canvasScale: number | null = null): SessionMetadata {
  const nav = navigator as Navigator & { userAgentData?: { brands?: { brand: string; version: string }[]; platform?: string } };
  return {
    app: "neurometric-web/0.1.0",
    schema_version: "1.0",
    user_agent: navigator.userAgent,
    ua_brands: nav.userAgentData?.brands?.map((b) => `${b.brand}/${b.version}`).join(", ") ?? null,
    platform: nav.userAgentData?.platform ?? null,
    device_pixel_ratio: window.devicePixelRatio,
    viewport_css_px: [window.innerWidth, window.innerHeight],
    screen_css_px: [screen.width, screen.height],
    canvas_scale: canvasScale,
    cross_origin_isolated: Boolean(globalThis.crossOriginIsolated),
    time_origin_epoch_ms: performance.timeOrigin,
    pointer_events: typeof PointerEvent !== "undefined",
    coalesced_events: typeof PointerEvent !== "undefined" && "getCoalescedEvents" in PointerEvent.prototype,
    gamepad_api: typeof navigator.getGamepads === "function",
    prefers_reduced_motion: mq("(prefers-reduced-motion: reduce)"),
    prefers_contrast_more: mq("(prefers-contrast: more)"),
    prefers_color_scheme_dark: mq("(prefers-color-scheme: dark)"),
    timing: { timer_resolution_ms: estimateTimerResolution(5000), refresh_interval_ms_median: null, refresh_interval_ms_p95: null, refresh_hz_est: null, frames_over_1_5x: 0, frames_sampled: 0 },
  };
}

export async function collectSessionMetadata(canvasScale: number | null = null): Promise<SessionMetadata> {
  const res = estimateTimerResolution();
  const { intervals } = await estimateRefresh();
  const nav = navigator as Navigator & { userAgentData?: { brands?: { brand: string; version: string }[]; platform?: string } };
  return {
    app: "neurometric-web/0.1.0",
    schema_version: "1.0",
    user_agent: navigator.userAgent,
    ua_brands: nav.userAgentData?.brands?.map((b) => `${b.brand}/${b.version}`).join(", ") ?? null,
    platform: nav.userAgentData?.platform ?? null,
    device_pixel_ratio: window.devicePixelRatio,
    viewport_css_px: [window.innerWidth, window.innerHeight],
    screen_css_px: [screen.width, screen.height],
    canvas_scale: canvasScale,
    cross_origin_isolated: Boolean(globalThis.crossOriginIsolated),
    time_origin_epoch_ms: performance.timeOrigin,
    pointer_events: typeof PointerEvent !== "undefined",
    coalesced_events: typeof PointerEvent !== "undefined" && "getCoalescedEvents" in PointerEvent.prototype,
    gamepad_api: typeof navigator.getGamepads === "function",
    prefers_reduced_motion: mq("(prefers-reduced-motion: reduce)"),
    prefers_contrast_more: mq("(prefers-contrast: more)"),
    prefers_color_scheme_dark: mq("(prefers-color-scheme: dark)"),
    timing: { timer_resolution_ms: res, ...summariseIntervals(intervals) },
  };
}
