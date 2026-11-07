import { useCallback, useEffect, useRef, useState } from "react";
import { BrainOSApiError, runtimeApi, type DeviceDescriptor } from "../sdk";
import {
  consoleApi,
  isDatasetFile,
  isLiveSource,
  labApi,
  type DiagnosticsSnapshot,
  type Fault,
  type RecordingInfo,
} from "./api";
import { AcquisitionView } from "./components/AcquisitionView";
import { AppsPanel } from "./components/AppsPanel";
import { ContractView } from "./components/ContractView";
import { ControlsPanel } from "./components/ControlsPanel";
import { DevicesPanel } from "./components/DevicesPanel";
import { DiagnosticsView } from "./components/DiagnosticsView";
import { EventStream } from "./components/EventStream";
import { Header } from "./components/Header";
import { IntentPad } from "./components/IntentPad";
import { NeuralView } from "./components/NeuralView";
import { PipelineView } from "./components/PipelineView";
import { SignalIntegrity } from "./components/SignalIntegrity";
import { SourcePanel } from "./components/SourcePanel";
import { SignalView, TelemetryPanel } from "./components/SignalView";
import { TestsView } from "./components/TestsView";
import { Panel } from "./components/ui";
import { usePoll } from "./hooks";
import { useConsoleStream } from "./useConsoleStream";

type Tab = "live" | "acquisition" | "pipeline" | "diagnostics" | "contract" | "tests";
interface Toast {
  id: number;
  tone: "err" | "ok";
  text: string;
}

