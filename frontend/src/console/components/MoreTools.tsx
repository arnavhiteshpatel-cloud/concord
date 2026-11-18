// More tools: every tool listed by name with what it does and when to use it, grouped, each with
// its own Show/Hide button. Closed tools render nothing, except the embedded participant screen,
// which keeps its own runtime connection while hidden.

import type { ReactNode } from "react";
import type { DeviceDescriptor, StreamStats } from "../../sdk";
import type { ConsoleStreamData } from "../useConsoleStream";
import { isDatasetFile, isLiveSource, type DiagnosticsSnapshot, type LiveSourceMetadata, type RecordingInfo } from "../api";
import { useHelp } from "../context";
import type { PipelineState } from "../pipeline";
import { SIMULATOR_TOOL, TOOL_GROUPS, type ToolInfo } from "../tools";
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
import { StoredData } from "./StoredData";
import { SupportReport } from "./SupportReport";
import { TelemetryPanel } from "./Telemetry";
import { TestsView } from "./TestsView";
import { ToolCard } from "./ui";

export function MoreTools({
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
  const openHelp = useHelp();
  const { runtime } = data;
  const device = runtime?.device && runtime.state !== "idle" ? runtime.device : null;
  const sim = isBuiltInSimulator(runtime);
  const neuralFeatures = !!device?.capabilities.some((c) => c.capability === "neural_features");
  const neuralHere = data.neural.bins.length > 0 && data.neural.session === runtime?.session_id;

  const content: Record<string, ReactNode> = {
    "adv-board": (
      <>
        <p className="hint">
          This is a preview. For the person using the BCI, click <b>Open participant screen</b> in step 4, or{" "}
          <a href="/board.html" target="_blank" rel="noreferrer">
            open it in a new tab
          </a>
          .
        </p>
        <iframe className="board-frame" src="/board.html" title="Communication Board" data-testid="board-frame" />
      </>
    ),
    "adv-events": <EventStream events={data.events} tick={data.tick} />,
    "adv-acquisition": (
      <>
        {!device && <p className="value-muted">No source connected.</p>}
        {device && isLiveSource(device) && <SignalIntegrity meta={liveMeta} error={liveError} diag={diag} />}
        {device && isDatasetFile(device) && <DatasetDetails deviceId={device.device_id} />}
        {device && neuralHere && (
          <NeuralView neural={data.neural} source={isDatasetFile(device) ? "offline" : neuralFeatures ? "stream" : "pipeline"} />
        )}
        {device && !isLiveSource(device) && !isDatasetFile(device) && <TelemetryPanel telemetry={data.telemetry} runtime={runtime} />}
      </>
    ),
    "adv-pipeline":
      pipeline.error && !pipeline.status ? <p className="error-text">{pipeline.error}</p> : <PipelineStatusPanel status={pipeline.status} />,
    "adv-recording": <RecordingPanel runtime={runtime} recordings={recordings} onRecordingsChanged={onRecordingsChanged} />,
    "adv-storage": <StoredData onChanged={onRecordingsChanged} />,
    "adv-apps": <AppsPanel apps={diag?.apps ?? runtime?.apps ?? []} />,
    "adv-diagnostics": <DiagnosticsView diag={diag} clientLatencyMs={data.clientLatencyMs} stats={stats} />,
    "adv-contract": <ContractView devices={devices} />,
    "adv-compat": <CompatibilityView />,
    "adv-tests": <TestsView />,
    "adv-support": <SupportReport />,
  };

  const card = (t: ToolInfo, body: ReactNode) => (
    <ToolCard key={t.id} title={t.title} what={t.what} when={t.when} testId={t.id} keepMounted={t.id === "adv-board"}>
      {body}
    </ToolCard>
  );

  return (
    <section className="tools" aria-labelledby="more-tools-title" data-testid="more-tools">
      <header className="tools-head">
        <h2 id="more-tools-title">More tools</h2>
        <p className="explain">
          Everything else Concord can do. Each tool says what it is for; click Show to open it.{" "}
          <button type="button" className="link" onClick={() => openHelp("tools")} data-testid="more-tools-help">
            About these tools
          </button>
        </p>
      </header>
      {sim && (
        <div className="tool-group" data-testid="tool-group-practice">
          <h3>Practice</h3>
          {card(
            SIMULATOR_TOOL,
            <>
              <IntentPad runtime={runtime} />
              <FaultInjection />
            </>,
          )}
        </div>
      )}
      {TOOL_GROUPS.map((g) => (
        <div key={g.title} className="tool-group">
          <h3>{g.title}</h3>
          {g.tools.map((t) => card(t, content[t.id]))}
        </div>
      ))}
    </section>
  );
}
