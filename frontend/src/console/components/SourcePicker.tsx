// The source picker (a sheet): simulated profiles, recorded human data, session recordings,
// live streams (LSL discovery, Open Ephys registration, registered sources) and plugins
// (installed adapter packages, each run in its own process).

import { useState } from "react";
import { runtimeApi, type DeviceDescriptor, type RuntimeSnapshot } from "../../sdk";
import { isDatasetFile, isLiveSource, isPluginSource, labApi } from "../api";
import { useLog, useLoggedAction } from "../context";
import { shapeSummary, sourceKind } from "../wording";
import { LslSources } from "./LslSources";
import { OpenEphysForm } from "./OpenEphysForm";
import { PluginSources } from "./PluginSources";
import { Disclosure, Sheet } from "./ui";

/** "sub-HumanPitt-held-in-calib_ses-19250108T111022.nwb (DANDI 000954). …" -> short label */
export function datasetLabel(d: DeviceDescriptor): { file: string; where: string } {
  const m = /^(\S+)\s+\(([^)]+)\)/.exec(d.description);
  const file = m?.[1] ?? d.device_id;
  const ses = /ses-([0-9T]+)/.exec(file)?.[1];
  const split = /held-(in|out)-(calib|minival)/.exec(file)?.[0];
  const where = [m?.[2], split].filter(Boolean).join(" · ");
  return { file: ses ? `Session ${ses}` : file, where };
}

/** Dataset files shown before "Show all": the list is long and the other groups matter as much. */
export const DATASETS_SHOWN = 4;

export function groupSources(devices: DeviceDescriptor[]) {
  // Only verified dataset files go in the recorded-data group: recordings of live sessions and
  // external streams declaring prerecorded content are not "recorded human intracranial data".
  const datasets = devices.filter(isDatasetFile);
  const live = devices.filter(isLiveSource);
  const plugins = devices.filter(isPluginSource);
  const recordings = devices.filter((d) => d.device_id.startsWith("replay:"));
  const rest = devices.filter(
    (d) => !isDatasetFile(d) && !isLiveSource(d) && !isPluginSource(d) && !d.device_id.startsWith("replay:"),
  );
  const simulated = rest.filter((d) => d.kind === "simulated");
  const other = rest.filter((d) => d.kind !== "simulated");
  return { simulated, datasets, recordings, live, plugins, other };
}

