// Milestone 5 (D): the research session strip above the rows — New session, session details and
// export, End session — and "Safe stop & disconnect" (command output off, recording closed,
// decoding stopped, source disconnected). Every control calls the runtime; nothing is local.

import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import type { RuntimeSnapshot } from "../../sdk";
import type { RecordingInfo } from "../api";
import { useLog, useLoggedAction } from "../context";
import {
  researchApi,
  safeStopText,
  type ExportInfo,
  type ResearchSession,
  type SessionDetail,
  type SessionLogEntry,
  type SessionsStatus,
} from "../researchApi";
import "../research.css";
import { Sheet, fmt } from "./ui";

/** Is anything running that a safe stop would stop? */
export function somethingRunning(runtime: RuntimeSnapshot | null, pipelineRunning: boolean, controlOn: boolean): boolean {
  const connected = !!runtime && runtime.state !== "idle";
  return connected || !!runtime?.recording || pipelineRunning || controlOn;
}

export function SessionBar({
  runtime,
  pipelineRunning,
  controlOn,
  recordings,
  onChanged,
}: {
  runtime: RuntimeSnapshot | null;
  pipelineRunning: boolean;
  controlOn: boolean;
  recordings: RecordingInfo[];
  /** refresh device / recording lists after a stop, export or end */
  onChanged: () => void;
}) {
  const log = useLog();
  const action = useLoggedAction();
  const [status, setStatus] = useState<SessionsStatus | null>(null);
  const [sheet, setSheet] = useState<"new" | "details" | null>(null);
  const refresh = useCallback(() => {
    researchApi
      .sessions()
      .then(setStatus)
      .catch(() => setStatus(null));
  }, []);
  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 5000);
    return () => clearInterval(t);
  }, [refresh]);

  // once: tell the operator about anything recovered after an unclean stop
  const told = useRef(false);
  useEffect(() => {
    if (told.current) return;
    told.current = true;
    researchApi
      .storage()
      .then((s) => {
        for (const name of s.recovered_recordings)
          log("caution", `Recording ${name} was interrupted when BrainOS stopped; its complete part was kept and marked incomplete`);
        for (const id of s.interrupted_sessions) log("caution", `Research session ${id} was interrupted when BrainOS stopped`);
      })
      .catch(() => {});
  }, [log]);

  const active = status?.active ?? null;
  const running = somethingRunning(runtime, pipelineRunning, controlOn);

  const safeStop = async () => {
    const r = await action.run(researchApi.safeStop);
    if (r) {
      log(r.ok ? "info" : "caution", safeStopText(r));
      onChanged();
      refresh();
    }
  };

  return (
    <section className="session-bar" aria-label="Research session" data-testid="session-bar">
      <div className="session-bar-text">
        {active ? (
          <>
            <span className="session-bar-label">Research session</span>
            <span className="session-bar-name" data-testid="session-name">
              {active.name}
            </span>
            <span className="hint" data-testid="session-summary">
              {[
                active.operator,
                `started ${fmt.time(active.created_at_ns)}`,
                `${active.recordings.length} recording${active.recordings.length === 1 ? "" : "s"}`,
                `${active.models.length} model${active.models.length === 1 ? "" : "s"}`,
              ]
                .filter(Boolean)
                .join(" · ")}
            </span>
          </>
        ) : (
          <span className="value-muted" data-testid="no-session">
            No research session. A session groups recordings, decoders and a log, and can be exported for reproduction.
          </span>
        )}
      </div>
      <div className="session-bar-actions">
        {active ? (
          <button type="button" className="btn btn-small" onClick={() => setSheet("details")} data-testid="session-details">
            Session and export…
          </button>
        ) : (
          <button type="button" className="btn btn-small" onClick={() => setSheet("new")} data-testid="new-session">
            New session
          </button>
        )}
        <button
          type="button"
          className="btn btn-small btn-danger"
          disabled={action.busy || !running}
          title={
            running
              ? "Turn command output off, close the recording, stop decoding and disconnect the source"
              : "Nothing is running"
          }
          onClick={safeStop}
          data-testid="safe-stop"
        >
          Safe stop &amp; disconnect
        </button>
      </div>
      {action.error && <p className="error-text session-bar-error">{action.error}</p>}
      {sheet === "new" && (
        <NewSessionSheet
          onClose={() => setSheet(null)}
          onCreated={(s) => {
            log("info", `Research session started: ${s.name}`);
            setSheet(null);
            refresh();
          }}
        />
      )}
      {sheet === "details" && active && (
        <SessionSheet
          session={active}
          recordings={recordings}
          onClose={() => setSheet(null)}
          onEnded={() => {
            setSheet(null);
            onChanged();
            refresh();
          }}
        />
      )}
    </section>
  );
}

