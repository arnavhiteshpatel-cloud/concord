// Row 1 — Acquisition source: what is connected and the actions that apply to it now.

import { useEffect, useState } from "react";
import { runtimeApi, type PlaybackStatus, type RuntimeSnapshot } from "../../sdk";
import { consoleApi, cursorClickLabel, isCursorClickFile, isDatasetFile } from "../api";
import { useLoggedAction } from "../context";
import { integrationLine, modalityWords, shapeSummary, sourceKind } from "../wording";
import { datasetLabel } from "./SourcePicker";
import { Disclosure, Row } from "./ui";

const SPEEDS = [0.5, 1, 2, 4, 8];

function clock(s: number | null | undefined): string {
  if (s === null || s === undefined) return "—";
  const m = Math.floor(s / 60);
  return `${m}:${(s - m * 60).toFixed(1).padStart(4, "0")}`;
}

/** Playback position of an offline replay, polled while one is connected. */
function usePlayback(deviceId: string | null): PlaybackStatus | null {
  const [pb, setPb] = useState<PlaybackStatus | null>(null);
  useEffect(() => {
    setPb(null);
    if (!deviceId) return;
    let alive = true;
    const poll = () =>
      consoleApi
        .playback()
        .then((p) => alive && setPb(p))
        .catch(() => alive && setPb(null));
    poll();
    const t = setInterval(poll, 250);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, [deviceId]);
  return pb;
}

export function SourceRow({
  runtime,
  onPick,
}: {
  runtime: RuntimeSnapshot | null;
  /** opens the source picker */
  onPick: () => void;
}) {
  const action = useLoggedAction();
  const state = runtime?.state ?? "idle";
  const device = state !== "idle" ? (runtime?.device ?? null) : null;
  const replayFile = isDatasetFile(device) || !!device?.device_id.startsWith("replay:");
  const pb = usePlayback(replayFile ? (device?.device_id ?? null) : null);
  const kind = sourceKind(device);
  const shape = shapeSummary(device);
  const integration = integrationLine(device);
  // modality in words for plugins (declared or "not declared") and for any source that declares it
  const modality = integration || device?.modality ? modalityWords(device) : null;
  const finished = state === "error" || state === "ended";
  // which file is playing (the display name is the same for every file of a dataset)
  const fileLine = !device
    ? null
    : isDatasetFile(device)
      ? (({ file, where }) => [file, where].filter(Boolean).join(" · "))(datasetLabel(device))
      : isCursorClickFile(device)
        ? `Cursor + click · ${cursorClickLabel(device) ?? device.device_id}`
        : null;

  if (!device) {
    return (
      <Row
        title="Acquisition source"
        explain="Where the brain data comes from."
        testId="row-source"
        actions={
          <button type="button" className="btn btn-primary" onClick={onPick} data-testid="connect-source">
            Connect a source
          </button>
        }
      >
        <p className="value-muted">No source connected.</p>
      </Row>
    );
  }

  const pct = pb?.duration_s ? Math.min(100, (pb.position_s / pb.duration_s) * 100) : 0;
  return (
    <Row
      title="Acquisition source"
      explain="Where the brain data comes from."
      testId="row-source"
      actions={
        <>
          <button type="button" className="btn" onClick={onPick} data-testid="change-source">
            Change source
          </button>
          <button
            type="button"
            className="btn"
            disabled={action.busy}
            onClick={() => action.run(runtimeApi.disconnect)}
            data-testid="disconnect"
          >
            {finished ? "Reset" : "Disconnect"}
          </button>
        </>
      }
    >
      <p className="value" data-testid="source-name">
        {device.display_name}
      </p>
      {fileLine && (
        <p className="value-sub" data-testid="source-file">
          {fileLine}
        </p>
      )}
      <p className="value-sub" title={kind?.title} data-testid="source-kind">
        {[kind?.text, shape].filter(Boolean).join(" · ")}
        {pb && (
          <span className="num" data-testid="playback-position">
            {" "}
            · {clock(pb.position_s)} of {clock(pb.duration_s)}
            {pb.speed !== 1 ? ` · ${pb.speed}×` : ""}
          </span>
        )}
      </p>
      {(integration || modality) && (
        <p className="value-sub" data-testid="source-integration">
          {[integration, modality].filter(Boolean).join(" · ")}
        </p>
      )}
      {runtime?.last_error && finished && (
        <p className="error-text" data-testid="last-error">
          {runtime.last_error}
        </p>
      )}
      {!finished && (
        <Disclosure title={replayFile ? "Playback" : "Options"} testId="source-options" className="inline">
          {replayFile && pb && (
            <div className="progress" aria-hidden>
              <div className="progress-bar" style={{ width: `${pct}%` }} />
            </div>
          )}
          <div className="btn-row">
            {state === "paused" ? (
              <button
                type="button"
                className="btn"
                disabled={action.busy}
                onClick={() => action.run(runtimeApi.resume)}
                data-testid="resume"
              >
                Resume
              </button>
            ) : (
              <button
                type="button"
                className="btn"
                disabled={action.busy || state !== "streaming"}
                onClick={() => action.run(runtimeApi.pause)}
                data-testid="pause"
              >
                Pause
              </button>
            )}
            {replayFile && (
              <span className="segmented" role="group" aria-label="Playback speed">
                {SPEEDS.map((s) => (
                  <button
                    key={s}
                    type="button"
                    className={`seg ${pb?.speed === s ? "seg-on" : ""}`}
                    aria-pressed={pb?.speed === s}
                    disabled={action.busy}
                    onClick={() => action.run(() => consoleApi.setSpeed(s))}
                    data-testid={`speed-${s}`}
                  >
                    {s}×
                  </button>
                ))}
              </span>
            )}
          </div>
        </Disclosure>
      )}
      {action.error && <p className="error-text">{action.error}</p>}
    </Row>
  );
}
