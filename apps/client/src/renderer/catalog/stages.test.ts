import { describe, expect, it } from "vitest";

import { driftRisks, drawnInto, FINS, geometryOf, legsOf, pilotOf, PURSUE, snap, wattsOf, type Hull, type Stage } from "./stages.js";

const launch = { x: 0, y: 0 };

describe("a stage drawn on the chart", () => {
  it("writes what was drawn in the place's frame, and drops what was relative", () => {
    const route = drawnInto({ kind: "waypoints", radiusM: 1, depthM: 4, points: [{ dx: 8, dy: 0 }] },
                            [{ x: 10, y: 0 }, { x: 10, y: 20 }]);
    expect(route["points"]).toEqual([{ x: 10, y: 0, depthM: 4 }, { x: 10, y: 20, depthM: 4 }]);
    const line = drawnInto({ kind: "transect", lengthM: 200, headingDeg: 0 }, [{ x: 0, y: 5 }, { x: 30, y: 45 }]);
    expect(line).toEqual({ kind: "transect", from: { x: 0, y: 5 }, to: { x: 30, y: 45 } });
    const area = drawnInto({ kind: "survey", widthM: 60, heightM: 30 }, [{ x: 30, y: 10 }, { x: 10, y: 2 }]);
    expect(area["area"]).toEqual([{ x: 10, y: 2 }, { x: 30, y: 2 }, { x: 30, y: 10 }, { x: 10, y: 10 }]);
    const at = drawnInto({ kind: "inspect", dx: 60, dy: 0, radiusM: 6, over: "frame-1" }, [{ x: 5, y: 6 }]);
    expect(at).toEqual({ kind: "inspect", radiusM: 6, target: { x: 5, y: 6 } });
  });

  it("points at a drawn thing when it is over one", () => {
    const g = geometryOf({ kind: "survey", over: "cell" }, [{ id: "cell", kind: "restoration-cell", x: 0, y: 0,
      corners: [{ x: 0, y: 0 }, { x: 10, y: 0 }, { x: 10, y: 4 }, { x: 0, y: 4 }] }], launch);
    expect(g.drawn).toBe(true);
    expect(g.area).toEqual([{ x: 0, y: 0 }, { x: 10, y: 0 }, { x: 10, y: 4 }, { x: 0, y: 4 }]);
  });
});

// Two hulls as their packages give them: mass with surge added mass, and surge drag.
const MINI_HOOT: Hull = { massKg: 2.722 + 1.367, linear: 1.584, quadratic: 12.357 };
const LUNA: Hull = { massKg: 25 + 12.148, linear: 7.167, quadratic: 54.609 };

describe("how long the plan takes", () => {
  // Flown on the box, undrawn, by pursue, on 4 October 2026.
  const within = (said: number, flown: number) => expect(Math.abs(said - flown) / flown).toBeLessThan(0.1);
  it("matches a tank route flown in 59.7 s", () => {
    const [leg] = legsOf([{ kind: "waypoints", radiusM: 0.08, points: [
      { x: 0.55, y: 0.15 }, { x: -0.55, y: 0.15 }, { x: -0.55, y: -0.15 }] }], [], launch, MINI_HOOT);
    within(leg!.flyS, 59.7);
  });
  it("matches three sides of a tank square flown in 59.9 s", () => {
    const [leg] = legsOf([{ kind: "waypoints", radiusM: 0.1, points: [
      { x: 0.4, y: 0.3 }, { x: -0.4, y: 0.3 }, { x: -0.4, y: -0.3 }] }], [], launch, MINI_HOOT);
    within(leg!.flyS, 59.9);
  });
  it("matches Luna's 30 m leg, which settled at 0.27 m/s rather than the 0.4 it asked for", () => {
    const start = { x: 115, y: -25 };
    const [leg] = legsOf([{ kind: "waypoints", radiusM: 1, points: [{ x: 145, y: -25 }] }], [], start, LUNA);
    within(leg!.flyS, 117);
  });
});