function NewSessionSheet({ onClose, onCreated }: { onClose: () => void; onCreated: (s: ResearchSession) => void }) {
  const action = useLoggedAction();
  const [name, setName] = useState("");
  const [operator, setOperator] = useState("");
  const [notes, setNotes] = useState("");
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const s = await action.run(() => researchApi.createSession(name.trim(), operator.trim() || null, notes.trim() || null));
    if (s) onCreated(s);
  };
  return (
    <Sheet title="New research session" onClose={onClose} testId="new-session-sheet">
      <form onSubmit={submit}>
        <p className="explain">
          Creates a session folder in the data directory. While the session is active, BrainOS logs source changes,
          decoding and control settings, recordings and calibrations into it.
        </p>
        <div className="form-grid">
          <label className="span-all">
            Session name
            <input
              required
              maxLength={80}
              value={name}
              onChange={(e) => setName(e.target.value)}
              data-testid="session-name-input"
            />
          </label>
          <label className="span-all">
            Operator (optional)
            <input maxLength={80} value={operator} onChange={(e) => setOperator(e.target.value)} data-testid="session-operator-input" />
          </label>
          <label className="span-all">
            Notes (optional)
            <textarea
              maxLength={4000}
              rows={5}
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              data-testid="session-notes-input"
            />
          </label>
        </div>
        <p className="hint">
          The operator name and notes stay in this session&apos;s folder: they are never written to logs or support reports,
          and an export includes them only if you choose so. Do not enter participant identifiers.
        </p>
        <div className="btn-row sheet-actions">
          <button type="submit" className="btn btn-primary" disabled={action.busy || !name.trim()} data-testid="session-create">
            Start session
          </button>
        </div>
        {action.error && <p className="error-text">{action.error}</p>}
      </form>
    </Sheet>
  );
}

const ENTRY_WORDS: Record<string, string> = {
  session_created: "Session started",
  session_closed: "Session ended",
  calibration: "Decoder calibrated",
  safe_stop: "Safe stop",
  export: "Exported",
  recording_started: "Recording started",
  recording_stopped: "Recording stopped",
  recording_deleted: "Recording deleted",
};

export function entryText(e: SessionLogEntry): string {
  if (e.kind === "device_status") return `Source ${String(e.device_id ?? "")}: ${String(e.state ?? "")}`;
  if (e.kind === "operator_action") {
    const what = (e.action as string | undefined) ?? `${String(e.method)} ${String(e.path)}`;
    const failed = e.status !== undefined && (e.status < 200 || e.status >= 300);
    return `${what.replace(/_/g, " ")}${failed ? ` (refused ${e.status})` : ""}`;
  }
  const head = ENTRY_WORDS[e.kind] ?? e.kind.replace(/_/g, " ");
  const subject = (e.recording as string | undefined) ?? (e.model_id as string | undefined) ?? (e.file as string | undefined);
  return subject ? `${head}: ${subject}` : head;
}

