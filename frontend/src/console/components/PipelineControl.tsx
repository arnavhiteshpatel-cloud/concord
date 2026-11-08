// Configure and start/stop the real-time processing pipeline (features -> optional decoder).
// Milestone 5: decoders of every origin (Concord-trained, imported file, plugin), a
// compatibility preview for the chosen processing, the explicit channel mapping by label
// (offered only when it applies), trust for unsafe model files, and decoded passthrough.

import { useEffect, useState } from "react";
import { labApi, type ModelInfo, type PipelineStartRequest, type PresetName, type ProcessingSpecInput } from "../api";
import { useLoggedAction } from "../context";
import { decoderLine, inputWords } from "../decoders";
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
  /** Milestone 5: explicit operator-enabled channel mapping by label */
  allowChannelMapping?: boolean;
}): { request: PipelineStartRequest | null; problem: string | null } {
  const processing: ProcessingSpecInput = { preset: form.preset };
  if (form.preset === "decoded_passthrough")
    // the source's own decoder outputs: no features computed, no model loaded
    return { request: { processing, model_id: null, allow_cross_source: false }, problem: null };
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
  const request: PipelineStartRequest = {
    processing,
    model_id: form.modelId || null,
    allow_cross_source: form.modelId ? form.allowCrossSource : false,
  };
  if (form.modelId && form.allowChannelMapping) request.allow_channel_mapping = true;
  return { request, problem: null };
}

function TrustAction({ m, onChanged }: { m: ModelInfo; onChanged: () => void }) {
  const action = useLoggedAction();
  const s = m.summary;
  if (!s.unsafe_format) return null;
  const set = async (trusted: boolean) => {
    if (await action.run(() => labApi.trustModel(s.model_id, trusted))) onChanged();
  };
  return (
    <div className="caution-box" data-testid="model-trust">
      {s.trust ? (
        <>
          <p>
            This {s.format} file was marked trusted by {s.trust.by} ({fmt.time(s.trust.at_ns)}). Loading it runs code from
            the file, in an isolated decoder process, which is not a security sandbox.
          </p>
          <button type="button" className="btn" disabled={action.busy} onClick={() => set(false)} data-testid="model-untrust">
            Withdraw trust
          </button>
        </>
      ) : (
        <>
          <p>
            A {s.format} file runs code from the file when it is loaded, so Concord refuses it. Mark it trusted only if you
            created this exact file or trust its author; the decision is recorded with the file&apos;s SHA-256.
          </p>
          <button type="button" className="btn" disabled={action.busy} onClick={() => set(true)} data-testid="model-trust-btn">
            Mark this file trusted
          </button>
        </>
      )}
      {action.error && <p className="error-text">{action.error}</p>}
    </div>
  );
}

function compatTarget(m: ModelInfo): string {
  return m.checked_against && m.checked_against !== "running pipeline"
    ? `this processing (${m.checked_against})`
    : "the running pipeline output";
}

