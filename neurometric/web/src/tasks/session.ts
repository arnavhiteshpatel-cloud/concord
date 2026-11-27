// One task run = one canonical event session (session_id), the upload unit for the backend's
// functional_sessions table. Holds the recorder, the marker / control streams and metadata.

import { EventRecorder, StreamHandle, newId } from "../input/recorder";
import type { InputEvent, Modality } from "../input/types";
import { checkStream, type StreamReport } from "../input/types";
import type { SessionMetadata } from "../input/metadata";
import type { Settings } from "../a11y/settings";
import type { Stimuli } from "./stimuli";
import { ASSIST_TYPES, type AssistType } from "../input/types";

export type Provenance = "live" | "simulated" | "replayed";

export interface ProvisionalSummary {
  /** Human-readable label/value pairs for the results screen. */
  rows: [string, string][];
  values: Record<string, number | string | boolean | null>;
}

export interface TaskRun {
  format: "neurometric.web-session/1";
  session_id: string;
  task_id: string;
  battery_version: string;
  stimulus_seed: number;
  stimulus_hash: string;
  modality: Modality;
  selection_method: string;
  provenance: Provenance;
  participant_code: string | null;
  started_at_epoch_ms: number;
  completed: boolean;
  settings: Record<string, unknown>;
  metadata: SessionMetadata | null;
  stream_report: StreamReport;
  provisional: ProvisionalSummary | null;
  events: InputEvent[];
}

export class TaskSession {
  readonly rec: EventRecorder;
  readonly task: StreamHandle;
  readonly ctl: StreamHandle;
  readonly startedAtEpoch = Date.now();
  trialIndex: number | null = null;
  inTrial = false;
  assistsInTrial = 0;
  completed = false;
  metadata: SessionMetadata | null = null;

  constructor(
    readonly stim: Stimuli,
    readonly settings: Settings,
    readonly modality: Modality,
    readonly provenance: Provenance = "live",
  ) {
    this.rec = new EventRecorder({ sessionId: newId("sess"), allowText: stim.task_id === "E1" });
    this.task = this.rec.stream("task", "other");
    this.ctl = this.rec.stream("ctl", "other");
  }

  now(): number {
    return this.rec.clock.now();
  }

  marker(marker: string, meta: Record<string, unknown> = {}, t?: number): InputEvent | null {
    if (marker === "stimulus_on" || marker === "phrase_start") {
      this.inTrial = true;
      this.assistsInTrial = 0;
      if (typeof meta.trial === "number") this.trialIndex = meta.trial;
    }
    if (marker === "trial_end" || marker === "phrase_end") this.inTrial = false;
    return this.task.emit({ kind: "marker", meta: { marker, ...meta } }, t === undefined ? {} : { t });
  }

  pause(reason = "participant"): void {
    if (this.rec.paused) return;
    this.ctl.emit({ kind: "pause", meta: { reason, trial: this.trialIndex } });
    this.rec.paused = true;
  }

  resume(): void {
    if (!this.rec.paused) return;
    this.rec.paused = false;
    this.ctl.emit({ kind: "resume", meta: { trial: this.trialIndex } });
  }

  assist(type: AssistType, by: string, note?: string): void {
    if (!ASSIST_TYPES.includes(type)) throw new Error("bad assist type");
    const wasPaused = this.rec.paused;
    this.rec.paused = false; // control events are recorded even while paused
    this.ctl.emit({ kind: "assist", meta: { assist_type: type, by, in_trial: this.inTrial, trial: this.trialIndex, ...(note ? { note } : {}) } });
    this.rec.paused = wasPaused;
    if (this.inTrial) this.assistsInTrial++;
  }

  toRun(provisional: ProvisionalSummary | null): TaskRun {
    const events = this.rec.merged().slice();
    const s = this.settings;
    return {
      format: "neurometric.web-session/1",
      session_id: this.rec.sessionId,
      task_id: this.stim.task_id,
      battery_version: this.stim.battery_version,
      stimulus_seed: this.stim.seed,
      stimulus_hash: this.stim.stimulus_hash,
      modality: this.modality,
      selection_method: s.selection,
      provenance: this.provenance,
      participant_code: s.participantCode || null,
      started_at_epoch_ms: this.startedAtEpoch,
      completed: this.completed,
      settings: {
        selection: s.selection, dwell_ms: s.dwellMs, switch: s.switch, no_time_pressure: s.noTimePressure,
        time_multiplier: s.timeMultiplier, target_min_px: s.targetMinPx, short: s.short, motion: s.motion,
        theme: s.theme, text_scale: s.textScale, declared_modality: s.modality,
      },
      metadata: this.metadata,
      stream_report: checkStream(events),
      provisional,
      events,
    };
  }
}
