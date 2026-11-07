// Console-only API wrappers: diagnostics, recordings, test reports, the simulation
// operator endpoints, and (Milestone 3) live sources, the processing pipeline,
// decoder models and calibration. Applications never use these.

import { apiCall, type ConnectedApp, type DeviceDescriptor, type PlaybackStatus, type SourceMetadata } from "../sdk";

export interface LatencySummary {
  count: number;
  p50_us: number | null;
  p95_us: number | null;
  p99_us: number | null;
  max_us: number | null;
}

export interface DiagnosticsSnapshot {
  uptime_s: number;
  measured_at_ns: number;
  counters: {
    events_published: number;
    decode_errors: number;
    validation_errors: number;
    undeclared_capability: number;
    timestamp_regressions: number;
    discarded_while_paused: number;
    link_errors: number;
    reconnect_attempts: number;
    reconnect_successes: number;
    subscriber_drops: number;
  };
  event_types: { event_type: string; total: number; rate_hz: number }[];
  pipeline_latency: LatencySummary;
  delivery_latency: LatencySummary;
  switches: { from_device: string | null; to_device: string; duration_ms: number; at_ns: number }[];
  recent_errors: { at_ns: number; kind: string; device_id: string | null; message: string }[];
  apps: ConnectedApp[];
  process: Record<string, string>;
}

export interface RecordingInfo {
  name: string;
  device_id: string;
  device_name: string;
  synthetic: boolean;
  created_at_ns: number;
  size_bytes: number;
  events: number | null;
  active: boolean;
  /** M5-D: false for a recording interrupted by a crash or kill (its valid prefix is kept) */
  complete?: boolean;
  recovery?: { status: string; reason: string; valid_events: number; discarded_bytes: number } | null;
}

export interface TestCase {
  suite: string;
  name: string;
  status: "passed" | "failed" | "skipped";
  time_s: number;
  message: string | null;
}

export interface TestReport {
  name: string;
  source: string;
  available: boolean;
  generated_at_ns: number | null;
  total: number;
  passed: number;
  failed: number;
  skipped: number;
  duration_s: number;
  cases: TestCase[];
  error: string | null;
}

export interface CapabilityInfo {
  capability: string;
  description: string;
  event_types: string[];
}

export type Fault = "link_drop" | "link_fail" | "malformed_packet" | "timestamp_regression";

// ------------------------------------------------------------------ Milestone 3: live sources
// Shapes mirror backend/src/brainos/server/live_routes.py and runtime/pipeline.py.

export interface LSLStreamInfo {
  key: string;
  device_id: string | null;
  name: string;
  type: string;
  source_id: string | null;
  hostname: string;
  channel_count: number;
  nominal_srate: number;
  channel_format: string;
  channels_described: boolean;
  units: (string | null)[];
  declared_prerecorded: boolean | null;
  declared_synthetic: boolean | null;
  usable_as_signal: boolean;
  reason: string | null;
}

export interface LSLDiscovery {
  library: string | null;
  discovered_at_ns: number | null;
  streams: LSLStreamInfo[];
  error: string | null;
}

export type OpenEphysUnit = "unknown" | "uV" | "mV" | "V";
export interface OpenEphysConfigInput {
  host: string;
  data_port: number;
  unit: OpenEphysUnit;
}

/** `/devices/{id}/source` for a live source: the adapter's own metadata dict (shape differs per protocol). */
export type LiveSourceMetadata = Record<string, unknown>;

// ------------------------------------------------------------------ Milestone 4: source plugins
// Shapes mirror backend/src/brainos/server/plugin_routes.py.

export type OptionValue = string | number | boolean | null;

export interface PluginOptionInfo {
  name: string;
  type: "str" | "int" | "float" | "bool" | "choice";
  description: string;
  default: OptionValue;
  required: boolean;
  choices: string[];
}

export interface PluginProblem {
  code: string;
  message: string;
  severity: "error" | "warning" | "info";
  where: string;
}

export interface PluginDeviceInfo {
  device_key: string;
  display_name: string;
  description: string;
  details: Record<string, string>;
  /** null when no valid BrainOS device id can be formed (reason says why) */
  device_id: string | null;
  reason: string | null;
  configured: boolean;
}

