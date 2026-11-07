// LSL discovery and source registration. Discovery only lists streams on the network;
// BrainOS opens read-only inlets when a registered source is connected.

import { useEffect, useState } from "react";
import { labApi, type LSLDiscovery, type LSLStreamInfo } from "../api";
import { useLog, useLoggedAction } from "../context";
import { fmt } from "./ui";

function declared(s: LSLStreamInfo): string {
  const parts: string[] = [];
  if (s.declared_prerecorded) parts.push("prerecorded");
  if (s.declared_synthetic) parts.push("synthetic");
  if (parts.length) return parts.join(" + ");
  if (s.declared_prerecorded === false || s.declared_synthetic === false) return "declared neither";
  return "no declaration";
}

function units(s: LSLStreamInfo): string {
  if (!s.channels_described) return "channels not described";
  const u = s.units.map((x) => x ?? "none");
  return u.length ? [...new Set(u)].join(", ") : "—";
}

const streamLabel = (s: LSLStreamInfo) => `${s.name} (${s.type}, ${s.channel_count} ch)`;

export function LslSources({ onSourcesChanged }: { onSourcesChanged: () => void }) {
  const log = useLog();
  const [disc, setDisc] = useState<LSLDiscovery | null>(null);
  const [signal, setSignal] = useState<string | null>(null);
  const [behavior, setBehavior] = useState("");
  const [markers, setMarkers] = useState("");
  const action = useLoggedAction();

  useEffect(() => {
    labApi
      .lslStreams()
      .then(setDisc)
      .catch(() => setDisc(null));
  }, []);

  const discover = async () => {
    const d = await action.run(() => labApi.lslDiscover(1.5));
    if (!d) return;
    setDisc(d);
    if (signal && !d.streams.some((s) => s.key === signal)) setSignal(null);
    onSourcesChanged(); // discovery offers every usable signal stream as a source
  };

  const register = async () => {
    if (!signal) return;
    const desc = await action.run(() => labApi.lslRegister(signal, behavior || null, markers || null));
    if (!desc) return;
    log("info", `Registered ${desc.display_name ?? desc.device_id}`);
    setSignal(null);
    onSourcesChanged();
  };

  const streams = disc?.streams ?? [];
  const sig = streams.find((s) => s.key === signal) ?? null;
  const others = streams.filter((s) => s.key !== signal);

  return (
    <div className="subsection" data-testid="lsl-sources">
      <div className="btn-row">
        <button type="button" className="btn" disabled={action.busy} onClick={discover} data-testid="lsl-discover">
          {action.busy ? "Searching…" : "Search the network"}
        </button>
        <span className="hint">
          {disc?.discovered_at_ns
            ? `Last search ${fmt.ago(disc.discovered_at_ns)} · ${streams.length} stream${streams.length === 1 ? "" : "s"}`
            : "Not searched yet"}
        </span>
      </div>
      {disc?.error && <p className="error-text">{disc.error}</p>}
      {action.error && (
        <p className="error-text" data-testid="lsl-error">
          {action.error}
        </p>
      )}

      {streams.length > 0 && (
        <div className="table-scroll">
          <table className="table" data-testid="lsl-streams">
            <thead>
              <tr>
                <th>Stream</th>
                <th className="r">Channels</th>
                <th className="r">Rate</th>
                <th>Units</th>
                <th>Declared</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {streams.map((s) => (
                <tr
                  key={s.key}
                  data-stream-key={s.key}
                  title={`key ${s.key} · host ${s.hostname} · source_id ${s.source_id ?? "not set"} · ${s.channel_format}`}
                >
                  <td>
                    <div>{s.name}</div>
                    <div className="hint">{s.type}</div>
                  </td>
                  <td className="r num">{s.channel_count}</td>
                  <td className="r num">{s.nominal_srate > 0 ? `${fmt.num(s.nominal_srate)} Hz` : "irregular"}</td>
                  <td>{units(s)}</td>
                  <td>{declared(s)}</td>
                  <td className="r">
                    {s.usable_as_signal ? (
                      <button
                        type="button"
                        className={`btn btn-small ${signal === s.key ? "btn-primary" : ""}`}
                        aria-pressed={signal === s.key}
                        onClick={() => setSignal(signal === s.key ? null : s.key)}
                        data-testid={`lsl-use-${s.key}`}
                      >
                        Use
                      </button>
                    ) : (
                      <span className="hint">{s.reason ?? "not usable"}</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {disc && !streams.length && !disc.error && disc.discovered_at_ns && (
        <p className="value-muted">No LSL streams found on the network.</p>
      )}

      {sig && (
        <div className="subform" data-testid="lsl-configure">
          <p>
            Signal: <b>{streamLabel(sig)}</b>
          </p>
          <div className="form-grid">
            <label>
              Behavior stream (optional)
              <select value={behavior} onChange={(e) => setBehavior(e.target.value)} data-testid="lsl-behavior">
                <option value="">None</option>
                {others.map((s) => (
                  <option key={s.key} value={s.key}>
                    {streamLabel(s)}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Marker stream (optional)
              <select value={markers} onChange={(e) => setMarkers(e.target.value)} data-testid="lsl-markers">
                <option value="">None</option>
                {others.map((s) => (
                  <option key={s.key} value={s.key}>
                    {streamLabel(s)}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <div className="btn-row">
            <button type="button" className="btn btn-primary" disabled={action.busy} onClick={register} data-testid="lsl-register">
              Add source
            </button>
          </div>
        </div>
      )}
      <p className="hint">
        A behavior stream provides calibration labels. Streams their publisher declares prerecorded or synthetic are
        labelled so; any other stream is shown as a live stream of unverified origin, because LSL cannot tell hardware
        from playback.
      </p>
    </div>
  );
}
