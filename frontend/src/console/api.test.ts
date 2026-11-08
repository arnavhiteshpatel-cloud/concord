// Milestone 3 console API helpers: exact endpoints and request bodies the backend expects
// (backend/src/concord/server/live_routes.py), and the server's error envelope surfaced.
import { afterEach, describe, expect, it, vi } from "vitest";
import { ConcordApiError } from "../sdk";
import { consoleApi, isDatasetFile, isLiveSource, isRecordable, labApi } from "./api";
import { apiError, stubFetch } from "./testFetch";

afterEach(() => vi.unstubAllGlobals());

describe("labApi", () => {
  it("calls the live-source endpoints with the documented bodies", async () => {
    const calls = stubFetch({
      "GET /sources/lsl": () => ({ library: null, discovered_at_ns: null, streams: [], error: null }),
      "POST /sources/lsl/discover": () => ({ library: "x", discovered_at_ns: 1, streams: [], error: null }),
      "POST /sources/lsl": () => ({ device_id: "lsl:sig" }),
      "POST /sources/openephys": () => ({ device_id: "openephys:127.0.0.1:5556" }),
      "DELETE /sources/lsl:sig": () => ({ removed: true }),
      "GET /devices/lsl:sig/source": () => ({ protocol: "lsl" }),
    });
    await labApi.lslStreams();
    await labApi.lslDiscover(2);
    await labApi.lslRegister("sig", "beh", null);
    await labApi.openEphysRegister({ host: "127.0.0.1", data_port: 5556, unit: "unknown" });
    expect(await labApi.removeSource("lsl:sig")).toEqual({ removed: true });
    expect(await labApi.liveSource("lsl:sig")).toEqual({ protocol: "lsl" });
    expect(calls.map((c) => [c.method, c.path, c.body])).toEqual([
      ["GET", "/sources/lsl", undefined],
      ["POST", "/sources/lsl/discover", { wait_s: 2 }],
      ["POST", "/sources/lsl", { signal: "sig", behavior: "beh", markers: null }],
      ["POST", "/sources/openephys", { host: "127.0.0.1", data_port: 5556, unit: "unknown" }],
      ["DELETE", "/sources/lsl:sig", undefined],
      ["GET", "/devices/lsl:sig/source", undefined],
    ]);
  });

  it("calls the pipeline, model and calibration endpoints", async () => {
    const calls = stubFetch({
      "GET /pipeline": () => ({ running: false }),
      "GET /pipeline/presets": () => ({ band_power: "x" }),
      "POST /pipeline/start": () => ({ running: true }),
      "POST /pipeline/stop": () => ({ running: false }),
      "POST /pipeline/router": () => ({ running: true }),
      "GET /models": () => [],
      "POST /calibration/train": () => ({ model: {}, report: {}, report_markdown: "" }),
    });
    await labApi.pipeline();
    await labApi.presets();
    await labApi.startPipeline({ processing: { preset: "spikeband_threshold", bin_ms: 20 }, model_id: null, allow_cross_source: false });
    await labApi.stopPipeline();
    const router = { enabled: true, x_dim: "vx", y_dim: "vy", gain: 1, deadzone: 0.3, invert_y: false, max_speed: 2 };
    await labApi.setRouter(router);
    await labApi.models();
    await labApi.calibrate({ recordings: ["a"], train_fraction: 0.8, gap_bins: 12, feature_source: "concord.pipeline" });
    expect(calls.map((c) => `${c.method} ${c.path}`)).toEqual([
      "GET /pipeline",
      "GET /pipeline/presets",
      "POST /pipeline/start",
      "POST /pipeline/stop",
      "POST /pipeline/router",
      "GET /models",
      "POST /calibration/train",
    ]);
    expect(calls[2]!.body).toEqual({
      processing: { preset: "spikeband_threshold", bin_ms: 20 },
      model_id: null,
      allow_cross_source: false,
    });
    expect(calls[4]!.body).toEqual(router);
    expect(calls[6]!.body).toEqual({
      recordings: ["a"],
      train_fraction: 0.8,
      gap_bins: 12,
      feature_source: "concord.pipeline",
    });
  });

  it("surfaces the server's refusal (code + message)", async () => {
    stubFetch({ "POST /pipeline/start": () => apiError(409, "incompatible_decoder", "bin_ms 50 != 20") });
    const err = await labApi
      .startPipeline({ processing: { preset: "band_power" }, model_id: "m", allow_cross_source: false })
      .catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ConcordApiError);
    expect((err as ConcordApiError).code).toBe("incompatible_decoder");
    expect((err as ConcordApiError).message).toBe("bin_ms 50 != 20");
    expect((err as ConcordApiError).status).toBe(409);
  });
});

describe("startRecording", () => {
  it("sends exclude_raw only when requested (older servers reject unknown fields)", async () => {
    const calls = stubFetch({ "POST /recordings/start": () => ({ name: "r" }) });
    await consoleApi.startRecording();
    await consoleApi.startRecording(undefined, true);
    await consoleApi.startRecording("cal-1", true);
    expect(calls.map((c) => c.body)).toEqual([{}, { exclude_raw: true }, { name: "cal-1", exclude_raw: true }]);
  });
});

describe("source classification", () => {
  it("distinguishes live sources, dataset files and recordable sources", () => {
    const d = (device_id: string) => ({ device_id });
    expect(isLiveSource(d("lsl:abc"))).toBe(true);
    expect(isLiveSource(d("openephys:127.0.0.1:5556"))).toBe(true);
    expect(isLiveSource(d("sim-a"))).toBe(false);
    expect(isLiveSource(null)).toBe(false);
    expect(isDatasetFile(d("nwb:sub-x"))).toBe(true);
    expect(isDatasetFile(d("replay:rec"))).toBe(false);
    expect(isRecordable(d("lsl:abc"))).toBe(true);
    expect(isRecordable(d("sim-a"))).toBe(true);
    expect(isRecordable(d("replay:rec"))).toBe(false);
    expect(isRecordable(d("nwb:sub-x"))).toBe(false);
  });
});