export function SourcePicker({
  devices,
  runtime,
  onClose,
  onSourcesChanged,
}: {
  devices: DeviceDescriptor[];
  runtime: RuntimeSnapshot | null;
  onClose: () => void;
  onSourcesChanged: () => void;
}) {
  const log = useLog();
  const action = useLoggedAction();
  const activeId = runtime?.device && runtime.state !== "idle" ? runtime.device.device_id : null;
  const { simulated, datasets, recordings, live, plugins, other } = groupSources(devices);
  // the connected file is always visible
  const activeHidden = datasets.slice(DATASETS_SHOWN).some((d) => d.device_id === activeId);
  const [showAll, setAllDatasets] = useState(false);
  const allDatasets = showAll || activeHidden;

  const connect = async (d: DeviceDescriptor) => {
    // the runtime reports the connection itself (device.status), so the log needs no entry here
    const r = await action.run(() =>
      activeId !== null ? runtimeApi.switch(d.device_id) : runtimeApi.connect(d.device_id),
    );
    if (r) onClose();
  };
  const remove = async (d: DeviceDescriptor) => {
    const r = await action.run(() => labApi.removeSource(d.device_id));
    if (!r) return;
    log("info", r.removed ? `Removed ${d.display_name}` : `${d.display_name} was not registered`);
    onSourcesChanged();
  };

  const item = (d: DeviceDescriptor, sub: string, removable = false) => {
    const active = d.device_id === activeId;
    return (
      <li key={d.device_id} className={`pick ${active ? "pick-active" : ""}`} title={d.description || undefined}>
        <div className="pick-text">
          <div className="pick-name">{d.display_name}</div>
          {sub && <div className="pick-sub">{sub}</div>}
        </div>
        <div className="pick-actions">
          {removable && !active && (
            <button
              type="button"
              className="btn btn-quiet"
              disabled={action.busy}
              onClick={() => remove(d)}
              data-testid={`remove-${d.device_id}`}
            >
              Remove
            </button>
          )}
          {active ? (
            <span className="pick-current">Connected</span>
          ) : (
            <button
              type="button"
              className="btn"
              disabled={action.busy}
              onClick={() => connect(d)}
              data-testid={`device-${d.device_id}`}
            >
              {activeId ? "Switch" : "Connect"}
            </button>
          )}
        </div>
      </li>
    );
  };

  return (
    <Sheet title={activeId ? "Change source" : "Connect a source"} onClose={onClose} testId="source-picker">
      {action.error && (
        <p className="error-text" data-testid="picker-error">
          {action.error}
        </p>
      )}

      <section className="group">
        <h3>Simulated profiles</h3>
        <p className="explain">Synthetic data for demonstrations and testing. Not brain data.</p>
        <ul className="pick-list" data-testid="sim-list">
          {simulated.map((d) => item(d, shapeSummary(d)))}
        </ul>
      </section>

      <section className="group">
        <h3>Recorded human data (offline replay)</h3>
        <p className="explain">Verified files from a public dataset, replayed. Not a live implant.</p>
        {datasets.length ? (
          <>
            <ul className="pick-list" data-testid="dataset-list">
              {(allDatasets ? datasets : datasets.slice(0, DATASETS_SHOWN)).map((d) => {
                const { file, where } = datasetLabel(d);
                return item({ ...d, display_name: file }, [where, shapeSummary(d)].filter(Boolean).join(" · "));
              })}
            </ul>
            {!allDatasets && datasets.length > DATASETS_SHOWN && (
              <button type="button" className="btn btn-quiet flush" onClick={() => setAllDatasets(true)} data-testid="datasets-more">
                Show all {datasets.length} files
              </button>
            )}
          </>
        ) : (
          <p className="value-muted" data-testid="no-datasets">
            No recorded datasets found in <code>data/datasets/</code>. Download the verified files with{" "}
            <code>make dataset</code>, then reload.
          </p>
        )}
      </section>

      {recordings.length > 0 && (
        <section className="group">
          <h3>Session recordings (replay)</h3>
          <p className="explain">Recordings made with this console, replayed through the same pipeline.</p>
          <ul className="pick-list" data-testid="recording-list">
            {recordings.map((d) => item(d, sourceKind(d)?.text ?? ""))}
          </ul>
        </section>
      )}

      {other.length > 0 && (
        <section className="group">
          <h3>Other sources</h3>
          <ul className="pick-list">{other.map((d) => item(d, [sourceKind(d)?.text, shapeSummary(d)].filter(Boolean).join(" · ")))}</ul>
        </section>
      )}

      <section className="group">
        <h3>Live streams</h3>
        <p className="explain">
          Lab Streaming Layer or Open Ephys. BrainOS only receives; nothing is sent to the acquisition system.
        </p>
        {live.length > 0 && (
          <ul className="pick-list" data-testid="live-source-list">
            {live.map((d) => item(d, [sourceKind(d)?.text, shapeSummary(d)].filter(Boolean).join(" · "), true))}
          </ul>
        )}
        <Disclosure title="Find LSL streams" testId="find-lsl">
          <LslSources onSourcesChanged={onSourcesChanged} />
        </Disclosure>
        <Disclosure title="Add Open Ephys source" testId="add-openephys">
          <OpenEphysForm onSourcesChanged={onSourcesChanged} />
        </Disclosure>
      </section>

      <section className="group" data-testid="plugin-group">
        <h3>Plugins</h3>
        <p className="explain">
          Sources from installed adapter packages. Each plugin runs in its own process and only delivers data to
          BrainOS; what it declares and sends is checked before use.
        </p>
        <PluginSources
          devices={plugins}
          activeId={activeId}
          onConnected={onClose}
          onSourcesChanged={onSourcesChanged}
        />
      </section>
    </Sheet>
  );
}
