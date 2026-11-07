// Acquisition tab: register live sources (LSL, Open Ephys), remove them, and watch the
// connected source's integrity counters. Connecting stays in "Devices & sources".

import type { DeviceDescriptor, RuntimeSnapshot } from "../../sdk";
import { isLiveSource, labApi, type DiagnosticsSnapshot, type LiveSourceMetadata } from "../api";
import { useAction } from "../hooks";
import { LslSources } from "./LslSources";
import { OpenEphysForm } from "./OpenEphysForm";
import { SignalIntegrity } from "./SignalIntegrity";
import { Panel } from "./ui";

function RegisteredSources({
  devices,
  runtime,
  onSourcesChanged,
  notify,
}: {
  devices: DeviceDescriptor[];
  runtime: RuntimeSnapshot | null;
  onSourcesChanged: () => void;
  notify: (text: string) => void;
}) {
  const live = devices.filter(isLiveSource);
  const action = useAction();
  const activeId = runtime?.device && runtime.state !== "idle" ? runtime.device.device_id : null;
  const remove = async (id: string) => {
    const r = await action.run(() => labApi.removeSource(id));
    if (!r) return;
    notify(r.removed ? `Removed ${id}` : `${id} was not registered`);
    onSourcesChanged();
  };
  return (
    <Panel title="Registered live sources" testId="registered-sources" right={<span className="muted">{live.length}</span>}>
      {live.length ? (
        <table className="table">
          <tbody>
            {live.map((d) => (
              <tr key={d.device_id}>
                <td>
                  <div>{d.display_name}</div>
                  <div className="device-meta mono">
                    {d.device_id} · {d.kind}
                    {d.synthetic ? " · synthetic" : ""}
                  </div>
                </td>
                <td className="r">
                  <button
                    className="btn btn-small btn-danger"
                    disabled={action.busy || d.device_id === activeId}
                    title={d.device_id === activeId ? "Disconnect the source before removing it" : undefined}
                    onClick={() => remove(d.device_id)}
                    data-testid={`remove-${d.device_id}`}
                  >
                    Remove
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <div className="empty">None yet. Discover LSL streams or register an Open Ephys endpoint.</div>
      )}
      {action.error && <div className="alert">{action.error}</div>}
      <p className="muted small">Registered sources appear under Devices &amp; sources, where you connect or switch to them.</p>
    </Panel>
  );
}

export function AcquisitionView({
  devices,
  runtime,
  liveMeta,
  liveError,
  diag,
  onSourcesChanged,
  notify,
}: {
  devices: DeviceDescriptor[];
  runtime: RuntimeSnapshot | null;
  liveMeta: LiveSourceMetadata | null;
  liveError: string | null;
  diag: DiagnosticsSnapshot | null;
  onSourcesChanged: () => void;
  notify: (text: string) => void;
}) {
  const liveConnected = isLiveSource(runtime?.device) && runtime?.state !== "idle";
  return (
    <div className="lab" data-testid="acquisition-view">
      <p className="muted small">
        Read-only acquisition: BrainOS only receives from LSL inlets and Open Ephys subscriber sockets; nothing is ever
        sent to an acquisition system.
      </p>
      <div className="lab-grid">
        <LslSources onSourcesChanged={onSourcesChanged} notify={notify} />
        <div className="lab-col">
          <OpenEphysForm onSourcesChanged={onSourcesChanged} notify={notify} />
          <RegisteredSources devices={devices} runtime={runtime} onSourcesChanged={onSourcesChanged} notify={notify} />
        </div>
      </div>
      {liveConnected ? (
        <SignalIntegrity meta={liveMeta} error={liveError} diag={diag} />
      ) : (
        <Panel title="Signal integrity">
          <div className="empty">Connect a live LSL or Open Ephys source to see its counters.</div>
        </Panel>
      )}
    </div>
  );
}