function SessionSheet({
  session,
  recordings,
  onClose,
  onEnded,
}: {
  session: ResearchSession;
  recordings: RecordingInfo[];
  onClose: () => void;
  onEnded: () => void;
}) {
  const log = useLog();
  const action = useLoggedAction();
  const [detail, setDetail] = useState<SessionDetail | null>(null);
  const [withRecordings, setWithRecordings] = useState(false);
  const [withPersonal, setWithPersonal] = useState(false);
  const [result, setResult] = useState<ExportInfo | null>(null);
  const [confirmEnd, setConfirmEnd] = useState(false);
  const load = useCallback(() => {
    researchApi
      .session(session.id)
      .then(setDetail)
      .catch(() => setDetail(null));
  }, [session.id]);
  useEffect(load, [load]);

  const own = recordings.filter((r) => session.recordings.includes(r.name));
  const bytes = own.reduce((n, r) => n + r.size_bytes, 0);
  const exportBundle = async () => {
    const r = await action.run(() =>
      researchApi.exportSession(session.id, { include_recordings: withRecordings, include_personal: withPersonal }),
    );
    if (r) {
      setResult(r);
      log("info", `Session exported: ${r.file}`);
      load();
    }
  };
  const end = async () => {
    const r = await action.run(() => researchApi.closeSession(session.id));
    if (r) {
      if (r.safe_stop) log(r.safe_stop.ok ? "info" : "caution", safeStopText(r.safe_stop));
      log("info", `Research session ended: ${r.session.name}`);
      onEnded();
    }
  };

  return (
    <Sheet title={`Session · ${session.name}`} onClose={onClose} testId="session-sheet">
      <section className="group">
        <dl className="kv">
          <dt>Session id</dt>
          <dd data-testid="session-id">{session.id}</dd>
          <dt>Started</dt>
          <dd>{new Date(session.created_at_ns / 1e6).toLocaleString()}</dd>
          {session.operator && (
            <>
              <dt>Operator</dt>
              <dd>{session.operator}</dd>
            </>
          )}
          {session.notes && (
            <>
              <dt>Notes</dt>
              <dd className="session-notes">{session.notes}</dd>
            </>
          )}
          <dt>Recordings</dt>
          <dd data-testid="session-recordings">
            {session.recordings.length
              ? session.recordings
                  .map((n) => {
                    const r = recordings.find((x) => x.name === n);
                    return r ? `${n} (${fmt.bytes(r.size_bytes)}${r.complete === false ? ", incomplete" : ""})` : `${n} (deleted)`;
                  })
                  .join(", ")
              : "none yet"}
          </dd>
          <dt>Decoder models</dt>
          <dd>{session.models.join(", ") || "none yet"}</dd>
        </dl>
      </section>
      <section className="group" data-testid="session-export">
        <h3>Export for reproduction</h3>
        <p className="explain">
          A zip with the session log, versions and package fingerprints, sources, pipeline settings, decoder models with
          their calibration reports, and a REPRODUCE.md. <code>brainos reproduce &lt;file&gt;</code> verifies it and re-runs
          the evaluation.
        </p>
        <label className="check">
          <input
            type="checkbox"
            checked={withRecordings}
            onChange={(e) => setWithRecordings(e.target.checked)}
            data-testid="export-recordings"
          />
          Include the session&apos;s recordings ({own.length}, {fmt.bytes(bytes)}) — neural data; needed to re-run the
          evaluation
        </label>
        <label className="check">
          <input
            type="checkbox"
            checked={withPersonal}
            onChange={(e) => setWithPersonal(e.target.checked)}
            data-testid="export-personal"
          />
          Include the operator name and notes
        </label>
        <div className="btn-row">
          <button type="button" className="btn btn-primary" disabled={action.busy} onClick={exportBundle} data-testid="export-create">
            Create export bundle
          </button>
        </div>
        {result && (
          <div className="subform" data-testid="export-result">
            <p>
              <a href={researchApi.exportUrl(session.id, result.file)} download={result.file} data-testid="export-download">
                {result.file}
              </a>{" "}
              · {fmt.bytes(result.size_bytes)} · {result.files} files
            </p>
            <p className="hint">
              SHA-256 <code className="export-hash">{result.sha256}</code>
            </p>
            <p className="hint">
              Recordings included: {result.included_recordings.join(", ") || "none"}
              {result.omitted_recordings.length ? ` · listed by hash only: ${result.omitted_recordings.join(", ")}` : ""}
            </p>
          </div>
        )}
        {detail && detail.exports.length > 0 && (
          <ul className="pick-list export-list" data-testid="export-list">
            {detail.exports.map((x) => (
              <li key={x.file} className="pick">
                <a href={researchApi.exportUrl(session.id, x.file)} download={x.file}>
                  {x.file}
                </a>
                <span className="hint">{fmt.bytes(x.size_bytes)}</span>
              </li>
            ))}
          </ul>
        )}
      </section>
      <section className="group">
        <h3>Session log</h3>
        {detail ? (
          <ol className="session-entries" data-testid="session-entries">
            {detail.log.slice(-12).map((e, i) => (
              <li key={`${e.at_ns}-${i}`}>
                <span className="hint mono">{fmt.time(e.at_ns)}</span> {entryText(e)}
              </li>
            ))}
          </ol>
        ) : (
          <p className="value-muted">Loading…</p>
        )}
        {detail && <p className="hint">{detail.log_total} entries in the session folder.</p>}
      </section>
      <section className="group">
        <h3>End session</h3>
        <p className="explain">Ending turns command output off, closes any recording, stops decoding and disconnects the source.</p>
        {confirmEnd ? (
          <div className="btn-row">
            <button type="button" className="btn btn-danger" disabled={action.busy} onClick={end} data-testid="session-end-confirm">
              End session now
            </button>
            <button type="button" className="btn" onClick={() => setConfirmEnd(false)}>
              Cancel
            </button>
          </div>
        ) : (
          <div className="btn-row">
            <button type="button" className="btn" onClick={() => setConfirmEnd(true)} data-testid="session-end">
              End session…
            </button>
          </div>
        )}
      </section>
      {action.error && <p className="error-text">{action.error}</p>}
    </Sheet>
  );
}
