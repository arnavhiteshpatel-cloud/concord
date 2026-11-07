import type { StreamStats } from "../../sdk";
import type { DiagnosticsSnapshot } from "../api";
import { percentile } from "../useConsoleStream";
import { AppsPanel } from "./AppsPanel";
import { Kpi, Panel, fmt } from "./ui";

export function DiagnosticsView({
  diag,
  clientLatencyMs,
  stats,
}: {
  diag: DiagnosticsSnapshot | null;
  clientLatencyMs: number[];
  stats: StreamStats;
}) {
  if (!diag) return <div className="empty">Loading diagnostics…</div>;
  const c = diag.counters;
  const errs = c.decode_errors + c.validation_errors + c.undeclared_capability;
  const p = diag.pipeline_latency;
  const d = diag.delivery_latency;
  return (
    <div className="diag" data-testid="diagnostics">
      <p className="muted small">
        Every number below is measured live in this process (runtime) or this browser (client). Pipeline
        = packet read from the device by the adapter → validated envelope enqueued for all subscribers (includes
        waiting behind other packets read in the same tick, e.g. pointer packets behind 32-channel frames). Delivery = enqueued →
        written to the WebSocket. Client = runtime ingest timestamp → received in this tab (same-machine clocks,
        ms resolution).
      </p>
      <div className="kpis">
        <Kpi label="events published" value={fmt.num(c.events_published)} />
        <Kpi label="pipeline p50" value={fmt.us(p.p50_us)} />
        <Kpi label="pipeline p99" value={fmt.us(p.p99_us)} />
        <Kpi label="delivery p95" value={fmt.us(d.p95_us)} />
        <Kpi label="client p50" value={fmt.num(percentile(clientLatencyMs, 0.5), 1)} unit="ms" />
        <Kpi label="client p95" value={fmt.num(percentile(clientLatencyMs, 0.95), 1)} unit="ms" />
        <Kpi label="contract violations" value={fmt.num(errs)} tone={errs ? "warn" : "ok"} />
        <Kpi label="subscriber drops" value={fmt.num(c.subscriber_drops)} tone={c.subscriber_drops ? "warn" : "ok"} />
        <Kpi
          label="reconnects ok / tried"
          value={`${c.reconnect_successes} / ${c.reconnect_attempts}`}
          tone={c.link_errors ? "warn" : undefined}
        />
        <Kpi label="uptime" value={fmt.num(diag.uptime_s, 0)} unit="s" />
      </div>

      <div className="diag-grid">
        <Panel title="Event types (5 s rolling rate)">
          <table className="table">
            <thead>
              <tr>
                <th>event type</th>
                <th className="r">rate</th>
                <th className="r">total</th>
              </tr>
            </thead>
            <tbody>
              {diag.event_types.map((t) => (
                <tr key={t.event_type}>
                  <td className="mono">{t.event_type}</td>
                  <td className="r mono">{fmt.num(t.rate_hz, 1)} Hz</td>
                  <td className="r mono">{fmt.num(t.total)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>

        <Panel title="Counters">
          <table className="table">
            <tbody>
              {Object.entries(c).map(([k, v]) => (
                <tr key={k}>
                  <td className="mono">{k}</td>
                  <td className={`r mono ${v && /error|undeclared|drops|regress/.test(k) ? "text-warn" : ""}`}>
                    {fmt.num(v)}
                  </td>
                </tr>
              ))}
              <tr>
                <td className="mono">console delivery gaps</td>
                <td className="r mono">{stats.deliveryGaps}</td>
              </tr>
              <tr>
                <td className="mono">console out-of-order</td>
                <td className="r mono">{stats.outOfOrder}</td>
              </tr>
            </tbody>
          </table>
        </Panel>

        <Panel title="Latency percentiles · microseconds · last 4096 events">
          <table className="table">
            <thead>
              <tr>
                <th />
                <th className="r">n</th>
                <th className="r">p50</th>
                <th className="r">p95</th>
                <th className="r">p99</th>
                <th className="r">max</th>
              </tr>
            </thead>
            <tbody>
              {[
                ["pipeline", p],
                ["delivery", d],
              ].map(([name, s]) => {
                const l = s as typeof p;
                return (
                  <tr key={name as string}>
                    <td>{name as string}</td>
                    <td className="r mono">{l.count}</td>
                    <td className="r mono">{fmt.num(l.p50_us, 0)}</td>
                    <td className="r mono">{fmt.num(l.p95_us, 0)}</td>
                    <td className="r mono">{fmt.num(l.p99_us, 0)}</td>
                    <td className="r mono">{fmt.num(l.max_us, 0)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </Panel>

        <Panel title="Device switches">
          {diag.switches.length ? (
            <table className="table">
              <thead>
                <tr>
                  <th>at</th>
                  <th>from → to</th>
                  <th className="r">duration</th>
                </tr>
              </thead>
              <tbody>
                {[...diag.switches].reverse().map((s) => (
                  <tr key={s.at_ns}>
                    <td className="mono">{fmt.time(s.at_ns)}</td>
                    <td className="mono">
                      {s.from_device ?? "—"} → {s.to_device}
                    </td>
                    <td className="r mono">{s.duration_ms.toFixed(1)} ms</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <div className="empty">No switches yet.</div>
          )}
        </Panel>

        <Panel title="Recent errors" className="span-2">
          {diag.recent_errors.length ? (
            <table className="table">
              <tbody>
                {[...diag.recent_errors].reverse().slice(0, 15).map((e, i) => (
                  <tr key={`${e.at_ns}-${i}`}>
                    <td className="mono nowrap">{fmt.time(e.at_ns)}</td>
                    <td className="mono text-warn nowrap">{e.kind}</td>
                    <td className="mono muted nowrap">{e.device_id ?? ""}</td>
                    <td>{e.message}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <div className="empty">No errors recorded.</div>
          )}
        </Panel>

        <Panel title="Process">
          <table className="table">
            <tbody>
              {Object.entries(diag.process).map(([k, v]) => (
                <tr key={k}>
                  <td>{k}</td>
                  <td className="mono">{v}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>
      </div>
    </div>
  );
}

export { AppsPanel };
