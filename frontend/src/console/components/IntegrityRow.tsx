// Row 2 — Signal integrity, laid out like a patient monitor: four live traces on the left,
// the verdict and three measured numbers stacked on the right.

import { VERDICT_RULE } from "../integrity";
import type { NeuralBuffer } from "../neuralBuffer";
import type { SignalBuffer } from "../signalBuffer";
import type { Tone } from "../wording";
import { TRACE_COUNT, Traces, traceWindowS } from "./Traces";
import { Dot, Row, fmt } from "./ui";

export interface IntegrityFigures {
  verdict: { text: string; tone: Tone };
  /** channels in the latest data event / declared by the source */
  channels: { latest: number | null; declared: number | null };
  received: { pct: number; basis: string } | null;
  /** median client latency, ms */
  delayMs: number | null;
  traces: "raw" | "binned" | null;
}

function Figure({ label, value, title, testId }: { label: string; value: string; title: string; testId: string }) {
  return (
    <div className="figure" title={title}>
      <div className="figure-value num" data-testid={testId}>
        {value}
      </div>
      <div className="figure-label">{label}</div>
    </div>
  );
}

export function IntegrityRow({
  connected,
  f,
  signal,
  neural,
}: {
  connected: boolean;
  f: IntegrityFigures;
  signal: SignalBuffer;
  neural: NeuralBuffer;
}) {
  const { latest, declared } = f.channels;
  const channels =
    latest !== null && declared !== null ? `${fmt.num(latest)} of ${fmt.num(declared)}` : fmt.num(latest ?? declared);
  const total = f.traces === "raw" ? signal.channelCount : f.traces === "binned" ? neural.channelCount : 0;
  const shown = Math.min(TRACE_COUNT, total);
  const verdict = (
    <p className="verdict" title={VERDICT_RULE} data-testid="verdict" data-tone={f.verdict.tone}>
      <Dot tone={f.verdict.tone} />
      {f.verdict.text}
    </p>
  );
  if (!connected) {
    return (
      <Row title="Signal integrity" explain="Whether the data is arriving complete and on time." testId="row-integrity">
        {verdict}
        <p className="value-sub">No source connected.</p>
      </Row>
    );
  }
  return (
    <Row title="Signal integrity" explain="Whether the data is arriving complete and on time." testId="row-integrity">
      <div className="monitor">
        <div className="monitor-traces">
          {shown > 0 && f.traces ? (
            <>
              <Traces mode={f.traces} signal={signal} neural={neural} />
              <p className="caption" data-testid="trace-caption">
                Showing {shown} of {fmt.num(total)} channels
                {f.traces === "raw"
                  ? ` · raw samples, last ${traceWindowS("raw", 0)} s, each scaled to fit`
                  : ` with the most activity · ${neural.feature.replace(/_/g, " ")} per ${neural.binMs} ms bin, last ${traceWindowS("binned", neural.binMs).toFixed(0)} s`}
              </p>
            </>
          ) : (
            <div className="well well-empty">
              <span>Waiting for data</span>
            </div>
          )}
        </div>
        <div className="monitor-numbers">
          {verdict}
          <Figure
            label="Channels"
            value={channels}
            title="Channels in the latest data block, of the channels the source declares."
            testId="fig-channels"
          />
          <Figure
            label="Data received (%)"
            value={f.received ? f.received.pct.toFixed(f.received.pct >= 99.95 ? 0 : 1) : "—"}
            title={
              f.received
                ? `Reported by the source adapter: ${f.received.basis}.`
                : "This source does not report lost data, so no percentage is shown."
            }
            testId="fig-received"
          />
          <Figure
            label="Delay to this screen (ms)"
            value={f.delayMs === null ? "—" : fmt.num(Math.max(0, f.delayMs), f.delayMs < 10 ? 1 : 0)}
            title="Median time from the runtime receiving an event to this screen receiving it (last 1,000 events, measured in this browser)."
            testId="fig-delay"
          />
        </div>
      </div>
    </Row>
  );
}
