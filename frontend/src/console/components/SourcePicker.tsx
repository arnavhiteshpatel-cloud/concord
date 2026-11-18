// The source picker (a sheet): simulated profiles, recorded human data, session recordings,
// live streams (LSL discovery, Open Ephys registration, registered sources) and plugins
// (installed adapter packages, each run in its own process).

import { useEffect, useState } from "react";
import { runtimeApi, type DeviceDescriptor, type RuntimeSnapshot } from "../../sdk";
import { consoleApi, cursorClickLabel, isCursorClickFile, isDatasetFile, isLiveSource, isPluginSource, labApi } from "../api";
import { useLog, useLoggedAction } from "../context";
import { hasCapability, shapeSummary, sourceKind } from "../wording";
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

/** The two FALCON H1 files the guide starts with (DANDI 000954, pinned in datasets/falcon_h1.json). */
export const STARTER_FILES = [
  {
    name: "sub-HumanPitt-held-in-calib_ses-19250108T110520.nwb",
    size: "5.8 MB",
    url: "https://api.dandiarchive.org/api/assets/e40a2eca-883d-4c80-81e3-4203a49506b5/download/",
  },
  {
    name: "sub-HumanPitt-held-in-calib_ses-19250108T111022.nwb",
    size: "3.3 MB",
    url: "https://api.dandiarchive.org/api/assets/98f1e471-ad68-4006-b090-9a3e347852e6/download/",
  },
];

/** "Moves a pointer and makes selections": what a simulated profile produces, from its capabilities. */
export function simulatedDoes(d: DeviceDescriptor): string {
  const does = [
    hasCapability(d, "pointer_intent") ? "moves a pointer" : null,
    hasCapability(d, "selection") ? "makes selections" : null,
    hasCapability(d, "text_intent") ? "types letters" : null,
  ].filter(Boolean);
  if (!does.length) return "";
  const text = does.length > 1 ? `${does.slice(0, -1).join(", ")} and ${does[does.length - 1]}` : does[0]!;
  return text[0]!.toUpperCase() + text.slice(1);
}

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
    <Sheet title={activeId ? "Change source" : "Choose a data source"} onClose={onClose} testId="source-picker">
      {action.error && (
        <p className="error-text" data-testid="picker-error">
          {action.error}
        </p>
      )}

      <section className="group">
        <h3>Demo data (simulated)</h3>
        <p className="explain">
          Made-up signals generated by Concord, for trying things out. No equipment needed. Not brain data. New here?
          Start with Profile A.
        </p>
        <ul className="pick-list" data-testid="sim-list">
          {simulated.map((d) => item(d, [simulatedDoes(d), shapeSummary(d)].filter(Boolean).join(" · ")))}
        </ul>
      </section>

      <section className="group">
        <h3>Real recordings (played back)</h3>
        <p className="explain">
          Brain recordings from public research studies, played back from files on this computer. Nobody is connected:
          they are labelled offline replay. Concord checks each file against a published fingerprint.
        </p>
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
          <div className="subform" data-testid="no-datasets">
            <p className="value-muted">No recordings on this computer yet. To add the two starter recordings (9 MB):</p>
            <ol className="steps-list">
              <li>
                Download both files (from the DANDI archive, where the study published them):
                <ul>
                  {STARTER_FILES.map((f) => (
                    <li key={f.name}>
                      <a href={f.url} target="_blank" rel="noreferrer">
                        {f.name}
                      </a>{" "}
                      <span className="hint">({f.size})</span>
                    </li>
                  ))}
                </ul>
              </li>
              <li>
                Move them into this folder (create it if it does not exist):{" "}
                <code>{datasetsDir ?? "the datasets folder of your data directory"}</code>
              </li>
              <li>Reload this page. The recordings appear here.</li>
            </ol>
            <p className="hint">
              By downloading you agree to the dataset&apos;s terms: do not try to identify or contact the participant, and
              do not share the files.
            </p>
          </div>
        )}
      </section>

      {recordings.length > 0 && (
        <section className="group">
          <h3>Your recordings</h3>
          <p className="explain">Recordings you made with Concord, played back the same way as a live source.</p>
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
        <h3>Live equipment</h3>
        <p className="explain">
          Connect to recording software already running in your lab, if it shares its data over Lab Streaming Layer
          (LSL) or Open Ephys. Concord only listens: nothing is sent to your equipment.
        </p>
        {live.length > 0 && (
          <ul className="pick-list" data-testid="live-source-list">
            {live.map((d) => item(d, [sourceKind(d)?.text, shapeSummary(d)].filter(Boolean).join(" · "), true))}
          </ul>
        )}
        <Disclosure title="Find LSL streams on this network" testId="find-lsl">
          <LslSources onSourcesChanged={onSourcesChanged} />
        </Disclosure>
        <Disclosure title="Connect to Open Ephys" testId="add-openephys">
          <OpenEphysForm onSourcesChanged={onSourcesChanged} />
        </Disclosure>
      </section>

      <section className="group" data-testid="plugin-group">
        <h3>Add-ons (plugins)</h3>
        <p className="explain">
          Extra connectors installed separately, for example for BCI2000. Each runs on its own, and Concord checks
          everything it sends before using it.
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
