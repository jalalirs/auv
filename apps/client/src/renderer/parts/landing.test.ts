import { describe, expect, it } from "vitest";

import { drape, fall, restOn } from "./landing.js";
import type { Ground } from "./SiteChart.js";

/** A square site whose depth at each (x, y) is whatever `depth` says. */
function site(acrossM: number, depth: (x: number, y: number) => number, n = 201): Ground {
  const grid = new Float32Array(n * n);
  for (let r = 0; r < n; r++) {
    for (let c = 0; c < n; c++) {
      grid[r * n + c] = depth((c / (n - 1) - 0.5) * acrossM, (r / (n - 1) - 0.5) * acrossM);
    }
  }
  return { rows: n, columns: n, acrossM, depth: grid };
}

describe("restOn", () => {
  it("sits level on a flat bottom", () => {
    const rest = restOn(site(100, () => 12), 0, 0, 2, 2);
    expect(rest.depthM).toBeCloseTo(12, 3);
    expect(rest.tiltDeg).toBeCloseTo(0, 3);
    expect(rest.clearM).toBeCloseTo(0, 3);
  });

  it("leans with a slope, flush on it", () => {
    // Deeper by 0.1 m for every metre east: a slope of about 5.7 degrees.
    const rest = restOn(site(100, (x) => 10 + 0.1 * x), 0, 0, 2, 2);
    expect(rest.tiltDeg).toBeCloseTo(5.71, 1);
    expect(rest.depthM).toBeCloseTo(10, 2);
    expect(rest.clearM).toBeLessThan(0.02);
  });

  it("bridges a hole under it", () => {
    const rest = restOn(site(100, (x, y) => (Math.hypot(x, y) < 0.6 ? 14 : 10)), 0, 0, 3, 3);
    expect(rest.depthM).toBeCloseTo(10, 1);
    expect(rest.clearM).toBeGreaterThan(3);
  });
});

describe("drape", () => {
  it("lies flat on a flat bottom", () => {
    const laid = drape(site(400, () => 20), [{ x: -100, y: 0 }, { x: 100, y: 0 }]);
    expect(laid.lengthM).toBeCloseTo(200, 3);
    expect(laid.spans).toHaveLength(0);
  });

  it("bridges a narrow trench and follows a broad hollow", () => {
    // A trench 4 m wide and 2 m deep at x = -50; a hollow 200 m wide and 2 m deep at x = 100.
    const ground = site(600, (x) => 20 + (Math.abs(x + 50) < 2 ? 2 : 0) + 2 * Math.exp(-(((x - 100) / 60) ** 2)), 601);
    const laid = drape(ground, [{ x: -200, y: 0 }, { x: 250, y: 0 }], 150);
    // Spans are measured along the route, which starts at x = -200.
    const over = laid.spans.filter((s) => s.from - 200 < -40 && s.to - 200 > -60);
    expect(over).toHaveLength(1);
    expect(over[0]!.gapM).toBeGreaterThan(1.5);
    const hollow = laid.samples.find((s) => Math.abs(s.x - 100) < 1)!;
    expect(hollow.groundM - hollow.pipeM).toBeLessThan(0.1);
  });
});

describe("fall", () => {
  it("sinks straight down in still water, at its terminal speed", () => {
    const ground = site(100, () => 15);
    const block = { massKg: 2000, volumeM3: 0.83, dragAreaM2: 1.05 };
    const dropped = fall(ground, 0, 0, block, { east: 0, north: 0 });
    expect(dropped.floats).toBe(false);
    expect(dropped.landed!.x).toBeCloseTo(0, 6);
    expect(dropped.landed!.depthM).toBeCloseTo(15, 3);
    expect(dropped.landed!.speed).toBeCloseTo(dropped.terminalMs, 1);
  });

  it("drifts with the current, the lighter thing further", () => {
    const ground = site(400, () => 20);
    const current = { east: 0.3, north: 0 };
    const heavy = fall(ground, 0, 0, { massKg: 2000, volumeM3: 0.83, dragAreaM2: 1.05 }, current);
    const light = fall(ground, 0, 0, { massKg: 60, volumeM3: 0.008, dragAreaM2: 1.2 }, current);
    expect(heavy.landed!.x).toBeGreaterThan(0);
    expect(light.landed!.x).toBeGreaterThan(heavy.landed!.x);
    expect(light.landed!.y).toBeCloseTo(0, 6);
  });

  it("floats when it is lighter than the water it moves", () => {
    expect(fall(site(100, () => 10), 0, 0, { massKg: 50, volumeM3: 0.1, dragAreaM2: 0.5 }, { east: 0, north: 0 }).floats).toBe(true);
  });
});