export interface PluginInfo {
  name: string;
  entry: string;
  package: string | null;
  package_version: string | null;
  status: "compatible" | "rejected" | "load_error";
  reason: string | null;
  display_name: string | null;
  description: string | null;
  version: string | null;
  api_version: string | null;
  author: string | null;
  license: string | null;
  homepage: string | null;
  ecosystem: string | null;
  network: boolean | null;
  roles: string[];
  options: PluginOptionInfo[];
  problems: PluginProblem[];
  error: { type: string; message: string; traceback: string | null } | null;
  devices: PluginDeviceInfo[];
  discovery_error: string | null;
  log_tail: string[];
}

export interface PluginsStatus {
  host_api_version: string;
  sdk_version: string;
  python: string;
  discovering: boolean;
  discovered_at_ns: number | null;
  error: string | null;
  plugins: PluginInfo[];
}

// ------------------------------------------------------------------ pipeline

export type PresetName = "spikeband_threshold" | "ecog_high_gamma" | "band_power" | "features_passthrough";

export interface ProcessingSpecInput {
  preset: PresetName;
  bin_ms?: number;
  threshold_k?: number;
  band_low_hz?: number;
  band_high_hz?: number;
}

export type DiscreteAction = "primary" | "activate" | "cancel" | "text";

/** One discrete action from a classifier's class posterior (Milestone 4). */
export interface DiscreteRule {
  output: string;
  threshold: number;
  release?: number | null;
  hold_ms: number;
  refractory_ms: number;
  action: DiscreteAction;
  text?: string | null;
}

export interface RouterSpec {
  enabled: boolean;
  /** pointer mapping (continuous decoders); both or neither */
  x_dim: string | null;
  y_dim: string | null;
  gain: number;
  deadzone: number;
  invert_y: boolean;
  max_speed: number;
  /** discrete actions (classifier decoders) */
  discrete?: DiscreteRule[];
  stall_ms?: number;
}

export interface PipelineStartRequest {
  processing: ProcessingSpecInput;
  model_id: string | null;
  allow_cross_source: boolean;
  router?: RouterSpec | null;
}

export interface LatencyStats {
  count: number;
  p50: number | null;
  p95: number | null;
  p99: number | null;
  max: number | null;
}

export interface PipelineOutputSpec {
  event_type: string;
  feature: string;
  bin_ms: number;
  channel_count: number;
  channel_labels: string[] | null;
  unit: string;
}

export interface ModelSummary {
  model_id: string;
  /** Milestone 4: classifiers output class posteriors (dims = class names) */
  outputs?: { type: "classes"; classes: string[] } | { type: "continuous" };
  held_out_balanced_accuracy?: number | null;
  chance_balanced_accuracy?: number | null;
  method?: string;
  space?: string;
  dims: string[];
  unit?: string;
  input?: { event_type?: string; feature?: string; bin_ms?: number; channel_count?: number; inferred?: boolean };
  source_identity?: string | null;
  trained_on?: string | null;
  training_session?: string | null;
  held_out_r2?: number | null;
  held_out_samples?: number | null;
  control_mean_predictor_r2?: number | null;
  created_at?: string;
}

export interface PipelineStatus {
  available: boolean;
  unavailable_reason: string | null;
  running: boolean;
  device_id: string | null;
  session_id: string | null;
  preset: string | null;
  stages: string[];
  input_event_type: string | null;
  output: PipelineOutputSpec | null;
  warmup_remaining_s: number;
  decoder: ModelSummary | null;
  compatibility_warnings: string[];
  cross_source_override: boolean;
  router: RouterSpec | null;
  counters: Record<string, number>;
  processing_us: LatencyStats;
  pipeline_latency_ms: LatencyStats;
  last_error: string | null;
  started_at_ns: number | null;
  // Milestone 4
  router_capabilities?: string[];
  stall_limit_ms?: number | null;
  last_router_stop?: RouterEvent | null;
  router_log?: RouterEvent[];
}

