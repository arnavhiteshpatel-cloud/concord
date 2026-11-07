// Advanced: session recording, and fault injection into the built-in simulator.

import { useState } from "react";
import type { RuntimeSnapshot } from "../../sdk";
import { consoleApi, isLiveSource, isRecordable, type Fault, type RecordingInfo } from "../api";
import { useLog, useLoggedAction } from "../context";
import { fmt } from "./ui";

const FAULTS: { fault: Fault; label: string; hint: string }[] = [
  { fault: "link_drop", label: "Link drop", hint: "Recoverable: the runtime reconnects automatically" },
  { fault: "link_fail", label: "Link failure", hint: "Unrecoverable: reconnect attempts fail, then error" },
  { fault: "malformed_packet", label: "Malformed packet", hint: "Corrupt native packet: dropped and counted" },
  { fault: "timestamp_regression", label: "Clock regression", hint: "Device clock jumps back: flagged" },
];

/** Fault injection exists only for the built-in simulator (an LSL stream declared synthetic is
 * kind "simulated" too, but it is an external publisher: nothing can be injected into it). */
export function isBuiltInSimulator(runtime: RuntimeSnapshot | null): boolean {
  const state = runtime?.state;
  return (
    runtime?.device?.kind === "simulated" &&
    !isLiveSource(runtime.device) &&
    state !== "error" &&
    state !== "idle" &&
    state !== undefined
  );
}

export function RecordingPanel({
  runtime,
  recordings,
  onRecordingsChanged,
}: {
  runtime: RuntimeSnapshot | null;
  recordings: RecordingInfo[];
  onRecordingsChanged: () => void;
}) {
  const action = useLoggedAction();
  const state = runtime?.state ?? "idle";
  const canRecord = (state === "streaming" || state === "paused") && isRecordable(runtime?.device);
  const [excludeRaw, setExcludeRaw] = useState(false);
  const start = async () => {
    // the session log entries come from the runtime's recording state
    await action.run(() => consoleApi.startRecording(undefined, excludeRaw));
  };
  const stop = async () => {
    if (await action.run(() => consoleApi.stopRecording())) onRecordingsChanged();
  };
  return (
    <div data-testid="recording-panel">
      <div className="btn-row">
        {runtime?.recording ? (
          <button type="button" className="btn" disabled={action.busy} onClick={stop} data-testid="rec-stop">
            Stop recording
          </button>
        ) : (
          <button type="button" className="btn" disabled={action.busy || !canRecord} onClick={start} data-testid="rec-start">
            Start recording
          </button>
        )}
        {!runtime?.recording && (
          <label className="check" title="Everything except raw frames; limit 3600 s instead of 300 s">
            <input
              type="checkbox"
              checked={excludeRaw}
              onChange={(e) => setExcludeRaw(e.target.checked)}
              data-testid="rec-exclude-raw"
            />
            Features and labels only (for calibration)
          </label>
        )}
      </div>
      {action.error && <p className="error-text">{action.error}</p>}
      <p className="hint">
        Writes the standardized events of the connected session to <code>data/recordings/</code>, including pipeline
        features and decoder output while decoding runs. Recordings appear as replay sources and can be used for
        calibration. With a raw high-rate source, record features and labels only: raw frames reach the size cap in
        seconds. Local file replays cannot be recorded.
      </p>
      {recordings.length > 0 && (
        <table className="table">
          <tbody>
            {recordings.slice(0, 8).map((r) => (
              <tr key={r.name}>
                <td>
                  {r.name}
                  {r.complete === false && (
                    <span className="hint" title={r.recovery?.reason}>
                      {" "}
                      · incomplete
                    </span>
                  )}
                </td>
                <td className="r num">{fmt.bytes(r.size_bytes)}</td>
                <td className="r">{r.active ? "recording" : fmt.ago(r.created_at_ns)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

export function FaultInjection() {
  const log = useLog();
  const action = useLoggedAction();
  const inject = async (f: (typeof FAULTS)[number]) => {
    const r = await action.run(() => consoleApi.simFault(f.fault));
    if (r !== undefined) log("info", `Injected fault: ${f.label.toLowerCase()}`);
  };
  return (
    <div data-testid="fault-injection">
      <h3 className="minor">Fault injection</h3>
      <div className="btn-row">
        {FAULTS.map((f) => (
          <button
            key={f.fault}
            type="button"
            className="btn btn-small"
            disabled={action.busy}
            title={f.hint}
            onClick={() => inject(f)}
            data-testid={`fault-${f.fault}`}
          >
            {f.label}
          </button>
        ))}
      </div>
      {action.error && <p className="error-text">{action.error}</p>}
    </div>
  );
}
