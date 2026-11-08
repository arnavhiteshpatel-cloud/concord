// Row 3 — Decoder: whether a decoder runs, what it is (origin, family, where it runs), whether
// it fits the source, whether it drifted, and how to start, stop or calibrate one.

import { useCallback, useEffect, useState } from "react";
import type { RuntimeSnapshot } from "../../sdk";
import {
  consoleApi,
  isRecordable,
  labApi,
  type CalibrationResult,
  type ModelInfo,
  type ModelSummary,
  type PipelineStartRequest,
  type PresetName,
  type ProcessingSpecInput,
  type RecordingInfo,
} from "../api";
import { useLog, useLoggedAction } from "../context";
import { decoderLine, driftLine, originLabel } from "../decoders";
import type { PipelineState } from "../pipeline";
import { defaultPreset, hasCapability, presetLabel, sentence } from "../wording";
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
  const [preview, setPreview] = useState<ProcessingSpecInput | null>(null);
  const [reload, setReload] = useState(0);
  const action = useLoggedAction();
  const discover = useLoggedAction();
  useEffect(() => {
    labApi
      .presets()
      .then(setPresets)
      .catch(() => setPresets({}));
  }, []);
  useEffect(() => {
    // compatibility of every model with what the chosen processing would produce
    let live = true;
    const t = setTimeout(() => {
      labApi
        .models(preview)
        .then((m) => live && setModels(m))
        .catch(() => live && setModels([]));
    }, 150);
    return () => {
      live = false;
      clearTimeout(t);
    };
  }, [preview, reload]);
  const canStart = runtime?.state === "streaming" || runtime?.state === "paused";
  const start = async (req: PipelineStartRequest) => {
    const st = await action.run(() => labApi.startPipeline(req));
    if (!st) return;
    pipeline.set(st); // the session log entry comes from the status change
    onClose();
  };
  const search = async () => {
    if (await discover.run(() => labApi.discoverModels())) setReload((n) => n + 1);
  };
  const onProcessing = useCallback((p: ProcessingSpecInput | null) => setPreview(p), []);
  const onModelsChanged = useCallback(() => setReload((n) => n + 1), []);
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
          hasSourceDecoder={hasCapability(runtime?.device, "kinematic_intent")}
          onProcessingChange={onProcessing}
          onModelsChanged={onModelsChanged}
        />
      )}
      <div className="btn-row">
        <button type="button" className="btn" disabled={discover.busy} onClick={search} data-testid="decoders-discover">
          {discover.busy ? "Searching…" : "Search for decoder plugins"}
        </button>
        <span className="hint">Installed decoder plugins and model files are listed with the models.</span>
      </div>
      {discover.error && <p className="error-text">{discover.error}</p>}
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
    const rep = r.report;
    const score =
      rep.events !== undefined
        ? `click events precision ${fmt.num(rep.events.event_precision, 3)}, recall ${fmt.num(rep.events.event_recall, 3)}`
        : (rep as { balanced_accuracy?: number }).balanced_accuracy !== undefined
          ? `offline held-out balanced accuracy ${fmt.num((rep as { balanced_accuracy?: number }).balanced_accuracy, 3)}`
          : `offline held-out R² ${fmt.num(rep.r2, 3)}`;
    log("ok", `Model ${r.model.model_id} trained · ${score}`);
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

function DecoderLines({ d, first }: { d: ModelSummary; first: boolean }) {
  const c = d.compatibility;
  return (
    <>
      <p className="value-sub" data-testid={first ? "decoder-model" : `decoder-model-${d.model_id}`}>
        Model {d.model_id} ·{" "}
        {d.outputs?.type === "classes" ? (
          <>
            classes {d.outputs.classes.join(", ")} · offline held-out balanced accuracy{" "}
            <span className="num">{fmt.num(d.held_out_balanced_accuracy ?? null, 3)}</span> (chance{" "}
            <span className="num">{fmt.num(d.chance_balanced_accuracy ?? null, 3)}</span>)
          </>
        ) : d.outputs?.type === "event" ? (
          <>events {d.outputs.events.join(", ")}</>
        ) : (
          <>
            offline held-out R² <span className="num">{fmt.num(d.held_out_r2 ?? null, 3)}</span>
          </>
        )}
      </p>
      {d.origin && (
        <p className="value-sub" data-testid={first ? "decoder-origin" : undefined}>
          {decoderLine(d)}
          {c && (c.ok ? <span className="text-ok"> · compatible with this source</span> : null)}
          {c?.mapping_applied && <span className="caution-text"> · channels mapped by label (operator enabled)</span>}
        </p>
      )}
      {d.state === "failed" && (
        <p className="error-text" data-testid={first ? "decoder-failed" : undefined}>
          Decoder stopped: {d.error}
        </p>
      )}
    </>
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
  const sources = running ? (st.source_decoders ?? []) : [];
  const decs = running ? (st.decoders?.length ? st.decoders : st.decoder && !sources.length ? [st.decoder] : []) : [];
  const drift = driftLine(st);

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
      {running && decs.length > 0 && (
        <>
          {decs.map((d, i) => (
            <DecoderLines key={d.model_id} d={d} first={i === 0} />
          ))}
          <p className="value-sub small-break" data-testid="decoder-trained-on">
            Trained on {decs[0]!.trained_on ?? "—"}
          </p>
        </>
      )}
      {running && sources.length > 0 && (
        <ul className="value-sub plain" data-testid="decoder-source-outputs">
          {sources.map((s) => (
            <li key={s.model_id}>
              {originLabel(s.origin)}: {s.model_id} → {s.dims.join(", ")} ({s.quantity}
              {s.received !== undefined ? `, ${fmt.num(s.received)} received` : ""})
            </li>
          ))}
        </ul>
      )}
      {running && decs.length === 0 && sources.length === 0 && <p className="value-sub">No model: features only.</p>}
      {running && st.warmup_remaining_s > 0 && (
        <p className="value-sub">Estimating thresholds ({st.warmup_remaining_s.toFixed(1)} s left).</p>
      )}
      {running && drift && (
        <p
          className={`value-sub ${drift.tone === "caution" ? "caution-text" : drift.tone === "ok" ? "text-ok" : ""}`}
          data-testid="decoder-drift"
        >
          {drift.text}
        </p>
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
