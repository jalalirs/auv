// What a dive can be for.
//
// From docs/plan/todo.md, item 4. Each says what it asks of the vehicle, what
// it is judged on, and the objective the dive is defined with — the document
// the runtime evaluates as the dive runs, measured from where the dive begins.
// The numbers here are the composer's defaults; the SDK's `coral_city.tasks`
// spells the same fields for a script.

export interface Task {
  key: string;
  name: string;
  asks: string;
  judgedOn: string[];
  /** The objective, or undefined for a dive that is only flown. */
  objective?: Record<string, unknown>;
  /** Why it cannot be chosen yet, when it cannot. */
  unavailable?: string;
}

export const TASKS: Task[] = [
  { key: "hold", name: "Hold station",
    asks: "Stay where you begin, within half a metre and a 30 cm depth band, for a minute.",
    judgedOn: ["seconds on station of 60", "worst distance off", "thruster effort"],
    objective: { kind: "hold-station", seconds: 60, radiusM: 0.5, depthBandM: 0.3 } },
  { key: "waypoints", name: "Waypoints",
    asks: "Visit four points in order: an eight-metre square ahead and to starboard, back to the start.",
    judgedOn: ["points reached within a metre, in order", "under five minutes"],
    objective: { kind: "waypoints", radiusM: 1.0, timeLimitS: 300,
      points: [{ dx: 8, dy: 0 }, { dx: 8, dy: 8 }, { dx: 0, dy: 8 }, { dx: 0, dy: 0 }] } },
  { key: "transect", name: "Transect",
    asks: "Fly twenty metres along your heading two metres above the bottom.",
    judgedOn: ["length flown within half a metre of altitude", "heading within ten degrees"],
    objective: { kind: "transect", lengthM: 20, altitudeM: 2.0, altitudeBandM: 0.5, headingToleranceDeg: 10, timeLimitS: 180 } },
  { key: "survey", name: "Survey",
    asks: "Cover a twenty by ten metre rectangle ahead of you in passes, two metres up, three-metre swath.",
    judgedOn: ["fraction of the rectangle seen", "at altitude"],
    objective: { kind: "survey", widthM: 20, heightM: 10, altitudeM: 2.0, swathM: 3.0, altitudeBandM: 1.0, timeLimitS: 600 } },
  { key: "reach", name: "Reach a point",
    asks: "Get to a point twenty-five metres ahead, by the shortest way you can find.",
    judgedOn: ["arriving", "how far you travelled against how far it was", "energy"],
    objective: { kind: "reach", dx: 25, dy: 0, radiusM: 1.5, timeLimitS: 600 } },
  { key: "search", name: "Find it",
    asks: "Something is in a thirty by twenty metre patch ahead. You are not told where.",
    judgedOn: ["finding it", "how long it took", "ground covered"],
    objective: { kind: "search", widthM: 30, heightM: 20, altitudeM: 2.5, seeM: 6,
      target: { dx: 22, dy: 13 }, timeLimitS: 900 } },
  { key: "treat", name: "Treat the coral",
    asks: "Pass within reach of every colony in a twelve-metre patch, low and slow.",
    judgedOn: ["share of the colonies covered", "altitude held", "energy"],
    objective: { kind: "treat", radiusM: 12, reachM: 1.2, altitudeM: 1.5, altitudeBandM: 1.0,
      speedMs: 0.35, timeLimitS: 1800 } },
  { key: "inspect", name: "Inspect",
    asks: "Circle a thing ten metres ahead at four metres, keeping it in frame.",
    judgedOn: ["how many of its twelve sides were seen", "distance held"],
    objective: { kind: "inspect", dx: 10, dy: 0, radiusM: 4.0, bandM: 2.0, timeLimitS: 900 } },
  { key: "revisit", name: "Revisit and sample",
    asks: "Visit each marked colony and hold there ten seconds to sample.",
    judgedOn: ["marks sampled", "time held at each"],
    objective: { kind: "revisit", reachM: 1.0, holdS: 10, timeLimitS: 1200,
      marks: [{ dx: 8, dy: 0 }, { dx: 16, dy: 6 }, { dx: 10, dy: -8 }] } },
  { key: "dock", name: "Dock",
    asks: "Get onto the station fifteen metres ahead: slowly, straight, and inside 40 cm.",
    judgedOn: ["docked", "how fast it arrived", "how straight"],
    objective: { kind: "dock", dx: 15, dy: 0, approachM: 6, toleranceM: 0.4,
      headingToleranceDeg: 20, speedMs: 0.25, timeLimitS: 900 } },
  { key: "mission", name: "Survey, dock, charge, survey",
    asks: "A survey, then onto the station for five minutes, then out again.",
    judgedOn: ["every stage on its own terms", "and all of them together"],
    objective: { kind: "mission", stages: [
      { kind: "survey", widthM: 14, heightM: 8, altitudeM: 2.0, swathM: 3.0, timeLimitS: 600 },
      { kind: "dock", dx: 0, dy: 0, approachM: 5, toleranceM: 0.5, headingToleranceDeg: 30,
        speedMs: 0.3, timeLimitS: 600 },
      { kind: "wait", seconds: 300, reason: "charging" },
      { kind: "survey", widthM: 14, heightM: 8, altitudeM: 2.0, swathM: 3.0, timeLimitS: 600 },
    ] } },
  { key: "return", name: "Return",
    asks: "Come back to where you began and surface.",
    judgedOn: ["home within two metres", "surfaced", "time taken"],
    objective: { kind: "return", homeRadiusM: 2.0, surfaceDepthM: 0.5, timeLimitS: 300 } },
];

/** What the water is doing: a current, and how far you can see. */
export interface Water {
  key: string;
  name: string;
  says: string;
  parameters: { currentMetresPerSecond: number; currentHeadingDeg: number; visibilityM?: number };
}

export const WATERS: Water[] = [
  { key: "still", name: "Still water", says: "No current. Visibility as the reef has it.",
    parameters: { currentMetresPerSecond: 0, currentHeadingDeg: 0 } },
  { key: "gentle", name: "A gentle set", says: "A quarter of a knot, flowing north.",
    parameters: { currentMetresPerSecond: 0.13, currentHeadingDeg: 0 } },
  { key: "knot", name: "One knot", says: "Half a metre a second, flowing east. The hold works for it.",
    parameters: { currentMetresPerSecond: 0.51, currentHeadingDeg: 90 } },
  { key: "two-knots", name: "Two knots", says: "A metre a second, flowing east. Near the BlueROV2's limit.",
    parameters: { currentMetresPerSecond: 1.03, currentHeadingDeg: 90 } },
  { key: "murky", name: "One knot, murky", says: "Half a metre a second and five metres of visibility.",
    parameters: { currentMetresPerSecond: 0.51, currentHeadingDeg: 90, visibilityM: 5 } },
];

/** A free dive: no task, no score, a person at the controls. */
export const PILOTED: Task = {
  key: "piloted", name: "Piloted",
  asks: "Fly it yourself. No score.",
  judgedOn: [],
};
