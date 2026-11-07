// Pipeline tab: processing pipeline, decoder models, command router and calibration.

import { useCallback, useEffect, useState } from "react";
import type { RuntimeSnapshot } from "../../sdk";
import {
  labApi,
  type CalibrationResult,
  type ModelInfo,
  type PipelineStartRequest,
  type PipelineStatus,
  type RecordingInfo,
  type RouterSpec,
} from "../api";
import { useAction, usePoll } from "../hooks";
import { CalibrationPanel } from "./CalibrationPanel";
import { PipelineControl } from "./PipelineControl";
import { PipelineStatusPanel } from "./PipelineStatusPanel";
import { RouterPanel } from "./RouterPanel";
import { Panel } from "./ui";

export function PipelineView({
  runtime,
  recordings,
  notify,
}: {
  runtime: RuntimeSnapshot | null;
  recordings: RecordingInfo[];
  notify: (text: string) => void;
}) {
  const [presets, setPresets] = useState<Record<string, string>>({});
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [override, setOverride] = useState<PipelineStatus | null>(null);
  const poll = usePoll("pipeline", labApi.pipeline, 1000);
  const status = override ?? poll.value;
  const pipeline = useAction();
  const router = useAction();

  useEffect(() => setOverride(null), [poll.value]); // a fresh poll supersedes an action's response

  const refreshModels = useCallback(() => {
    labApi
      .models()
      .then(setModels)
      .catch(() => setModels([]));
  }, []);

  useEffect(() => {
    labApi
      .presets()
      .then(setPresets)
      .catch(() => setPresets({}));
  }, []);

  // model compatibility is evaluated against the running pipeline's output
  const outputKey = status?.running ? JSON.stringify([status.started_at_ns, status.output]) : "stopped";
  useEffect(refreshModels, [refreshModels, outputKey]);

  const canStart = runtime?.state === "streaming" || runtime?.state === "paused";

  const start = async (req: PipelineStartRequest) => {
    const st = await pipeline.run(() => labApi.startPipeline(req));
    if (!st) return;
    setOverride(st);
    notify(`Pipeline started: ${st.preset}${st.decoder ? ` + ${st.decoder.model_id}` : ""}`);
  };
  const stop = async () => {
    const st = await pipeline.run(() => labApi.stopPipeline());
    if (st) setOverride(st);
  };
  const applyRouter = async (r: RouterSpec) => {
    const st = await router.run(() => labApi.setRouter(r));
    if (!st) return;
    setOverride(st);
    notify(r.enabled ? `Router ON: ${r.x_dim}/${r.y_dim} → pointer` : "Router OFF");
  };
  const trained = (r: CalibrationResult) => {
    notify(`Model ${r.model.model_id} saved`);
    refreshModels();
  };

  return (
    <div className="lab" data-testid="pipeline-view">
      <div className="lab-grid">
        <Panel title="Processing pipeline" testId="pipeline-panel">
          <PipelineControl
            presets={presets}
            models={models}
            status={status}
            canStart={canStart}
            busy={pipeline.busy}
            error={pipeline.error}
            onStart={start}
            onStop={stop}
          />
        </Panel>
        <Panel title="Pipeline status" right={<span className="muted small">polled 1 s</span>}>
          {poll.error && !status ? <div className="alert">{poll.error}</div> : <PipelineStatusPanel status={status} />}
        </Panel>
      </div>
      <div className="lab-grid">
        <Panel title="Command router">
          <RouterPanel status={status} busy={router.busy} error={router.error} onApply={applyRouter} />
        </Panel>
        <Panel title="Calibration">
          <CalibrationPanel recordings={recordings} onTrained={trained} />
        </Panel>
      </div>
    </div>
  );
}
