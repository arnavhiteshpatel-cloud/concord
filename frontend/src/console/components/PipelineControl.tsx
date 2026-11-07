// Configure and start/stop the real-time processing pipeline (features -> optional decoder).

import { useState } from "react";
import type { ModelInfo, PipelineStartRequest, PresetName, ProcessingSpecInput } from "../api";
import { presetLabel } from "../wording";
import { fmt } from "./ui";

/** "" -> undefined (server default); otherwise a finite number or NaN (invalid). */
function optNum(s: string): number | undefined {
  return s.trim() === "" ? undefined : Number(s);
}

export function buildStartRequest(form: {
  preset: PresetName;
  binMs: string;
  thresholdK: string;
  bandLow: string;
  bandHigh: string;
  modelId: string;
  allowCrossSource: boolean;
}): { request: PipelineStartRequest | null; problem: string | null } {
  const processing: ProcessingSpecInput = { preset: form.preset };
  const check = (name: string, v: number | undefined): string | null =>
    v !== undefined && !Number.isFinite(v) ? `${name} must be a number` : null;
  const binMs = form.preset === "features_passthrough" ? undefined : optNum(form.binMs);
  const problems: (string | null)[] = [check("bin_ms", binMs)];
  if (binMs !== undefined) processing.bin_ms = binMs;
  if (form.preset === "spikeband_threshold") {
    const k = optNum(form.thresholdK);
    problems.push(check("threshold_k", k));
    if (k !== undefined) processing.threshold_k = k;
  }
  if (form.preset === "band_power") {
    const lo = optNum(form.bandLow);
    const hi = optNum(form.bandHigh);
    if (lo === undefined || hi === undefined) problems.push("band_power needs a low and a high band edge");
    problems.push(check("band low", lo), check("band high", hi));
    if (lo !== undefined) processing.band_low_hz = lo;
    if (hi !== undefined) processing.band_high_hz = hi;
  }
  const problem = problems.find((p) => p !== null) ?? null;
  if (problem) return { request: null, problem };
  return {
    request: {
      processing,
      model_id: form.modelId || null,
      allow_cross_source: form.modelId ? form.allowCrossSource : false,
    },
    problem: null,
  };
}

