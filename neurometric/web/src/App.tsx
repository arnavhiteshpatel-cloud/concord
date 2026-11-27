import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { DEFAULT_SETTINGS, MODALITY_LABELS, SELECTION_LABELS, loadSettings, saveSettings, type Settings } from "./a11y/settings";
import { useAppScanning } from "./a11y/scanning";
import { Choice, Stepper, Toggle } from "./ui/controls";
import { TaskRunner } from "./tasks/TaskRunner";
import { IMPLEMENTED, loadManifest, loadStimuli, type Manifest, type Stimuli, type TaskSpec } from "./tasks/stimuli";
import type { TaskRun } from "./tasks/session";
import type { Limits } from "./tasks/api";
import { downloadJson, login, saveLocal, serverAvailable, uploadRun } from "./tasks/upload";
import { DemoApp } from "./demo/DemoApp";

interface Route {
  name: "setup" | "tasks" | "run" | "results" | "demo";
  id?: string;
  params: URLSearchParams;
}

function parseRoute(): Route {
  const h = location.hash.replace(/^#\/?/, "");
  const [path, q] = h.split("?");
  const parts = path.split("/").filter(Boolean);
  const params = new URLSearchParams(q ?? "");
  const name = (parts[0] ?? "setup") as Route["name"];
  if (!["setup", "tasks", "run", "results", "demo"].includes(name)) return { name: "setup", params };
  return { name, id: parts[1], params };
}

function useRoute(): Route {
  const [r, setR] = useState(parseRoute);
  useEffect(() => {
    const on = () => setR(parseRoute());
    window.addEventListener("hashchange", on); // navigation only; no input listeners on window
    return () => window.removeEventListener("hashchange", on);
  }, []);
  return r;
}

const TITLES: Record<Route["name"], string> = { setup: "Setup", tasks: "Tasks", run: "Task", results: "Results and export", demo: "Degradation demo" };

declare global {
  interface Window {
    __nm?: { runs: TaskRun[]; settings: Settings };
  }
}

export function App() {
  const route = useRoute();
  const [settings, setSettingsState] = useState<Settings>(loadSettings);
  const [runs, setRuns] = useState<TaskRun[]>([]);
  const [root, setRoot] = useState<HTMLDivElement | null>(null);
  const mainRef = useRef<HTMLElement>(null);
  const setSettings = useCallback((s: Settings) => {
    setSettingsState(s);
    saveSettings(s);
  }, []);
  const update = (p: Partial<Settings>) => setSettings({ ...settings, ...p });

  // theme, text size, motion
  useEffect(() => {
    const el = document.documentElement;
    if (settings.theme === "system") delete el.dataset.theme;
    else el.dataset.theme = settings.theme;
    if (settings.motion === "system") delete el.dataset.motion;
    else el.dataset.motion = settings.motion;
    el.style.setProperty("--text-scale", String(settings.textScale));
  }, [settings.theme, settings.motion, settings.textScale]);

  useEffect(() => {
    document.title = `${TITLES[route.name]} – NeuroMetric`;
    // move focus to the new screen's heading for screen-reader and keyboard users
    if (route.name !== "run") queueMicrotask(() => mainRef.current?.querySelector<HTMLElement>("h2")?.focus());
  }, [route.name, route.id]);

  window.__nm = { runs, settings };

  useAppScanning(root, settings.switch, settings.uiScanning || settings.selection === "scan");

  const onDone = useCallback((run: TaskRun) => {
    saveLocal(run);
    setRuns((r) => [...r, run]);
    location.hash = "#/results";
  }, []);

  return (
    <div className="app" ref={setRoot}>
      <a className="skip-link" href="#main" onClick={(e) => { e.preventDefault(); mainRef.current?.focus(); }}>
        Skip to main content
      </a>
      <header className="site">
        <h1>NeuroMetric</h1>
        <span className="badge">Research software – not a medical device</span>
        <nav aria-label="Main">
          <ul>
            {(["setup", "tasks", "results", "demo"] as const).map((n) => (
              <li key={n}>
                <a className="button" href={`#/${n}`} aria-current={route.name === n ? "page" : undefined}>
                  {TITLES[n]}
                </a>
              </li>
            ))}
          </ul>
        </nav>
      </header>
      <main id="main" ref={mainRef} tabIndex={-1} className={route.name === "run" || route.name === "demo" ? "wide" : ""} data-scan-root>
        {route.name === "setup" && <SetupScreen settings={settings} update={update} reset={() => setSettings({ ...DEFAULT_SETTINGS })} />}
        {route.name === "tasks" && <TaskList settings={settings} />}
        {route.name === "run" && route.id && <RunScreen id={route.id} params={route.params} settings={settings} onDone={onDone} />}
        {route.name === "results" && <ResultsScreen runs={runs} />}
        {route.name === "demo" && <DemoApp settings={settings} />}
      </main>
    </div>
  );
}

// ----------------------------------------------------------------------------- setup
function SetupScreen({ settings: s, update, reset }: { settings: Settings; update: (p: Partial<Settings>) => void; reset: () => void }) {
  const [capture, setCapture] = useState<0 | 1 | null>(null);
  const captureRef = useRef<HTMLButtonElement>(null);
  return (
    <section aria-labelledby="setup-h">
      <h2 id="setup-h" tabIndex={-1}>
        Setup
      </h2>
      <p>
        Choose how the participant will use the tasks. Everything here can be changed later. The browser cannot tell which device produced an input
        (for example eye gaze or a BCI that works through the computer&apos;s pointer), so please declare it below.
      </p>
      <div className="notice" data-scan-row={0}>
        <Toggle
          id="toggle-ui-scanning"
          label="Switch scanning for this app"
          value={s.uiScanning}
          onChange={(v) => update({ uiScanning: v })}
          hint={`When on, a highlight moves through the controls; press switch 1 (${s.switch.keys[0]}) to choose the highlighted control. With one switch, pressing the switch also starts the scan.`}
        />
      </div>
      <div className="grid2">
        <div>
          <fieldset data-scan-row={1}>
            <legend>Participant</legend>
            <label htmlFor="pcode">Study code (optional, pseudonymous – never a name)</label>
            <input id="pcode" type="text" autoComplete="off" value={s.participantCode} onChange={(e) => update({ participantCode: e.target.value.slice(0, 40) })} style={{ width: "100%" }} />
          </fieldset>
          <Choice row={2} legend="Input the participant uses (declared)" value={s.modality} options={MODALITY_LABELS} onChange={(v) => update({ modality: v })} />
          <Choice row={3} legend="Selection method" value={s.selection} options={SELECTION_LABELS} onChange={(v) => update({ selection: v })} />
        </div>
        <div>
          <fieldset data-scan-row={4}>
            <legend>Dwell</legend>
            <Stepper label="Dwell time" value={s.dwellMs} min={200} max={4000} step={100} unit="ms" onChange={(v) => update({ dwellMs: v })} />
            <p className="muted">A ring fills while the pointer rests on an item; leaving the item resets it.</p>
          </fieldset>
          <fieldset data-scan-row={5}>
            <legend>Switch scanning</legend>
            <Choice legend="Number of switches" value={s.switch.switches} options={[[1, "One switch"], [2, "Two switches"]]} onChange={(v) => update({ switch: { ...s.switch, switches: v as 1 | 2, mode: v === 1 ? "auto" : s.switch.mode } })} />
            <Choice
              legend="Scan mode"
              value={s.switch.mode}
              options={[["auto", "Automatic scan"], ["step", "Step scan (switch 1 moves, switch 2 selects)"]]}
              onChange={(v) => update({ switch: { ...s.switch, mode: v as "auto" | "step", switches: v === "step" ? 2 : s.switch.switches } })}
            />
            <Stepper label="Scan interval" value={s.switch.rateMs} min={300} max={5000} step={100} unit="ms" onChange={(v) => update({ switch: { ...s.switch, rateMs: v } })} />
            <Stepper label="Stop after this many cycles without a choice (0 = never)" value={s.switch.maxCycles} min={0} max={10} step={1} onChange={(v) => update({ switch: { ...s.switch, maxCycles: v } })} />
            <Choice legend="After a choice, scanning restarts" value={s.switch.restart} options={[["first", "From the first item"], ["continue", "From the chosen item"]]} onChange={(v) => update({ switch: { ...s.switch, restart: v as "first" | "continue" } })} />
            <Toggle label="Row-column scanning for grids and keyboards" value={s.switch.rowColumn} onChange={(v) => update({ switch: { ...s.switch, rowColumn: v } })} />
            <div className="row">
              {[0, 1].map((k) => (
                <button
                  key={k}
                  ref={k === capture ? captureRef : undefined}
                  type="button"
                  data-scan-skip={capture !== null ? "" : undefined}
                  onClick={() => setCapture(k as 0 | 1)}
                  onKeyDown={(e) => {
                    if (capture !== k) return;
                    e.preventDefault();
                    e.stopPropagation();
                    const keys: [string, string] = [...s.switch.keys] as [string, string];
                    keys[k] = e.code || e.key;
                    update({ switch: { ...s.switch, keys } });
                    setCapture(null);
                  }}
                >
                  {capture === k ? `Press the key for switch ${k + 1} now…` : `Switch ${k + 1} key: ${s.switch.keys[k]} (change)`}
                </button>
              ))}
            </div>
            <p className="muted">Switch interfaces usually send Space or Enter. Changing a key needs a keyboard or the switch itself.</p>
          </fieldset>
        </div>
        <div>
          <fieldset data-scan-row={6}>
            <legend>Timing</legend>
            <Toggle
              id="toggle-no-time-pressure"
              label="No time pressure"
              value={s.noTimePressure}
              onChange={(v) => update({ noTimePressure: v })}
              hint="On by default: tasks have no time limits and the time-constrained task (A5) is not offered (WCAG 2.2.1)."
            />
            {!s.noTimePressure && <Stepper label="Time limit multiplier" value={s.timeMultiplier} min={1} max={10} step={0.5} format={(v) => `× ${v}`} onChange={(v) => update({ timeMultiplier: v })} />}
            <Toggle label="Short practice version" value={s.short} onChange={(v) => update({ short: v })} hint="Fewer trials per task; for practice and demonstrations." />
          </fieldset>
          <fieldset data-scan-row={7}>
            <legend>Display</legend>
            <Choice legend="Theme" value={s.theme} options={[["system", "Follow system"], ["light", "Light"], ["dark", "Dark"], ["contrast", "High contrast"]]} onChange={(v) => update({ theme: v })} />
            <Stepper label="Text size" value={s.textScale} min={1} max={2} step={0.1} format={(v) => `${Math.round(v * 100)} %`} onChange={(v) => update({ textScale: v })} />
            <Choice legend="Motion" value={s.motion} options={[["system", "Follow system"], ["reduce", "Reduce motion"], ["full", "Full motion"]]} onChange={(v) => update({ motion: v })} />
            <Choice legend="Smallest target in task A2" value={s.targetMinPx} options={[[0, "All sizes"], [64, "64 px and larger"], [96, "96 px only"]]} onChange={(v) => update({ targetMinPx: v })} />
          </fieldset>
        </div>
      </div>
      <div className="row" data-scan-row={8}>
        <a className="button primary" href="#/tasks" id="go-tasks">
          Continue to tasks
        </a>
        <button type="button" onClick={reset}>
          Restore default settings
        </button>
      </div>
    </section>
  );
}

// ----------------------------------------------------------------------------- task list
function TaskList({ settings }: { settings: Settings }) {
  const [man, setMan] = useState<Manifest | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    loadManifest().then(setMan, (e) => setErr(String(e)));
  }, []);
  return (
    <section aria-labelledby="tasks-h">
      <h2 id="tasks-h" tabIndex={-1}>
        Tasks
      </h2>
      <p>
        Selection method: <strong>{SELECTION_LABELS.find(([k]) => k === settings.selection)?.[1]}</strong>. Declared input:{" "}
        <strong>{MODALITY_LABELS.find(([k]) => k === settings.modality)?.[1]}</strong>. <a href="#/setup">Change in Setup</a>.
      </p>
      <p className="notice">Battery tasks are experimental and are not validated clinical outcome assessments. You can pause at any time.</p>
      {err && <p className="warn" role="alert">Could not load the task battery: {err}</p>}
      {!man && !err && <p role="status">Loading tasks…</p>}
      {man && (
        <ul className="task-list">
          {man.tasks
            .filter((t) => IMPLEMENTED.includes(t.id))
            .map((t, i) => {
              const blocked = t.id === "A5" && settings.noTimePressure;
              const reasonId = `reason-${t.id}`;
              return (
                <li key={t.id} data-scan-row={Math.floor(i / 3)}>
                  <h3>
                    {t.id}: {t.name}
                  </h3>
                  <p className="muted" style={{ margin: "0 0 8px" }}>
                    {t.construct}
                  </p>
                  {blocked && (
                    <p id={reasonId} className="muted">
                      Not offered while &ldquo;No time pressure&rdquo; is on (Setup → Timing).
                    </p>
                  )}
                  {blocked ? (
                    <button type="button" disabled aria-describedby={reasonId}>
                      Start {t.id}
                    </button>
                  ) : (
                    <a className="button primary" id={`start-${t.id}`} href={`#/run/${t.id}`}>
                      Start {t.id}
                    </a>
                  )}
                </li>
              );
            })}
        </ul>
      )}
    </section>
  );
}

