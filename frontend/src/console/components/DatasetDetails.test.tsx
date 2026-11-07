// Milestone 5 (workstream B): an ECoG extract's metadata is shown as raw voltage in samples
// (not "bins"), with its unit as declared, the pinned slice it came from and bad electrodes.
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { SourceMetadata } from "../../sdk";
import { stubFetch } from "../testFetch";
import { DatasetDetails, signalLine } from "./DatasetDetails";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const ID = "nwb:sub-07_ses-6_behavior-ecephys_slice-047925s";

const ecog: SourceMetadata = {
  device_id: ID,
  label: "Recorded Human ECoG — Offline Replay",
  source_type: "nwb_electrical_series",
  live: false,
  dataset: null,
  file: { name: "x.nwb", size_bytes: 1, sha256: "a", verified: true, verification: "Extract: SHA-256 … matches" },
  species: "Homo sapiens",
  subject_id: "07",
  identifier: "id",
  session_description: "",
  session_start_time: "2000-01-05T19:00:00-05:00",
  experiment_description: "",
  institution: "",
  lab: "",
  recording_type: "electrocorticography",
  profile: "ajile12",
  feature: "raw_voltage",
  feature_unit: "uV",
  bin_ms: 2,
  n_bins: 337500,
  duration_s: 675,
  channel_count: 2,
  channels: [],
  behavior: null,
  decoder: null,
  notes: [],
  modality: "ecog",
  invasive: true,
  signal: {
    series: "acquisition/ElectricalSeries",
    sample_rate_hz: 500,
    unit: "uV",
    declared_unit: "volts",
    conversion: 1e-6,
    n_samples: 337500,
    start_s: 47925,
    first_sample_index: 23962500,
    frame_samples: 50,
    line_hz: 60,
    bad_channels: ["RFGRID/0"],
  },
  electrodes: [0, 1].map((i) => ({
    index: i,
    id: i,
    label: `RFGRID/${i}`,
    group: "RFGRID",
    group_description: "Right Frontal ECoG grid",
    location: "unknown",
    x: 1,
    y: 2,
    z: 3,
    bad: i === 0,
    filtering: "250 Hz lowpass",
  })),
  intervals: [],
  slice: {
    id: "s07-d6-047925",
    asset_path: "sub-07/sub-07_ses-6_behavior+ecephys.nwb",
    asset_sha256: "b",
    series: "acquisition/ElectricalSeries",
    samples: [23962500, 24300000],
    data_sha256: "c",
    role: "test",
  },
};

describe("DatasetDetails (raw-voltage sources)", () => {
  it("describes samples, the declared unit, mains and bad electrodes", () => {
    expect(signalLine(ecog, ecog.signal!)).toContain("raw voltage in µV · 500 Hz · 337,500 samples");
    expect(signalLine(ecog, ecog.signal!)).toContain("mains 60 Hz · bad: RFGRID/0");
    const arbitrary = signalLine(ecog, { ...ecog.signal!, unit: "arbitrary", line_hz: null, bad_channels: [] });
    expect(arbitrary).toContain("arbitrary units (no convertible unit declared)");
    expect(arbitrary).toContain("bad: none marked");
  });

  it("renders the slice provenance and the electrode list", async () => {
    stubFetch({ [`GET /devices/${ID}/source`]: () => ecog });
    render(<DatasetDetails deviceId={ID} />);
    await waitFor(() => expect(screen.getByTestId("source-signal").textContent).toContain("raw voltage"));
    expect(screen.getByTestId("source-slice").textContent).toContain("[23962500, 24300000) · test slice");
    expect(screen.getByTestId("source-electrodes").textContent).toContain("RFGRID/0 (bad)");
    expect(screen.getByText(/modality ecog/)).toBeTruthy();
  });
});
