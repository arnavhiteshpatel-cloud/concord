// Fit a decoder on closed recordings (chronological train / held-out split) via
// POST /calibration/train, and show the report the server returns — nothing is computed here.

import { useState } from "react";
import { labApi, type CalibrationResult, type RecordingInfo } from "../api";
import { useAction } from "../hooks";
import { fmt } from "./ui";

const FEATURE_SOURCES = [
  ["", "all feature events in the recording"],
  ["brainos.pipeline", "brainos.pipeline — features computed by the BrainOS pipeline"],
  ["brainos.lsl", "brainos.lsl — features delivered by an LSL stream"],
  ["brainos.openephys.zmq", "brainos.openephys.zmq — spike bins from Open Ephys"],
] as const;

function Report({ result }: { result: CalibrationResult }) {
  const r = result.report;
  return (
    <div className="cal-report" data-testid="cal-report">
      <div>
        Saved model <span className="mono" data-testid="cal-model-id">{result.model.model_id}</span> — now selectable as a
        decoder above.
      </div>
      <table className="table kv">
        <tbody>
          <tr>
            <td>held-out R²</td>
            <td>
              <b className="mono" data-testid="cal-r2">
                {fmt.num(r.r2, 3)}
              </b>{" "}
              (variance-weighted, {fmt.num(r.samples)} samples) · mean-predictor control{" "}
              <span className="mono">{fmt.num(r.control_mean_predictor_r2, 3)}</span>
              {r.control_time_shift_r2 !== undefined && (
                <>
                  {" "}
                  · time-shift control <span className="mono">{fmt.num(r.control_time_shift_r2, 3)}</span>
                </>
              )}
            </td>
          </tr>
          <tr>
            <td>per dimension</td>
            <td className="mono">
              {Object.entries(r.r2_per_dim)
                .map(([k, v]) => `${k} ${v.toFixed(3)}`)
                .join(" · ")}
            </td>
          </tr>
          <tr>
            <td>bins</td>
            <td className="mono">
              {r.bins_total} total ({r.labelled_bins} labelled) · train {r.train_bins} · gap {r.gap_bins} · held-out{" "}
              {r.test_bins}
            </td>
          </tr>
          <tr>
            <td>source</td>
            <td className="mono">
              {r.source_identity ?? "—"}
              {r.synthetic_source && <span className="text-warn"> · synthetic data</span>}
              {r.prerecorded_source && <span className="text-warn"> · prerecorded data streamed live</span>}
            </td>
          </tr>
          <tr>
            <td>recordings</td>
            <td className="mono">{r.recordings.join(", ")}</td>
          </tr>
        </tbody>
      </table>
    </div>
  );
}

export function CalibrationPanel({
  recordings,
  onTrained,
}: {
  recordings: RecordingInfo[];
  onTrained: (r: CalibrationResult) => void;
}) {
  const closed = recordings.filter((r) => !r.active);
  const [picked, setPicked] = useState<string[]>([]);
  const [fraction, setFraction] = useState("0.8");
  const [gap, setGap] = useState("12");
  const [featureSource, setFeatureSource] = useState("");
  const [result, setResult] = useState<CalibrationResult | null>(null);
  const action = useAction();

  const frac = Number(fraction);
  const gapBins = Number(gap);
  const chosen = picked.filter((n) => closed.some((r) => r.name === n));
  const valid = chosen.length > 0 && frac >= 0.5 && frac <= 0.95 && Number.isInteger(gapBins) && gapBins >= 0;
  const toggle = (name: string) =>
    setPicked((p) => (p.includes(name) ? p.filter((x) => x !== name) : [...p, name]));

  const train = async () => {
    const res = await action.run(() =>
      labApi.calibrate({
        recordings: chosen,
        train_fraction: frac,
        gap_bins: gapBins,
        feature_source: featureSource || null,
      }),
    );
    if (!res) return;
    setResult(res);
    onTrained(res);
  };

  return (
    <div data-testid="calibration-panel">
      <p className="muted small">
        Record a session with behavior labels (Recording panel on the left — with the pipeline running when the features
        should come from it, and <b>features + labels only</b> ticked for a raw high-rate source, which records
        everything except raw frames for up to 3600 s), stop the recording, then fit a ridge decoder here. The first part of the data trains the
        model; the chronological tail, after a gap, is held out for scoring.
      </p>
      {closed.length ? (
        <div className="cal-list" data-testid="cal-recordings">
          {closed.map((r) => (
            <label key={r.name} className="check">
              <input
                type="checkbox"
                checked={picked.includes(r.name)}
                onChange={() => toggle(r.name)}
                data-testid={`cal-rec-${r.name}`}
              />
              <span className="mono">{r.name}</span>
              <span className="muted small">
                {r.device_id} · {fmt.num(r.events)} events · {fmt.bytes(r.size_bytes)}
                {r.synthetic ? " · synthetic" : ""}
              </span>
            </label>
          ))}
        </div>
      ) : (
        <div className="empty">No closed recordings yet.</div>
      )}
      <div className="form-grid">
        <label title="0.5 – 0.95">
          train fraction
          <input value={fraction} onChange={(e) => setFraction(e.target.value)} data-testid="cal-fraction" />
        </label>
        <label title="bins skipped between train and held-out data">
          gap (bins)
          <input value={gap} onChange={(e) => setGap(e.target.value)} data-testid="cal-gap" />
        </label>
        <label className="span-2">
          feature source
          <select value={featureSource} onChange={(e) => setFeatureSource(e.target.value)} data-testid="cal-source">
            {FEATURE_SOURCES.map(([v, l]) => (
              <option key={v} value={v}>
                {l}
              </option>
            ))}
          </select>
        </label>
      </div>
      <div className="btn-row">
        <button className="btn btn-primary" disabled={action.busy || !valid} onClick={train} data-testid="cal-train">
          {action.busy ? "Training…" : "Train decoder"}
        </button>
      </div>
      {action.error && (
        <div className="alert" data-testid="cal-error">
          {action.error}
        </div>
      )}
      {result && <Report result={result} />}
      <p className="muted small" data-testid="cal-disclaimer">
        Offline held-out R² on a recording does not establish closed-loop performance: it measures how well the model
        reconstructs recorded labels, not how well a person can control anything with it.
      </p>
    </div>
  );
}
