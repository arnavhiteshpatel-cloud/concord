// The graphite title bar: wordmark, research-use tag, source, status line and the
// always-visible Stop control button.

import type { ConnectionStatus, RuntimeSnapshot } from "../../sdk";
import { sourceKind, statusLine } from "../wording";
import { Dot } from "./ui";

export function TitleBar({
  conn,
  runtime,
  controlOn,
  stopping,
  onStopControl,
}: {
  conn: ConnectionStatus;
  runtime: RuntimeSnapshot | null;
  /** command output (router) is enabled */
  controlOn: boolean;
  stopping: boolean;
  onStopControl: () => void;
}) {
  const status = statusLine(conn, runtime);
  const device = runtime && runtime.state !== "idle" ? runtime.device : null;
  const kind = sourceKind(device);
  return (
    <header className="titlebar">
      <div className="titlebar-left">
        <span className="wordmark">BrainOS</span>
        <span className="tag" title="Not a medical device. Read-only: BrainOS never writes to or stimulates a device.">
          Research use only
        </span>
        {device && (
          <span className="tb-source" title={device.display_name} data-testid="runtime-device">
            {device.display_name}
          </span>
        )}
        <span
          className="tb-status"
          role="status"
          aria-live="polite"
          title={kind?.title}
          data-testid="status-line"
          data-state={conn === "open" ? (runtime?.state ?? "unknown") : "unknown"}
        >
          <Dot tone={status.tone} />
          <span>{status.text}</span>
          {runtime?.recording && (
            <span className="tb-rec" data-testid="recording-indicator">
              · Recording
            </span>
          )}
        </span>
      </div>
      <button
        type="button"
        className="btn btn-stop"
        disabled={!controlOn || stopping}
        onClick={onStopControl}
        title={controlOn ? "Stop command output to applications now" : "Command output is off"}
        data-testid="stop-control"
      >
        Stop control
      </button>
    </header>
  );
}
