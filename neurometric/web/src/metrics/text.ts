// TypeScript subset of neurometric.metrics.text (Soukoreff & MacKenzie 2003) for provisional
// feedback; checked against Python golden fixtures. Text content is only ever processed for the
// predefined copy-typing phrases (E1).

export const BACKSPACE = "\b";

export function msd(a: string, b: string): number {
  const A = Array.from(a);
  const B = Array.from(b);
  if (a === b) return 0;
  if (!A.length) return B.length;
  if (!B.length) return A.length;
  let prev = Array.from({ length: B.length + 1 }, (_, i) => i);
  for (let i = 1; i <= A.length; i++) {
    const cur = [i];
    for (let j = 1; j <= B.length; j++) {
      cur.push(Math.min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (A[i - 1] !== B[j - 1] ? 1 : 0)));
    }
    prev = cur;
  }
  return prev[B.length];
}

export function applyStream(stream: string[]): string {
  const out: string[] = [];
  for (const k of stream) {
    if (k === BACKSPACE) out.pop();
    else out.push(k);
  }
  return out.join("");
}

export interface TextEntryResult {
  presented_len: number;
  transcribed_len: number;
  keystrokes: number;
  seconds: number;
  msd: number;
  msd_error_rate: number;
  wpm: number;
  ccpm: number;
  kspc: number;
  C: number;
  INF: number;
  IF: number;
  F: number;
  corrected_error_rate: number;
  uncorrected_error_rate: number;
  total_error_rate: number;
  correction_burden: number;
}

export function textEntryMetrics(presented: string, stream: string[], seconds: number): TextEntryResult {
  const T = applyStream(stream);
  const tl = Array.from(T).length;
  const pl = Array.from(presented).length;
  const d = msd(presented, T);
  const nMax = Math.max(pl, tl);
  const C = Math.max(nMax - d, 0);
  const INF = d;
  const F = stream.filter((k) => k === BACKSPACE).length;
  const nonEdit = stream.length - F;
  const IF = Math.max(nonEdit - tl, 0);
  const denom = C + INF + IF;
  const minutes = seconds > 0 ? seconds / 60 : NaN;
  return {
    presented_len: pl,
    transcribed_len: tl,
    keystrokes: stream.length,
    seconds,
    msd: d,
    msd_error_rate: nMax ? d / nMax : 0,
    wpm: seconds > 0 && tl > 0 ? (((tl - 1) / seconds) * 60) / 5 : NaN,
    ccpm: seconds > 0 ? Math.max(tl - d, 0) / minutes : NaN,
    kspc: tl ? stream.length / tl : NaN,
    C, INF, IF, F,
    corrected_error_rate: denom ? IF / denom : 0,
    uncorrected_error_rate: denom ? INF / denom : 0,
    total_error_rate: denom ? (INF + IF) / denom : 0,
    correction_burden: tl ? F / tl : NaN,
  };
}
