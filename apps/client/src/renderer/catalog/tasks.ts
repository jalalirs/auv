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
  /** How a person actually does it, in the water, with these controls. */
  howTo?: string;
  judgedOn: string[];
  /** The objective, or undefined for a dive that is only flown. */
  objective?: Record<string, unknown>;
  /** Why it cannot be chosen yet, when it cannot. */
  unavailable?: string;
}

export const TASKS: Task[] = [
  { key: "hold", name: "Hold station",
    asks: "Stay where you begin, within half a metre and a 30 cm depth band, for five minutes.",
    judgedOn: ["seconds on station of 300", "worst distance off", "thruster effort"],
    objective: { kind: "hold-station", seconds: 300, radiusM: 0.5, depthBandM: 0.3 } },
  { key: "waypoints", name: "Waypoints",
    asks: "Visit four points in order: an eighty by sixty metre box, and back to the start.",
    judgedOn: ["points reached within three metres, in order", "under twenty minutes"],
    objective: { kind: "waypoints", radiusM: 3.0, timeLimitS: 1200,
      points: [{ dx: 80, dy: 0 }, { dx: 80, dy: 60 }, { dx: 0, dy: 60 }, { dx: 0, dy: 0 }] } },
  { key: "transect", name: "Transect",
    asks: "Fly two hundred metres along your heading, three metres above the bottom.",
    judgedOn: ["length flown within 60 cm of altitude", "heading within ten degrees"],
    objective: { kind: "transect", lengthM: 200, altitudeM: 3.0, altitudeBandM: 0.6, headingToleranceDeg: 10, timeLimitS: 900 } },
  { key: "survey", name: "Survey",
    asks: "Cover a sixty by thirty metre rectangle ahead of you in passes, five metres up.",
    judgedOn: ["fraction of the rectangle seen", "at altitude"],
    objective: { kind: "survey", widthM: 60, heightM: 30, altitudeM: 5.0, swathM: 4.0, altitudeBandM: 1.2, timeLimitS: 1500 } },
  { key: "reach", name: "Reach a point",
    asks: "Get to a point two hundred and fifty metres ahead, by the shortest way you can find.",
    judgedOn: ["arriving", "how far you travelled against how far it was", "energy"],
    objective: { kind: "reach", dx: 250, dy: 0, radiusM: 3.0, timeLimitS: 1200 } },
  { key: "search", name: "Find it",
    asks: "Something is in an eighty by fifty metre patch ahead. You are not told where.",
    judgedOn: ["finding it", "how long it took", "ground covered"],
    objective: { kind: "search", widthM: 80, heightM: 50, altitudeM: 4.0, seeM: 8,
      target: { dx: 62, dy: 34 }, timeLimitS: 1500 } },
  { key: "treat", name: "Treat the coral",
    asks: "Pass within reach of every colony in a fifteen-metre patch, low and slow.",
    judgedOn: ["share of the colonies covered", "altitude held", "energy"],
    objective: { kind: "treat", radiusM: 15, reachM: 1.5, altitudeM: 1.5, altitudeBandM: 1.5,
      speedMs: 0.35, timeLimitS: 1500 } },
  { key: "inspect", name: "Inspect",
    asks: "Circle a thing sixty metres away at six metres, keeping it in frame.",
    judgedOn: ["how many of its twelve sides were seen", "distance held"],
    objective: { kind: "inspect", dx: 60, dy: 0, radiusM: 6.0, bandM: 2.5, timeLimitS: 900 } },
  { key: "revisit", name: "Revisit and sample",
    asks: "Visit each marked colony and hold there ten seconds to sample.",
    judgedOn: ["marks sampled", "time held at each"],
    objective: { kind: "revisit", reachM: 2.0, holdS: 10, timeLimitS: 1200,
      marks: [{ dx: 50, dy: 0 }, { dx: 95, dy: 40 }, { dx: 30, dy: 65 }] } },
  { key: "dock", name: "Dock",
    asks: "Get onto the station eighty metres ahead: slowly, straight, and inside 40 cm.",
    judgedOn: ["docked", "how fast it arrived", "how straight"],
    objective: { kind: "dock", dx: 80, dy: 0, approachM: 8, toleranceM: 0.4,
      headingToleranceDeg: 20, speedMs: 0.25, timeLimitS: 1200 } },
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
    asks: "Come back a hundred and fifty metres to the dock, and surface.",
    judgedOn: ["home within three metres", "surfaced", "time taken"],
    objective: { kind: "return", homeRadiusM: 3.0, surfaceDepthM: 0.5, timeLimitS: 900,
      awayM: 150 } },
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


/**
 * How to do each of them, for somebody at the keys.
 *
 * Keyed by the runtime's own kind rather than the composer's, because the
 * console is told what the dive is for by the dive, not by what was clicked
 * an hour ago — a stack can set an objective this application never offered.
 */
export const HOW_TO: Record<string, string> = {
  "hold-station":
    "Let go of the keys. The hold has the vehicle whenever your hands are off it, and holding still is what it does. "
    + "If you have drifted, press Hold here to make this spot the station.",
  waypoints:
    "W drives ahead, Q and E turn. Put the nose on the next point on the chart and run at it; "
    + "the yellow circle fills as each one is reached. Space and C trim the depth.",
  transect:
    "Hold your heading and fly a straight line. The altitude band is what is scored, so watch the section pane "
    + "and keep the trace parallel to the bottom rather than level.",
  survey:
    "Fly the rectangle in passes a swath apart, like mowing. Keep the altitude steady — what is not seen from "
    + "the right height is not covered — and turn at the ends rather than cutting the corner.",
  reach:
    "The point is so many metres ahead of where you were put in — in the vehicle's own frame, because there is "
    + "no GPS down here. It flies on what its log and compass believe, and it is scored on where it actually "
    + "ends up, so the gap between the two is the task. Straight beats fast: you are judged on the ground you "
    + "covered against the ground there was.",
  search:
    "Nobody will tell you where it is. Fly the box in passes so nothing is left unlooked-at, and keep it in "
    + "front of you: the camera only sees what it faces. Your own position is dead reckoned, so the box you "
    + "think you are covering drifts with you.",
  treat:
    "Go low and slow over the patch until every colony has been passed within reach. "
    + "The chart marks them as they are done. Height matters more than speed here.",
  inspect:
    "Circle it while facing it — yaw with Q and E as you go round with A and D. "
    + "It is scored on how many of its twelve sides were actually seen.",
  revisit:
    "Go to each mark and stay there. The sample is the ten seconds of holding still, not the arriving.",
  dock:
    "Line up on the approach and come in straight and slowly. Inside forty centimetres, under a quarter of a "
    + "metre a second, and pointing the right way — arriving fast is a miss. Forty centimetres is finer than "
    + "dead reckoning gets you, which is why a real station has something on it to home to.",
  wait:
    "Nothing to do but stay put. Drifting off the station is what loses marks.",
  mission:
    "Several stages, in order. The panel says which one you are on; finish it and the next begins.",
  return:
    "Come back to where you began, then rise. Home first, surface second — both are scored.",
};
