// BrainOS TypeScript SDK — wire types.
// Mirrors contracts/event-envelope.v1.schema.json and backend/src/brainos/contracts/*.py.
// Keep in sync when the schema changes (see CLAUDE.md "Changing contracts").

export const SCHEMA_MAJOR = 1;
export const STREAM_PROTOCOL = "brainos.stream/1";

export const CAPABILITIES = [
  "recording",
  "pointer_intent",
  "selection",
  "text_intent",
  "telemetry",
  "device_status",
  // schema 1.1
  "neural_features",
  "behavior",
  "kinematic_intent",
] as const;
export type Capability = (typeof CAPABILITIES)[number];

export const EVENT_CAPABILITY = {
  "recording.frame": "recording",
  "recording.annotation": "recording",
  "intent.pointer": "pointer_intent",
  "intent.selection": "selection",
  "intent.text": "text_intent",
  "telemetry.sample": "telemetry",
  "device.status": "device_status",
  // schema 1.1
  "features.binned": "neural_features",
  "behavior.sample": "behavior",
  "intent.kinematics": "kinematic_intent",
} as const satisfies Record<string, Capability>;
export type EventType = keyof typeof EVENT_CAPABILITY;

export const PROVENANCE_KINDS = [
  "raw_signal",
  "behavioral_label",
  "simulated_intent",
  "decoded_intent",
  "device_report",
  "runtime",
  "processed_feature", // 1.1
] as const;
export type ProvenanceKind = (typeof PROVENANCE_KINDS)[number];

export const ALLOWED_PROVENANCE: Record<EventType, readonly ProvenanceKind[]> = {
  "recording.frame": ["raw_signal"],
  "recording.annotation": ["behavioral_label"],
  "intent.pointer": ["simulated_intent", "decoded_intent"],
  "intent.selection": ["simulated_intent", "decoded_intent"],
  "intent.text": ["simulated_intent", "decoded_intent"],
  "telemetry.sample": ["device_report"],
  "device.status": ["device_report", "runtime"],
  "features.binned": ["processed_feature"],
  "behavior.sample": ["behavioral_label"],
  "intent.kinematics": ["simulated_intent", "decoded_intent"],
};

export type QualityFlag =
  | "synthetic"
  | "replayed"
  | "low_link_quality"
  | "timestamp_regression"
  | "saturated"
  | "dropped_samples";

export interface Quality {
  score: number;
  flags: QualityFlag[];
}

export interface Provenance {
  kind: ProvenanceKind;
  adapter: string;
  synthetic: boolean;
  model_id: string | null;
  origin: string;
  replayed: boolean;
}

export interface RecordingFramePayload {
  sample_rate_hz: number;
  channel_count: number;
  first_sample_index: number;
  unit: "uV";
  samples: number[][];
}
export interface RecordingAnnotationPayload {
  label: string;
  value: number | string | null;
  duration_ms: number | null;
}
export interface PointerIntentPayload {
  vx: number;
  vy: number;
}
export interface SelectionIntentPayload {
  action: "primary";
  confidence: number;
}
export interface TextIntentPayload {
  text: string;
  mode: "character" | "word";
  confidence: number;
}
export interface TelemetryMetric {
  name: string;
  value: number;
  unit: string;
}
export interface TelemetrySamplePayload {
  metrics: TelemetryMetric[];
}
export type DeviceState =
  | "connected"
  | "streaming"
  | "paused"
  | "reconnecting"
  | "disconnected"
  | "error"
  | "ended";
export interface DeviceStatusPayload {
  state: DeviceState;
  detail: string;
}

export interface FeaturesBinnedPayload {
  feature: "threshold_crossing_count" | "spike_count";
  unit: "count";
  bin_ms: number;
  bin_index: number;
  channel_count: number;
  counts: number[];
}
export interface BehaviorSamplePayload {
  quantity: string;
  dims: string[];
  unit: string;
  values: number[];
  sample_index: number;
  valid: boolean;
}
export interface KinematicIntentPayload {
  quantity: string;
  dims: string[];
  unit: string;
  values: number[];
  space: string;
}

export interface PayloadByType {
  "recording.frame": RecordingFramePayload;
  "recording.annotation": RecordingAnnotationPayload;
  "intent.pointer": PointerIntentPayload;
  "intent.selection": SelectionIntentPayload;
  "intent.text": TextIntentPayload;
  "telemetry.sample": TelemetrySamplePayload;
  "device.status": DeviceStatusPayload;
  "features.binned": FeaturesBinnedPayload;
  "behavior.sample": BehaviorSamplePayload;
  "intent.kinematics": KinematicIntentPayload;
}

