// The session log column: the latest entries, newest first, with "Show all".

import { useState } from "react";
import { clock, type LogEntry } from "../sessionLog";
import { Dot } from "./ui";

export const LOG_PREVIEW = 8;

export function SessionLogView({ entries }: { entries: LogEntry[] }) {
  const [all, setAll] = useState(false);
  const shown = all ? entries : entries.slice(0, LOG_PREVIEW);
  return (
    <section className="log" aria-labelledby="session-log-h" data-testid="session-log">
      <h2 id="session-log-h">Session log</h2>
      <p className="explain">What happened, newest first.</p>
      {entries.length === 0 ? (
        <p className="value-muted">Nothing yet.</p>
      ) : (
        <ol className="log-list">
          {shown.map((e) => (
            <li key={e.id} className="log-entry" data-tone={e.tone}>
              <time className="num" dateTime={new Date(e.at).toISOString()}>
                {clock(e.at)}
              </time>
              <Dot tone={e.tone} />
              <span className="log-text">{e.text}</span>
            </li>
          ))}
        </ol>
      )}
      {entries.length > LOG_PREVIEW && (
        <button type="button" className="btn btn-quiet" onClick={() => setAll((a) => !a)} data-testid="log-toggle">
          {all ? "Show latest only" : `Show all (${entries.length})`}
        </button>
      )}
    </section>
  );
}
