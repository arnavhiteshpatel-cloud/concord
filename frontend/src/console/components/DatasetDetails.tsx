import { useEffect, useState } from "react";
import type { SourceMetadata, SourceSignal } from "../../sdk";
import { consoleApi } from "../api";
import { errorText } from "../hooks";
import { Panel, fmt } from "./ui";

/** M5: the signal line of a raw-voltage source (e.g. ECoG) — samples, not bins. */
export function signalLine(meta: SourceMetadata, s: SourceSignal): string {
  const unit = s.unit === "uV" ? "µV" : "arbitrary units (no convertible unit declared)";
  const mains = s.line_hz ? ` · mains ${s.line_hz} Hz` : "";
  return (
    `${meta.channel_count} channels · raw voltage in ${unit} · ${s.sample_rate_hz} Hz · ` +
    `${s.n_samples.toLocaleString()} samples · ${meta.duration_s.toFixed(1)} s from t = ${s.start_s} s` +
    `${mains} · bad: ${s.bad_channels.length ? s.bad_channels.join(", ") : "none marked"}`
  );
}

// Metadata of a verified offline dataset file, as reported by /devices/{id}/source.
export function DatasetDetails({ deviceId }: { deviceId: string }) {
  const [meta, setMeta] = useState<SourceMetadata | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setMeta(null);
    setError(null);
    consoleApi
      .source(deviceId)
      .then(setMeta)
      .catch((e: unknown) => setError(errorText(e)));
  }, [deviceId]);

  if (error) return <p className="error-text">{error}</p>;
  return (
    <Panel title="Recorded data source" testId="source-panel">
      {meta && (
        <p className="source-label" data-testid="source-label">
          {meta.label}
        </p>
      )}
      {meta ? (
        <div className="meta" data-testid="source-meta">
          <table className="table kv">
            <tbody>
              {meta.dataset && (
                <tr>
                  <td>Dataset</td>
                  <td>
                    <a href={meta.dataset.url} target="_blank" rel="noreferrer">
                      DANDI {meta.dataset.dandiset}
                    </a>{" "}
                    · {meta.dataset.title} · {meta.dataset.license}
                  </td>
                </tr>
              )}
              <tr>
                <td>File</td>
                <td className="mono">
                  {meta.file.name}
                  <div
                    className={meta.file.verified ? "text-ok" : "caution-text"}
                    style={{ overflowWrap: "anywhere" }}
                    data-testid="source-verified"
                  >
                    {meta.file.verification}
                  </div>
                </td>
              </tr>
              <tr>
                <td>Recording</td>
                <td>
                  {meta.species ?? "species not stated"} · {meta.recording_type}
                  {meta.modality ? ` · modality ${meta.modality}` : ""}
                </td>
              </tr>
              {meta.slice && (
                <tr>
                  <td>Extract</td>
                  <td className="mono" data-testid="source-slice">
                    {meta.slice.asset_path} samples [{meta.slice.samples.join(", ")}) · {meta.slice.role} slice
                  </td>
                </tr>
              )}
              <tr>
                <td>Signal</td>
                <td className="mono" data-testid="source-signal">
                  {meta.signal ? (
                    signalLine(meta, meta.signal)
                  ) : (
                    <>
                      {meta.channel_count} channels · {meta.feature} ({meta.feature_unit}) · {meta.bin_ms} ms bins (
                      {(1000 / meta.bin_ms).toFixed(0)} Hz) · {meta.n_bins.toLocaleString()} bins ·{" "}
                      {meta.duration_s.toFixed(1)} s
                    </>
                  )}
                </td>
              </tr>
              {meta.behavior && (
                <tr>
                  <td>Behavior</td>
                  <td className="mono">
                    {meta.behavior.quantity} [{meta.behavior.dims.join(", ")}] ({meta.behavior.unit}) ·{" "}
                    {(meta.behavior.valid_fraction * 100).toFixed(1)}% valid
                  </td>
                </tr>
              )}
              <tr>
                <td>Session</td>
                <td className="mono">
                  {meta.identifier} · {meta.institution}
                </td>
              </tr>
              <tr>
                <td>Decoder</td>
                <td data-testid="source-decoder">
                  {meta.decoder ? (
                    <>
                      <span className="mono">{meta.decoder.model_id}</span> · trained on {meta.decoder.trained_on} ·
                      offline held-out R² <b>{fmt.num(meta.decoder.evaluated_r2, 3)}</b> (mean-predictor{" "}
                      {fmt.num(meta.decoder.control_mean_predictor_r2, 3)}, time-shift{" "}
                      {fmt.num(meta.decoder.control_time_shift_r2, 3)})
                    </>
                  ) : (
                    <span className="hint">None attached (no held-out evaluation for this file)</span>
                  )}
                </td>
              </tr>
            </tbody>
          </table>
          <details>
            <summary>Metadata notes ({meta.notes.length}): corrections and what the file does not provide</summary>
            <ul className="notes" data-testid="source-notes">
              {meta.notes.map((n) => (
                <li key={n}>{n}</li>
              ))}
            </ul>
          </details>
          {meta.electrodes ? (
            <details>
              <summary>Electrodes ({meta.electrodes.length})</summary>
              <div className="channel-grid mono" data-testid="source-electrodes">
                {meta.electrodes.map((e) => (
                  <span
                    key={e.index}
                    className={e.bad ? "caution-text" : undefined}
                    title={
                      `${e.label}: group ${e.group ?? "?"} (${e.group_description ?? "no description"}), ` +
                      `location ${e.location ?? "not stated"}, xyz ${[e.x, e.y, e.z].map((v) => fmt.num(v, 1)).join(", ")}, ` +
                      (e.bad === null ? "quality not stated" : e.bad ? "marked bad" : "marked good")
                    }
                  >
                    {e.label}
                    {e.bad ? " (bad)" : ""}
                  </span>
                ))}
              </div>
            </details>
          ) : (
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
          )}
          {meta.dataset && <p className="hint">Citation: {meta.dataset.citation}</p>}
        </div>
      ) : (
        <p className="value-muted">Loading source metadata…</p>
      )}
    </Panel>
  );
}
