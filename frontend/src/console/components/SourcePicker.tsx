// The source picker (a sheet): simulated profiles, recorded human data, session recordings,
// live streams (LSL discovery, Open Ephys registration, registered sources) and plugins
// (installed adapter packages, each run in its own process).

import { useEffect, useState } from "react";
import { runtimeApi, type DeviceDescriptor, type RuntimeSnapshot } from "../../sdk";
import { consoleApi, cursorClickLabel, isCursorClickFile, isDatasetFile, isLiveSource, isPluginSource, labApi } from "../api";
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
  // T15 cursor + click blocks: verified dataset files too, listed with their own names
  const cursorClick = devices.filter(isCursorClickFile);
  const live = devices.filter(isLiveSource);
  const plugins = devices.filter(isPluginSource);
  const recordings = devices.filter((d) => d.device_id.startsWith("replay:"));
  const rest = devices.filter(
    (d) =>
      !isDatasetFile(d) && !isCursorClickFile(d) && !isLiveSource(d) && !isPluginSource(d) && !d.device_id.startsWith("replay:"),
  );
  const simulated = rest.filter((d) => d.kind === "simulated");
  const other = rest.filter((d) => d.kind !== "simulated");
  return { simulated, datasets, cursorClick, recordings, live, plugins, other };
}

export function SourcePicker({
  devices,
  devicesLoaded = true,
  runtime,
  onClose,
  onSourcesChanged,
}: {
  devices: DeviceDescriptor[];
  /** false while the first device list is still being fetched */
  devicesLoaded?: boolean;
  runtime: RuntimeSnapshot | null;
  onClose: () => void;
  onSourcesChanged: () => void;
}) {
  const log = useLog();
  const action = useLoggedAction();
  const activeId = runtime?.device && runtime.state !== "idle" ? runtime.device.device_id : null;
  const { simulated, datasets, cursorClick, recordings, live, plugins, other } = groupSources(devices);
  // where dataset files go, so the empty-state message can name the real folder (asked only
  // when there are no files: the dataset listing scans the folder)
  const noFiles = devicesLoaded && datasets.length === 0 && cursorClick.length === 0;
  const [datasetsDir, setDatasetsDir] = useState<string | null>(null);
  useEffect(() => {
    if (!noFiles) return;
    let alive = true;
    consoleApi
      .datasets()
      .then((d) => alive && setDatasetsDir(d.datasets_dir))
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, [noFiles]);
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
        {datasets.length || cursorClick.length ? (
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
            {cursorClick.length > 0 && (
              <ul className="pick-list" data-testid="cursorclick-list">
                {cursorClick.map((d) =>
                  item(
                    { ...d, display_name: `Cursor + click · ${cursorClickLabel(d) ?? d.device_id}` },
                    ["Dryad T15", shapeSummary(d)].filter(Boolean).join(" · "),
                  ),
                )}
              </ul>
            )}
          </>
        ) : !devicesLoaded ? (
          <p className="value-muted" data-testid="datasets-loading">
            Checking the recorded datasets… The first time after Concord starts, this takes a few seconds.
          </p>
        ) : (
          <p className="value-muted" data-testid="no-datasets">
            No recorded datasets yet. Put downloaded dataset files in{" "}
            <code>{datasetsDir ?? "the datasets folder of your data directory"}</code> (create the folder if needed;
            Getting started, section 4), then reload this page.
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
          Lab Streaming Layer or Open Ephys. Concord only receives; nothing is sent to the acquisition system.
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
          Concord; what it declares and sends is checked before use.
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
