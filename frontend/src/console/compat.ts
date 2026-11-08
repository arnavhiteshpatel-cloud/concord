// Compatibility registry (Milestone 5, workstream F): GET /api/v1/compatibility.
// Shapes mirror backend/src/concord/compat/model.py, compat/live.py and server/compat_routes.py.
// Levels are derived by the backend from evidence; the console only displays them.

import { apiCall } from "../sdk";

export type CompatLevel = "software_implemented" | "protocol_tested" | "hardware_verified" | "human_validated";
export type CompatKind = "builtin_adapter" | "source_plugin" | "offline_dataset";
export type CompatEvidenceType = "test" | "certify_report" | "benchmark" | "doc";
export type CompatLiveState = "installed" | "different_version" | "unavailable" | "not_installed" | "not_checked";

export interface CompatCertify {
  level: "adapter_implementation" | "protocol_tested" | "hardware_tested" | null;
  tool: string;
  plugin: string;
  plugin_version: string;
  entry_point: string;
  device_key: string | null;
  data_source: string;
  counts: Record<string, number>;
  protocol_reference: string | null;
  attestation_accepted: boolean | null;
  tree_sha256: string;
  source_matches: boolean | null;
  changed_files: string[];
}

export interface CompatEvidence {
  type: CompatEvidenceType;
  path: string;
  description: string;
  date: string;
  supports: "software_implemented" | "protocol_tested" | null;
  counted: boolean;
  note: string | null;
  protocol_reference: string | null;
  runs_in_ci: boolean | null;
  record: string | null;
  real_data: boolean;
  claim: "independent_reference_comparison" | "approved_human_protocol" | null;
  certify: CompatCertify | null;
}

export interface CompatEntry {
  id: string;
  display_name: string;
  kind: CompatKind;
  ecosystem: string | null;
  protocol: string;
  package: string;
  version: string;
  adapter: string | null;
  entry_point: string | null;
  module: string | null;
  in_checkout: boolean;
  synthetic_only: boolean;
  modalities_declared: string[];
  modality_note: string | null;
  read_only: { statement: string; verified_by: string[] };
  level: CompatLevel | null;
  level_number: number | null;
  real_data_replay: boolean;
  level_basis: string[];
  evidence: CompatEvidence[];
  not_tested: string[];
  limitations: string[];
  requires_modules: string[];
}

export interface CompatRegistry {
  registry_version: string;
  notice: string;
  concord_version: string;
  levels: { id: CompatLevel; number: number; name: string; meaning: string }[];
  rules: string[];
  sources: { curated: string; certify_reports: string[]; validation_levels: string };
  summary: Record<string, number>;
  entries: CompatEntry[];
}

export interface CompatLiveStatus {
  state: CompatLiveState;
  installed_version: string | null;
  version_matches: boolean | null;
  detail: string;
}

export interface CompatibilityResponse {
  available: boolean;
  source: string;
  error: string | null;
  concord_version: string;
  registry: CompatRegistry | null;
  live: Record<string, CompatLiveStatus>;
  plugin_discovery: { discovering: boolean; discovered_at_ns: number | null; error: string | null };
}

export const compatApi = {
  get: () => apiCall<CompatibilityResponse>("/compatibility"),
};

// ------------------------------------------------------------------------------ wording
// Level names are those of docs/VALIDATION_LEVELS.md, as the registry states them.

const LEVEL_NAMES: Record<CompatLevel, string> = {
  software_implemented: "Software-implemented",
  protocol_tested: "Protocol-tested",
  hardware_verified: "Hardware-verified",
  human_validated: "Human-participant validated",
};

/** "Level 2 · Protocol-tested" from the registry's own level definitions. */
export function levelText(entry: CompatEntry, registry: CompatRegistry): string {
  if (entry.level === null) return entry.in_checkout ? "No level: no counted evidence" : "No level: not in this build";
  const def = registry.levels.find((l) => l.id === entry.level);
  return `Level ${def?.number ?? entry.level_number ?? "?"} · ${def?.name ?? LEVEL_NAMES[entry.level]}`;
}

export const KIND_TEXT: Record<CompatKind, string> = {
  builtin_adapter: "Built-in adapter",
  source_plugin: "Source plugin",
  offline_dataset: "Offline dataset",
};

const EVIDENCE_TEXT: Record<CompatEvidenceType, string> = {
  test: "test",
  certify_report: "certification report",
  benchmark: "benchmark",
  doc: "document",
};

/** "test · supports Protocol-tested · not run in CI" — what the registry says about one item. */
export function evidenceText(e: CompatEvidence): string {
  const parts = [EVIDENCE_TEXT[e.type]];
  if (e.counted && e.supports) parts.push(`supports ${LEVEL_NAMES[e.supports]}`);
  if (e.real_data) parts.push("real recorded data");
  if (e.runs_in_ci === false) parts.push("not run in CI");
  parts.push(e.date);
  return parts.join(" · ");
}

/** What this installation has, in one short phrase. */
export function liveText(s: CompatLiveStatus | undefined): string {
  if (!s) return "Not reported";
  switch (s.state) {
    case "not_installed":
      return "Not installed here";
    case "not_checked":
      return "Not checked yet: the plugin search has not run";
    default: // installed, different_version, unavailable: the server's sentence
      return s.detail;
  }
}
