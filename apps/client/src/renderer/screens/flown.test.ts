// A controller's record, out of runs the application already holds.
//
// The Autonomy page answered "what have I uploaded", which is the smallest
// question anybody has about a controller. The one they have is which of
// these should fly my mission.

import { describe, expect, it } from "vitest";

import { recordOf } from "./flown.js";

const run = (state: string, outcome: unknown, at: string, failureReason?: string) =>
  ({ state, outcome, requestedAt: at, failureReason } as never);

const RUNS = [
  { name: "bench · quick · reach", flownBy: "Station hold",
    run: run("succeeded", { task: { score: 0.8, energyWh: 4 }, navigation: { driftM: 2 },
                            hit: { things: 1 } }, "2026-09-20T10:00:00Z") },
  { name: "bench · quick · dock", flownBy: "Station hold",
    run: run("succeeded", { task: { score: 0.4, energyWh: 6 }, navigation: { driftM: 4 },
                            hit: { things: 0 } }, "2026-09-21T10:00:00Z") },
  // Its own controller broke: counted as a dive, not as a score.
  { name: "bench · quick · transect", flownBy: "Station hold",
    run: run("failed", {}, "2026-09-22T10:00:00Z",
             "the controller started and then stopped, so nothing flew this dive") },
  { name: "somebody else's", flownBy: "Sonar follow",
    run: run("succeeded", { task: { score: 0.1 } }, "2026-09-19T10:00:00Z") },
  { name: "flown by hand", flownBy: "by hand",
    run: run("succeeded", { task: { score: 0.9 } }, "2026-09-19T10:00:00Z") },
];

describe("what a controller has flown", () => {
  it("averages only the dives that finished", () => {
    const said = recordOf("Station hold", RUNS);
    expect(said.dives).toBe(3);
    expect(said.succeeded).toBe(2);
    expect(said.score).toBeCloseTo(0.6);
    expect(said.driftM).toBeCloseTo(3);
    expect(said.energyWh).toBeCloseTo(5);
  });

  it("sums what it ran into rather than averaging it", () => {
    // A controller that hit three frames on one dive and nothing on seven did
    // not hit three-eighths of a frame.
    expect(recordOf("Station hold", RUNS).struck).toBe(1);
  });

  it("takes nothing from another controller's dives, or from a hand", () => {
    expect(recordOf("Sonar follow", RUNS).dives).toBe(1);
    expect(recordOf("Sonar follow", RUNS).score).toBeCloseTo(0.1);
  });

  it("says when it last flew", () => {
    expect(recordOf("Station hold", RUNS).lastAt).toBe("2026-09-22T10:00:00Z");
  });

  it("has nothing to say about a controller that has never flown", () => {
    const said = recordOf("Deployed yesterday", RUNS);
    expect(said).toEqual({ dives: 0, succeeded: 0, score: undefined, driftM: undefined,
                           energyWh: undefined, struck: 0, lastAt: undefined,
                           neverFlew: 0 });
  });

  it("does not count a dive the platform could not start against it", () => {
    // Not somebody's controller flying badly. Counting it as one of that
    // controller's dives puts the wrong name on a number — but it is not
    // hidden either.
    const ours = [{ name: "x", flownBy: "Station hold",
                    run: run("failed", {}, "2026-09-23T10:00:00Z",
                             "the simulator could not be started: no such image") }];
    const said = recordOf("Station hold", ours);
    expect(said.dives).toBe(0);
    expect(said.neverFlew).toBe(1);
  });

  it("does count a dive its own controller broke", () => {
    const ours = [{ name: "x", flownBy: "Station hold",
                    run: run("failed", {}, "2026-09-23T10:00:00Z",
                             "the controller started and then stopped, so nothing "
                             + "flew this dive: AttributeError") }];
    const said = recordOf("Station hold", ours);
    expect(said.dives).toBe(1);
    expect(said.neverFlew).toBe(0);
  });

  it("does not pin an unexplained failure on a controller", () => {
    const ours = [{ name: "x", flownBy: "Station hold",
                    run: run("failed", {}, "2026-09-23T10:00:00Z") }];
    expect(recordOf("Station hold", ours).dives).toBe(0);
  });

  it("does not invent a score from dives that carried no task", () => {
    const untasked = [{ name: "a look", flownBy: "Station hold",
                        run: run("succeeded", { surfaced: true }, "2026-09-20T10:00:00Z") }];
    const said = recordOf("Station hold", untasked);
    expect(said.dives).toBe(1);
    expect(said.score).toBeUndefined();
  });
});
