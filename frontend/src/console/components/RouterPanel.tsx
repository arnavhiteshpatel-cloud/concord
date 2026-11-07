// Command router: the only path from decoded output to an application command.

import { useEffect, useState } from "react";
import type { PipelineStatus, RouterSpec } from "../api";

export function RouterPanel({
  status,
  busy,
  error,
  onApply,
}: {
  status: PipelineStatus | null;
  busy: boolean;
  error: string | null;
  onApply: (r: RouterSpec) => void;
}) {
  const decoder = status?.running ? status.decoder : null;
  const dims = decoder?.dims ?? [];
  const current = status?.router ?? null;
  const [form, setForm] = useState({
    enabled: false,
    x_dim: "",
    y_dim: "",
    gain: "1",
    deadzone: "0.3",
    invert_y: false,
    max_speed: "2",
  });

  // (Re)initialise when a different decoder is loaded; keep the operator's edits otherwise.
  const modelId = decoder?.model_id ?? null;
  useEffect(() => {
    if (!modelId) return;
    setForm({
      enabled: current?.enabled ?? false,
      x_dim: current?.x_dim ?? dims[0] ?? "",
      y_dim: current?.y_dim ?? dims[1] ?? dims[0] ?? "",
      gain: String(current?.gain ?? 1),
      deadzone: String(current?.deadzone ?? 0.3),
      invert_y: current?.invert_y ?? false,
      max_speed: String(current?.max_speed ?? 2),
    });
    // deliberately keyed on the decoder only: status polls must not overwrite edits
  }, [modelId]);

  const intro = (
    <p className="muted small">
      Decoded output (<code>intent.kinematics</code>, provenance <code>decoded_intent</code>) is never an app command.
      Commands reach applications <b>only while the router is ON</b>: it maps two decoder dimensions to{" "}
      <code>intent.pointer</code> velocity (still <code>decoded_intent</code> with the model id).
    </p>
  );
  if (!decoder) {
    return (
      <div data-testid="router-panel">
        {intro}
        <div className="empty">Start the pipeline with a decoder model to configure the router.</div>
      </div>
    );
  }

  const gain = Number(form.gain);
  const deadzone = Number(form.deadzone);
  const maxSpeed = Number(form.max_speed);
  const valid =
    !!form.x_dim &&
    !!form.y_dim &&
    gain > 0 &&
    gain <= 10 &&
    deadzone >= 0 &&
    deadzone < 3 &&
    maxSpeed > 0 &&
    maxSpeed <= 10;
  const set = (patch: Partial<typeof form>) => setForm((f) => ({ ...f, ...patch }));
  const spec = (enabled: boolean): RouterSpec => ({
    enabled,
    x_dim: form.x_dim,
    y_dim: form.y_dim,
    gain,
    deadzone,
    invert_y: form.invert_y,
    max_speed: maxSpeed,
  });

  return (
    <div data-testid="router-panel">
      {intro}
      <div className={`router-state ${current?.enabled ? "text-ok" : "muted"}`} data-testid="router-state">
        Router is {current?.enabled ? "ON — decoded pointer commands are delivered to apps" : "OFF — no commands reach apps"}
      </div>
      <div className="form-grid">
        <label>
          x ← dimension
          <select value={form.x_dim} onChange={(e) => set({ x_dim: e.target.value })} data-testid="router-x">
            {dims.map((d) => (
              <option key={d} value={d}>
                {d}
              </option>
            ))}
          </select>
        </label>
        <label>
          y ← dimension
          <select value={form.y_dim} onChange={(e) => set({ y_dim: e.target.value })} data-testid="router-y">
            {dims.map((d) => (
              <option key={d} value={d}>
                {d}
              </option>
            ))}
          </select>
        </label>
        <label title="workspace/s per training-std unit (0 < gain ≤ 10)">
          gain
          <input value={form.gain} onChange={(e) => set({ gain: e.target.value })} data-testid="router-gain" />
        </label>
        <label title="in training-std units (0 ≤ deadzone < 3)">
          deadzone
          <input value={form.deadzone} onChange={(e) => set({ deadzone: e.target.value })} data-testid="router-deadzone" />
        </label>
        <label title="0 < max speed ≤ 10">
          max speed
          <input value={form.max_speed} onChange={(e) => set({ max_speed: e.target.value })} data-testid="router-max" />
        </label>
        <label className="check">
          <input
            type="checkbox"
            checked={form.invert_y}
            onChange={(e) => set({ invert_y: e.target.checked })}
            data-testid="router-invert"
          />
          invert y
        </label>
      </div>
      <div className="btn-row">
        {current?.enabled ? (
          <>
            <button className="btn" disabled={busy || !valid} onClick={() => onApply(spec(true))} data-testid="router-apply">
              Apply changes
            </button>
            <button className="btn btn-danger" disabled={busy || !valid} onClick={() => onApply(spec(false))} data-testid="router-off">
              Turn router OFF
            </button>
          </>
        ) : (
          <button className="btn btn-primary" disabled={busy || !valid} onClick={() => onApply(spec(true))} data-testid="router-on">
            Turn router ON
          </button>
        )}
      </div>
      {!valid && <p className="text-warn small">Check the values: 0 &lt; gain ≤ 10, 0 ≤ deadzone &lt; 3, 0 &lt; max speed ≤ 10.</p>}
      {error && (
        <div className="alert" data-testid="router-error">
          {error}
        </div>
      )}
    </div>
  );
}
