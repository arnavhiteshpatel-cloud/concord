// Milestone 5 (D), Advanced → Stored data: what is on disk, the retention policy, and deletion of
// recordings, decoder models and research sessions (each with a confirmation step). The server
// also requires the name as confirmation, and refuses items in use.

import { useCallback, useEffect, useState } from "react";
import { consoleApi, labApi, type ModelInfo, type RecordingInfo } from "../api";
import { useLog, useLoggedAction } from "../context";
import { researchApi, type ResearchSession, type StorageStatus } from "../researchApi";
import { fmt } from "./ui";

const KINDS = ["recordings", "models", "sessions", "exports"] as const;

export function retentionText(r: Record<string, number | null> | undefined): string {
  const set = Object.entries(r ?? {}).filter(([, v]) => v !== null && v !== undefined);
  if (!set.length) return "No retention policy: data is kept until you delete it ([retention] in the config file).";
  return `Retention policy (config file, applied at startup): ${set
    .map(([k, v]) => `${k.replace("_days", "")} ${v} days`)
    .join(", ")}.`;
}

/** A Delete button that asks once more, inline, before calling `onDelete`. */
export function DeleteButton({
  testId,
  what,
  busy,
  onDelete,
}: {
  testId: string;
  what: string;
  busy: boolean;
  onDelete: () => void;
}) {
  const [asking, setAsking] = useState(false);
  if (!asking)
    return (
      <button type="button" className="btn btn-small" disabled={busy} onClick={() => setAsking(true)} data-testid={testId}>
        Delete
      </button>
    );
  return (
    <span className="confirm" data-testid={`${testId}-ask`}>
      Delete {what} permanently?{" "}
      <button
        type="button"
        className="btn btn-small btn-danger"
        disabled={busy}
        onClick={() => {
          setAsking(false);
          onDelete();
        }}
        data-testid={`${testId}-confirm`}
      >
        Delete
      </button>{" "}
      <button type="button" className="btn btn-small" onClick={() => setAsking(false)}>
        Cancel
      </button>
    </span>
  );
}

