import type { RuntimeSnapshot } from "../../sdk";
import type { Fault, RecordingInfo } from "../api";
import { Panel, fmt } from "./ui";

const FAULTS: { fault: Fault; label: string; hint: string }[] = [
  { fault: "link_drop", label: "Link drop", hint: "Recoverable: runtime reconnects automatically" },
  { fault: "link_fail", label: "Link failure", hint: "Unrecoverable: reconnect attempts fail → error" },
  { fault: "malformed_packet", label: "Malformed packet", hint: "Corrupt native packet: dropped and counted" },
  { fault: "timestamp_regression", label: "Clock regression", hint: "Device clock jumps back: flagged" },
];

export function ControlsPanel({
  runtime,
  busy,
  recordings,
  onPause,
  onResume,
  onDisconnect,
  onStartRecording,
  onStopRecording,
  onFault,
}: {
  runtime: RuntimeSnapshot | null;
  busy: boolean;
  recordings: RecordingInfo[];
  onPause: () => void;
  onResume: () => void;
  onDisconnect: () => void;
  onStartRecording: () => void;
  onStopRecording: () => void;
  onFault: (f: Fault) => void;
}) {
  const state = runtime?.state ?? "idle";
  const hasDevice = !!runtime?.device;
  const simulated = runtime?.device?.kind === "simulated" && state !== "error" && state !== "idle";
  const canRecord =
    (state === "streaming" || state === "paused") && runtime?.device?.kind === "simulated";
  return (
    <>
      <Panel title="Runtime">
        <div className="btn-row">
          {state === "paused" ? (
            <button className="btn" disabled={busy} onClick={onResume} data-testid="resume">
              Resume
            </button>
          ) : (
            <button
              className="btn"
              disabled={busy || state !== "streaming"}
              onClick={onPause}
              data-testid="pause"
            >
              Pause
            </button>
          )}
          <button
            className="btn btn-danger"
            disabled={busy || (!hasDevice && state === "idle")}
            onClick={onDisconnect}
            data-testid="disconnect"
          >
            {state === "error" || state === "ended" ? "Reset" : "Disconnect"}
          </button>
        </div>
        {runtime?.last_error && (
          <div className="alert" data-testid="last-error">
            {runtime.last_error}
          </div>
        )}
      </Panel>

      <Panel
        title="Recording"
        right={runtime?.recording ? <span className="chip rec">recording</span> : undefined}
      >
        <div className="btn-row">
          {runtime?.recording ? (
            <button className="btn btn-danger" disabled={busy} onClick={onStopRecording} data-testid="rec-stop">
              Stop recording
            </button>
          ) : (
            <button className="btn" disabled={busy || !canRecord} onClick={onStartRecording} data-testid="rec-start">
              Start recording
            </button>
          )}
        </div>
        <p className="muted small">
          Writes the standardized events of the live simulated session to <code>data/recordings/</code>.
          Recordings appear as replay devices.
        </p>
        {recordings.length > 0 && (
          <ul className="rec-list">
            {recordings.slice(0, 4).map((r) => (
              <li key={r.name}>
                <span className="mono">{r.name}</span>
                <span className="muted">
                  {fmt.bytes(r.size_bytes)} · {fmt.ago(r.created_at_ns)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </Panel>

      <Panel title="Fault injection" right={<span className="muted">simulated devices</span>}>
        <div className="fault-grid">
          {FAULTS.map((f) => (
            <button
              key={f.fault}
              className="btn btn-small"
              disabled={busy || !simulated}
              title={f.hint}
              onClick={() => onFault(f.fault)}
              data-testid={`fault-${f.fault}`}
            >
              {f.label}
            </button>
          ))}
        </div>
        {!simulated && <p className="muted small">Connect a simulated profile to inject faults.</p>}
      </Panel>
    </>
  );
}
