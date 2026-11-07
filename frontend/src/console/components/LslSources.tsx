// LSL discovery and source registration. Discovery only lists streams on the network;
// BrainOS opens read-only inlets when a registered source is connected.

import { useEffect, useState } from "react";
import { labApi, type LSLDiscovery, type LSLStreamInfo } from "../api";
import { useAction } from "../hooks";
import { Panel, fmt } from "./ui";

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
  return u.length ? u.join(", ") : "—";
}

const streamLabel = (s: LSLStreamInfo) => `${s.name} (${s.type}, ${s.channel_count} ch)`;

export function LslSources({
  onSourcesChanged,
  notify,
}: {
  onSourcesChanged: () => void;
  notify: (text: string) => void;
}) {
  const [disc, setDisc] = useState<LSLDiscovery | null>(null);
  const [signal, setSignal] = useState<string | null>(null);
  const [behavior, setBehavior] = useState("");
  const [markers, setMarkers] = useState("");
  const action = useAction();

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
    notify(`Registered ${desc.device_id} — connect it from Devices & sources`);
    setSignal(null);
    onSourcesChanged();
  };

  const streams = disc?.streams ?? [];
  const sig = streams.find((s) => s.key === signal) ?? null;
  const others = streams.filter((s) => s.key !== signal);

  return (
    <Panel
      title="Lab Streaming Layer"
      testId="lsl-sources"
      right={
        disc?.library ? (
          <span className="muted small" title={disc.library}>
            liblsl {/v\d+\.\d+\.\d+/.exec(disc.library)?.[0] ?? ""}
          </span>
        ) : undefined
      }
    >
      <div className="btn-row">
        <button className="btn btn-primary" disabled={action.busy} onClick={discover} data-testid="lsl-discover">
          {action.busy ? "Discovering…" : "Discover LSL streams"}
        </button>
        <span className="muted small" style={{ alignSelf: "center" }}>
          {disc?.discovered_at_ns ? `last discovery ${fmt.ago(disc.discovered_at_ns)} · ${streams.length} stream(s)` : "not run yet"}
        </span>
      </div>
      {disc?.error && <div className="alert">{disc.error}</div>}
      {action.error && (
        <div className="alert" data-testid="lsl-error">
          {action.error}
        </div>
      )}

      {streams.length > 0 && (
        <table className="table lsl-table" data-testid="lsl-streams">
          <thead>
            <tr>
              <th>stream</th>
              <th>type</th>
              <th className="r">ch</th>
              <th className="r">rate</th>
              <th>format</th>
              <th>units</th>
              <th>declared</th>
              <th>as signal</th>
            </tr>
          </thead>
          <tbody>
            {streams.map((s) => (
              <tr key={s.key} data-stream-key={s.key} title={`key ${s.key} · host ${s.hostname} · source_id ${s.source_id ?? "not set"}`}>
                <td className="mono">{s.name}</td>
                <td className="mono">{s.type}</td>
                <td className="r mono">{s.channel_count}</td>
                <td className="r mono">{s.nominal_srate > 0 ? `${fmt.num(s.nominal_srate)} Hz` : "irregular"}</td>
                <td className="mono">{s.channel_format}</td>
                <td className="mono">{units(s)}</td>
                <td>{declared(s)}</td>
                <td>
                  {s.usable_as_signal ? (
                    <button
                      className={`btn btn-small ${signal === s.key ? "btn-primary" : ""}`}
                      onClick={() => setSignal(signal === s.key ? null : s.key)}
                      data-testid={`lsl-use-${s.key}`}
                    >
                      configure
                    </button>
                  ) : (
                    <span className="text-warn small">{s.reason ?? "not usable"}</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {disc && !streams.length && !disc.error && disc.discovered_at_ns && (
        <div className="empty">No LSL streams found on the network.</div>
      )}

      {sig && (
        <div className="subform" data-testid="lsl-configure">
          <div className="small">
            Signal: <span className="mono">{streamLabel(sig)}</span> → device <span className="mono">lsl:{sig.key}</span>
          </div>
          <div className="form-grid">
            <label>
              behavior stream (optional)
              <select value={behavior} onChange={(e) => setBehavior(e.target.value)} data-testid="lsl-behavior">
                <option value="">none</option>
                {others.map((s) => (
                  <option key={s.key} value={s.key}>
                    {streamLabel(s)}
                  </option>
                ))}
              </select>
            </label>
            <label>
              marker stream (optional)
              <select value={markers} onChange={(e) => setMarkers(e.target.value)} data-testid="lsl-markers">
                <option value="">none</option>
                {others.map((s) => (
                  <option key={s.key} value={s.key}>
                    {streamLabel(s)}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <div className="btn-row">
            <button className="btn btn-primary" disabled={action.busy} onClick={register} data-testid="lsl-register">
              Register source
            </button>
          </div>
        </div>
      )}
      <p className="muted small">
        Discovery offers every usable signal stream as a source; use <b>configure</b> to attach a behavior stream
        (calibration labels) and a marker stream. Streams declared prerecorded or synthetic by their publisher are labelled
        so; any other stream is shown as a live stream of unverified origin — LSL cannot tell hardware from playback.
      </p>
    </Panel>
  );
}
