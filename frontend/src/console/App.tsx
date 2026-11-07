import { useCallback, useEffect, useRef, useState } from "react";
import { BrainOSApiError, runtimeApi, type DeviceDescriptor } from "../sdk";
import { consoleApi, type DiagnosticsSnapshot, type Fault, type RecordingInfo } from "./api";
import { AppsPanel } from "./components/AppsPanel";
import { ContractView } from "./components/ContractView";
import { ControlsPanel } from "./components/ControlsPanel";
import { DevicesPanel } from "./components/DevicesPanel";
import { DiagnosticsView } from "./components/DiagnosticsView";
import { EventStream } from "./components/EventStream";
import { Header } from "./components/Header";
import { IntentPad } from "./components/IntentPad";
import { SignalView, TelemetryPanel } from "./components/SignalView";
import { TestsView } from "./components/TestsView";
import { Panel } from "./components/ui";
import { useConsoleStream } from "./useConsoleStream";

type Tab = "live" | "diagnostics" | "contract" | "tests";
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

  useEffect(refreshLists, [refreshLists, runtime?.recording]);

  useEffect(() => {
    let alive = true;
    const poll = () =>
      consoleApi
        .diagnostics()
        .then((d) => alive && setDiag(d))
        .catch(() => undefined);
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
            onStartRecording={() => act(() => consoleApi.startRecording(), "Recording started")}
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
                <IntentPad runtime={runtime} onError={onError} />
              </div>
              <div className="live-bottom">
                <SignalView signal={data.signal} runtime={runtime} />
                <TelemetryPanel telemetry={data.telemetry} runtime={runtime} />
              </div>
          </div>
          {tab === "diagnostics" && (
            <DiagnosticsView diag={diag} clientLatencyMs={data.clientLatencyMs} stats={data.stats} />
          )}
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
