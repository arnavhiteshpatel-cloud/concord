// Test helper: a fetch stub that routes "METHOD /path" to handlers and records calls.
import { vi } from "vitest";

export interface Call {
  method: string;
  path: string;
  body: unknown;
}

export class Reply {
  constructor(
    readonly status: number,
    readonly body: unknown,
  ) {}
}

/** The server's error envelope, e.g. apiError(409, "incompatible_decoder", "…"). */
export const apiError = (status: number, code: string, message: string) =>
  new Reply(status, { error: { code, message } });

type Handler = (body: unknown) => unknown;

export function stubFetch(routes: Record<string, Handler>): Call[] {
  const calls: Call[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(String(input), "http://localhost");
      const method = init?.method ?? "GET";
      const path = decodeURIComponent(url.pathname.replace(/^\/api\/v1/, ""));
      const body = typeof init?.body === "string" ? (JSON.parse(init.body) as unknown) : undefined;
      calls.push({ method, path, body });
      const h = routes[`${method} ${path}`];
      const r = h ? h(body) : apiError(404, "not_found", path);
      const res = r instanceof Reply ? r : new Reply(200, r);
      return new Response(JSON.stringify(res.body), { status: res.status });
    }),
  );
  return calls;
}