describe("the plan, stage by stage", () => {
  const stages: Stage[] = [
    { kind: "waypoints", points: [{ x: 30, y: 0 }, { x: 30, y: 40 }], timeLimitS: 600 },
    { kind: "hold-station", seconds: 120 },
    { kind: "survey", swathM: 5, area: [{ x: 30, y: 40 }, { x: 50, y: 40 }, { x: 50, y: 60 }, { x: 30, y: 60 }], timeLimitS: 900 },
    { kind: "return", timeLimitS: 300 },
  ];
  it("flies each stage from where the last one left it", () => {
    const legs = legsOf(stages, [], launch, LUNA);
    expect(legs[1]!.flyS).toBe(120);
    expect(legs[1]!.from).toEqual({ x: 30, y: 40 });
    expect(legs[3]!.from).toEqual(legs[2]!.to);
    expect(legs[3]!.to).toEqual(launch);
    expect(legs[0]!.allowS).toBe(600);
  });
  it("takes a vehicle's watts from the middle of what its runs drew", () => {
    const drew = wattsOf([
      { task: { energyWh: 0.709, seconds: 59.7 } },
      { energyWh: 1.237, seconds: 100.1 },
      { task: { energyWh: 20.431, seconds: 900 } },
      { task: { seconds: 30 } },
      undefined,
    ]);
    expect(drew?.runs).toBe(3);
    expect(drew?.watts).toBeCloseTo(44.5, 0);
  });
  it("warns where the drift with no fix outgrows a stage's radius", () => {
    const route: Stage[] = [{ kind: "waypoints", radiusM: 1, points: [{ x: 30, y: 0 }] },
                            { kind: "waypoints", radiusM: 8, points: [{ x: 60, y: 0 }] }];
    const risks = driftRisks(route, legsOf(route, [], launch, LUNA));
    // 30 m flown is 0.7 m of drift, inside 1 m; 60 m is 1.4 m, inside 8 m.
    expect(risks).toEqual([]);
    const far: Stage[] = [{ kind: "waypoints", radiusM: 1, points: [{ x: 100, y: 0 }] }];
    expect(driftRisks(far, legsOf(far, [], launch, LUNA))[0]?.stage).toBe(0);
  });
  it("follows a pipeline along its route, from the nearer end", () => {
    const pipe = { id: "pipe-1", kind: "pipeline", x: 50, y: 0, route: [{ x: 0, y: 0 }, { x: 100, y: 0 }] };
    const [leg] = legsOf([{ kind: "follow", over: "pipe-1" }], [pipe], { x: 110, y: 0 }, LUNA);
    expect(leg!.to).toEqual({ x: 0, y: 0 });
    expect(leg!.metres).toBeGreaterThan(105);
  });
  it("rounds to the place's scale", () => {
    expect(snap(1.23456, 2)).toBeCloseTo(1.235);
    expect(snap(123.4, 1000)).toBe(123);
  });
});

describe("a vehicle steered by fins", () => {
  it("is estimated as the fins controller flies it, not as pursue", () => {
    expect(pilotOf({ commandedIn: "fins" })).toBe(FINS);
    expect(pilotOf({ commandedIn: "wrench" })).toBe(PURSUE);
    // The pipeline landfall: 452 m, flown by a REMUS in 308 s on the box.
    const pipe = { id: "pipeline-1", kind: "pipeline", x: 150, y: -20,
                   route: [{ x: 0, y: -40 }, { x: 150, y: -20 }, { x: 450, y: 0 }] };
    const remus: Hull = { massKg: 36, linear: 0, quadratic: 4 };
    const legs = legsOf([{ kind: "follow", over: "pipeline-1", timeLimitS: 1500 }], [pipe as never],
                        { x: -10, y: -40 }, remus, FINS);
    const flyS = legs.reduce((s, l) => s + l.flyS, 0);
    expect(flyS).toBeGreaterThan(250);
    expect(flyS).toBeLessThan(420);
  });
});
