// Compatibility (Milestone 5, workstream F): the registry of integrations, the validation
// level each has reached and the evidence for it, read from GET /compatibility. Read-only:
// levels are derived from evidence by `make compat`; nothing here can change them.

import { useCallback, useEffect, useState } from "react";
import { KIND_TEXT, compatApi, evidenceText, levelText, liveText, type CompatEntry, type CompatRegistry, type CompatibilityResponse } from "../compat";
import { errorText } from "../hooks";

function Evidence({ entry }: { entry: CompatEntry }) {
  if (!entry.evidence.length) return <span className="hint">None in this build</span>;
  return (
    <ul className="compat-list">
      {entry.evidence.map((e) => (
        <li key={`${e.type}:${e.path}`} title={e.description}>
          <code>{e.path}</code>
          <div className="hint">{evidenceText(e)}</div>
          {!e.counted && e.note && <div className="caution-text">Not counted: {e.note}</div>}
        </li>
      ))}
    </ul>
  );
}

function Row({ entry, registry, data }: { entry: CompatEntry; registry: CompatRegistry; data: CompatibilityResponse }) {
  const live = data.live[entry.id];
  return (
    <tr data-testid={`compat-${entry.id}`}>
      <td>
        <div>{entry.display_name}</div>
        <div className="hint">
          {entry.package} {entry.version} · {entry.protocol}
        </div>
        <div className={live?.state === "different_version" ? "caution-text" : "hint"} data-testid={`compat-live-${entry.id}`}>
          This installation: {liveText(live)}
        </div>
      </td>
      <td className="nowrap">{KIND_TEXT[entry.kind]}</td>
      <td title={entry.level_basis.join("\n")}>
        <div data-testid={`compat-level-${entry.id}`}>{levelText(entry, registry)}</div>
        {entry.real_data_replay && <div className="hint">Real-data replay (recorded data, not live)</div>}
        {entry.synthetic_only && <div className="hint">Synthetic data only</div>}
      </td>
      <td className="compat-evidence">
        <Evidence entry={entry} />
      </td>
      <td>
        {entry.not_tested.length ? (
          <ul className="compat-list">
            {entry.not_tested.map((t) => (
              <li key={t}>{t}</li>
            ))}
          </ul>
        ) : (
          <span className="hint">—</span>
        )}
      </td>
    </tr>
  );
}

export function CompatibilityView() {
  const [data, setData] = useState<CompatibilityResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    compatApi
      .get()
      .then((r) => {
        setData(r);
        setError(null);
      })
      .catch((e: unknown) => setError(errorText(e)));
  }, []);
  useEffect(load, [load]);

  if (error) return <p className="error-text">{error}</p>;
  if (!data) return <p className="value-muted">Loading the compatibility registry…</p>;
  const reg = data.registry;
  return (
    <div className="compat" data-testid="compat-view">
      <div className="btn-row">
        <p className="hint">
          Which integrations exist and the validation level each has reached, derived from the listed evidence by{" "}
          <code>make compat</code>. Read from <code>compat/{data.source}</code>; this page cannot change a level.
        </p>
        <button type="button" className="btn btn-small" onClick={load}>
          Reload
        </button>
      </div>
      {!data.available || !reg ? (
        <p className="value-muted" data-testid="compat-unavailable">
          {data.error ?? "No compatibility registry."} Generate it with <code>make compat</code>.
        </p>
      ) : (
        <>
          <p className="hint" data-testid="compat-notice">
            {reg.notice}
          </p>
          <div className="table-scroll">
            <table className="table compat-table">
              <thead>
                <tr>
                  <th>Integration</th>
                  <th>Kind</th>
                  <th>Level</th>
                  <th>Evidence</th>
                  <th>Not tested</th>
                </tr>
              </thead>
              <tbody>
                {reg.entries.map((e) => (
                  <Row key={e.id} entry={e} registry={reg} data={data} />
                ))}
              </tbody>
            </table>
          </div>
          <p className="hint">
            Levels as defined in <code>{reg.sources.validation_levels}</code>. Evidence for Concord {reg.concord_version}
            {data.concord_version !== reg.concord_version ? `; this server runs Concord ${data.concord_version}` : ""}.
          </p>
        </>
      )}
    </div>
  );
}
