import { useEffect, useState } from "react";
import { CAPABILITIES, type DeviceDescriptor } from "../../sdk";
import { consoleApi, type CapabilityInfo } from "../api";
import { Panel } from "./ui";

function params(p: Record<string, unknown>): string {
  return Object.entries(p)
    .map(([k, v]) => `${k}=${Array.isArray(v) ? v.join("|") : String(v)}`)
    .join(", ");
}

export function ContractView({ devices, onError }: { devices: DeviceDescriptor[]; onError: (e: unknown) => void }) {
  const [caps, setCaps] = useState<CapabilityInfo[]>([]);
  useEffect(() => {
    consoleApi.capabilities().then(setCaps).catch(onError);
  }, [onError]);

  return (
    <div className="contract" data-testid="contract-view">
      <Panel title="Capability matrix" right={<span className="muted">✓ declared by device · — explicitly unsupported</span>}>
        <table className="table matrix">
          <thead>
            <tr>
              <th>capability</th>
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
                          <span className="tick">✓</span>
                          <span className="mono small muted">{params(desc.params)}</span>
                        </>
                      ) : (
                        <span className="muted">—</span>
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}
            <tr>
              <td className="mono">native format</td>
              {devices.map((d) => (
                <td key={d.device_id} className="small muted">
                  {d.native_format}
                </td>
              ))}
            </tr>
          </tbody>
        </table>
      </Panel>
      <div className="diag-grid">
        <Panel title="Capability vocabulary (schema 1.0)">
          <table className="table">
            <tbody>
              {caps.map((c) => (
                <tr key={c.capability}>
                  <td className="mono nowrap">{c.capability}</td>
                  <td className="mono muted">{c.event_types.join(", ")}</td>
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
                <td>recording.frame only</td>
              </tr>
              <tr>
                <td className="prov-behavioral_label mono">behavioral_label</td>
                <td>recording.annotation only — never delivered as an intent</td>
              </tr>
              <tr>
                <td className="prov-simulated_intent mono">simulated_intent</td>
                <td>intent.* with synthetic=true (all v1 intents)</td>
              </tr>
              <tr>
                <td className="prov-decoded_intent mono">decoded_intent</td>
                <td>intent.* with a model_id (no decoder ships in v1)</td>
              </tr>
              <tr>
                <td className="prov-device_report mono">device_report / runtime</td>
                <td>telemetry.sample, device.status</td>
              </tr>
            </tbody>
          </table>
          <p className="muted small">
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
