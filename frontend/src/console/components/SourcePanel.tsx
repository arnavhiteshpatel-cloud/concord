import { useEffect, useState } from "react";
import { runtimeApi, type PlaybackStatus, type RuntimeSnapshot, type SourceMetadata } from "../../sdk";
import { consoleApi } from "../api";
import { Panel, fmt } from "./ui";

const SPEEDS = [0.5, 1, 2, 4, 8];

function clock(s: number | null | undefined): string {
  if (s === null || s === undefined) return "—";
  const m = Math.floor(s / 60);
  return `${m}:${(s - m * 60).toFixed(1).padStart(4, "0")}`;
}

export function SourcePanel({
  runtime,
  busy,
  act,
  onError,
}: {
  runtime: RuntimeSnapshot;
  busy: boolean;
  act: (fn: () => Promise<unknown>, ok?: string) => Promise<void>;
  onError: (e: unknown) => void;
}) {
  const deviceId = runtime.device?.device_id ?? "";
  const [meta, setMeta] = useState<SourceMetadata | null>(null);
  const [pb, setPb] = useState<PlaybackStatus | null>(null);

  useEffect(() => {
    setMeta(null);
    consoleApi.source(deviceId).then(setMeta).catch(onError);
  }, [deviceId, onError]);

  useEffect(() => {
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

  const state = runtime.state;
  const pct = pb?.duration_s ? Math.min(100, (pb.position_s / pb.duration_s) * 100) : 0;
  return (
    <Panel
      title="Data source"
      className="source-panel"
      testId="source-panel"
      right={<span className="chip plain badge-real">OFFLINE REPLAY</span>}
    >
      <div className="source-label" data-testid="source-label">
        {meta?.label ?? runtime.device?.display_name}
      </div>
      <p className="muted small">
        A recording made in the past, replayed from a verified file. This is not a live implant connection, and
        recorded neural activity is never presented to applications as intent.
      </p>

      <div className="playback" data-testid="playback">
        <div className="progress">
          <div className="progress-bar" style={{ width: `${pct}%` }} />
        </div>
        <div className="playback-row mono small">
          <span data-testid="playback-position">
            {clock(pb?.position_s)} / {clock(pb?.duration_s)}
          </span>
          <span>
            {pb?.paused || state === "paused" ? "paused" : state} · {pb?.speed ?? 1}× · loop {pb?.loops ?? 0}
          </span>
        </div>
        <div className="btn-row">
          {state === "paused" ? (
            <button className="btn" disabled={busy} onClick={() => act(runtimeApi.resume)} data-testid="pb-resume">
              Resume
            </button>
          ) : (
            <button
              className="btn"
              disabled={busy || state !== "streaming"}
              onClick={() => act(runtimeApi.pause)}
              data-testid="pb-pause"
            >
              Pause
            </button>
          )}
          <button className="btn btn-danger" disabled={busy} onClick={() => act(runtimeApi.disconnect)} data-testid="pb-stop">
            Stop
          </button>
          <span className="speed-group">
            {SPEEDS.map((s) => (
              <button
                key={s}
                className={`btn btn-small ${pb?.speed === s ? "btn-primary" : ""}`}
                disabled={busy}
                onClick={() => act(() => consoleApi.setSpeed(s))}
                data-testid={`speed-${s}`}
              >
                {s}×
              </button>
            ))}
          </span>
        </div>
      </div>

      {meta ? (
        <div className="meta" data-testid="source-meta">
          <table className="table kv">
            <tbody>
              {meta.dataset && (
                <tr>
                  <td>dataset</td>
                  <td>
                    <a href={meta.dataset.url} target="_blank" rel="noreferrer">
                      DANDI {meta.dataset.dandiset}
                    </a>{" "}
                    · {meta.dataset.title} · {meta.dataset.license}
                  </td>
                </tr>
              )}
              <tr>
                <td>file</td>
                <td className="mono">
                  {meta.file.name}
                  <div className={meta.file.verified ? "text-ok" : "text-warn"} data-testid="source-verified">
                    {meta.file.verified ? "✓ " : "⚠ "}
                    {meta.file.verification}
                  </div>
                </td>
              </tr>
              <tr>
                <td>recording</td>
                <td>
                  {meta.species ?? "species not stated"} · {meta.recording_type}
                </td>
              </tr>
              <tr>
                <td>signal</td>
                <td className="mono" data-testid="source-signal">
                  {meta.channel_count} channels · {meta.feature} ({meta.feature_unit}) · {meta.bin_ms} ms bins (
                  {(1000 / meta.bin_ms).toFixed(0)} Hz) · {meta.n_bins.toLocaleString()} bins · {meta.duration_s.toFixed(1)} s
                </td>
              </tr>
              {meta.behavior && (
                <tr>
                  <td>behavior</td>
                  <td className="mono">
                    {meta.behavior.quantity} [{meta.behavior.dims.join(", ")}] ({meta.behavior.unit}) ·{" "}
                    {(meta.behavior.valid_fraction * 100).toFixed(1)}% valid
                  </td>
                </tr>
              )}
              <tr>
                <td>session</td>
                <td className="mono">
                  {meta.identifier} · {meta.institution}
                </td>
              </tr>
              <tr>
                <td>decoder</td>
                <td data-testid="source-decoder">
                  {meta.decoder ? (
                    <>
                      <span className="mono">{meta.decoder.model_id}</span> · trained on {meta.decoder.trained_on} ·
                      held-out R² <b>{fmt.num(meta.decoder.evaluated_r2, 3)}</b> (mean-predictor{" "}
                      {fmt.num(meta.decoder.control_mean_predictor_r2, 3)}, time-shift{" "}
                      {fmt.num(meta.decoder.control_time_shift_r2, 3)})
                    </>
                  ) : (
                    <span className="muted">none attached (no held-out evaluation for this file)</span>
                  )}
                </td>
              </tr>
            </tbody>
          </table>
          <details>
            <summary>Metadata notes ({meta.notes.length}) — corrections and what the file does not provide</summary>
            <ul className="notes" data-testid="source-notes">
              {meta.notes.map((n) => (
                <li key={n}>{n}</li>
              ))}
            </ul>
          </details>
          <details>
            <summary>Channels ({meta.channels.length})</summary>
            <div className="channel-grid mono">
              {meta.channels.map((c) => (
                <span key={c.index} title={`unit ${c.unit_id}: ${c.spike_count} spikes; electrode ${c.electrode ?? "not provided"}`}>
                  {c.unit_id}:{c.spike_count}
                </span>
              ))}
            </div>
          </details>
          {meta.dataset && <p className="muted small">Citation: {meta.dataset.citation}</p>}
        </div>
      ) : (
        <div className="empty">Loading source metadata…</div>
      )}
    </Panel>
  );
}
