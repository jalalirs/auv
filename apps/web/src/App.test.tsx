import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";

describe("Coral City web foundation", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          name: "Coral City",
          service: "control-plane",
          version: "test",
          commit: "abc123",
          builtAt: "2026-08-28T00:00:00Z",
        }),
      }),
    );
  });

  it("shows the real platform connection and honest default area", async () => {
    render(<App />);

    expect(await screen.findByText("control-plane · test")).toBeInTheDocument();
    expect(screen.getByText("No reef survey source is connected.")).toBeInTheDocument();
    expect(screen.queryByText(/available gpu/i)).not.toBeInTheDocument();
  });

  it("moves between bounded product areas", async () => {
    render(<App />);
    await screen.findByText("control-plane · test");

    fireEvent.click(screen.getByRole("button", { name: /Simulation/ }));

    expect(screen.getByRole("heading", { name: "Simulation" })).toBeInTheDocument();
    expect(screen.getByText("No simulator session has been allocated.")).toBeInTheDocument();
  });

  it("reports a disconnected control plane without inventing state", async () => {
    vi.mocked(fetch).mockRejectedValueOnce(new Error("offline"));

    render(<App />);

    expect(await screen.findByText("Control plane unavailable")).toBeInTheDocument();
  });
});
