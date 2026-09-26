// Water somebody measured, against water somebody composed.

import { describe, expect, it } from "vitest";

import type { SeaRecord } from "../../shared/bridge.js";
import { asMeasured } from "./asMeasured.js";

function aRecord(now: SeaRecord["now"]): SeaRecord {
  return {
    site: { id: 1, name: "Looe Key", region: undefined, latitude: 24.5,
            longitude: -81.4, depth: undefined, status: "deployed",
            hasBuoy: true, timezone: undefined, maxMonthlyMean: undefined,
            page: "" } as unknown as SeaRecord["site"],
    now, days: [], surveys: [], fetchedAt: "2026-09-16T12:00:00Z",
  };
}

describe("the sea as it was measured", () => {
  it("prefers an instrument in the water over a satellite", () => {
    const got = asMeasured(aRecord({
      satelliteTemperatureC: { value: 30.1, at: "2026-09-16T00:00:00Z", source: "noaa" },
      bottomTemperatureC: { value: 28.4, at: "2026-09-16T11:00:00Z", source: "spotter" },
    }));
    expect(got?.parameters["temperatureC"]).toBe(28.4);
    expect(got?.observedAt).toBe("2026-09-16T11:00:00Z");
  });

  it("says who measured it and when", () => {
    const got = asMeasured(aRecord({
      bottomTemperatureC: { value: 28.4, at: "2026-09-16T11:00:00Z", source: "spotter" },
      significantWaveHeightM: { value: 0.7, at: "2026-09-16T11:00:00Z", source: "spotter" },
    }));
    expect(got?.sources.length).toBe(2);
    expect(String(got?.sources[0]?.["from"])).toContain("Spotter");
    // Named by the field it became, so a run can put the instrument beside
    // the number instead of beside a word for it.
    expect(got?.sources.map((one) => one["parameter"])).toContain("temperatureC");
    expect(got?.parameters["significantWaveHeightM"]).toBe(0.7);
  });

  // An instant is a claim that somebody took a reading. A claim like that has
  // to fail rather than fall back on a default, which is the whole reason the
  // platform refuses observed conditions that name no instant.
  it("gives nothing when nobody measured anything", () => {
    expect(asMeasured(aRecord({}))).toBeUndefined();
    expect(asMeasured(undefined)).toBeUndefined();
  });

  // The one thing a dive most wants, and nothing here measures it.
  it("says out loud that the current is not measured", () => {
    const got = asMeasured(aRecord({
      bottomTemperatureC: { value: 28.4, at: "2026-09-16T11:00:00Z", source: "spotter" },
    }));
    expect(got?.parameters["currentNotMeasured"]).toBe(true);
    expect(got?.parameters["currentMetresPerSecond"]).toBeUndefined();
  });
});
