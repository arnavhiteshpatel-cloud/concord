// Fit a decoder on closed recordings (chronological train / held-out split) via
// POST /calibration/train, and show the report the server returns — nothing is computed here.
// Milestone 5: the operator first chooses WHAT the decoder should output (continuous movement,
// discrete classes, click); the server checks that the recordings carry the labels it needs
// (POST /calibration/check) and scores the model with metrics for that output.

import { useEffect, useState } from "react";
import {
  labApi,
  type CalibrationCapability,
  type CalibrationOptions,
  type CalibrationRequest,
  type CalibrationResult,
  type LabelCheck,
  type RecordingInfo,
} from "../api";
import { useLoggedAction } from "../context";
import { familyLabel } from "../decoders";
import { fmt } from "./ui";

const FEATURE_SOURCES = [
  ["", "All feature events in the recording"],
  ["concord.pipeline", "Features computed by the Concord pipeline"],
  ["concord.lsl", "Features delivered by an LSL stream"],
  ["concord.openephys.zmq", "Spike bins from Open Ephys"],
] as const;

// Shown until /calibration/options answers (same wording as decoding/calibrate.py).
const CAPABILITIES: { name: CalibrationCapability; label: string; needs: string }[] = [
  { name: "continuous", label: "Continuous movement", needs: "a behavior stream with continuous targets (e.g. cued cursor velocity)" },
  { name: "classes", label: "Discrete classes", needs: "a behavior dimension with a small-integer class code per bin (e.g. a cue)" },
  { name: "click", label: "Click", needs: "a behavior dimension that is 1 while a click is attempted and 0 otherwise" },
];

