// The operator console: one session screen. Title bar (status + Stop control), four rows
// (acquisition source, signal integrity, decoder, command output), the session log, and a
// single collapsed "Advanced" section for technical detail.

import { useCallback, useEffect, useRef, useState } from "react";
import { runtimeApi, type DeviceDescriptor } from "../sdk";
import { consoleApi, isLiveSource, labApi, type DiagnosticsSnapshot, type RecordingInfo } from "./api";
import { Advanced } from "./components/Advanced";
import { ControlRow } from "./components/ControlRow";
import { DecoderRow } from "./components/DecoderRow";
import { IntegrityRow, type IntegrityFigures } from "./components/IntegrityRow";
import { SessionLogView } from "./components/SessionLogView";
import { SourcePicker } from "./components/SourcePicker";
import { SourceRow } from "./components/SourceRow";
import { TitleBar } from "./components/TitleBar";
import { LogContext } from "./context";
import { useAction, usePoll } from "./hooks";
import { LossTracker, dataReceived, integrityVerdict, lossTotal } from "./integrity";
import { controlOn, mappingText, stopSpec, usePipeline } from "./pipeline";
import { ERRORS_COVERED_BY_STATUS, errorEntry, statusEntry, useSessionLog } from "./sessionLog";
import { percentile, useConsoleStream } from "./useConsoleStream";
import { declaredChannels, hasCapability, presetLabel } from "./wording";

