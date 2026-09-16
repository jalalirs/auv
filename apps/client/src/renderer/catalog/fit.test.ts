import { describe, expect, it } from "vitest";

import { beyondTheHull, drawOf, hoursAtRest } from "./fit.js";

const CARRIED = [
  { kind: "imaging_sonar", watts: 18 },
  { kind: "dvl", watts: 4 },
  { kind: "ctd", watts: 0.35 },
];

describe("what a vehicle carries", () => {
  it("costs what the things on it cost", () => {
    expect(drawOf(CARRIED, { watts: 5 }, 6, new Set())).toBeCloseTo(33.35, 2);
  });

  // The whole reason the screen exists: a fit that changes nothing is a label.
  it("costs less when something is left behind", () => {
    const all = drawOf(CARRIED, { watts: 5 }, 6, new Set());
    const noSonar = drawOf(CARRIED, { watts: 5 }, 6, new Set(["imaging_sonar"]));
    expect(noSonar).toBeLessThan(all);
    expect(all - noSonar).toBeCloseTo(18, 2);
  });

  it("turns that into hours a person can act on", () => {
    const usable = 240;
    const laden = hoursAtRest(usable, drawOf(CARRIED, { watts: 5 }, 6, new Set()));
    const light = hoursAtRest(usable, drawOf(CARRIED, { watts: 5 }, 6, new Set(["imaging_sonar"])));
    expect(light).toBeGreaterThan(laden);
  });

  // Checked against the hull, not against the machine the simulator runs on.
  it("refuses a controller the hull could not run", () => {
    expect(beyondTheHull({ kind: "raspberry-pi-4", tops: 0, ramGb: 4 }, { tops: 100 }))
      .toContain("would not run at sea");
    expect(beyondTheHull({ kind: "jetson-orin-nx", tops: 100, ramGb: 16 }, { tops: 40 }))
      .toBeUndefined();
  });
});
