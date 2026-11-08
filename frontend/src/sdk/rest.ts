// Concord TypeScript SDK — REST client for the runtime control surface.

import type { DeviceDescriptor, NegotiationResult, RuntimeSnapshot, Capability } from "./types";

export class ConcordApiError extends Error {
  constructor(
    readonly code: string,
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

export async function apiCall<T>(path: string, init?: { method?: string; body?: unknown }): Promise<T> {
  const resp = await fetch(`/api/v1${path}`, {
    method: init?.method ?? "GET",
    headers: init?.body !== undefined ? { "content-type": "application/json" } : undefined,
    body: init?.body !== undefined ? JSON.stringify(init.body) : undefined,
  });
  const text = await resp.text();
  let data: unknown = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    /* non-JSON error body */
  }
  if (!resp.ok) {
    const err = (data as { error?: { code: string; message: string }; detail?: unknown } | null) ?? {};
    if (err.error) throw new ConcordApiError(err.error.code, err.error.message, resp.status);
    const detail = Array.isArray(err.detail)
      ? (err.detail as { msg?: string }[]).map((d) => d.msg).join("; ")
      : text.slice(0, 200);
    throw new ConcordApiError("http_error", detail || resp.statusText, resp.status);
  }
  return data as T;
}

export const runtimeApi = {
  devices: () => apiCall<DeviceDescriptor[]>("/devices"),
  runtime: () => apiCall<RuntimeSnapshot>("/runtime"),
  connect: (device_id: string) =>
    apiCall<RuntimeSnapshot>("/runtime/connect", { method: "POST", body: { device_id } }),
  switch: (device_id: string) =>
    apiCall<RuntimeSnapshot>("/runtime/switch", { method: "POST", body: { device_id } }),
  disconnect: () => apiCall<RuntimeSnapshot>("/runtime/disconnect", { method: "POST" }),
  pause: () => apiCall<RuntimeSnapshot>("/runtime/pause", { method: "POST" }),
  resume: () => apiCall<RuntimeSnapshot>("/runtime/resume", { method: "POST" }),
  negotiate: (required: Capability[], optional: Capability[] = [], device_id?: string) =>
    apiCall<NegotiationResult>("/negotiate", {
      method: "POST",
      body: { required, optional, device_id: device_id ?? null },
    }),
};
