// Live counters of the connected LSL / Open Ephys source, exactly as the adapter reports
// them in /devices/{id}/source. Only fields present in the dict are rendered: the two
// protocols report different things and nothing here is derived or estimated.

import type { ReactNode } from "react";
import type { DiagnosticsSnapshot, LiveSourceMetadata } from "../api";
import { Panel, fmt } from "./ui";

type Obj = Record<string, unknown>;
const isObj = (v: unknown): v is Obj => typeof v === "object" && v !== null && !Array.isArray(v);
const num = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null);
const str = (v: unknown): string | null => (typeof v === "string" && v ? v : null);

/** Counters whose non-zero value means data was lost, rejected or late. */
const ATTENTION =
  /gap|missing|missed|malformed|lost|stall|timeout|error|incomplete|discarded|regression|duplicate|overflow|nonfinite|skipped/;

const label = (k: string) => k.replace(/_/g, " ");

function Counters({ counters, testId }: { counters: Obj; testId: string }) {
  const entries = Object.entries(counters).filter((e): e is [string, number] => num(e[1]) !== null);
  if (!entries.length) return null;
  return (
    <div className="counter-grid" data-testid={testId}>
      {entries.map(([k, v]) => (
        <div key={k} className={`counter ${ATTENTION.test(k) && v > 0 ? "counter-warn" : ""}`} data-counter={k}>
          <span className="counter-name">{label(k)}</span>
          <span className="counter-value num">{fmt.num(v)}</span>
        </div>
      ))}
    </div>
  );
}

function Row({ k, v }: { k: string; v: ReactNode }) {
  return (
    <tr>
      <td>{k}</td>
      <td>{v}</td>
    </tr>
  );
}

function LslStreams({ streams }: { streams: unknown[] }) {
  const rows = streams.filter(isObj);
  if (!rows.length) return null;
  return (
    <div className="table-scroll">
      <table className="table" data-testid="integrity-streams">
        <thead>
          <tr>
            <th>Role</th>
            <th>Stream</th>
            <th className="r">Received</th>
            <th className="r">Gaps</th>
            <th className="r">Est. missing</th>
            <th className="r">Time correction</th>
            <th className="r">Last timestamp</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((s, i) => {
            const corr = num(s.time_correction_s);
            const last = num(s.last_timestamp_s);
            const gaps = num(s.gaps);
            const miss = num(s.estimated_missing_samples);
            return (
              <tr key={`${String(s.role)}-${i}`}>
                <td>{str(s.role) ?? "—"}</td>
                <td>
                  {str(s.name) ?? "—"} {str(s.type) ? `(${str(s.type)})` : ""}
                </td>
                <td className="r num">{fmt.num(num(s.received_samples))}</td>
                <td className={`r num ${gaps ? "caution-text" : ""}`}>{fmt.num(gaps)}</td>
                <td className={`r num ${miss ? "caution-text" : ""}`}>{fmt.num(miss)}</td>
                <td className="r num">{corr === null ? "—" : `${(corr * 1000).toFixed(3)} ms`}</td>
                <td className="r num">{last === null ? "—" : `${last.toFixed(3)} s`}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export function SignalIntegrity({
  meta,
  error,
  diag,
}: {
  meta: LiveSourceMetadata | null;
  error: string | null;
  diag: DiagnosticsSnapshot | null;
}) {
  if (!meta) {
    return (
      <Panel title="Live source counters" testId="signal-integrity">
        {error ? <p className="error-text">{error}</p> : <p className="value-muted">Waiting for source counters…</p>}
      </Panel>
    );
  }
  const protocol = str(meta.protocol);
  const counters = isObj(meta.stats) ? meta.stats : isObj(meta.counters) ? meta.counters : null;
  const streams = Array.isArray(meta.streams) ? meta.streams : null;
  const offset = isObj(meta.sender_to_local_offset_ms) ? meta.sender_to_local_offset_ms : null;
  const heartbeat = isObj(meta.heartbeat) ? meta.heartbeat : null;
  const notes = [
    ...(Array.isArray(meta.notes) ? meta.notes.filter((n): n is string => typeof n === "string") : []),
    ...[meta.unit_note, meta.liveness_note].filter((n): n is string => typeof n === "string"),
  ];
  const lastError = str(meta.last_error);
  const rc = diag?.counters;

  return (
    <Panel
      title="Live source counters"
      testId="signal-integrity"
      right={<span className="hint">{protocol ?? "live source"} · polled every second</span>}
    >
      <table className="table kv">
        <tbody>
          {str(meta.device_id) && <Row k="Source" v={str(meta.device_id)} />}
          {str(meta.library) && <Row k="Library" v={str(meta.library)} />}
          {str(meta.host) && <Row k="Endpoint" v={`${str(meta.host)}:${num(meta.data_port) ?? "?"}`} />}
          {str(meta.stream) && <Row k="Stream" v={str(meta.stream)} />}
          {num(meta.sample_rate_hz) !== null && <Row k="Rate" v={`${num(meta.sample_rate_hz)} Hz`} />}
          {str(meta.interpretation) && <Row k="Interpreted as" v={str(meta.interpretation)} />}
          {str(meta.unit) && <Row k="Unit" v={str(meta.unit)} />}
          {str(meta.unit_configured) && (
            <Row k="Unit" v={`configured ${str(meta.unit_configured)} → emitted ${str(meta.unit_emitted) ?? "?"}`} />
          )}
          {heartbeat && str(heartbeat.status) && <Row k="Heartbeat" v={str(heartbeat.status)} />}
          {num(meta.last_message_num) !== null && <Row k="Last message #" v={fmt.num(num(meta.last_message_num))} />}
          {offset && (num(offset.last) !== null || num(offset.min) !== null) && (
            <Row
              k="Clock offset"
              v={
                <span title={str(offset.note) ?? undefined}>
                  last {fmt.num(num(offset.last), 3)} ms · min {fmt.num(num(offset.min), 3)} ms
                </span>
              }
            />
          )}
          {rc && (
            <Row
              k="Runtime (since start)"
              v={`reconnect attempts ${fmt.num(rc.reconnect_attempts)} · successes ${fmt.num(rc.reconnect_successes)} · link errors ${fmt.num(rc.link_errors)}`}
            />
          )}
        </tbody>
      </table>
      {counters && <Counters counters={counters} testId="integrity-counters" />}
      {streams && <LslStreams streams={streams} />}
      {offset && str(offset.note) && <p className="hint">Clock offset: {str(offset.note)}.</p>}
      {lastError && (
        <p className="error-text" data-testid="integrity-last-error">
          {lastError}
        </p>
      )}
      {notes.length > 0 && (
        <ul className="notes hint" data-testid="integrity-notes">
          {notes.map((n) => (
            <li key={n}>{n}</li>
          ))}
        </ul>
      )}
    </Panel>
  );
}
