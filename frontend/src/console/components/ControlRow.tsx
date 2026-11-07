// Row 4 — Command output: the command router, the only path from decoded output to an
// application command. Off unless the operator starts it; stopped from the title bar's Stop control.

import { useEffect, useState, type MouseEvent } from "react";
import type { ConnectedApp } from "../../sdk";
import { labApi, type RouterSpec } from "../api";
import { useLoggedAction } from "../context";
import { controlOn, mappingText, runningDecoder, type PipelineState } from "../pipeline";
import { Disclosure, Dot, Row } from "./ui";

interface Form {
  x_dim: string;
  y_dim: string;
  gain: string;
  deadzone: string;
  invert_y: boolean;
  max_speed: string;
}

export function routerSpec(form: Form, enabled: boolean): { spec: RouterSpec | null; problem: string | null } {
  const gain = Number(form.gain);
  const deadzone = Number(form.deadzone);
  const maxSpeed = Number(form.max_speed);
  const ok =
    !!form.x_dim &&
    !!form.y_dim &&
    gain > 0 &&
    gain <= 10 &&
    deadzone >= 0 &&
    deadzone < 3 &&
    maxSpeed > 0 &&
    maxSpeed <= 10;
  if (!ok) return { spec: null, problem: "Check the settings: 0 < gain ≤ 10, 0 ≤ dead-zone < 3, 0 < max speed ≤ 10." };
  return {
    spec: { enabled, x_dim: form.x_dim, y_dim: form.y_dim, gain, deadzone, invert_y: form.invert_y, max_speed: maxSpeed },
    problem: null,
  };
}

/** "2 applications connected · Communication Board waiting for: selection" */
export function appsLine(apps: ConnectedApp[]): string {
  const real = apps.filter((a) => a.app.kind !== "console");
  if (!real.length) return "No applications connected.";
  const head = `${real.length} application${real.length === 1 ? "" : "s"} connected`;
  const waiting = real
    .filter((a) => a.negotiation.status !== "active")
    .map((a) => {
      const missing = a.negotiation.rejected.filter((r) => r.required).map((r) => r.capability.replace(/_/g, " "));
      return `${a.app.name} waiting for: ${missing.length ? missing.join(", ") : "a source"}`;
    });
  return [head, ...waiting].join(" · ");
}

const PARTICIPANT_URL = "/board.html";
const PARTICIPANT_WINDOW = "brainos-participant";

/** Open (or bring forward) the participant screen as its own window, sized for a second display.
 *  Falls back to the link's normal new-tab behaviour if the browser blocks the window. */
function openParticipantScreen(e: MouseEvent<HTMLAnchorElement>): void {
  const w = window.open(PARTICIPANT_URL, PARTICIPANT_WINDOW, "popup=yes,width=1280,height=800");
  if (w) {
    e.preventDefault();
    w.focus();
  }
}