function ModelDetails({ m }: { m: ModelInfo }) {
  const s = m.summary;
  const inp = s.input;
  return (
    <div className="model-details" data-testid="model-details">
      <dl className="kv">
        <dt>Trained on</dt>
        <dd>{s.trained_on ?? "—"}</dd>
        {s.source_identity && (
          <>
            <dt>Source</dt>
            <dd>{s.source_identity}</dd>
          </>
        )}
        {s.outputs?.type === "classes" ? (
          <>
            <dt>Offline held-out balanced accuracy</dt>
            <dd className="num">
              {fmt.num(s.held_out_balanced_accuracy ?? null, 3)}{" "}
              <span className="hint">
                as reported by the model file · chance {fmt.num(s.chance_balanced_accuracy ?? null, 3)} ·{" "}
                {fmt.num(s.held_out_samples ?? null)} bins · classes {s.outputs.classes.join(", ")}
              </span>
            </dd>
          </>
        ) : (
          <>
            <dt>Offline held-out R²</dt>
            <dd className="num">
              {fmt.num(s.held_out_r2 ?? null, 3)}{" "}
              <span className="hint">
                as reported by the model file · mean-predictor control {fmt.num(s.control_mean_predictor_r2 ?? null, 3)} ·{" "}
                {fmt.num(s.held_out_samples ?? null)} samples
              </span>
            </dd>
          </>
        )}
        <dt>Expects</dt>
        <dd>
          {inp?.feature?.replace(/_/g, " ") ?? "?"} · {inp?.bin_ms ?? "?"} ms bins · {inp?.channel_count ?? "?"} channels
          {inp?.inferred ? " (inferred)" : ""} → {s.dims.join(", ")}
        </dd>
      </dl>
      <p className="hint" data-testid="model-compat">
        {m.compatible === null && "Compatibility is checked against the pipeline output when it starts."}
        {m.compatible === true && <span className="text-ok">Compatible with the running pipeline output.</span>}
        {m.compatible === false && <span className="error-text">Not compatible with the running pipeline output.</span>}
      </p>
      {m.errors.length > 0 && (
        <ul className="notes error-text">
          {m.errors.map((e) => (
            <li key={e}>{e}</li>
          ))}
        </ul>
      )}
      {m.warnings.length > 0 && (
        <ul className="notes caution-text">
          {m.warnings.map((w) => (
            <li key={w}>{w}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function PipelineControl({
  presets,
  models,
  defaultPreset,
  canStart,
  busy,
  error,
  onStart,
}: {
  presets: Record<string, string>;
  models: ModelInfo[];
  defaultPreset: PresetName;
  canStart: boolean;
  busy: boolean;
  error: string | null;
  onStart: (req: PipelineStartRequest) => void;
}) {
  const names = Object.keys(presets) as PresetName[];
  const [preset, setPreset] = useState<PresetName>(defaultPreset);
  const [binMs, setBinMs] = useState("");
  const [thresholdK, setThresholdK] = useState("-4.5");
  const [bandLow, setBandLow] = useState("");
  const [bandHigh, setBandHigh] = useState("");
  const [modelId, setModelId] = useState("");
  const [allowCross, setAllowCross] = useState(false);

  const effectivePreset = names.includes(preset) ? preset : (names[0] ?? preset);
  const { request, problem } = buildStartRequest({
    preset: effectivePreset,
    binMs,
    thresholdK,
    bandLow,
    bandHigh,
    modelId,
    allowCrossSource: allowCross,
  });
  const selected = models.find((m) => m.summary.model_id === modelId) ?? null;

  return (
    <div data-testid="pipeline-control">
      <div className="form-grid">
        <label className="span-all">
          Processing
          <select
            value={effectivePreset}
            onChange={(e) => setPreset(e.target.value as PresetName)}
            data-testid="pl-preset"
          >
            {names.map((n) => (
              <option key={n} value={n}>
                {presetLabel(n)}
              </option>
            ))}
          </select>
        </label>
      </div>
      {presets[effectivePreset] && <p className="hint">{presets[effectivePreset]}</p>}
      {effectivePreset !== "features_passthrough" && (
        <div className="form-grid">
          <label>
            Bin (ms)
            <input
              value={binMs}
              placeholder={effectivePreset === "spikeband_threshold" ? "20 (default)" : "50 (default)"}
              onChange={(e) => setBinMs(e.target.value)}
              data-testid="pl-bin"
            />
          </label>
          {effectivePreset === "spikeband_threshold" && (
            <label>
              Threshold (× RMS)
              <input value={thresholdK} onChange={(e) => setThresholdK(e.target.value)} data-testid="pl-threshold" />
            </label>
          )}
          {effectivePreset === "band_power" && (
            <>
              <label>
                Band low (Hz)
                <input value={bandLow} onChange={(e) => setBandLow(e.target.value)} data-testid="pl-band-low" />
              </label>
              <label>
                Band high (Hz)
                <input value={bandHigh} onChange={(e) => setBandHigh(e.target.value)} data-testid="pl-band-high" />
              </label>
            </>
          )}
        </div>
      )}

      <div className="form-grid">
        <label className="span-all">
          Decoder model
          <select value={modelId} onChange={(e) => setModelId(e.target.value)} data-testid="pl-model">
            <option value="">None (features only)</option>
            {models.map((m) => (
              <option key={m.summary.model_id} value={m.summary.model_id}>
                {m.summary.model_id}
                {m.compatible === false ? " (incompatible)" : m.compatible === true ? " (compatible)" : ""}
              </option>
            ))}
          </select>
        </label>
      </div>
      {selected && <ModelDetails m={selected} />}
      {modelId && (
        <label className="check" data-testid="pl-cross-label">
          <input type="checkbox" checked={allowCross} onChange={(e) => setAllowCross(e.target.checked)} data-testid="pl-cross" />
          Allow a model trained on a different source
        </label>
      )}
      {modelId && allowCross && (
        <p className="caution-box" data-testid="pl-cross-warning">
          Runs a decoder calibrated on a different source or session. Its output is not expected to be meaningful on this
          stream; decoded events are marked with reduced quality. Use only for deliberate cross-source tests.
        </p>
      )}

      <div className="btn-row sheet-actions">
        <button
          type="button"
          className="btn btn-primary"
          disabled={busy || !canStart || !request}
          onClick={() => request && onStart(request)}
          data-testid="pl-start"
        >
          Start decoding
        </button>
      </div>
      {!canStart && <p className="hint">Connect a source (streaming or paused) first.</p>}
      {problem && <p className="caution-text">{problem}</p>}
      {error && (
        <p className="error-text" data-testid="pl-error">
          {error}
        </p>
      )}
    </div>
  );
}