export function App() {
  const data = useConsoleStream();
  const { runtime } = data;
  const log = useSessionLog();
  const [devices, setDevices] = useState<DeviceDescriptor[]>([]);
  const [recordings, setRecordings] = useState<RecordingInfo[]>([]);
  const [diag, setDiag] = useState<DiagnosticsSnapshot | null>(null);
  const [picker, setPicker] = useState(false);
  const pipeline = usePipeline();
  const stopAction = useAction((text) => log.add("info", `Refused: ${text}`));

  const refreshLists = useCallback(() => {
    runtimeApi
      .devices()
      .then(setDevices)
      .catch(() => {});
    consoleApi
      .recordings()
      .then(setRecordings)
      .catch(() => {});
  }, []);

  // Waits for the stream, so an outage shows no errors and lists refresh on reconnect.
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

  const connected = !!runtime?.device && runtime.state !== "idle";
  const device = connected ? (runtime?.device ?? null) : null;
  const session = connected ? (runtime?.session_id ?? null) : null;
  const liveDevice = device && isLiveSource(device) ? device.device_id : null;
  const live = usePoll(liveDevice, () => labApi.liveSource(liveDevice ?? ""), 1000);
  const pst = pipeline.status;

  // ------------------------------------------------------------ signal integrity (measured)
  const loss = useRef(new LossTracker());
  const now = Date.now();
  const pipelineHere = !!pst?.running && pst.session_id === session;
  const lossKey = session === null ? null : `${session}|${liveDevice ? (live.value ? "m" : "-") : ""}|${diag ? "d" : "-"}`;
  const msSinceLoss = loss.current.update(
    lossKey,
    lossTotal({
      liveMeta: live.value,
      pipelineDropped: pipelineHere ? (pst?.counters.dropped_inputs ?? 0) : 0,
      subscriberDrops: diag?.counters.subscriber_drops ?? 0,
      streamMissed: data.stats.missedEvents,
    }),
    now,
  );
  const lastData = data.lastData && data.lastData.session === session ? data.lastData : null;
  const rawHere = hasCapability(device, "recording") && session !== null && data.signal.key.startsWith(`${session}:`);
  const binnedHere = session !== null && data.neural.session === session && data.neural.bins.length > 0;
  const figures: IntegrityFigures = {
    verdict: integrityVerdict({
      connected,
      state: runtime?.state ?? null,
      msSinceData: lastData ? now - lastData.at : null,
      msSinceLoss,
    }),
    channels: { latest: lastData?.channels ?? null, declared: declaredChannels(device) },
    received: liveDevice ? dataReceived(live.value) : null,
    delayMs: percentile(data.clientLatencyMs, 0.5),
    traces: rawHere ? "raw" : binnedHere ? "binned" : null,
  };

  // ------------------------------------------------------------ session log sources
  const add = log.add;
  const prevConn = useRef(data.conn);
  useEffect(() => {
    const before = prevConn.current;
    prevConn.current = data.conn;
    if (data.conn === before) return;
    if (data.conn === "open") add("info", before === "reconnecting" ? "Reconnected to BrainOS" : "Console connected to BrainOS");
    else if (data.conn === "reconnecting" && before === "open") add("caution", "Connection to BrainOS lost, reconnecting");
    else if (data.conn === "closed" || data.conn === "rejected") add("caution", "Not connected to BrainOS");
  }, [data.conn, add]);

  const statusSeen = useRef(0);
  const lastStatusErrorAt = useRef(0);
  useEffect(() => {
    const st = data.statusEvents;
    const fresh = Math.min(st.total - statusSeen.current, st.list.length);
    statusSeen.current = st.total;
    for (const e of st.list.slice(st.list.length - fresh)) {
      const { tone, text } = statusEntry(e.payload);
      if (e.payload.state === "error") lastStatusErrorAt.current = Date.now();
      add(tone, text, e.timestamp_ns / 1e6);
    }
  }, [data.tick, data.statusEvents, add]);

  const prevRt = useRef<{ state: string | null; recording: string | null }>({ state: null, recording: null });
  useEffect(() => {
    const prev = prevRt.current;
    const state = runtime?.state ?? null;
    const recording = runtime?.recording ?? null;
    prevRt.current = { state, recording };
    if (runtime === null) return;
    // reconnect failures already arrive as a device.status error event; other failures do not
    if (state === "error" && prev.state !== "error" && Date.now() - lastStatusErrorAt.current > 3000)
      add("alarm", `Source stopped: ${runtime.last_error ?? "error"}`);
    if (recording && recording !== prev.recording) add("info", `Recording started: ${recording}`);
    if (!recording && prev.recording) add("info", `Recording stopped: ${prev.recording}`);
  }, [runtime, add]);

  const prevPl = useRef<{ running: boolean; router: boolean } | null>(null);
  useEffect(() => {
    if (!pst) return;
    const cur = { running: pst.running, router: controlOn(pst) };
    const prev = prevPl.current;
    prevPl.current = cur;
    if (!prev) return; // first observation is the baseline, not an event
    if (cur.running && !prev.running)
      add("info", `Decoding started: ${presetLabel(pst.preset)}${pst.decoder ? `, model ${pst.decoder.model_id}` : ", no model"}`);
    if (!cur.running && prev.running) add("info", "Decoding stopped");
    if (cur.router && !prev.router && pst.router) add("info", `Control started: ${mappingText(pst.router)}`);
    if (!cur.router && prev.router) add("info", "Control stopped");
  }, [pst, add]);

  const errorsSince = useRef(Date.now() * 1e6);
  useEffect(() => {
    if (!diag) return;
    const fresh = diag.recent_errors.filter((e) => e.at_ns > errorsSince.current);
    if (!fresh.length) return;
    errorsSince.current = Math.max(...fresh.map((e) => e.at_ns));
    for (const e of fresh) {
      if (ERRORS_COVERED_BY_STATUS.has(e.kind)) continue;
      const { tone, text } = errorEntry(e.kind, e.message);
      add(tone, text, e.at_ns / 1e6);
    }
  }, [diag, add]);

  // ------------------------------------------------------------ stop control (title bar)
  const on = controlOn(pst);
  const stopControl = async () => {
    const spec = stopSpec(pst);
    // /control/stop: command output off now (idempotent); queued commands are withdrawn
    const r = await stopAction.run(() => labApi.stopControl("stopped by operator (console)"));
    if (r && pst && spec) pipeline.set({ ...pst, router: spec });
  };

  const apps = diag?.apps ?? runtime?.apps ?? [];
  const closePicker = useCallback(() => setPicker(false), []);

  return (
    <LogContext.Provider value={add}>
      <div className="shell">
        <TitleBar conn={data.conn} runtime={runtime} controlOn={on} stopping={stopAction.busy} onStopControl={stopControl} />
        <main className="session">
          <div className="session-grid">
            <div className="rows">
              <SourceRow runtime={runtime} onPick={() => setPicker(true)} />
              <IntegrityRow connected={connected} f={figures} signal={data.signal} neural={data.neural} />
              <DecoderRow
                runtime={runtime}
                pipeline={pipeline}
                recordings={recordings}
                replayedModel={!pipelineHere && binnedHere && data.neural.decoded.size > 0 ? data.neural.modelId : null}
                onRecordingsChanged={refreshLists}
              />
              <ControlRow pipeline={pipeline} apps={apps} />
            </div>
            <SessionLogView entries={log.entries} />
          </div>
          <Advanced
            data={data}
            devices={devices}
            diag={diag}
            pipeline={pipeline}
            recordings={recordings}
            liveMeta={live.value}
            liveError={live.error}
            stats={data.stats}
            onRecordingsChanged={refreshLists}
          />
        </main>
        {picker && (
          <SourcePicker devices={devices} runtime={runtime} onClose={closePicker} onSourcesChanged={refreshLists} />
        )}
      </div>
    </LogContext.Provider>
  );
}
