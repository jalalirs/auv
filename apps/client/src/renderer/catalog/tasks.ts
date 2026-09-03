// The six tasks a dive can be for.
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
  { key: "inspect", name: "Inspect",
    asks: "Approach a structure and circle it.",
    judgedOn: ["object in frame", "from how many bearings", "at what distance"],
    unavailable: "needs a structure in the place; none is placed yet" },
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
