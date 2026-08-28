import { useEffect, useState } from "react";

export interface PlatformInfo {
  name: string;
  service: string;
  version: string;
  commit: string;
  builtAt: string;
}

export type PlatformState =
  | { status: "loading" }
  | { status: "connected"; info: PlatformInfo }
  | { status: "disconnected" };

export function usePlatform(): PlatformState {
  const [state, setState] = useState<PlatformState>({ status: "loading" });

  useEffect(() => {
    const controller = new AbortController();

    async function loadPlatform() {
      try {
        const response = await fetch("/api/v1/platform", {
          headers: { Accept: "application/json" },
          signal: controller.signal,
        });
        if (!response.ok) {
          throw new Error(`platform request failed with ${response.status}`);
        }
        const info = (await response.json()) as PlatformInfo;
        setState({ status: "connected", info });
      } catch (error) {
        if (!(error instanceof DOMException && error.name === "AbortError")) {
          setState({ status: "disconnected" });
        }
      }
    }

    void loadPlatform();
    return () => controller.abort();
  }, []);

  return state;
}