// ----------------------------------------------------------------------------- run
function RunScreen({ id, params, settings, onDone }: { id: string; params: URLSearchParams; settings: Settings; onDone: (r: TaskRun) => void }) {
  const [stim, setStim] = useState<Stimuli | null>(null);
  const [spec, setSpec] = useState<TaskSpec | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [started, setStarted] = useState(params.get("autostart") === "1");
  const limits: Limits = useMemo(() => {
    const g = (k: string) => (params.get(k) ? Number(params.get(k)) : undefined);
    return { trials: g("trials"), blocks: g("blocks"), n: g("n") };
  }, [params]);
  useEffect(() => {
    Promise.all([loadStimuli(id), loadManifest()]).then(
      ([s, m]) => {
        setStim(s);
        setSpec(m.tasks.find((t) => t.id === id) ?? null);
      },
      (e) => setErr(String(e)),
    );
  }, [id]);
  if (err) return <p className="warn" role="alert">Could not load task {id}: {err}</p>;
  if (!stim || !spec) return <p role="status">Loading task {id}…</p>;
  if (id === "A5" && settings.noTimePressure)
    return (
      <section>
        <h2 tabIndex={-1}>A5 is not available</h2>
        <p>The time-constrained task is switched off while &ldquo;No time pressure&rdquo; is on.</p>
        <a className="button" href="#/tasks">Back to tasks</a>
      </section>
    );
  if (!started)
    return (
      <section aria-labelledby="intro-h">
        <h2 id="intro-h" tabIndex={-1}>
          {spec.id}: {spec.name}
        </h2>
        <p>{spec.construct}</p>
        <p className="muted">{spec.timing}</p>
        <p className="muted">Accessibility: {spec.accessibility}</p>
        <p>You can pause at any time (Pause button or Escape key). Staff can record any help with &ldquo;Record assistance&rdquo;.</p>
        <div className="row">
          <button type="button" className="primary" id="begin-task" onClick={() => setStarted(true)}>
            Begin {spec.id}
          </button>
          <a className="button" href="#/tasks">
            Back to tasks
          </a>
        </div>
      </section>
    );
  return <TaskRunner key={`${id}-${stim.stimulus_hash}`} stim={stim} spec={spec} settings={settings} limits={limits} onDone={onDone} />;
}

