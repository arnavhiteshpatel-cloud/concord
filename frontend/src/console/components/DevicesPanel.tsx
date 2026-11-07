import type { DeviceDescriptor, RuntimeSnapshot } from "../../sdk";
import { Panel } from "./ui";

const SHORT: Record<string, string> = {
  recording: "rec",
  pointer_intent: "pointer",
  selection: "select",
  text_intent: "text",
  telemetry: "telem",
  device_status: "status",
};

function paramSummary(d: DeviceDescriptor): string {
  const rec = d.capabilities.find((c) => c.capability === "recording");
  const ptr = d.capabilities.find((c) => c.capability === "pointer_intent");
  const parts: string[] = [];
  if (rec) parts.push(`${rec.params.channel_count} ch @ ${rec.params.sample_rate_hz} Hz`);
  if (ptr) parts.push(`pointer ${ptr.params.rate_hz} Hz`);
  return parts.join(" · ");
}

export function DevicesPanel({
  devices,
  runtime,
  busy,
  onConnect,
}: {
  devices: DeviceDescriptor[];
  runtime: RuntimeSnapshot | null;
  busy: boolean;
  onConnect: (id: string) => void;
}) {
  const activeId = runtime?.device?.device_id ?? null;
  const connected = !!activeId && runtime?.state !== "idle";
  return (
    <Panel title="Devices" right={<span className="muted">{devices.length} available</span>}>
      <div className="device-list">
        {devices.map((d) => {
          const isActive = d.device_id === activeId && connected;
          const label = isActive ? "Active" : connected ? "Switch" : "Connect";
          return (
            <div key={d.device_id} className={`device ${isActive ? "device-active" : ""}`}>
              <div className="device-top">
                <div>
                  <div className="device-name">{d.display_name}</div>
                  <div className="device-meta mono">
                    {d.device_id} · {d.kind}
                    {d.synthetic ? " · synthetic" : ""}
                  </div>
                </div>
                <button
                  className={`btn ${isActive ? "btn-ghost" : "btn-primary"}`}
                  disabled={busy || isActive}
                  onClick={() => onConnect(d.device_id)}
                  data-testid={`device-${d.device_id}`}
                >
                  {label}
                </button>
              </div>
              <div className="cap-chips">
                {d.capabilities.map((c) => (
                  <span key={c.capability} className="cap" title={c.description || c.capability}>
                    {SHORT[c.capability] ?? c.capability}
                  </span>
                ))}
              </div>
              <div className="device-desc">{paramSummary(d)}</div>
            </div>
          );
        })}
      </div>
    </Panel>
  );
}
