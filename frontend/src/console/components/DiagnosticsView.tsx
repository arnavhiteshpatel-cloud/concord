import type { StreamStats } from "../../sdk";
import type { DiagnosticsSnapshot } from "../api";
import { percentile } from "../useConsoleStream";
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
  if (!diag) return <p className="value-muted">Diagnostics unavailable.</p>;
  const c = diag.counters;
  const errs = c.decode_errors + c.validation_errors + c.undeclared_capability;
  const p = diag.pipeline_latency;
  const d = diag.delivery_latency;
  return (
    <div className="diag" data-testid="diagnostics">
      <p className="hint">
        Every number below is measured live in this process (runtime) or this browser (client). Pipeline
        = packet read from the device by the adapter → validated envelope enqueued for all subscribers (includes
        waiting behind other packets read in the same tick, e.g. pointer packets behind 32-channel frames). Delivery = enqueued →
        written to the WebSocket. Client = runtime ingest timestamp → received in this tab (same-machine clocks,
        ms resolution).
      </p>
      <div className="kpis">
        <Kpi label="Events published" value={fmt.num(c.events_published)} />
        <Kpi label="Runtime pipeline p50" value={fmt.us(p.p50_us)} />
        <Kpi label="Runtime pipeline p99" value={fmt.us(p.p99_us)} />
        <Kpi label="Delivery p95" value={fmt.us(d.p95_us)} />
        <Kpi label="Client p50" value={fmt.num(percentile(clientLatencyMs, 0.5), 1)} unit="ms" />
        <Kpi label="Client p95" value={fmt.num(percentile(clientLatencyMs, 0.95), 1)} unit="ms" />
        <Kpi label="Contract violations" value={fmt.num(errs)} tone={errs ? "warn" : undefined} />
        <Kpi label="Subscriber drops" value={fmt.num(c.subscriber_drops)} tone={c.subscriber_drops ? "warn" : undefined} />
        <Kpi
          label="Reconnects ok / tried"
          value={`${c.reconnect_successes} / ${c.reconnect_attempts}`}
          tone={c.link_errors ? "warn" : undefined}
        />
        <Kpi label="Uptime" value={fmt.num(diag.uptime_s, 0)} unit="s" />
      </div>

      <div className="diag-grid">
        <Panel title="Event types (5 s rolling rate)">
          <table className="table">
            <thead>
              <tr>
                <th>Event type</th>
                <th className="r">Rate</th>
                <th className="r">Total</th>
              </tr>
            </thead>
            <tbody>
              {diag.event_types.map((t) => (
                <tr key={t.event_type}>
                  <td className="mono">{t.event_type}</td>
                  <td className="r num">{fmt.num(t.rate_hz, 1)} Hz</td>
                  <td className="r num">{fmt.num(t.total)}</td>
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
                  <td>{k.replace(/_/g, " ")}</td>
                  <td className="r num">
                    {fmt.num(v)}
                  </td>
                </tr>
              ))}
              <tr>
                <td>console delivery gaps</td>
                <td className="r num">{stats.deliveryGaps}</td>
              </tr>
              <tr>
                <td>console out-of-order</td>
                <td className="r num">{stats.outOfOrder}</td>
              </tr>
            </tbody>
          </table>
        </Panel>

        <Panel title="Latency percentiles in µs (last 4,096 events)">
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
                    <td className="r num">{l.count}</td>
                    <td className="r num">{fmt.num(l.p50_us, 0)}</td>
                    <td className="r num">{fmt.num(l.p95_us, 0)}</td>
                    <td className="r num">{fmt.num(l.p99_us, 0)}</td>
                    <td className="r num">{fmt.num(l.max_us, 0)}</td>
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
                  <th>At</th>
                  <th>From → to</th>
                  <th className="r">Duration</th>
                </tr>
              </thead>
              <tbody>
                {[...diag.switches].reverse().map((s) => (
                  <tr key={s.at_ns}>
                    <td className="mono">{fmt.time(s.at_ns)}</td>
                    <td className="mono">
                      {s.from_device ?? "—"} → {s.to_device}
                    </td>
                    <td className="r num">{s.duration_ms.toFixed(1)} ms</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className="value-muted">No switches yet.</p>
          )}
        </Panel>

        <Panel title="Recent errors" className="span-2">
          {diag.recent_errors.length ? (
            <table className="table">
              <tbody>
                {[...diag.recent_errors].reverse().slice(0, 15).map((e, i) => (
                  <tr key={`${e.at_ns}-${i}`}>
                    <td className="mono nowrap">{fmt.time(e.at_ns)}</td>
                    <td className="nowrap">{e.kind}</td>
                    <td className="mono muted nowrap">{e.device_id ?? ""}</td>
                    <td>{e.message}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className="value-muted">No errors recorded.</p>
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