export function StoredData({ onChanged }: { onChanged: () => void }) {
  const log = useLog();
  const action = useLoggedAction();
  const [storage, setStorage] = useState<StorageStatus | null>(null);
  const [recordings, setRecordings] = useState<RecordingInfo[]>([]);
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [sessions, setSessions] = useState<ResearchSession[]>([]);
  const [activeSession, setActiveSession] = useState<string | null>(null);
  const [withRecordings, setWithRecordings] = useState<Record<string, boolean>>({});

  const load = useCallback(() => {
    researchApi.storage().then(setStorage).catch(() => setStorage(null));
    consoleApi.recordings().then(setRecordings).catch(() => setRecordings([]));
    labApi.models().then(setModels).catch(() => setModels([]));
    researchApi
      .sessions()
      .then((s) => {
        setSessions(s.sessions);
        setActiveSession(s.active?.id ?? null);
      })
      .catch(() => setSessions([]));
  }, []);
  useEffect(load, [load]);

  const remove = async (label: string, fn: () => Promise<{ bytes: number; also_deleted: string[] }>) => {
    const r = await action.run(fn);
    if (r) {
      const also = r.also_deleted.length ? ` and ${r.also_deleted.length} recording(s)` : "";
      log("info", `Deleted ${label}${also} (${fmt.bytes(r.bytes)})`);
      load();
      onChanged();
    }
  };

  return (
    <div data-testid="stored-data">
      {storage && (
        <>
          <p className="hint">
            Data directory <code>{storage.data_dir}</code> (only your user can read it).
          </p>
          <div className="kpis">
            {KINDS.map((k) => (
              <div className="kpi" key={k} data-testid={`usage-${k}`}>
                <span className="kpi-label">{k}</span>
                <span className="kpi-value">
                  {storage.usage[k].count} · {fmt.bytes(storage.usage[k].bytes)}
                </span>
              </div>
            ))}
          </div>
          <p className="hint" data-testid="retention-policy">
            {retentionText(storage.retention)}
            {storage.last_retention
              ? ` At this start it deleted ${storage.last_retention.deleted.length} item(s)${
                  storage.last_retention.deleted.length
                    ? `: ${storage.last_retention.deleted.map((d) => `${d.kind} ${d.name}`).join(", ")}`
                    : ""
                }.`
              : ""}
          </p>
        </>
      )}
      {action.error && <p className="error-text">{action.error}</p>}

      <h3 className="minor stored-head">Recordings</h3>
      {recordings.length ? (
        <table className="table" data-testid="stored-recordings">
          <tbody>
            {recordings.map((r) => (
              <tr key={r.name}>
                <td>
                  {r.name}
                  {r.complete === false && (
                    <span className="hint" title={r.recovery?.reason} data-testid={`incomplete-${r.name}`}>
                      {" "}
                      · incomplete ({r.recovery?.valid_events ?? "?"} events kept)
                    </span>
                  )}
                </td>
                <td className="r num">{fmt.bytes(r.size_bytes)}</td>
                <td className="r">{r.active ? "recording" : fmt.ago(r.created_at_ns)}</td>
                <td className="r">
                  {!r.active && (
                    <DeleteButton
                      testId={`delete-recording-${r.name}`}
                      what={r.name}
                      busy={action.busy}
                      onDelete={() => remove(`recording ${r.name}`, () => researchApi.deleteRecording(r.name))}
                    />
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <p className="value-muted">No recordings.</p>
      )}

      <h3 className="minor stored-head">Decoder models</h3>
      <p className="hint" data-testid="model-trust">
        Models are loaded by Concord&apos;s decoders. Load only models from sources you trust; a model trained on another
        source is refused unless you override it, and the override is shown.
      </p>
      {models.length ? (
        <table className="table" data-testid="stored-models">
          <tbody>
            {models.map((m) => (
              <tr key={m.summary.model_id}>
                <td>{m.summary.model_id}</td>
                <td className="r">{m.summary.created_at ?? ""}</td>
                <td className="r">
                  <DeleteButton
                    testId={`delete-model-${m.summary.model_id}`}
                    what={m.summary.model_id}
                    busy={action.busy}
                    onDelete={() =>
                      remove(`model ${m.summary.model_id}`, () => researchApi.deleteModel(m.summary.model_id))
                    }
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <p className="value-muted">No models.</p>
      )}

      <h3 className="minor stored-head">Research sessions</h3>
      {sessions.length ? (
        <table className="table" data-testid="stored-sessions">
          <tbody>
            {sessions.map((s) => (
              <tr key={s.id}>
                <td>
                  {s.name} <span className="hint">({s.id})</span>
                </td>
                <td>{s.status}</td>
                <td className="r">{fmt.ago(s.created_at_ns)}</td>
                <td className="r">
                  {s.id !== activeSession && (
                    <>
                      {s.recordings.length > 0 && (
                        <label className="check">
                          <input
                            type="checkbox"
                            checked={!!withRecordings[s.id]}
                            onChange={(e) => setWithRecordings({ ...withRecordings, [s.id]: e.target.checked })}
                            data-testid={`delete-session-recordings-${s.id}`}
                          />
                          with its {s.recordings.length} recording(s)
                        </label>
                      )}{" "}
                      <DeleteButton
                        testId={`delete-session-${s.id}`}
                        what={`session ${s.name}`}
                        busy={action.busy}
                        onDelete={() =>
                          remove(`session ${s.name}`, () => researchApi.deleteSession(s.id, !!withRecordings[s.id]))
                        }
                      />
                    </>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <p className="value-muted">No research sessions.</p>
      )}
      <p className="hint">
        Deleting removes the files from the data directory. It does not erase copies elsewhere: exports you shared, backups
        or snapshots (docs/SECURITY.md).
      </p>
    </div>
  );
}