export function ControlRow({ pipeline, apps }: { pipeline: PipelineState; apps: ConnectedApp[] }) {
  const action = useLoggedAction();
  const st = pipeline.status;
  const decoder = runningDecoder(st);
  const dims = decoder?.dims ?? [];
  const current = st?.router ?? null;
  const on = controlOn(st);
  const [form, setForm] = useState<Form>({ x_dim: "", y_dim: "", gain: "1", deadzone: "0.3", invert_y: false, max_speed: "2" });

  // (Re)initialise when a different decoder is loaded; keep the operator's edits otherwise.
  const modelId = decoder?.model_id ?? null;
  useEffect(() => {
    if (!modelId) return;
    setForm({
      x_dim: current?.x_dim ?? dims[0] ?? "",
      y_dim: current?.y_dim ?? dims[1] ?? dims[0] ?? "",
      gain: String(current?.gain ?? 1),
      deadzone: String(current?.deadzone ?? 0.3),
      invert_y: current?.invert_y ?? false,
      max_speed: String(current?.max_speed ?? 2),
    });
    // deliberately keyed on the decoder only: status polls must not overwrite edits
  }, [modelId]);

  const set = (patch: Partial<Form>) => setForm((f) => ({ ...f, ...patch }));
  const { spec, problem } = routerSpec(form, true);

  const apply = async (r: RouterSpec) => {
    const res = await action.run(() => labApi.setRouter(r));
    if (!res) return;
    pipeline.set(res); // the session log entry comes from the status change
  };

  const reason = !st?.running ? "Start decoding with a model first." : !decoder ? "The decoder has no model. Start decoding with a model." : null;

  // When on, stopping is the title bar's Stop control (one red button on screen, not two).
  const actions = (
    <>
      {decoder && !on && (
        <button
          type="button"
          className="btn btn-primary"
          disabled={action.busy || !spec}
          onClick={() => spec && apply(spec)}
          data-testid="router-on"
        >
          Start control
        </button>
      )}
      <a
        className="btn"
        href={PARTICIPANT_URL}
        target={PARTICIPANT_WINDOW}
        rel="opener"
        onClick={openParticipantScreen}
        data-testid="open-participant"
        title="Opens the communication board in its own window, for a second screen facing the participant."
      >
        Open participant screen
      </a>
    </>
  );

  return (
    <Row
      title="Command output"
      explain="Lets the decoder move the cursor in connected apps. Off unless you start it."
      testId="row-control"
      actions={actions}
    >
      <p className="value" data-testid="router-state">
        <Dot tone={on ? "ok" : "inactive"} />
        {on && current ? `On · ${mappingText(current)}` : "Off"}
      </p>
      {reason && <p className="value-sub" data-testid="control-reason">{reason}</p>}
      {decoder && !on && (
        <p className="value-sub" data-testid="control-what">
          When started, the cursor in connected apps follows the decoder's {form.x_dim || "x"}/{form.y_dim || "y"} output.
        </p>
      )}
      {decoder && (
        <Disclosure title="Settings" testId="control-settings" className="inline">
          <div className="form-grid">
            <label>
              Horizontal (x) from
              <select value={form.x_dim} onChange={(e) => set({ x_dim: e.target.value })} data-testid="router-x">
                {dims.map((d) => (
                  <option key={d} value={d}>
                    {d}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Vertical (y) from
              <select value={form.y_dim} onChange={(e) => set({ y_dim: e.target.value })} data-testid="router-y">
                {dims.map((d) => (
                  <option key={d} value={d}>
                    {d}
                  </option>
                ))}
              </select>
            </label>
            <label title="Workspace per second per training-standard-deviation unit (0 < gain ≤ 10)">
              Gain
              <input value={form.gain} onChange={(e) => set({ gain: e.target.value })} data-testid="router-gain" />
            </label>
            <label title="In training-standard-deviation units (0 ≤ dead-zone < 3)">
              Dead-zone
              <input value={form.deadzone} onChange={(e) => set({ deadzone: e.target.value })} data-testid="router-deadzone" />
            </label>
            <label title="0 < max speed ≤ 10">
              Max speed
              <input value={form.max_speed} onChange={(e) => set({ max_speed: e.target.value })} data-testid="router-max" />
            </label>
            <label className="check">
              <input
                type="checkbox"
                checked={form.invert_y}
                onChange={(e) => set({ invert_y: e.target.checked })}
                data-testid="router-invert"
              />
              Invert y
            </label>
          </div>
          {on && (
            <div className="btn-row">
              <button
                type="button"
                className="btn"
                disabled={action.busy || !spec}
                onClick={() => spec && apply(spec)}
                data-testid="router-apply"
              >
                Apply settings
              </button>
            </div>
          )}
          {problem && <p className="caution-text">{problem}</p>}
          <p className="hint">
            Decoded output is never an app command by itself. Only while control is on, two decoder dimensions are
            mapped to pointer velocity and delivered to applications, marked as decoded with the model id.
          </p>
        </Disclosure>
      )}
      {action.error && (
        <p className="error-text" data-testid="router-error">
          {action.error}
        </p>
      )}
      <p className="apps-line" data-testid="apps-line">
        {appsLine(apps)}
      </p>
    </Row>
  );
}