export interface RouterEvent {
  at_ns: number;
  on: boolean;
  reason: string;
}

// ------------------------------------------------------------------ control bridge (M4)
// Shapes mirror backend/src/brainos/server/control_routes.py.

export type CommandCapability = "pointer_intent" | "selection" | "text_intent";

export interface AppControl {
  app_id: string;
  name: string | null;
  kind: "application" | "console" | "sdk" | null;
  connections: number;
  status: "active" | "suspended" | "no_device" | null;
  requested: CommandCapability[];
  required: CommandCapability[];
  authorized: CommandCapability[];
  authorized_at_ns: number | null;
  receiving: CommandCapability[];
  waiting: { capability: CommandCapability; reason: "unsupported_by_device" | "no_device" | "not_authorized"; required: boolean }[];
  refused_commands: number;
}

export interface ControlEvent {
  at_ns: number;
  kind: "authorized" | "revoked" | "router_on" | "router_off";
  app_id: string | null;
  capabilities: string[];
  detail: string;
}

export interface ControlStatus {
  router_on: boolean;
  model_id: string | null;
  provides: CommandCapability[];
  router: RouterSpec | null;
  stall_limit_ms: number | null;
  last_stop: RouterEvent | null;
  apps: AppControl[];
  history: ControlEvent[];
}

export interface ModelInfo {
  summary: ModelSummary;
  /** null: no pipeline running, so there is no output to check against yet */
  compatible: boolean | null;
  errors: string[];
  warnings: string[];
}

export interface CalibrationRequest {
  recordings: string[];
  train_fraction?: number;
  gap_bins?: number;
  feature_source?: string | null;
  /** "classifier": LDA on a class-label behavior stream (Milestone 4) */
  kind?: "regression" | "classifier";
  label_dim?: string | null;
  class_names?: string[] | null;
}

export interface CalibrationReport {
  model_id: string;
  recordings: string[];
  source_identity: string | null;
  prerecorded_source: boolean;
  synthetic_source: boolean;
  bins_total: number;
  labelled_bins: number;
  train_bins: number;
  gap_bins: number;
  test_bins: number;
  alpha: number;
  samples: number;
  r2: number;
  r2_per_dim: Record<string, number>;
  control_mean_predictor_r2: number;
  control_time_shift_r2?: number;
  control_time_shift_max_r2?: number;
  beats_all_shifts?: boolean;
}

export interface CalibrationResult {
  model: ModelSummary;
  report: CalibrationReport;
  report_markdown: string;
}

const enc = encodeURIComponent;

export const labApi = {
  lslStreams: () => apiCall<LSLDiscovery>("/sources/lsl"),
  lslDiscover: (wait_s = 1.5) => apiCall<LSLDiscovery>("/sources/lsl/discover", { method: "POST", body: { wait_s } }),
  lslRegister: (signal: string, behavior: string | null, markers: string | null) =>
    apiCall<DeviceDescriptor>("/sources/lsl", { method: "POST", body: { signal, behavior, markers } }),
  openEphysRegister: (config: OpenEphysConfigInput) =>
    apiCall<DeviceDescriptor>("/sources/openephys", { method: "POST", body: config }),
  plugins: () => apiCall<PluginsStatus>("/plugins"),
  discoverPlugins: () => apiCall<PluginsStatus>("/plugins/discover", { method: "POST", body: {} }),
  configurePlugin: (name: string, deviceKey: string, options: Record<string, OptionValue>) =>
    apiCall<DeviceDescriptor>(`/plugins/${enc(name)}/configure`, {
      method: "POST",
      body: { device_key: deviceKey, options },
    }),
  removeSource: (deviceId: string) => apiCall<{ removed: boolean }>(`/sources/${enc(deviceId)}`, { method: "DELETE" }),
  liveSource: (deviceId: string) => apiCall<LiveSourceMetadata>(`/devices/${enc(deviceId)}/source`),
  pipeline: () => apiCall<PipelineStatus>("/pipeline"),
  presets: () => apiCall<Record<string, string>>("/pipeline/presets"),
  startPipeline: (req: PipelineStartRequest) =>
    apiCall<PipelineStatus>("/pipeline/start", { method: "POST", body: req }),
  stopPipeline: () => apiCall<PipelineStatus>("/pipeline/stop", { method: "POST" }),
  setRouter: (router: RouterSpec) => apiCall<PipelineStatus>("/pipeline/router", { method: "POST", body: router }),
  control: () => apiCall<ControlStatus>("/control"),
  authorizeApp: (appId: string, capabilities: CommandCapability[]) =>
    apiCall<ControlStatus>(`/control/apps/${enc(appId)}/authorize`, { method: "POST", body: { capabilities } }),
  revokeApp: (appId: string) => apiCall<ControlStatus>(`/control/apps/${enc(appId)}/revoke`, { method: "POST" }),
  stopControl: (reason?: string) =>
    apiCall<ControlStatus>("/control/stop", { method: "POST", body: reason ? { reason } : undefined }),
  models: () => apiCall<ModelInfo[]>("/models"),
  calibrate: (req: CalibrationRequest) =>
    apiCall<CalibrationResult>("/calibration/train", { method: "POST", body: req }),
};

