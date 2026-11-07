// Fit a decoder on closed recordings (chronological train / held-out split) via
// POST /calibration/train, and show the report the server returns — nothing is computed here.

import { useState } from "react";
import { labApi, type CalibrationResult, type RecordingInfo } from "../api";
import { useLoggedAction } from "../context";
import { fmt } from "./ui";

const FEATURE_SOURCES = [
  ["", "All feature events in the recording"],
  ["brainos.pipeline", "Features computed by the BrainOS pipeline"],
  ["brainos.lsl", "Features delivered by an LSL stream"],
  ["brainos.openephys.zmq", "Spike bins from Open Ephys"],
] as const;

function Report({ result }: { result: CalibrationResult }) {
  const r = result.report;
  return (
    <div className="cal-report" data-testid="cal-report">
      <p>
        Saved model <b data-testid="cal-model-id">{result.model.model_id}</b>. It is now selectable under Start decoding.
      </p>
      <dl className="kv">
        <dt>Offline held-out R²</dt>
        <dd>
          <b className="num" data-testid="cal-r2">
            {fmt.num(r.r2, 3)}
          </b>{" "}
          <span className="hint">
            variance-weighted, {fmt.num(r.samples)} samples · mean-predictor control{" "}
            {fmt.num(r.control_mean_predictor_r2, 3)}
            {r.control_time_shift_r2 !== undefined && <> · time-shift control {fmt.num(r.control_time_shift_r2, 3)}</>}
          </span>
        </dd>
        <dt>Per dimension</dt>
        <dd className="num">
          {Object.entries(r.r2_per_dim)
            .map(([k, v]) => `${k} ${v.toFixed(3)}`)
            .join(" · ")}
        </dd>
        <dt>Bins</dt>
        <dd className="num">
          {r.bins_total} total ({r.labelled_bins} labelled) · train {r.train_bins} · gap {r.gap_bins} · held-out{" "}
          {r.test_bins}
        </dd>
        <dt>Source</dt>
        <dd>
          {r.source_identity ?? "—"}
          {r.synthetic_source && <span className="caution-text"> · synthetic data</span>}
          {r.prerecorded_source && <span className="caution-text"> · prerecorded data streamed live</span>}
        </dd>
        <dt>Recordings</dt>
        <dd>{r.recordings.join(", ")}</dd>
      </dl>
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
  const action = useLoggedAction();

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
      <p className="hint">
        The first part of the data trains a ridge decoder; the chronological tail, after a gap, is held out for scoring.
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
              <span>
                {r.name}
                <span className="hint">
                  {" "}
                  · {r.device_id} · {fmt.num(r.events)} events · {fmt.bytes(r.size_bytes)}
                  {r.synthetic ? " · synthetic" : ""}
                </span>
              </span>
            </label>
          ))}
        </div>
      ) : (
        <p className="value-muted">No finished recordings yet.</p>
      )}
      <div className="form-grid">
        <label title="0.5 – 0.95">
          Train fraction
          <input value={fraction} onChange={(e) => setFraction(e.target.value)} data-testid="cal-fraction" />
        </label>
        <label title="Bins skipped between train and held-out data">
          Gap (bins)
          <input value={gap} onChange={(e) => setGap(e.target.value)} data-testid="cal-gap" />
        </label>
        <label className="span-all">
          Feature source
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
        <button type="button" className="btn btn-primary" disabled={action.busy || !valid} onClick={train} data-testid="cal-train">
          {action.busy ? "Training…" : "Train decoder"}
        </button>
      </div>
      {action.error && (
        <p className="error-text" data-testid="cal-error">
          {action.error}
        </p>
      )}
      {result && <Report result={result} />}
      <p className="hint" data-testid="cal-disclaimer">
        Offline held-out R² on a recording does not establish closed-loop performance: it measures how well the model
        reconstructs recorded labels, not how well a person can control anything with it.
      </p>
    </div>
  );
}