/** Report of a classifier (LDA) calibration: accuracy against chance, per class, confusion. */
function ClassifierReport({ result }: { result: CalibrationResult }) {
  const r = result.report as unknown as ClassifierReportData;
  return (
    <div className="cal-report" data-testid="cal-report">
      <p>
        Saved classifier <b data-testid="cal-model-id">{result.model.model_id}</b>. It is now selectable under Start decoding.
      </p>
      <dl className="kv">
        <dt>Held-out balanced accuracy</dt>
        <dd>
          <b className="num" data-testid="cal-bacc">
            {fmt.num(r.balanced_accuracy, 3)}
          </b>{" "}
          <span className="hint">
            chance {fmt.num(r.chance_balanced_accuracy, 3)} · accuracy {fmt.num(r.accuracy, 3)} (majority class{" "}
            {fmt.num(r.chance_majority_accuracy, 3)}) · time-shift control {fmt.num(r.control_time_shift_balanced_accuracy, 3)} ·{" "}
            {fmt.num(r.samples)} bins
          </span>
        </dd>
        <dt>Per class</dt>
        <dd className="num">
          {Object.entries(r.per_class_accuracy)
            .map(([k, v]) => `${k} ${v.toFixed(2)}`)
            .join(" · ")}
        </dd>
        {r.confusion && (
          <>
            <dt>Confusion</dt>
            <dd>
              <table className="table confusion" data-testid="cal-confusion">
                <thead>
                  <tr>
                    <th>true \ predicted</th>
                    {r.classes.map((c) => (
                      <th key={c}>{c}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {r.confusion.map((row, i) => (
                    <tr key={r.classes[i]}>
                      <th>{r.classes[i]}</th>
                      {row.map((v, j) => (
                        <td key={j} className="num">
                          {v}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </dd>
          </>
        )}
        <EventsBlock result={result} />
        <dt>Source</dt>
        <dd>
          {r.source_identity ?? "—"}
          {r.synthetic_source && <span className="caution-text"> · synthetic data</span>}
          {r.prerecorded_source && <span className="caution-text"> · prerecorded data streamed live</span>}
        </dd>
      </dl>
    </div>
  );
}

interface ClassifierReportData {
  classes: string[];
  balanced_accuracy: number;
  accuracy: number;
  chance_balanced_accuracy: number;
  chance_majority_accuracy: number;
  control_time_shift_balanced_accuracy: number;
  per_class_accuracy: Record<string, number>;
  confusion: number[][];
  samples: number;
  source_identity: string | null;
  synthetic_source: boolean;
  prerecorded_source: boolean;
}

/** Click calibrations: event-level precision / recall (an event is a label onset). */
function EventsBlock({ result }: { result: CalibrationResult }) {
  const ev = result.report.events;
  if (!ev) return null;
  return (
    <>
      <dt>Click events (held-out)</dt>
      <dd data-testid="cal-events">
        precision <b className="num">{fmt.num(ev.event_precision, 3)}</b> · recall{" "}
        <b className="num">{fmt.num(ev.event_recall, 3)}</b> · F1 {fmt.num(ev.event_f1, 3)}{" "}
        <span className="hint">
          {ev.true_events} clicks, {ev.detected_events} detected within ±{ev.tolerance_ms} ms ·{" "}
          {fmt.num(ev.false_positives_per_min, 2)} false clicks per minute · per-bin ROC AUC {fmt.num(ev.roc_auc ?? null, 3)}
        </span>
      </dd>
    </>
  );
}

function Report({ result }: { result: CalibrationResult }) {
  const rep = result.report as { kind?: string; confusion?: unknown };
  if (rep.kind === "classifier" || rep.confusion !== undefined) return <ClassifierReport result={result} />;
  const r = result.report;
  if (r.r2 === undefined) {
    return (
      <div className="cal-report" data-testid="cal-report">
        <p>
          Saved model <b data-testid="cal-model-id">{result.model.model_id}</b> ({familyLabel(r.family)}). It is now
          selectable under Start decoding.
        </p>
        <dl className="kv">
          <EventsBlock result={result} />
        </dl>
      </div>
    );
  }
  const ve = r.velocity_error;
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
        {ve && (
          <>
            <dt>Velocity error</dt>
            <dd className="num" data-testid="cal-velocity-error">
              mean error {ve.mean_vector_error.toPrecision(3)} (mean target speed {ve.mean_target_speed.toPrecision(3)}) · RMSE{" "}
              {Object.entries(ve.rmse_per_dim)
                .map(([k, v]) => `${k} ${v.toPrecision(3)}`)
                .join(" · ")}
            </dd>
          </>
        )}
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
  const [capability, setCapability] = useState<CalibrationCapability>("continuous");
  const [family, setFamily] = useState("");
  const [labelDim, setLabelDim] = useState("");
  const [classNames, setClassNames] = useState("");
  const [joinFeatures, setJoinFeatures] = useState(false);
  const [options, setOptions] = useState<CalibrationOptions | null>(null);
  const [check, setCheck] = useState<LabelCheck | null>(null);
  const [result, setResult] = useState<CalibrationResult | null>(null);
  const action = useLoggedAction();
  const checking = useLoggedAction();

  useEffect(() => {
    labApi
      .calibrationOptions()
      .then(setOptions)
      .catch(() => setOptions(null));
  }, []);

  const caps = options?.capabilities ?? CAPABILITIES.map((c) => ({ ...c, families: [], default_family: "" }));
  const cap = caps.find((c) => c.name === capability);
  const families = options?.capabilities.find((c) => c.name === capability)?.families ?? [];
  const frac = Number(fraction);
  const gapBins = Number(gap);
  const chosen = picked.filter((n) => closed.some((r) => r.name === n));
  const valid = chosen.length > 0 && frac >= 0.5 && frac <= 0.95 && Number.isInteger(gapBins) && gapBins >= 0;
  const toggle = (name: string) =>
    setPicked((p) => (p.includes(name) ? p.filter((x) => x !== name) : [...p, name]));

  const request = (): CalibrationRequest => {
    const req: CalibrationRequest = {
      recordings: chosen,
      train_fraction: frac,
      gap_bins: gapBins,
      feature_source: featureSource || null,
    };
    // continuous with the default family is the Milestone 3 request (kind regression)
    if (capability !== "continuous" || family) req.capability = capability;
    if (family) req.family = family;
    if (capability !== "continuous" && labelDim.trim()) req.label_dim = labelDim.trim();
    if (capability === "classes" && classNames.trim())
      req.class_names = classNames
        .split(",")
        .map((x) => x.trim())
        .filter(Boolean);
    if (joinFeatures) req.join_features = true;
    return req;
  };

  const runCheck = async () => {
    const res = await checking.run(() => labApi.calibrationCheck({ ...request(), capability }));
    if (res) setCheck(res);
  };

  const train = async () => {
    const res = await action.run(() => labApi.calibrate(request()));
    if (!res) return;
    setResult(res);
    onTrained(res);
  };

  return (
    <div data-testid="calibration-panel">
      <p className="hint">
        The first part of the data trains the decoder; the chronological tail, after a gap, is held out for scoring.
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
        <label className="span-all">
          What the decoder should output
          <select
            value={capability}
            onChange={(e) => {
              setCapability(e.target.value as CalibrationCapability);
              setFamily("");
              setCheck(null);
            }}
            data-testid="cal-capability"
          >
            {caps.map((c) => (
              <option key={c.name} value={c.name}>
                {c.label}
              </option>
            ))}
          </select>
        </label>
        {cap && (
          <p className="hint span-all" data-testid="cal-needs">
            Needs {cap.needs}. One calibration task does not fit every modality: record the task that matches this output.
          </p>
        )}
        {families.length > 1 && (
          <label className="span-all">
            Decoder family
            <select value={family} onChange={(e) => setFamily(e.target.value)} data-testid="cal-family">
              <option value="">Default ({familyLabel(options?.capabilities.find((c) => c.name === capability)?.default_family)})</option>
              {families.map((f) => (
                <option key={f.name} value={f.name} title={f.description}>
                  {familyLabel(f.name)}
                </option>
              ))}
            </select>
          </label>
        )}
        {capability !== "continuous" && (
          <label title="The behavior dimension holding the label (only needed when there are several)">
            Label dimension (optional)
            <input value={labelDim} placeholder={capability === "click" ? "click" : "cue_class"} onChange={(e) => setLabelDim(e.target.value)} data-testid="cal-label-dim" />
          </label>
        )}
        {capability === "classes" && (
          <label className="span-all" title="Comma-separated; the first names label 0, the next label 1, …">
            Class names (optional)
            <input value={classNames} placeholder="rest, left, right" onChange={(e) => setClassNames(e.target.value)} data-testid="cal-classes" />
          </label>
        )}
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
        <label className="check span-all" title="Recordings with several feature streams of the same bins (e.g. threshold crossings and spike-band power)">
          <input type="checkbox" checked={joinFeatures} onChange={(e) => setJoinFeatures(e.target.checked)} data-testid="cal-join" />
          Use every feature stream in the recording, joined per bin
        </label>
      </div>
      <div className="btn-row">
        <button type="button" className="btn" disabled={checking.busy || !chosen.length} onClick={runCheck} data-testid="cal-check">
          Check labels
        </button>
        <button type="button" className="btn btn-primary" disabled={action.busy || !valid} onClick={train} data-testid="cal-train">
          {action.busy ? "Training…" : "Train decoder"}
        </button>
      </div>
      {check && (
        <div data-testid="cal-check-result" className={check.ok ? "text-ok" : "error-text"}>
          {check.ok
            ? `Labels found: ${check.label_dims.join(", ")} · ${fmt.num(check.labelled_bins)} labelled bins` +
              (check.classes ? ` · classes ${check.classes.join(", ")}` : "") +
              (check.events !== null ? ` · ${check.events} click events` : "")
            : check.problems.join(" ")}
          {check.notes.length > 0 && <p className="hint">{check.notes.join(" · ")}</p>}
        </div>
      )}
      {checking.error && <p className="error-text">{checking.error}</p>}
      {action.error && (
        <p className="error-text" data-testid="cal-error">
          {action.error}
        </p>
      )}
      {result && <Report result={result} />}
      <p className="hint" data-testid="cal-disclaimer">
        An offline held-out score on a recording does not establish closed-loop performance: it measures how well the
        model reconstructs recorded labels, not how well a person can control anything with it.
      </p>
    </div>
  );
}
