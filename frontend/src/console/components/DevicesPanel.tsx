import type { DeviceDescriptor, RuntimeSnapshot } from "../../sdk";
import { isDatasetFile, isLiveSource } from "../api";
import { Panel } from "./ui";

const SHORT: Record<string, string> = {
  recording: "rec",
  pointer_intent: "pointer",
  selection: "select",
  text_intent: "text",
  telemetry: "telem",
  device_status: "status",
  neural_features: "features",
  behavior: "behavior",
  kinematic_intent: "decoded",
};

function paramSummary(d: DeviceDescriptor): string {
  const rec = d.capabilities.find((c) => c.capability === "recording");
  const ptr = d.capabilities.find((c) => c.capability === "pointer_intent");
  const parts: string[] = [];
  // live sources may not know their layout until opened (e.g. Open Ephys learns it from the stream)
  if (rec && rec.params.channel_count !== undefined)
    parts.push(`${rec.params.channel_count} ch @ ${rec.params.sample_rate_hz} Hz`);
  if (rec?.params.unit !== undefined && rec.params.unit !== "uV") parts.push(`unit ${String(rec.params.unit)}`);
  if (ptr) parts.push(`pointer ${ptr.params.rate_hz} Hz`);
  return parts.join(" · ");
}

/** "sub-HumanPitt-held-in-calib_ses-19250108T111022.nwb (DANDI 000954). …" -> short label */
function datasetLabel(d: DeviceDescriptor): { file: string; where: string } {
  const m = /^(\S+)\s+\(([^)]+)\)/.exec(d.description);
  const file = m?.[1] ?? d.device_id;
  const ses = /ses-([0-9T]+)/.exec(file)?.[1];
  const split = /held-(in|out)-(calib|minival)/.exec(file)?.[0];
  return { file: ses ? `${split ?? ""} · ${ses}` : file, where: m?.[2] ?? "" };
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
  // Only verified dataset files go in the dataset group: recordings of live sessions and
  // external streams declaring prerecorded content are not "recorded human intracranial data".
  const datasets = devices.filter(isDatasetFile);
  const live = devices.filter(isLiveSource);
  const cards = devices.filter((d) => !isDatasetFile(d) && !isLiveSource(d));
  const label = (id: string) => (id === activeId && connected ? "Active" : connected ? "Switch" : "Connect");

  const card = (d: DeviceDescriptor) => {
    const isActive = d.device_id === activeId && connected;
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
            {label(d.device_id)}
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
  };

  return (
    <Panel title="Devices & sources" right={<span className="muted">{devices.length} available</span>}>
      <div className="device-list">{cards.map(card)}</div>

      {live.length > 0 && (
        <>
          <div className="device-group">Live sources · LSL / Open Ephys (registered in Acquisition)</div>
          <div className="device-list" data-testid="live-source-list">
            {live.map(card)}
          </div>
        </>
      )}

      <div className="device-group">Recorded human intracranial data · offline replay</div>
      {datasets.length ? (
        <div className="dataset-rows" data-testid="dataset-list">
          {datasets.map((d) => {
            const isActive = d.device_id === activeId && connected;
            const { file, where } = datasetLabel(d);
            const decoded = d.capabilities.some((c) => c.capability === "kinematic_intent");
            return (
              <div key={d.device_id} className={`dataset-row ${isActive ? "device-active" : ""}`} title={d.description}>
                <div>
                  <div className="dataset-name">{file}</div>
                  <div className="device-meta">
                    {where}
                    {decoded && <span className="cap cap-dec"> held-out decoder</span>}
                  </div>
                </div>
                <button
                  className={`btn btn-small ${isActive ? "btn-ghost" : ""}`}
                  disabled={busy || isActive}
                  onClick={() => onConnect(d.device_id)}
                  data-testid={`device-${d.device_id}`}
                >
                  {label(d.device_id)}
                </button>
              </div>
            );
          })}
        </div>
      ) : (
        <p className="muted small" data-testid="no-datasets">
          No recorded datasets found in <code>data/datasets/</code>. Download the verified FALCON H1 files with{" "}
          <code>make dataset</code>, then reload.
        </p>
      )}
    </Panel>
  );
}
