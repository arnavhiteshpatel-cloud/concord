// The graphite title bar: wordmark, research-use tag, source, status line and the
// always-visible Stop control button.

import { useEffect, useState } from "react";
import type { ConnectionStatus, RuntimeSnapshot } from "../../sdk";
import { consoleApi } from "../api";
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
  // the running server's version, read again whenever the connection (re)opens
  const [version, setVersion] = useState<string | null>(null);
  const open = conn === "open";
  useEffect(() => {
    if (!open) return;
    let alive = true;
    consoleApi
      .health()
      .then((h) => alive && setVersion(h.version))
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, [open]);
  return (
    <header className="titlebar">
      <div className="titlebar-left">
        <span className="wordmark">Concord</span>
        {version && (
          <span className="tb-version" title="The version of the Concord that serves this console" data-testid="version">
            {version}
          </span>
        )}
        <span className="tag" title="Not a medical device. Read-only: Concord never writes to or stimulates a device.">
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
