import type { ConnectionStatus, RuntimeSnapshot } from "../../sdk";
import type { DiagnosticsSnapshot } from "../api";
import { fmt } from "./ui";

export function Header({
  runtime,
  conn,
  diag,
}: {
  runtime: RuntimeSnapshot | null;
  conn: ConnectionStatus;
  diag: DiagnosticsSnapshot | null;
}) {
  const state = runtime?.state ?? "unknown";
  const rate = diag?.event_types.reduce((a, t) => a + t.rate_hz, 0) ?? 0;
  return (
    <header className="topbar">
      <div className="brand">
        <div className="logo" aria-hidden>
          <span />
          <span />
          <span />
        </div>
        <div>
          <div className="brand-name">BrainOS</div>
          <div className="brand-sub">Runtime Console · v0.1 MVP</div>
        </div>
      </div>
      <div className="topbar-mid">
        <span className={`state-pill state-${state}`} data-testid="runtime-state">
          {state}
        </span>
        <div className="topbar-field">
          <span className="label">device</span>
          <span data-testid="runtime-device">{runtime?.device?.display_name ?? "none"}</span>
        </div>
        <div className="topbar-field">
          <span className="label">session</span>
          <span className="mono">{runtime?.session_id?.slice(0, 12) ?? "—"}</span>
        </div>
        <div className="topbar-field">
          <span className="label">events/s</span>
          <span className="mono">{fmt.num(rate, 0)}</span>
        </div>
        <div className="topbar-field">
          <span className="label">pipeline p95</span>
          <span className="mono">{fmt.us(diag?.pipeline_latency.p95_us)}</span>
        </div>
        {runtime?.recording && (
          <span className="chip rec" data-testid="recording-indicator">
            REC {runtime.recording}
          </span>
        )}
      </div>
      <div className="topbar-right">
        <span className={`chip conn-${conn}`}>stream {conn}</span>
        <span className="chip plain badge-ro" title="v1 has no write or stimulation path">
          READ-ONLY
        </span>
        {runtime?.device &&
          (runtime.device.synthetic ? (
            <span className="chip plain badge-sim" title="The connected source generates synthetic data" data-testid="data-badge">
              SIMULATED DATA
            </span>
          ) : (
            <span
              className="chip plain badge-real"
              title="Genuine recorded data replayed from a file — not a live implant"
              data-testid="data-badge"
            >
              RECORDED HUMAN DATA · OFFLINE REPLAY
            </span>
          ))}
      </div>
    </header>
  );
}
