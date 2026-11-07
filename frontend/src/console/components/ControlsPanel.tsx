import { useState } from "react";
import type { RuntimeSnapshot } from "../../sdk";
import { isLiveSource, isRecordable, type Fault, type RecordingInfo } from "../api";
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
  onStartRecording: (excludeRaw: boolean) => void;
  onStopRecording: () => void;
  onFault: (f: Fault) => void;
}) {
  const state = runtime?.state ?? "idle";
  const hasDevice = !!runtime?.device;
  // Fault injection exists only for the built-in simulator (an LSL stream declared synthetic is
  // kind "simulated" too, but it is an external publisher: nothing can be injected into it).
  const simulated =
    runtime?.device?.kind === "simulated" && !isLiveSource(runtime.device) && state !== "error" && state !== "idle";
  const canRecord = (state === "streaming" || state === "paused") && isRecordable(runtime?.device);
  const [excludeRaw, setExcludeRaw] = useState(false);
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
            <button
              className="btn"
              disabled={busy || !canRecord}
              onClick={() => onStartRecording(excludeRaw)}
              data-testid="rec-start"
            >
              Start recording
            </button>
          )}
        </div>
        {!runtime?.recording && (
          <label className="check small" title="Everything except recording.frame; limit 3600 s instead of 300 s">
            <input
              type="checkbox"
              checked={excludeRaw}
              onChange={(e) => setExcludeRaw(e.target.checked)}
              data-testid="rec-exclude-raw"
            />
            features + labels only (for calibration)
          </label>
        )}
        <p className="muted small">
          Writes the standardized events of the connected session (simulator or live LSL / Open Ephys source,
          plus pipeline features and decoder output while the pipeline runs) to <code>data/recordings/</code>.
          Recordings appear as replay devices and can be used for calibration (Pipeline tab). With a raw
          high-rate source, record <b>features + labels only</b>: raw frames would reach the size cap in seconds.
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
