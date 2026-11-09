import { useEffect, useState } from "react";
import { CAPABILITIES, type DeviceDescriptor } from "../../sdk";
import { consoleApi, type CapabilityInfo } from "../api";
import { errorText } from "../hooks";
import { Panel } from "./ui";

function paramText(v: unknown): string {
  if (!Array.isArray(v)) return String(v);
  // schema 1.4: a list of objects (e.g. feature streams, source decoders) -> their names
  return v
    .map((x) =>
      x !== null && typeof x === "object"
        ? String((x as Record<string, unknown>).model_id ?? (x as Record<string, unknown>).feature ?? "object")
        : String(x),
    )
    .join("|");
}

function params(p: Record<string, unknown>): string {
  return Object.entries(p)
    .map(([k, v]) => `${k}=${paramText(v)}`)
    .join(", ");
}

export function ContractView({ devices }: { devices: DeviceDescriptor[] }) {
  const [caps, setCaps] = useState<CapabilityInfo[]>([]);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    consoleApi
      .capabilities()
      .then(setCaps)
      .catch((e: unknown) => setError(errorText(e)));
  }, []);

  return (
    <div className="contract" data-testid="contract-view">
      {error && <p className="error-text">{error}</p>}
      <Panel title="Capability matrix" right={<span className="hint">Yes: declared by the device · —: not supported</span>}>
        <table className="table matrix">
          <thead>
            <tr>
              <th>Capability</th>
              {devices.map((d) => (
                <th key={d.device_id}>{d.display_name}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {CAPABILITIES.map((cap) => (
              <tr key={cap}>
                <td className="mono">{cap}</td>
                {devices.map((d) => {
                  const desc = d.capabilities.find((c) => c.capability === cap);
                  return (
                    <td key={d.device_id} className={desc ? "yes" : "no"}>
                      {desc ? (
                        <>
                          <span>Yes</span> <span className="hint">{params(desc.params)}</span>
                        </>
                      ) : (
                        <span className="hint">—</span>
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}
            <tr>
              <td>Native format</td>
              {devices.map((d) => (
                <td key={d.device_id} className="hint">
                  {d.native_format}
                </td>
              ))}
            </tr>
          </tbody>
        </table>
      </Panel>
      <div className="diag-grid">
        <Panel title="Capability vocabulary">
          <table className="table">
            <tbody>
              {caps.map((c) => (
                <tr key={c.capability}>
                  <td className="mono nowrap">{c.capability}</td>
                  <td className="hint">{c.event_types.join(", ")}</td>
                  <td>{c.description}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>
        <Panel title="Provenance separation">
          <table className="table">
            <tbody>
              <tr>
                <td className="prov-raw_signal mono">raw_signal</td>
                <td>recording.frame: samples as the source sent them. Never delivered as a command.</td>
              </tr>
              <tr>
                <td className="prov-processed_feature mono">processed_feature</td>
                <td>features.binned, features.vector: features computed from a signal (e.g. spike counts). Never a command.</td>
              </tr>
              <tr>
                <td className="prov-behavioral_label mono">behavioral_label</td>
                <td>behavior.sample, recording.annotation: what the task or participant did (labels). Never a command.</td>
              </tr>
              <tr>
                <td className="prov-simulated_intent mono">simulated_intent</td>
                <td>intent.* from a simulated profile (synthetic=true): an operator standing in for a participant.</td>
              </tr>
              <tr>
                <td className="prov-decoded_intent mono">decoded_intent</td>
                <td>
                  intent.* and intent.kinematics from a decoder, always with its model id and origin (Concord, external, historical).
                  Reaches applications only while command output is on and only those you authorized.
                </td>
              </tr>
              <tr>
                <td className="prov-device_report mono">device_report / runtime</td>
                <td>telemetry.sample, device.status, control.state: reports about the device and the runtime.</td>
              </tr>
            </tbody>
          </table>
          <p className="hint">
            Enforced by the envelope validator on the server and re-checked by both SDKs. Full JSON Schema:{" "}
            <a href="/api/v1/schema/event" target="_blank" rel="noreferrer">
              /api/v1/schema/event
            </a>{" "}
            · API docs:{" "}
            <a href="/docs" target="_blank" rel="noreferrer">
              /docs
            </a>
          </p>
        </Panel>
      </div>
    </div>
  );
}
