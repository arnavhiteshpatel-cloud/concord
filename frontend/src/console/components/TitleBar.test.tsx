// Title bar (0.3.1): it shows the running server's version, so a researcher can see at a glance
// that the console belongs to the Concord they installed and not an older copy still running.
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { stubFetch } from "../testFetch";
import { TitleBar } from "./TitleBar";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("TitleBar", () => {
  it("shows the version of the server it is connected to", async () => {
    stubFetch({ "GET /health": () => ({ status: "ok", version: "0.3.1" }) });
    render(<TitleBar conn="open" runtime={null} controlOn={false} stopping={false} onStopControl={vi.fn()} />);
    await waitFor(() => expect(screen.getByTestId("version").textContent).toBe("0.3.1"));
  });

  it("asks for no version while disconnected", () => {
    const calls = stubFetch({ "GET /health": () => ({ status: "ok", version: "0.3.1" }) });
    render(<TitleBar conn="closed" runtime={null} controlOn={false} stopping={false} onStopControl={vi.fn()} />);
    expect(screen.queryByTestId("version")).toBeNull();
    expect(calls.some((c) => c.path === "/health")).toBe(false);
  });
});