function ModelDetails({ m, onChanged }: { m: ModelInfo; onChanged: () => void }) {
  const s = m.summary;
  const inp = s.input;
  return (
    <div className="model-details" data-testid="model-details">
      <dl className="kv">
        {s.origin && (
          <>
            <dt>Decoder</dt>
            <dd data-testid="model-origin">{decoderLine(s)}</dd>
          </>
        )}
        {s.modalities && (
          <>
            <dt>Trained on data from</dt>
            <dd>
              {s.modalities.length ? s.modalities.join(", ") : "modality not declared"}
              {s.participant_specific === false && " · not participant-specific (not calibrated on this participant)"}
            </dd>
          </>
        )}
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
        ) : s.outputs?.type === "event" ? (
          <>
            <dt>Outputs</dt>
            <dd>event probabilities: {s.outputs.events.join(", ")}</dd>
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
          {(s.inputs?.length ?? 0) > 1 && (
            <span className="hint"> · inputs joined per bin: {s.inputs!.map((i) => inputWords(i)).join(" + ")}</span>
          )}
        </dd>
      </dl>
      <p className="hint" data-testid="model-compat">
        {m.compatible === null && "Compatibility is checked against the pipeline output when it starts."}
        {m.compatible === true && <span className="text-ok">Compatible with {compatTarget(m)}.</span>}
        {m.compatible === false && <span className="error-text">Not compatible with {compatTarget(m)}.</span>}
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
      <TrustAction m={m} onChanged={onChanged} />
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
  hasSourceDecoder = false,
  onProcessingChange,
  onModelsChanged,
}: {
  presets: Record<string, string>;
  models: ModelInfo[];
  defaultPreset: PresetName;
  canStart: boolean;
  busy: boolean;
  error: string | null;
  onStart: (req: PipelineStartRequest) => void;
  /** the source provides its own decoder outputs (decoded passthrough is offered only then) */
  hasSourceDecoder?: boolean;
  /** the processing the form would start (for a compatibility preview of the models) */
  onProcessingChange?: (p: ProcessingSpecInput | null) => void;
  onModelsChanged?: () => void;
}) {
  const names = (Object.keys(presets) as PresetName[]).filter((n) => n !== "decoded_passthrough" || hasSourceDecoder);
  const [preset, setPreset] = useState<PresetName>(defaultPreset);
  const [binMs, setBinMs] = useState("");
  const [thresholdK, setThresholdK] = useState("-4.5");
  const [bandLow, setBandLow] = useState("");
  const [bandHigh, setBandHigh] = useState("");
  const [modelId, setModelId] = useState("");
  const [allowCross, setAllowCross] = useState(false);
  const [allowMapping, setAllowMapping] = useState(false);

  const effectivePreset = names.includes(preset) ? preset : (names[0] ?? preset);
  const passthrough = effectivePreset === "decoded_passthrough";
  const { request, problem } = buildStartRequest({
    preset: effectivePreset,
    binMs,
    thresholdK,
    bandLow,
    bandHigh,
    modelId: passthrough ? "" : modelId,
    allowCrossSource: allowCross,
    allowChannelMapping: allowMapping,
  });
  const selected = passthrough ? null : (models.find((m) => m.summary.model_id === modelId) ?? null);
  const previewKey = request ? JSON.stringify(request.processing) : "";
  useEffect(() => {
    onProcessingChange?.(previewKey ? (JSON.parse(previewKey) as ProcessingSpecInput) : null);
  }, [previewKey, onProcessingChange]);

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
      {effectivePreset !== "features_passthrough" && !passthrough && (
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

      {passthrough ? (
        <p className="hint" data-testid="pl-passthrough">
          The source&apos;s own decoder outputs go to Command output unchanged, keeping their model and origin (a research
          system&apos;s recorded decoder, or an external system&apos;s live decoder). No model is loaded.
        </p>
      ) : (
        <div className="form-grid">
          <label className="span-all">
            Decoder model
            <select value={modelId} onChange={(e) => setModelId(e.target.value)} data-testid="pl-model">
              <option value="">None (features only)</option>
              {models.map((m) => (
                <option key={m.summary.model_id} value={m.summary.model_id} disabled={m.summary.status === "rejected"}>
                  {m.summary.model_id}
                  {m.compatible === false ? " (incompatible)" : m.compatible === true ? " (compatible)" : ""}
                </option>
              ))}
            </select>
          </label>
        </div>
      )}
      {selected && <ModelDetails m={selected} onChanged={() => onModelsChanged?.()} />}
      {selected?.mapping_available && (
        <label className="check" data-testid="pl-mapping-label">
          <input
            type="checkbox"
            checked={allowMapping}
            onChange={(e) => setAllowMapping(e.target.checked)}
            data-testid="pl-mapping"
          />
          Map channels by label (the model&apos;s channels are taken from the source by name)
        </label>
      )}
      {selected?.mapping_available && allowMapping && (
        <p className="caution-box" data-testid="pl-mapping-warning">
          Concord will feed the model the source channels that carry the model&apos;s labels, in the model&apos;s order. Use
          this only if the labels name the same electrodes. The mapping is logged and shown while decoding.
        </p>
      )}
      {modelId && !passthrough && (
        <label className="check" data-testid="pl-cross-label">
          <input type="checkbox" checked={allowCross} onChange={(e) => setAllowCross(e.target.checked)} data-testid="pl-cross" />
          Allow a model trained on a different source
        </label>
      )}
      {modelId && !passthrough && allowCross && (
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
