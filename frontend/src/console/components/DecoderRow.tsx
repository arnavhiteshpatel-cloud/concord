// Row 3 — Decoder: whether a decoder runs, what it is, and how to start, stop or calibrate one.

import { useCallback, useEffect, useState } from "react";
import type { RuntimeSnapshot } from "../../sdk";
import {
  consoleApi,
  isRecordable,
  labApi,
  type CalibrationResult,
  type ModelInfo,
  type PipelineStartRequest,
  type PresetName,
  type RecordingInfo,
} from "../api";
import { useLog, useLoggedAction } from "../context";
import type { PipelineState } from "../pipeline";
import { defaultPreset, presetLabel, sentence } from "../wording";
import { CalibrationPanel } from "./CalibrationPanel";
import { PipelineControl } from "./PipelineControl";
import { Dot, Row, Sheet, fmt } from "./ui";

function StartDecodingSheet({
  runtime,
  pipeline,
  onClose,
}: {
  runtime: RuntimeSnapshot | null;
  pipeline: PipelineState;
  onClose: () => void;
}) {
  const [presets, setPresets] = useState<Record<string, string> | null>(null);
  const [models, setModels] = useState<ModelInfo[]>([]);
  const action = useLoggedAction();
  useEffect(() => {
    labApi
      .presets()
      .then(setPresets)
      .catch(() => setPresets({}));
    labApi
      .models()
      .then(setModels)
      .catch(() => setModels([]));
  }, []);
  const canStart = runtime?.state === "streaming" || runtime?.state === "paused";
  const start = async (req: PipelineStartRequest) => {
    const st = await action.run(() => labApi.startPipeline(req));
    if (!st) return;
    pipeline.set(st); // the session log entry comes from the status change
    onClose();
  };
  return (
    <Sheet title="Start decoding" onClose={onClose} testId="start-decoding">
      {presets === null ? (
        <p className="value-muted">Loading…</p>
      ) : (
        <PipelineControl
          presets={presets}
          models={models}
          defaultPreset={defaultPreset(runtime?.device) as PresetName}
          canStart={canStart}
          busy={action.busy}
          error={action.error}
          onStart={start}
        />
      )}
    </Sheet>
  );
}

function CalibrationSheet({
  runtime,
  recordings,
  onRecordingsChanged,
  onClose,
}: {
  runtime: RuntimeSnapshot | null;
  recordings: RecordingInfo[];
  onRecordingsChanged: () => void;
  onClose: () => void;
}) {
  const log = useLog();
  const action = useLoggedAction();
  const state = runtime?.state;
  const canRecord = (state === "streaming" || state === "paused") && isRecordable(runtime?.device);
  const startRec = async () => {
    await action.run(() => consoleApi.startRecording(undefined, true));
  };
  const stopRec = async () => {
    if (await action.run(() => consoleApi.stopRecording())) onRecordingsChanged();
  };
  const trained = (r: CalibrationResult) => {
    log("ok", `Model ${r.model.model_id} trained · offline held-out R² ${fmt.num(r.report.r2, 3)}`);
  };
  return (
    <Sheet title="Calibrate a decoder" onClose={onClose} testId="calibration">
      <section className="group">
        <h3>1. Record a calibration session</h3>
        <p className="explain">
          Records features and behavior labels only, not raw samples, for up to an hour. With a raw source, start
          decoding without a model first so that the pipeline computes the features.
        </p>
        <div className="btn-row">
          {runtime?.recording ? (
            <button type="button" className="btn" disabled={action.busy} onClick={stopRec} data-testid="cal-rec-stop">
              Stop recording
            </button>
          ) : (
            <button
              type="button"
              className="btn"
              disabled={action.busy || !canRecord}
              onClick={startRec}
              data-testid="cal-rec-start"
            >
              Start recording
            </button>
          )}
          {runtime?.recording && <span className="hint">Recording {runtime.recording}</span>}
          {!runtime?.recording && !canRecord && <span className="hint">This source cannot be recorded.</span>}
        </div>
        {action.error && <p className="error-text">{action.error}</p>}
      </section>
      <section className="group">
        <h3>2. Train</h3>
        <CalibrationPanel recordings={recordings} onTrained={trained} />
      </section>
    </Sheet>
  );
}

