// Row 4 — Command output: the command router, the only path from decoded output to an
// application command, and the applications the operator authorizes to receive it. Off unless
// the operator starts it; stopped from the title bar's Stop control.

import { useEffect, useState, type MouseEvent } from "react";
import type { ConnectedApp } from "../../sdk";
import { labApi, type AppControl, type CommandCapability, type ControlStatus, type DiscreteAction, type DiscreteRule, type RouterSpec } from "../api";
import { useLoggedAction, useLog } from "../context";
import { usePoll } from "../hooks";
import { actionLabel, controlOn, decoderClasses, mappingText, runningDecoder, type PipelineState } from "../pipeline";
import { Disclosure, Dot, Row } from "./ui";

interface Form {
  x_dim: string;
  y_dim: string;
  gain: string;
  deadzone: string;
  invert_y: boolean;
  max_speed: string;
  /** schema 1.4: a click from one decoder output ("" = none) */
  click_dim?: string;
  click_threshold?: string;
  click_min_confidence?: string;
  click_refractory_ms?: string;
}

/** One editable discrete rule per decoder class; action "" = no action for that class. */
export interface RuleForm {
  output: string;
  action: DiscreteAction | "";
  threshold: string;
  hold_ms: string;
  refractory_ms: string;
  text: string;
}

const POINTER_DEFAULTS = { gain: 1, deadzone: 0.3, invert_y: false, max_speed: 2 };

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
  const spec: RouterSpec = { enabled, x_dim: form.x_dim, y_dim: form.y_dim, gain, deadzone, invert_y: form.invert_y, max_speed: maxSpeed };
  if (form.click_dim) {
    const threshold = Number(form.click_threshold ?? "0.5");
    const minConf = Number(form.click_min_confidence ?? "0");
    const refractory = Number(form.click_refractory_ms ?? "300");
    if (form.click_dim === form.x_dim || form.click_dim === form.y_dim)
      return { spec: null, problem: "The click cannot come from a dimension that moves the pointer." };
    if (!(threshold > 0 && threshold <= 1) || !(minConf >= 0 && minConf <= 1) || !(refractory >= 0 && refractory <= 10000))
      return { spec: null, problem: "Check the click: 0 < threshold ≤ 1, 0 ≤ minimum confidence ≤ 1, pause 0–10000 ms." };
    spec.click = { output: form.click_dim, threshold, min_confidence: minConf, refractory_ms: refractory };
  }
  return { spec, problem: null };
}

/** Default rules: "rest"-like classes do nothing; the others get select, activate, cancel in order. */
export function defaultRules(classes: string[]): RuleForm[] {
  const order: DiscreteAction[] = ["primary", "activate", "cancel"];
  let k = 0;
  return classes.map((output) => {
    const idle = /^(rest|idle|none|baseline)$/i.test(output);
    const action = idle ? "" : (order[k++] ?? "");
    return { output, action, threshold: "0.8", hold_ms: "300", refractory_ms: "1000", text: "" };
  });
}