interface EnvelopeBase {
  schema_version: string;
  session_id: string;
  device_id: string;
  seq: number;
  timestamp_ns: number;
  device_timestamp_ns: number | null;
  quality: Quality;
  provenance: Provenance;
}

export type EventEnvelope = {
  [T in EventType]: EnvelopeBase & {
    event_type: T;
    capability: (typeof EVENT_CAPABILITY)[T];
    payload: PayloadByType[T];
  };
}[EventType];

export type EnvelopeOf<T extends EventType> = Extract<EventEnvelope, { event_type: T }>;

// ------------------------------------------------------------------ protocol

export interface CapabilityDescriptor {
  capability: Capability;
  params: Record<string, number | string | boolean | string[]>;
  description: string;
}

export interface DeviceDescriptor {
  device_id: string;
  display_name: string;
  kind: "simulated" | "replay" | "hardware";
  adapter: string;
  description: string;
  native_format: string;
  capabilities: CapabilityDescriptor[];
  synthetic: boolean;
}

export type AppStatus = "active" | "suspended" | "no_device";

export interface CapabilityRejection {
  capability: Capability;
  reason: "unsupported_by_device" | "no_device";
  required: boolean;
}

export interface NegotiationResult {
  device_id: string | null;
  status: AppStatus;
  granted: Capability[];
  rejected: CapabilityRejection[];
}

export interface AppInfo {
  id: string;
  name: string;
  kind?: "application" | "console" | "sdk";
}

export type RuntimeState =
  | "idle"
  | "connecting"
  | "streaming"
  | "paused"
  | "reconnecting"
  | "disconnecting"
  | "error"
  | "ended";

export interface ConnectedApp {
  connection_id: string;
  app: Required<AppInfo>;
  negotiation: NegotiationResult;
  connected_at_ns: number;
  delivered: number;
  dropped: number;
  queue_depth: number;
}

export interface RuntimeSnapshot {
  state: RuntimeState;
  device: DeviceDescriptor | null;
  session_id: string | null;
  state_since_ns: number;
  last_error: string | null;
  recording: string | null;
  apps: ConnectedApp[];
}

// ------------------------------------------------------------- offline sources

export interface PlaybackStatus {
  device_id: string;
  speed: number;
  position_s: number;
  duration_s: number | null;
  loops: number;
  loop: boolean;
  paused: boolean;
  records_emitted: number;
  origin: string;
}

export interface SourceMetadata {
  device_id: string;
  label: string;
  source_type: "nwb_units";
  live: false;
  dataset: {
    id: string;
    title: string;
    dandiset: string;
    version: string;
    url: string;
    license: string;
    access: string;
    citation: string;
    asset_id: string;
    asset_path: string;
  } | null;
  file: { name: string; size_bytes: number; sha256: string; verified: boolean; verification: string };
  species: string | null;
  subject_id: string | null;
  identifier: string;
  session_description: string;
  session_start_time: string;
  experiment_description: string;
  institution: string;
  lab: string;
  recording_type: string;
  profile: string;
  feature: string;
  feature_unit: string;
  bin_ms: number;
  n_bins: number;
  duration_s: number;
  channel_count: number;
  channels: { index: number; unit_id: number; spike_count: number; electrode: string | null }[];
  behavior: { series: string; quantity: string; dims: string[]; unit: string; valid_fraction: number } | null;
  decoder: {
    model_id: string;
    method: string;
    dims: string[];
    alpha: number;
    trained_on: string;
    evaluated_r2: number | null;
    evaluated_samples: number | null;
    control_mean_predictor_r2: number | null;
    control_time_shift_r2: number | null;
  } | null;
  notes: string[];
}

export type ServerMessage =
  | {
      type: "welcome";
      protocol: string;
      schema_version: string;
      connection_id: string;
      negotiation: NegotiationResult;
      runtime: RuntimeSnapshot;
    }
  | { type: "event"; delivery_seq: number; event: unknown }
  | { type: "negotiation"; negotiation: NegotiationResult }
  | { type: "runtime"; runtime: RuntimeSnapshot }
  | { type: "error"; code: string; message: string }
  | { type: "pong"; nonce: unknown; server_ns: number };
