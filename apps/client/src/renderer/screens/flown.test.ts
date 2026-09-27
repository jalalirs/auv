// A controller's record, out of runs the application already holds.
//
// The Autonomy page answered "what have I uploaded", which is the smallest
// question anybody has about a controller. The one they have is which of
// these should fly my mission.

import { describe, expect, it } from "vitest";

import { headToHead, recordOf, saidAs, trialOf } from "./flown.js";

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

// ---------------------------------------------------------------------------
// Two controllers, compared where they can be.
//
// An average over different dives is not a comparison, and the page was
// offering one. These are the same task at the same suite over the same reef in
// the same hull, which is the only arrangement under which the higher score
// means the better controller.

const TRIALS = [
  { name: "bench · quick · pursue · reach", flownBy: "pursue",
    run: run("succeeded", { task: { score: 0.80 } }, "2026-09-20T10:00:00Z") },
  { name: "bench · quick · wary · reach", flownBy: "wary",
    run: run("succeeded", { task: { score: 0.60 } }, "2026-09-20T11:00:00Z") },
  { name: "bench · quick · pursue · transect", flownBy: "pursue",
    run: run("succeeded", { task: { score: 0.30 } }, "2026-09-20T12:00:00Z") },
  { name: "bench · quick · wary · transect", flownBy: "wary",
    run: run("succeeded", { task: { score: 0.55 } }, "2026-09-20T13:00:00Z") },
  // Same task, same suite, a different reef: not the same trial.
  { name: "bench · quick · pursue over al-fahal · dock", flownBy: "pursue",
    run: run("succeeded", { task: { score: 0.90 } }, "2026-09-20T14:00:00Z") },
  { name: "bench · quick · wary · dock", flownBy: "wary",
    run: run("succeeded", { task: { score: 0.10 } }, "2026-09-20T15:00:00Z") },
  // A dive somebody set up by hand has no counterpart.
  { name: "a look at the mooring", flownBy: "pursue",
    run: run("succeeded", { task: { score: 0.99 } }, "2026-09-20T16:00:00Z") },
];

describe("one controller against another", () => {
  it("compares only the trials they both flew", () => {
    const [said] = headToHead("pursue", ["pursue", "wary"], TRIALS);
    expect(said).toBeDefined();
    expect(said!.against).toBe("wary");
    // reach and transect. Not dock — different reefs — and not the hand-flown one.
    expect(said!.shared).toBe(2);
    expect(said!.better).toBe(1);
  });

  it("reads a trial out of the name the bench gave it", () => {
    expect(trialOf("bench · quick · pursue · reach"))
      .toEqual({ suite: "quick", task: "reach", over: "" });
    expect(trialOf("bench · standard · pursue on remus-100 over al-fahal · transect"))
      .toEqual({ suite: "standard", task: "transect", over: "on remus-100 over al-fahal" });
    expect(trialOf("a look at the mooring")).toBeUndefined();
    expect(trialOf("bench · quick · pursue")).toBeUndefined();
  });

  it("says nothing about a controller it has nothing in common with", () => {
    expect(headToHead("pursue", ["pursue", "nobody"], TRIALS)).toEqual([]);
  });

  it("calls a tie a tie rather than a win", () => {
    const tied = [
      { name: "bench · quick · a · reach", flownBy: "a",
        run: run("succeeded", { task: { score: 0.5 } }, "2026-09-20T10:00:00Z") },
      { name: "bench · quick · b · reach", flownBy: "b",
        run: run("succeeded", { task: { score: 0.5 } }, "2026-09-20T10:00:00Z") },
    ];
    const [said] = headToHead("a", ["b"], tied);
    expect(said!.shared).toBe(1);
    expect(said!.better).toBe(0);
    expect(said!.same).toBe(1);
    expect(saidAs(said!)).toBe("the same as b on all 1 shared task");
  });

  it("puts the comparison with the most behind it first", () => {
    const many = [
      ...TRIALS,
      { name: "bench · quick · third · reach", flownBy: "third",
        run: run("succeeded", { task: { score: 0.1 } }, "2026-09-20T10:00:00Z") },
    ];
    const said = headToHead("pursue", ["wary", "third"], many);
    expect(said.map((one) => one.against)).toEqual(["wary", "third"]);
    expect(said[0]!.shared).toBe(2);
    expect(said[1]!.shared).toBe(1);
  });

  it("says it in words somebody can act on", () => {
    const [said] = headToHead("pursue", ["wary"], TRIALS);
    expect(saidAs(said!)).toBe("better than wary on 1 of 2");
  });
});