export function discreteSpec(rules: RuleForm[], enabled: boolean): { spec: RouterSpec | null; problem: string | null } {
  const discrete: DiscreteRule[] = [];
  for (const r of rules) {
    if (!r.action) continue;
    const threshold = Number(r.threshold);
    const hold = Number(r.hold_ms);
    const refractory = Number(r.refractory_ms);
    if (!(threshold > 0 && threshold <= 1) || !(hold >= 0 && hold <= 10000) || !(refractory >= 0 && refractory <= 60000))
      return { spec: null, problem: "Check the actions: 0 < threshold ≤ 1, hold 0–10000 ms, pause 0–60000 ms." };
    if (r.action === "text" && !r.text.trim()) return { spec: null, problem: `Enter the text to type for ${r.output}.` };
    discrete.push({
      output: r.output,
      action: r.action,
      threshold,
      hold_ms: hold,
      refractory_ms: refractory,
      ...(r.action === "text" ? { text: r.text.trim() } : {}),
    });
  }
  if (!discrete.length) return { spec: null, problem: "Choose an action for at least one class." };
  return { spec: { enabled, x_dim: null, y_dim: null, ...POINTER_DEFAULTS, discrete }, problem: null };
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

const CAP_TEXT: Record<CommandCapability, string> = {
  pointer_intent: "pointer movement",
  selection: "discrete actions",
  text_intent: "text",
  navigation: "navigation",
};

const list = (caps: CommandCapability[]) => caps.map((c) => CAP_TEXT[c]).join(", ");

/** One plain sentence: what the app gets now, or would get if authorized. */
export function describeApp(a: AppControl, provides: CommandCapability[], router: RouterSpec | null): string {
  if (a.connections === 0) return `Not connected. Authorized for ${list(a.authorized)}.`;
  const detail = (c: CommandCapability) => {
    if (c !== "selection" || !router?.discrete?.length) return CAP_TEXT[c];
    const acts = router.discrete.filter((d) => d.action !== "text" && !d.action.startsWith("navigate:")).map(actionLabel);
    return acts.length ? `${CAP_TEXT[c]} (${acts.join(", ")})` : CAP_TEXT[c];
  };
  const would = a.requested.filter((c) => provides.includes(c));
  const missingRequired = a.waiting.filter((w) => w.required && w.reason !== "not_authorized").map((w) => w.capability);
  if (a.receiving.length) return `Receiving ${a.receiving.map(detail).join(", ")}.`;
  const blocked = missingRequired.length ? ` It cannot run without ${list(missingRequired)}, which command output does not provide now.` : "";
  if (a.authorized.length) {
    return would.length && !blocked
      ? `Authorized for ${list(a.authorized)}.`
      : `Authorized for ${list(a.authorized)}. Nothing to receive now.${blocked}`;
  }
  if (would.length) return `Not authorized. Would receive ${would.map(detail).join(", ")}.${blocked}`;
  return `Not authorized. Asks for ${list(a.requested)}; command output does not provide it now.`;
}

function AuthorizedApps({ control, onChange }: { control: ControlStatus; onChange: (c: ControlStatus) => void }) {
  const action = useLoggedAction();
  const log = useLog();
  const apps = control.apps.filter((a) => a.kind !== "console");
  if (!apps.length) return null;
  const authorize = async (a: AppControl) => {
    const caps = a.requested.filter((c) => !a.authorized.includes(c));
    const res = await action.run(() => labApi.authorizeApp(a.app_id, caps));
    if (!res) return;
    log("info", `Authorized ${a.name ?? a.app_id} for ${list(caps)}`);
    onChange(res);
  };
  const revoke = async (a: AppControl) => {
    const res = await action.run(() => labApi.revokeApp(a.app_id));
    if (!res) return;
    log("info", `Revoked ${a.name ?? a.app_id}`);
    onChange(res);
  };
  return (
    <div className="control-apps" data-testid="control-apps">
      <h3 className="minor">Authorized applications</h3>
      <p className="hint">Decoded commands reach only the applications you authorize here, until you revoke them.</p>
      {apps.map((a) => {
        const canAuthorize = a.connections > 0 && a.requested.some((c) => !a.authorized.includes(c));
        return (
          <div key={a.app_id} className="control-app" data-testid={`control-app-${a.app_id}`}>
            <div className="control-app-text">
              <span className="control-app-name">{a.name ?? a.app_id}</span>
              <span className="value-sub" data-testid={`control-app-line-${a.app_id}`}>
                {describeApp(a, control.provides, control.router)}
              </span>
            </div>
            <div className="control-app-actions">
              {canAuthorize && (
                <button type="button" className="btn" disabled={action.busy} onClick={() => authorize(a)} data-testid={`authorize-${a.app_id}`}>
                  Authorize
                </button>
              )}
              {a.authorized.length > 0 && (
                <button type="button" className="btn" disabled={action.busy} onClick={() => revoke(a)} data-testid={`revoke-${a.app_id}`}>
                  Revoke
                </button>
              )}
            </div>
          </div>
        );
      })}
      {action.error && <p className="error-text">{action.error}</p>}
    </div>
  );
}

const PARTICIPANT_URL = "/board.html";
const PARTICIPANT_WINDOW = "concord-participant";

/** Open (or bring forward) the participant screen as its own window, sized for a second display.
 *  Falls back to the link's normal new-tab behaviour if the browser blocks the window. */
function openParticipantScreen(e: MouseEvent<HTMLAnchorElement>): void {
  const w = window.open(PARTICIPANT_URL, PARTICIPANT_WINDOW, "popup=yes,width=1280,height=800");
  if (w) {
    e.preventDefault();
    w.focus();
  }
}

const isControlStatus = (v: unknown): v is ControlStatus =>
  !!v && typeof v === "object" && Array.isArray((v as ControlStatus).apps) && Array.isArray((v as ControlStatus).provides);

export function ControlRow({ pipeline, apps }: { pipeline: PipelineState; apps: ConnectedApp[] }) {
  const action = useLoggedAction();
  const st = pipeline.status;
  const decoder = runningDecoder(st);
  const classes = decoderClasses(decoder);
  const dims = decoder?.dims ?? [];
  const current = st?.router ?? null;
  const on = controlOn(st);
  const [form, setForm] = useState<Form>({ x_dim: "", y_dim: "", gain: "1", deadzone: "0.3", invert_y: false, max_speed: "2", click_dim: "" });
  const [rules, setRules] = useState<RuleForm[]>([]);
  const poll = usePoll("control", labApi.control, 1000);
  const [override, setOverride] = useState<ControlStatus | null>(null);
  useEffect(() => setOverride(null), [poll.value]);
  const control = override ?? (isControlStatus(poll.value) ? poll.value : null);

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
      click_dim: current?.click?.output ?? "",
      click_threshold: String(current?.click?.threshold ?? 0.5),
      click_min_confidence: String(current?.click?.min_confidence ?? 0),
      click_refractory_ms: String(current?.click?.refractory_ms ?? 300),
    });
    if (classes) {
      const base = defaultRules(classes);
      const have = current?.discrete ?? [];
      setRules(
        have.length
          ? base.map((r) => {
              const d = have.find((x) => x.output === r.output);
              return d
                ? { output: r.output, action: d.action, threshold: String(d.threshold), hold_ms: String(d.hold_ms), refractory_ms: String(d.refractory_ms), text: d.text ?? "" }
                : { ...r, action: "" };
            })
          : base,
      );
    }
    // deliberately keyed on the decoder only: status polls must not overwrite edits
  }, [modelId]);

  const set = (patch: Partial<Form>) => setForm((f) => ({ ...f, ...patch }));
  const setRule = (i: number, patch: Partial<RuleForm>) => setRules((rs) => rs.map((r, j) => (j === i ? { ...r, ...patch } : r)));
  const { spec, problem } = classes ? discreteSpec(rules, true) : routerSpec(form, true);

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

  const chosen = rules.filter((r) => r.action);
  const what = classes
    ? chosen.length
      ? `When started, authorized apps receive ${chosen.map((r) => `${actionLabel({ action: r.action as DiscreteAction, text: r.text })} when ${r.output} is held`).join(", ")}.`
      : "Choose in Settings which class triggers which action."
    : `When started, the cursor in authorized apps follows the decoder's ${form.x_dim || "x"}/${form.y_dim || "y"} output.`;

  return (
    <Row
      title="Command output"
      explain="Lets the decoder send commands to the applications you authorize. Off unless you start it."
      testId="row-control"
      actions={actions}
    >
      <p className="value" data-testid="router-state">
        <Dot tone={on ? "ok" : "inactive"} />
        {on && current ? `On · ${mappingText(current)}` : "Off"}
      </p>
      {!on && st?.last_router_stop && decoder && (
        <p className="value-sub" data-testid="router-last-stop">
          Last stopped: {st.last_router_stop.reason}.
        </p>
      )}
      {reason && <p className="value-sub" data-testid="control-reason">{reason}</p>}
      {decoder && !on && (
        <p className="value-sub" data-testid="control-what">
          {what}
        </p>
      )}
      {decoder && !classes && (
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
            <label title="A decoder output that is a click probability or a 0/1 click decision (optional)">
              Click from
              <select value={form.click_dim ?? ""} onChange={(e) => set({ click_dim: e.target.value })} data-testid="router-click">
                <option value="">No click</option>
                {dims
                  .filter((d) => d !== form.x_dim && d !== form.y_dim)
                  .map((d) => (
                    <option key={d} value={d}>
                      {d}
                    </option>
                  ))}
              </select>
            </label>
            {form.click_dim && (
              <>
                <label title="The click output must reach this value (0 < threshold ≤ 1)">
                  Click threshold
                  <input value={form.click_threshold ?? "0.5"} onChange={(e) => set({ click_threshold: e.target.value })} data-testid="router-click-threshold" />
                </label>
                <label title="Clicks whose confidence is below this are not sent (0–1)">
                  Minimum confidence
                  <input value={form.click_min_confidence ?? "0"} onChange={(e) => set({ click_min_confidence: e.target.value })} data-testid="router-click-confidence" />
                </label>
                <label title="Minimum time between two clicks">
                  Click pause (ms)
                  <input value={form.click_refractory_ms ?? "300"} onChange={(e) => set({ click_refractory_ms: e.target.value })} data-testid="router-click-pause" />
                </label>
              </>
            )}
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
            mapped to pointer velocity and delivered to authorized applications, marked as decoded with the model id.
          </p>
        </Disclosure>
      )}
      {decoder && classes && (
        <Disclosure title="Settings" testId="control-settings" className="inline">
          <p className="hint">
            The decoder estimates how likely each class is. An action is sent when a class stays above its threshold for
            the hold time; it can repeat only after the class drops back and the pause has passed.
          </p>
          <div className="rule-list" data-testid="rules-editor">
            {rules.map((r, i) => (
              <div key={r.output} className="form-grid rule" data-testid={`rule-${r.output}`}>
                <label>
                  When {r.output} is held
                  <select
                    value={r.action}
                    onChange={(e) => setRule(i, { action: e.target.value as RuleForm["action"] })}
                    data-testid={`rule-action-${r.output}`}
                  >
                    <option value="">No action</option>
                    <option value="primary">Select</option>
                    <option value="activate">Activate</option>
                    <option value="cancel">Cancel</option>
                    <option value="navigate:next">Move to next</option>
                    <option value="navigate:previous">Move to previous</option>
                    <option value="navigate:up">Move up</option>
                    <option value="navigate:down">Move down</option>
                    <option value="navigate:left">Move left</option>
                    <option value="navigate:right">Move right</option>
                    <option value="text">Type text</option>
                  </select>
                </label>
                {r.action && (
                  <>
                    <label title="Probability the class must exceed (0 < threshold ≤ 1)">
                      Threshold
                      <input value={r.threshold} onChange={(e) => setRule(i, { threshold: e.target.value })} data-testid={`rule-threshold-${r.output}`} />
                    </label>
                    <label title="How long the class must stay above the threshold">
                      Hold (ms)
                      <input value={r.hold_ms} onChange={(e) => setRule(i, { hold_ms: e.target.value })} data-testid={`rule-hold-${r.output}`} />
                    </label>
                    <label title="Minimum time between two actions from this class">
                      Pause (ms)
                      <input value={r.refractory_ms} onChange={(e) => setRule(i, { refractory_ms: e.target.value })} data-testid={`rule-pause-${r.output}`} />
                    </label>
                  </>
                )}
                {r.action === "text" && (
                  <label>
                    Text
                    <input value={r.text} maxLength={64} onChange={(e) => setRule(i, { text: e.target.value })} data-testid={`rule-text-${r.output}`} />
                  </label>
                )}
              </div>
            ))}
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
        </Disclosure>
      )}
      {action.error && (
        <p className="error-text" data-testid="router-error">
          {action.error}
        </p>
      )}
      {control && <AuthorizedApps control={control} onChange={setOverride} />}
      <p className="apps-line" data-testid="apps-line">
        {appsLine(apps)}
      </p>
    </Row>
  );
}