export function DecoderRow({
  runtime,
  pipeline,
  recordings,
  replayedModel,
  onRecordingsChanged,
}: {
  runtime: RuntimeSnapshot | null;
  pipeline: PipelineState;
  recordings: RecordingInfo[];
  /** model id carried by decoded events of a replayed file (no pipeline involved) */
  replayedModel: string | null;
  onRecordingsChanged: () => void;
}) {
  const action = useLoggedAction();
  const [sheet, setSheet] = useState<"start" | "calibrate" | null>(null);
  const close = useCallback(() => setSheet(null), []);
  const st = pipeline.status;
  const connected = !!runtime?.device && runtime.state !== "idle";
  const running = !!st?.running;
  const dec = running ? st.decoder : null;

  const stop = async () => {
    const r = await action.run(() => labApi.stopPipeline());
    if (!r) return;
    pipeline.set(r);
  };

  const actions = !connected || (st && !st.available) ? undefined : (
    <>
      {running ? (
        <button type="button" className="btn" disabled={action.busy} onClick={stop} data-testid="pl-stop">
          Stop decoding
        </button>
      ) : (
        <button type="button" className="btn btn-primary" onClick={() => setSheet("start")} data-testid="start-decoding-open">
          Start decoding
        </button>
      )}
      <button type="button" className="btn" onClick={() => setSheet("calibrate")} data-testid="calibrate-open">
        Calibrate…
      </button>
    </>
  );

  return (
    <Row
      title="Decoder"
      explain="Turns brain activity into intended movement."
      testId="row-decoder"
      actions={actions}
    >
      <p className="value" data-testid="decoder-state">
        <Dot tone={running ? "ok" : "inactive"} />
        {running ? `Running · ${presetLabel(st.preset)}` : "Off"}
      </p>
      {!connected && <p className="value-sub">Connect a source first.</p>}
      {st && !st.available && <p className="value-sub">Unavailable: {st.unavailable_reason}</p>}
      {running &&
        (dec ? (
          <>
            <p className="value-sub" data-testid="decoder-model">
              Model {dec.model_id} · offline held-out R²{" "}
              <span className="num">{fmt.num(dec.held_out_r2 ?? null, 3)}</span>
            </p>
            <p className="value-sub small-break" data-testid="decoder-trained-on">
              Trained on {dec.trained_on ?? "—"}
            </p>
          </>
        ) : (
          <p className="value-sub">No model: features only.</p>
        ))}
      {running && st.warmup_remaining_s > 0 && (
        <p className="value-sub">Estimating thresholds ({st.warmup_remaining_s.toFixed(1)} s left).</p>
      )}
      {running && (st.cross_source_override || st.compatibility_warnings.length > 0) && (
        <ul className="warnings caution-text" data-testid="decoder-warnings">
          {st.cross_source_override && <li>Cross-source override: decoded output is marked as reduced quality.</li>}
          {st.compatibility_warnings.map((w) => (
            <li key={w}>{sentence(w)}</li>
          ))}
        </ul>
      )}
      {!running && connected && replayedModel && (
        <p className="value-sub">
          This recording carries the replayed output of an offline decoder ({replayedModel}); it is not used for control.
        </p>
      )}
      {st?.last_error && <p className="error-text">{st.last_error}</p>}
      {action.error && <p className="error-text">{action.error}</p>}
      {sheet === "start" && <StartDecodingSheet runtime={runtime} pipeline={pipeline} onClose={close} />}
      {sheet === "calibrate" && (
        <CalibrationSheet
          runtime={runtime}
          recordings={recordings}
          onRecordingsChanged={onRecordingsChanged}
          onClose={close}
        />
      )}
    </Row>
  );
}
