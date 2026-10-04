import { describe, expect, it } from "vitest";

import { drawnInto, energyWh, geometryOf, legsOf, snap, type Stage } from "./stages.js";

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

describe("what the plan costs", () => {
  const stages: Stage[] = [
    { kind: "waypoints", points: [{ x: 30, y: 0 }, { x: 30, y: 40 }], timeLimitS: 600 },
    { kind: "hold-station", seconds: 120 },
    { kind: "survey", swathM: 5, area: [{ x: 30, y: 40 }, { x: 50, y: 40 }, { x: 50, y: 60 }, { x: 30, y: 60 }], timeLimitS: 900 },
    { kind: "return", timeLimitS: 300 },
  ];
  it("flies each stage from where the last one left it", () => {
    const legs = legsOf(stages, [], launch, 0.5);
    expect(legs[0]!.metres).toBe(70);
    expect(legs[1]!.flyS).toBe(120);
    // Four lanes of twenty metres and three steps of five, from the corner it is already at.
    expect(legs[2]!.metres).toBe(95);
    expect(legs[3]!.from).toEqual(legs[2]!.to);
    expect(legs[3]!.to).toEqual(launch);
  });
  it("spends the hotel load all day and the drag only while moving", () => {
    const legs = legsOf([{ kind: "hold-station", seconds: 3600 }], [], launch, 0.5);
    expect(energyWh(legs, 0.5, 10, 12)).toBeCloseTo(10);
  });
  it("rounds to the place's scale", () => {
    expect(snap(1.23456, 2)).toBeCloseTo(1.235);
    expect(snap(123.4, 1000)).toBe(123);
  });
});
