// The sea at a place, today.
//
// Asked of the main process, which asks Aqualink. Kept per place for the life
// of the page so that switching between cards does not fetch the same record
// twice, and asked for once per place at a time so that ten cards appearing
// together do not become ten identical requests.

import { useEffect, useState } from "react";

import { AqualinkReader, InMemoryStore } from "../../shared/aqualink.js";
import type { Bridge, LatLon, SeaRecord, SeaSite } from "../../shared/bridge.js";

/** How far a monitoring site may be from a place and still speak for it. */
const WITHIN_KM = 25;

export type SeaState =
  | { at: "nowhere" }                 // the place does not say where it is
  | { at: "asking" }
  | { at: "none"; withinKm: number }  // nobody monitors the sea near here
  | { at: "known"; record: SeaRecord }
  | { at: "unreachable"; why: string };

/**
 * Who answers: the main process through the bridge, or — when this page is
 * open in a plain browser while it is being built, and there is no bridge —
 * Aqualink directly, remembered only in memory. The application never takes
 * the second path.
 */
function ocean(): Bridge["ocean"] {
  if (typeof window !== "undefined" && window.coralCity !== undefined) return window.coralCity.ocean;
  const reader = new AqualinkReader(async (url) => {
    const response = await fetch(url);
    if (!response.ok) throw new Error(`Aqualink answered ${response.status}`);
    return response.json();
  }, new InMemoryStore());
  return { nearestSite: (at, km) => reader.nearestSite(at, km), record: (id, at) => reader.record(id, at) };
}

const asked = new Map<string, Promise<SeaState>>();

function keyOf(at: LatLon): string {
  return `${at.latitude.toFixed(4)},${at.longitude.toFixed(4)}`;
}

export function seaAt(at: LatLon | undefined): Promise<SeaState> {
  if (at === undefined) return Promise.resolve({ at: "nowhere" });
  const key = keyOf(at);
  let pending = asked.get(key);
  if (pending === undefined) {
    pending = (async (): Promise<SeaState> => {
      try {
        const sea = ocean();
        const site: SeaSite | undefined = await sea.nearestSite(at, WITHIN_KM);
        if (site === undefined) return { at: "none", withinKm: WITHIN_KM };
        const record = await sea.record(site.id, at);
        return { at: "known", record };
      } catch (problem) {
        // Forgotten, so the next look tries again rather than remembering an outage.
        asked.delete(key);
        return { at: "unreachable", why: problem instanceof Error ? problem.message : "could not reach Aqualink" };
      }
    })();
    asked.set(key, pending);
  }
  return pending;
}

/** The sea at a point, as a page sees it: asking, then whatever it is. */
export function useSea(at: LatLon | undefined): SeaState {
  const [state, setState] = useState<SeaState>(at === undefined ? { at: "nowhere" } : { at: "asking" });
  const key = at === undefined ? "" : keyOf(at);
  useEffect(() => {
    let live = true;
    if (at === undefined) { setState({ at: "nowhere" }); return; }
    setState({ at: "asking" });
    void seaAt(at).then((answer) => { if (live) setState(answer); });
    return () => { live = false; };
    // The point is compared by its rounded coordinates, not by object identity.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  return state;
}

// ── reading the numbers ───────────────────────────────────────────────────────

/** NOAA Coral Reef Watch's alert levels, in the words they use. */
export const ALERT_LEVELS = [
  "no stress", "watch", "warning", "alert level 1", "alert level 2",
] as const;

export function alertName(level: number | undefined): string | undefined {
  if (level === undefined) return undefined;
  return ALERT_LEVELS[Math.max(0, Math.min(4, Math.round(level)))];
}

/** How worried to be, as the one word a pill can carry. */
export function alertKind(level: number | undefined): "good" | "busy" | "bad" | undefined {
  if (level === undefined) return undefined;
  if (level <= 0) return "good";
  if (level <= 2) return "busy";
  return "bad";
}

/** The temperature to lead with: the buoy's if it has one, the satellite's otherwise. */
export function leadTemperature(record: SeaRecord): { value: number; source: string; where: string } | undefined {
  const { now } = record;
  if (now.bottomTemperatureC) return { value: now.bottomTemperatureC.value, source: "buoy", where: "at the bottom" };
  if (now.topTemperatureC) return { value: now.topTemperatureC.value, source: "buoy", where: "at the surface" };
  if (now.satelliteTemperatureC) return { value: now.satelliteTemperatureC.value, source: "satellite", where: "sea surface" };
  return undefined;
}

export function compassName(degrees: number): string {
  const names = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"];
  return names[Math.round(((degrees % 360) + 360) % 360 / 45) % 8]!;
}