const LIVE_PREFIXES = ["lsl:", "openephys:"];

/** A source registered at runtime (LSL / Open Ephys), as opposed to simulators and local files. */
export function isLiveSource(device: Pick<DeviceDescriptor, "device_id"> | null | undefined): boolean {
  return !!device && LIVE_PREFIXES.some((p) => device.device_id.startsWith(p));
}

/** A device provided by an installed source plugin (adapter SDK), run in its own process. */
export function isPluginSource(device: Pick<DeviceDescriptor, "device_id"> | null | undefined): boolean {
  return !!device && device.device_id.startsWith("plugin:");
}

/** Offline dataset files (verified NWB) — the only sources with dataset SourceMetadata + playback. */
export function isDatasetFile(device: Pick<DeviceDescriptor, "device_id"> | null | undefined): boolean {
  return !!device && device.device_id.startsWith("nwb:");
}

/** The recorder refuses local file players; every other connected source can be recorded. */
export function isRecordable(device: Pick<DeviceDescriptor, "device_id"> | null | undefined): boolean {
  return !!device && !device.device_id.startsWith("replay:") && !device.device_id.startsWith("nwb:");
}

export const consoleApi = {
  diagnostics: () => apiCall<DiagnosticsSnapshot>("/diagnostics"),
  recordings: () => apiCall<RecordingInfo[]>("/recordings"),
  /** excludeRaw: record everything except recording.frame (features, labels, markers, decoded output). */
  startRecording: (name?: string, excludeRaw = false) =>
    apiCall<{ name: string }>("/recordings/start", {
      method: "POST",
      body: { ...(name ? { name } : {}), ...(excludeRaw ? { exclude_raw: true } : {}) },
    }),
  stopRecording: () => apiCall<RecordingInfo>("/recordings/stop", { method: "POST" }),
  tests: () => apiCall<TestReport[]>("/system/tests"),
  capabilities: () => apiCall<CapabilityInfo[]>("/capabilities"),
  source: (deviceId: string) => apiCall<SourceMetadata>(`/devices/${encodeURIComponent(deviceId)}/source`),
  datasets: () =>
    apiCall<{ nwb_support: boolean; unavailable_reason: string | null; devices: string[]; problems: { file: string; error: string }[]; fetch_command: string }>(
      "/datasets",
    ),
  playback: () => apiCall<PlaybackStatus>("/runtime/playback"),
  setSpeed: (speed: number) => apiCall<PlaybackStatus>("/runtime/playback", { method: "POST", body: { speed } }),
  simPointer: (vx: number, vy: number) =>
    apiCall<unknown>("/sim/pointer", { method: "POST", body: { vx, vy } }),
  simSelect: () => apiCall<unknown>("/sim/select", { method: "POST" }),
  simText: (text: string) => apiCall<unknown>("/sim/text", { method: "POST", body: { text } }),
  simFault: (fault: Fault) => apiCall<unknown>("/sim/faults", { method: "POST", body: { fault } }),
};
