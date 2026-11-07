// Advanced: one collapsed disclosure holding the technical sections, each collapsed too.
// Everything stays mounted cheaply (closed sections render nothing) except the embedded
// Communication Board, which keeps its own runtime connection while hidden.

import type { DeviceDescriptor, StreamStats } from "../../sdk";
import type { ConsoleStreamData } from "../useConsoleStream";
import { isDatasetFile, isLiveSource, type DiagnosticsSnapshot, type LiveSourceMetadata, type RecordingInfo } from "../api";
import type { PipelineState } from "../pipeline";
import { AppsPanel } from "./AppsPanel";
import { CompatibilityView } from "./CompatibilityView";
import { ContractView } from "./ContractView";
import { FaultInjection, RecordingPanel, isBuiltInSimulator } from "./ControlsPanel";
import { DatasetDetails } from "./DatasetDetails";
import { DiagnosticsView } from "./DiagnosticsView";
import { EventStream } from "./EventStream";
import { IntentPad } from "./IntentPad";
import { NeuralView } from "./NeuralView";
import { PipelineStatusPanel } from "./PipelineStatusPanel";
import { SignalIntegrity } from "./SignalIntegrity";
import { TelemetryPanel } from "./Telemetry";
import { TestsView } from "./TestsView";
import { Disclosure } from "./ui";

export function Advanced({
  data,
  devices,
  diag,
  pipeline,
  recordings,
  liveMeta,
  liveError,
  stats,
  onRecordingsChanged,
}: {
  data: ConsoleStreamData;
  devices: DeviceDescriptor[];
  diag: DiagnosticsSnapshot | null;
  pipeline: PipelineState;
  recordings: RecordingInfo[];
  liveMeta: LiveSourceMetadata | null;
  liveError: string | null;
  stats: StreamStats;
  onRecordingsChanged: () => void;
}) {
  const { runtime } = data;
  const device = runtime?.device && runtime.state !== "idle" ? runtime.device : null;
  const sim = isBuiltInSimulator(runtime);
  const neuralFeatures = !!device?.capabilities.some((c) => c.capability === "neural_features");
  const neuralHere = data.neural.bins.length > 0 && data.neural.session === runtime?.session_id;

  return (
    <Disclosure title="Advanced" testId="advanced" className="advanced" keepMounted>
      <div className="advanced-body">
        <Disclosure title="Event stream" testId="adv-events">
          <EventStream events={data.events} tick={data.tick} />
        </Disclosure>
        <Disclosure title="Pipeline details" testId="adv-pipeline">
          {pipeline.error && !pipeline.status ? (
            <p className="error-text">{pipeline.error}</p>
          ) : (
            <PipelineStatusPanel status={pipeline.status} />
          )}
        </Disclosure>
        <Disclosure title="Acquisition details" testId="adv-acquisition">
          {!device && <p className="value-muted">No source connected.</p>}
          {device && isLiveSource(device) && <SignalIntegrity meta={liveMeta} error={liveError} diag={diag} />}
          {device && isDatasetFile(device) && <DatasetDetails deviceId={device.device_id} />}
          {device && neuralHere && (
            <NeuralView
              neural={data.neural}
              source={isDatasetFile(device) ? "offline" : neuralFeatures ? "stream" : "pipeline"}
            />
          )}
          {device && !isLiveSource(device) && !isDatasetFile(device) && (
            <TelemetryPanel telemetry={data.telemetry} runtime={runtime} />
          )}
        </Disclosure>
        <Disclosure title="Diagnostics" testId="adv-diagnostics">
          <DiagnosticsView diag={diag} clientLatencyMs={data.clientLatencyMs} stats={stats} />
        </Disclosure>
        <Disclosure title="Recording" testId="adv-recording">
          <RecordingPanel runtime={runtime} recordings={recordings} onRecordingsChanged={onRecordingsChanged} />
        </Disclosure>
        <Disclosure title="Capability contract" testId="adv-contract">
          <ContractView devices={devices} />
        </Disclosure>
        <Disclosure title="Connected applications" testId="adv-apps">
          <AppsPanel apps={diag?.apps ?? runtime?.apps ?? []} />
        </Disclosure>
        {sim && (
          <Disclosure title="Simulator controls" testId="adv-simulator">
            <IntentPad runtime={runtime} />
            <FaultInjection />
          </Disclosure>
        )}
        <Disclosure title="Communication board" testId="adv-board" keepMounted>
          <p className="hint">
            A separate demo app with its own connection. It uses only the SDK and adapts to the capabilities the runtime
            grants; it contains no device-specific code.{" "}
            <a href="/board.html" target="_blank" rel="noreferrer">
              Open in a new window
            </a>
          </p>
          <iframe className="board-frame" src="/board.html" title="Communication Board" data-testid="board-frame" />
        </Disclosure>
        <Disclosure title="Tests" testId="adv-tests">
          <TestsView />
        </Disclosure>
        <Disclosure title="Compatibility" testId="adv-compat">
          <CompatibilityView />
        </Disclosure>
      </div>
    </Disclosure>
  );
}