export function App() {
  const data = useConsoleStream();
  const { runtime } = data;
  const [tab, setTab] = useState<Tab>("live");
  const [devices, setDevices] = useState<DeviceDescriptor[]>([]);
  const [recordings, setRecordings] = useState<RecordingInfo[]>([]);
  const [diag, setDiag] = useState<DiagnosticsSnapshot | null>(null);
  const [busy, setBusy] = useState(false);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const toastId = useRef(0);

  const toast = useCallback((tone: Toast["tone"], text: string) => {
    const id = ++toastId.current;
    setToasts((t) => [...t.slice(-3), { id, tone, text }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 5000);
  }, []);

  const onError = useCallback(
    (e: unknown) => {
      if (e instanceof BrainOSApiError) toast("err", `${e.code}: ${e.message}`);
      else toast("err", e instanceof Error ? e.message : String(e));
    },
    [toast],
  );

  const refreshLists = useCallback(() => {
    runtimeApi.devices().then(setDevices).catch(onError);
    consoleApi.recordings().then(setRecordings).catch(onError);
  }, [onError]);

  // Waits for the stream, so an outage shows no error toasts and lists refresh on reconnect.
  const streamOpen = data.conn === "open";
  useEffect(() => {
    if (streamOpen) refreshLists();
  }, [refreshLists, streamOpen, runtime?.recording]);

  useEffect(() => {
    let alive = true;
    const poll = () =>
      consoleApi
        .diagnostics()
        .then((d) => alive && setDiag(d))
        .catch(() => alive && setDiag(null)); // don't keep showing stale metrics as current
    poll();
    const t = setInterval(poll, 1000);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, []);

  const act = useCallback(
    async (fn: () => Promise<unknown>, ok?: string) => {
      setBusy(true);
      try {
        await fn();
        if (ok) toast("ok", ok);
      } catch (e) {
        onError(e);
      } finally {
        setBusy(false);
      }
    },
    [onError, toast],
  );

  const connected = !!runtime?.device && runtime.state !== "idle";
  // Verified offline dataset file: show provenance + playback instead of the simulator pad.
  const offlineData = isDatasetFile(runtime?.device);
  // Live LSL / Open Ephys source: show its integrity counters there instead.
  const liveDevice = connected && runtime?.device && isLiveSource(runtime.device) ? runtime.device.device_id : null;
  const live = usePoll(liveDevice, () => labApi.liveSource(liveDevice ?? ""), 1000);
  const neuralFeatures = !!runtime?.device?.capabilities.some((c) => c.capability === "neural_features");
  // Binned features computed by the pipeline from a raw source arrive on the same session.
  const pipelineFeatures =
    !neuralFeatures && data.neural.bins.length > 0 && data.neural.session === runtime?.session_id;
  const notify = useCallback((text: string) => toast("ok", text), [toast]);
  const onConnect = (id: string) =>
    act(() => (connected ? runtimeApi.switch(id) : runtimeApi.connect(id)), connected ? `Switched to ${id}` : `Connected ${id}`);

  return (
    <div className="app-shell">
      <Header runtime={runtime} conn={data.conn} diag={diag} />
      <div className="layout">
        <aside className="col-left">
          <DevicesPanel devices={devices} runtime={runtime} busy={busy} onConnect={onConnect} />
          <ControlsPanel
            runtime={runtime}
            busy={busy}
            recordings={recordings}
            onPause={() => act(runtimeApi.pause)}
            onResume={() => act(runtimeApi.resume)}
            onDisconnect={() => act(runtimeApi.disconnect)}
            onStartRecording={(excludeRaw) =>
              act(
                () => consoleApi.startRecording(undefined, excludeRaw),
                excludeRaw ? "Recording started (features + labels, no raw frames)" : "Recording started",
              )
            }
            onStopRecording={() =>
              act(async () => {
                const info = await consoleApi.stopRecording();
                toast("ok", `Saved ${info.name} (${info.events ?? 0} events) — available as replay:${info.name}`);
                refreshLists();
              })
            }
            onFault={(f: Fault) => act(() => consoleApi.simFault(f), `Injected ${f}`)}
          />
        </aside>

        <main className="col-main">
          <nav className="tabs" role="tablist">
            {(
              [
                ["live", "Live"],
                ["acquisition", "Acquisition"],
                ["pipeline", "Pipeline"],
                ["diagnostics", "Diagnostics"],
                ["contract", "Contract"],
                ["tests", "Tests"],
              ] as [Tab, string][]
            ).map(([id, label]) => (
              <button
                key={id}
                role="tab"
                aria-selected={tab === id}
                className={`tab ${tab === id ? "tab-active" : ""}`}
                onClick={() => setTab(id)}
                data-testid={`tab-${id}`}
              >
                {label}
              </button>
            ))}
          </nav>

          {/* Live stays mounted so the embedded app keeps its runtime connection across tabs. */}
          <div className="live" hidden={tab !== "live"}>
              <div className="live-top">
                <Panel
                  title="Application · Communication Board"
                  className="board-panel"
                  right={
                    <a className="muted small" href="/board.html" target="_blank" rel="noreferrer">
                      open in new window ↗
                    </a>
                  }
                >
                  <iframe
                    className="board-frame"
                    src="/board.html"
                    title="Communication Board"
                    data-testid="board-frame"
                  />
                  <p className="muted small">
                    Separate app, separate connection. It uses only the SDK and adapts to whatever capabilities the
                    runtime grants — it contains no device-specific code.
                  </p>
                </Panel>
                {offlineData && runtime ? (
                  <SourcePanel runtime={runtime} busy={busy} act={act} onError={onError} />
                ) : liveDevice ? (
                  <SignalIntegrity meta={live.value} error={live.error} diag={diag} />
                ) : (
                  <IntentPad runtime={runtime} onError={onError} />
                )}
              </div>
              <div className="live-bottom">
                {neuralFeatures ? (
                  <NeuralView neural={data.neural} source="offline" />
                ) : (
                  <SignalView signal={data.signal} runtime={runtime} />
                )}
                <TelemetryPanel telemetry={data.telemetry} runtime={runtime} />
              </div>
              {pipelineFeatures && <NeuralView neural={data.neural} source="pipeline" />}
          </div>
          {tab === "diagnostics" && (
            <DiagnosticsView diag={diag} clientLatencyMs={data.clientLatencyMs} stats={data.stats} />
          )}
          {tab === "acquisition" && (
            <AcquisitionView
              devices={devices}
              runtime={runtime}
              liveMeta={live.value}
              liveError={live.error}
              diag={diag}
              onSourcesChanged={refreshLists}
              notify={notify}
            />
          )}
          {tab === "pipeline" && <PipelineView runtime={runtime} recordings={recordings} notify={notify} />}
          {tab === "contract" && <ContractView devices={devices} onError={onError} />}
          {tab === "tests" && <TestsView onError={onError} />}
        </main>

        <aside className="col-right">
          <EventStream events={data.events} tick={data.tick} />
          <AppsPanel apps={diag?.apps ?? runtime?.apps ?? []} />
        </aside>
      </div>
      <div className="toasts">
        {toasts.map((t) => (
          <div key={t.id} className={`toast toast-${t.tone}`} role="status">
            {t.text}
          </div>
        ))}
      </div>
    </div>
  );
}
