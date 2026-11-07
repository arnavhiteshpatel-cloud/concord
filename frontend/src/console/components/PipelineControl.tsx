// Configure and start/stop the real-time processing pipeline (features -> optional decoder).

import { useState } from "react";
import type { ModelInfo, PipelineStartRequest, PipelineStatus, PresetName, ProcessingSpecInput } from "../api";
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
      <div className="mono small">
        dims [{s.dims.join(", ")}] · input {inp?.event_type ?? "?"} / {inp?.feature ?? "?"} · {inp?.bin_ms ?? "?"} ms ·{" "}
        {inp?.channel_count ?? "?"} ch{inp?.inferred ? " (inferred)" : ""}
      </div>
      <div className="small">
        trained on <span className="mono">{s.trained_on ?? "—"}</span>
        {s.source_identity ? (
          <>
            {" "}
            · source <span className="mono">{s.source_identity}</span>
          </>
        ) : null}
      </div>
      <div className="small">
        held-out R² (offline, as reported by the model file): <b>{fmt.num(s.held_out_r2 ?? null, 3)}</b> · mean-predictor
        control {fmt.num(s.control_mean_predictor_r2 ?? null, 3)} · {fmt.num(s.held_out_samples ?? null)} samples
      </div>
      <div className="small" data-testid="model-compat">
        {m.compatible === null && <span className="muted">Compatibility is checked against the pipeline output when it starts.</span>}
        {m.compatible === true && <span className="text-ok">✓ compatible with the running pipeline output</span>}
        {m.compatible === false && <span className="text-err">✗ incompatible with the running pipeline output</span>}
      </div>
      {m.errors.length > 0 && (
        <ul className="notes text-err small">
          {m.errors.map((e) => (
            <li key={e}>{e}</li>
          ))}
        </ul>
      )}
      {m.warnings.length > 0 && (
        <ul className="notes text-warn small">
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
  status,
  canStart,
  busy,
  error,
  onStart,
  onStop,
}: {
  presets: Record<string, string>;
  models: ModelInfo[];
  status: PipelineStatus | null;
  canStart: boolean;
  busy: boolean;
  error: string | null;
  onStart: (req: PipelineStartRequest) => void;
  onStop: () => void;
}) {
  const names = Object.keys(presets) as PresetName[];
  const [preset, setPreset] = useState<PresetName>("spikeband_threshold");
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
  const running = !!status?.running;

  return (
    <div data-testid="pipeline-control">
      <div className="form-grid">
        <label>
          preset
          <select
            value={effectivePreset}
            onChange={(e) => setPreset(e.target.value as PresetName)}
            data-testid="pl-preset"
          >
            {names.map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </label>
        {effectivePreset !== "features_passthrough" && (
          <label>
            bin (ms)
            <input
              value={binMs}
              placeholder={effectivePreset === "spikeband_threshold" ? "20 (default)" : "50 (default)"}
              onChange={(e) => setBinMs(e.target.value)}
              data-testid="pl-bin"
            />
          </label>
        )}
        {effectivePreset === "spikeband_threshold" && (
          <label>
            threshold k (× RMS)
            <input value={thresholdK} onChange={(e) => setThresholdK(e.target.value)} data-testid="pl-threshold" />
          </label>
        )}
        {effectivePreset === "band_power" && (
          <>
            <label>
              band low (Hz)
              <input value={bandLow} onChange={(e) => setBandLow(e.target.value)} data-testid="pl-band-low" />
            </label>
            <label>
              band high (Hz)
              <input value={bandHigh} onChange={(e) => setBandHigh(e.target.value)} data-testid="pl-band-high" />
            </label>
          </>
        )}
      </div>
      {presets[effectivePreset] && <p className="muted small">{presets[effectivePreset]}</p>}

      <div className="form-grid">
        <label className="span-all">
          decoder model (optional)
          <select value={modelId} onChange={(e) => setModelId(e.target.value)} data-testid="pl-model">
            <option value="">none — features only</option>
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
          allow cross-source decoding
        </label>
      )}
      {modelId && allowCross && (
        <div className="alert alert-warn" data-testid="pl-cross-warning">
          Runs a decoder calibrated on a different source or session. Its output is not expected to be meaningful on this
          stream; decoded events are marked with reduced quality. Use only for deliberate cross-source tests.
        </div>
      )}

      <div className="btn-row" style={{ marginTop: 10 }}>
        <button
          className="btn btn-primary"
          disabled={busy || !canStart || !request}
          onClick={() => request && onStart(request)}
          data-testid="pl-start"
        >
          {running ? "Restart pipeline" : "Start pipeline"}
        </button>
        <button className="btn btn-danger" disabled={busy || !running} onClick={onStop} data-testid="pl-stop">
          Stop pipeline
        </button>
      </div>
      {!canStart && <p className="muted small">Connect a device (streaming or paused) to start a pipeline.</p>}
      {problem && <p className="text-warn small">{problem}</p>}
      {error && (
        <div className="alert" data-testid="pl-error">
          {error}
        </div>
      )}
    </div>
  );
}