// ----------------------------------------------------------------------------- results
function ResultsScreen({ runs }: { runs: TaskRun[] }) {
  const [server, setServer] = useState<boolean | null>(null);
  const [pid, setPid] = useState("");
  const [user, setUser] = useState("");
  const [pw, setPw] = useState("");
  const [msg, setMsg] = useState<string>("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    serverAvailable().then(setServer);
  }, []);
  const upload = async () => {
    setBusy(true);
    setMsg("Uploading…");
    try {
      const token = await login(user, pw);
      const out: string[] = [];
      for (const r of runs) {
        const res = await uploadRun(r, pid, token);
        out.push(`${r.task_id}: stored as ${String(res.id ?? res.session_id ?? "session")}`);
      }
      setMsg(`Uploaded ${runs.length} session(s). Authoritative scores were computed on the server. ${out.join("; ")}`);
    } catch (e) {
      setMsg(`Upload failed: ${(e as Error).message}. Nothing was lost: the sessions are still here and can be downloaded as JSON.`);
    } finally {
      setPw("");
      setBusy(false);
    }
  };
  return (
    <section aria-labelledby="res-h">
      <h2 id="res-h" tabIndex={-1}>
        Results and export
      </h2>
      <p className="provisional">
        <strong>Provisional — authoritative scoring is server-side.</strong> Numbers shown here are computed in the browser for immediate feedback only.
      </p>
      {!runs.length && <p>No tasks have been completed in this browser session yet.</p>}
      {runs.map((r) => (
        <article key={r.session_id} className="stack" style={{ marginBottom: 24 }} data-run={r.task_id}>
          <h3>
            {r.task_id} {r.completed ? "(completed)" : "(stopped early – incomplete)"}
          </h3>
          {r.provisional && (
            <table>
              <caption>Provisional results for {r.task_id}</caption>
              <tbody>
                {r.provisional.rows.map(([k, v]) => (
                  <tr key={k}>
                    <th scope="row">{k}</th>
                    <td>{v}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <p className="muted">
            {r.events.length} events · stimulus {r.stimulus_hash} · declared input {r.modality} · non-monotonic {r.stream_report.non_monotonic} ·
            sequence gaps {r.stream_report.seq_gaps} · duplicates {r.stream_report.duplicate_seq}
          </p>
          <div className="row">
            <button type="button" onClick={() => downloadJson(`neurometric_${r.task_id}_${r.session_id}.json`, r)}>
              Download {r.task_id} session (JSON)
            </button>
          </div>
        </article>
      ))}
      {runs.length > 0 && (
        <>
          <div className="row">
            <button type="button" className="primary" onClick={() => downloadJson(`neurometric_sessions_${Date.now()}.json`, { format: "neurometric.web-export/1", runs })}>
              Download all sessions (JSON)
            </button>
          </div>
          <h3>Upload to the study server</h3>
          {server === null && <p role="status">Checking for a study server…</p>}
          {server === false && (
            <p className="notice" role="status">
              No study server is available at this address. The sessions are saved in this browser; download the JSON file and give it to the study team.
            </p>
          )}
          {server && (
            <form
              className="stack"
              onSubmit={(e) => {
                e.preventDefault();
                void upload();
              }}
            >
              <div>
                <label htmlFor="up-pid">Participant ID (from the study system)</label>
                <br />
                <input id="up-pid" type="text" autoComplete="off" required value={pid} onChange={(e) => setPid(e.target.value)} />
              </div>
              <div>
                <label htmlFor="up-user">Staff username</label>
                <br />
                <input id="up-user" type="text" autoComplete="username" required value={user} onChange={(e) => setUser(e.target.value)} />
              </div>
              <div>
                <label htmlFor="up-pw">Password</label>
                <br />
                <input id="up-pw" type="password" autoComplete="current-password" required value={pw} onChange={(e) => setPw(e.target.value)} style={{ font: "inherit", minHeight: 44 }} />
              </div>
              <button type="submit" className="primary" disabled={busy}>
                Upload {runs.length} session(s)
              </button>
            </form>
          )}
          <p role="status" aria-live="polite">
            {msg}
          </p>
        </>
      )}
      <p>
        <a className="button" href="#/tasks">
          Back to tasks
        </a>
      </p>
    </section>
  );
}
