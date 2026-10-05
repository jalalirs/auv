// A mission's stages as things on a chart: where each one is, how it is drawn,
// where it leaves the vehicle, and what it costs in time and battery.
//
// Every position is in the place's own frame — metres from the site's middle,
// east and north — which is the frame the runtime flies a drawn stage in, so
// what is drawn here is what is flown. A stage nobody drew is still relative to
// where it begins, as before; it is placed on the chart from where the stage
// before it left the vehicle.

/** A point in the place's frame. */
export interface P { x: number; y: number }

/** One stage, as a mission's document carries it. */
export type Stage = Record<string, unknown> & { kind: string; over?: string };

/** Something laid out in the mission's arrangement, as far as a stage needs it. */
export interface Drawn { id: string; kind: string; x: number; y: number; corners?: P[]; ends?: P[]; route?: P[] }

/**
 * How a stage is drawn on the chart:
 *   route  clicked points in order, finished by hand (waypoints, revisit)
 *   line   two clicks, start then end (a transect)
 *   area   two clicks, opposite corners (a survey)
 *   point  one click (reach, inspect, treat, dock)
 *   none   it happens where the vehicle already is (hold, wait, return)
 *   thing  it is pointed at something laid out, not drawn (follow a pipeline)
 */
export type DrawMode = "route" | "line" | "area" | "point" | "none" | "thing";

interface Shape { mode: DrawMode; field?: string; ring?: string }

const SHAPES: Record<string, Shape> = {
  waypoints: { mode: "route", field: "points" },
  revisit: { mode: "route", field: "marks" },
  transect: { mode: "line" },
  survey: { mode: "area", field: "area" },
  reach: { mode: "point", field: "target" },
  inspect: { mode: "point", field: "target", ring: "radiusM" },
  treat: { mode: "point", field: "centre", ring: "radiusM" },
  dock: { mode: "point", field: "dock" },
  follow: { mode: "thing" },
};

export function drawMode(kind: string): DrawMode {
  return SHAPES[kind]?.mode ?? "none";
}

/** What the palette says a mode asks of the person drawing. */
export function drawPrompt(kind: string, clicked: number): string {
  switch (drawMode(kind)) {
    case "route": return clicked === 0 ? "click each point in order; double-click the last" : "click the next point, or double-click to finish";
    case "line": return clicked === 0 ? "click where the line starts" : "click where it ends";
    case "area": return clicked === 0 ? "click one corner" : "click the opposite corner";
    case "point": return "click where";
    case "thing": return "choose what it follows, in the arrangement";
    default: return "this stage happens where the vehicle already is";
  }
}

function centreOfDrawn(thing: Drawn): P {
  if (thing.corners?.length) {
    const xs = thing.corners.map((c) => c.x), ys = thing.corners.map((c) => c.y);
    return { x: (Math.min(...xs) + Math.max(...xs)) / 2, y: (Math.min(...ys) + Math.max(...ys)) / 2 };
  }
  if (thing.ends?.length === 2) return { x: (thing.ends[0]!.x + thing.ends[1]!.x) / 2, y: (thing.ends[0]!.y + thing.ends[1]!.y) / 2 };
  return { x: thing.x, y: thing.y };
}

function isP(v: unknown): v is P {
  return typeof v === "object" && v !== null
    && typeof (v as P).x === "number" && typeof (v as P).y === "number";
}

/** What a stage looks like on the chart, resolved against what is laid out. */
export interface Geometry {
  route?: P[];
  line?: [P, P];
  area?: P[];
  point?: P;
  /** A ring round the point, metres. */
  ring?: number;
  /** Drawn, rather than relative to where it begins. */
  drawn: boolean;
}

export function geometryOf(stage: Stage, things: Drawn[], from: P): Geometry {
  const over = stage.over ? things.find((t) => t.id === stage.over) : undefined;
  const shape = SHAPES[stage.kind];
  const ring = shape?.ring && typeof stage[shape.ring] === "number" ? Number(stage[shape.ring]) : undefined;
  switch (shape?.mode) {
    case "route": {
      const list = (stage[shape.field!] as unknown[] | undefined) ?? [];
      const route = list.filter(isP);
      return { route, drawn: route.length > 0 };
    }
    case "line": {
      if (isP(stage["from"]) && isP(stage["to"])) return { line: [stage["from"], stage["to"]], drawn: true };
      // Not drawn: along the heading it is given, from where it begins.
      const length = Number(stage["lengthM"] ?? 20);
      const heading = (Number(stage["headingDeg"] ?? 0) * Math.PI) / 180;
      return { line: [from, { x: from.x + length * Math.cos(heading), y: from.y + length * Math.sin(heading) }], drawn: false };
    }
    case "area": {
      const area = (stage["area"] as unknown[] | undefined)?.filter(isP);
      if (area && area.length >= 2) return { area: box(area), drawn: true };
      if (over?.corners?.length) return { area: box(over.corners), drawn: true };
      const w = Number(stage["widthM"] ?? 20), h = Number(stage["heightM"] ?? 10);
      return { area: [from, { x: from.x + w, y: from.y }, { x: from.x + w, y: from.y - h }, { x: from.x, y: from.y - h }], drawn: false };
    }
    case "thing": {
      // Along what it follows, as laid.
      return { route: over?.route ?? over?.ends ?? [], drawn: Boolean(over) };
    }
    case "point": {
      const said = stage[shape.field!];
      if (isP(said)) return { point: said, ring, drawn: true };
      if (over) return { point: centreOfDrawn(over), ring, drawn: true };
      const dx = Number(stage["dx"] ?? 0), dy = Number(stage["dy"] ?? 0);
      return { point: { x: from.x + dx, y: from.y - dy }, ring, drawn: false };
    }
    default:
      return { point: from, drawn: false };
  }
}

/** The four corners of the rectangle some points bound, east and north. */
export function box(points: P[]): P[] {
  const xs = points.map((p) => p.x), ys = points.map((p) => p.y);
  const west = Math.min(...xs), east = Math.max(...xs), south = Math.min(...ys), north = Math.max(...ys);
  return [{ x: west, y: south }, { x: east, y: south }, { x: east, y: north }, { x: west, y: north }];
}

/** A stage given its drawing: what one finished drawing writes into the stage. */
export function drawnInto(stage: Stage, clicks: P[]): Stage {
  const shape = SHAPES[stage.kind];
  if (!shape) return stage;
  const out: Stage = { ...stage };
  for (const relative of ["dx", "dy", "lengthM", "widthM", "heightM", "headingDeg"]) delete out[relative];
  delete out.over;
  switch (shape.mode) {
    case "route": {
      const depth = typeof stage["depthM"] === "number" ? { depthM: stage["depthM"] as number } : {};
      out[shape.field!] = clicks.map((p) => ({ ...p, ...depth }));
      break;
    }
    case "line":
      if (clicks.length < 2) return stage;
      out["from"] = clicks[0]; out["to"] = clicks[1];
      break;
    case "area":
      if (clicks.length < 2) return stage;
      out["area"] = box(clicks.slice(0, 2));
      break;
    case "point":
      if (clicks.length < 1) return stage;
      out[shape.field!] = clicks[0];
      break;
  }
  return out;
}


// ── how it is flown ──────────────────────────────────────────────────────────
//
// The estimate flies the plan the way the runtime's planner and its pursue
// controller do, rather than dividing metres by a speed: the planner turns
// each stage into points and how close counts as there; pursue turns to face
// each point, runs at it with a speed that eases off over the last two metres,
// and its speed loop is proportional only, so it settles below the speed it
// asks for by however much the hull's drag takes. Reckoning at half the top
// speed said four seconds for a tank route that flew in sixty.
//
// Everything below is pursue's own declared settings and the hull's own
// package, except the turn rate, which is fitted: 0.2 rad/s put the arrivals
// of three runs flown on the box (mini-hoot twice in the tank, Boxfish Luna on
// a 30 m leg at Looe Key) within about 5% of when they happened. What it does
// not know: walls, a tether caught on a rock, a current, and how far the
// vehicle's own idea of where it is has drifted.

/** How pursue flies: its declared settings, and the fitted turn rate. */
export interface Pilot { cruiseMs: number; easeM: number; speedKp: number; faceFirstDeg: number; turnRadS: number; arriveM: number }
export const PURSUE: Pilot = { cruiseMs: 0.4, easeM: 2.0, speedKp: 1.2, faceFirstDeg: 45, turnRadS: 0.2, arriveM: 1.0 };

/** The hull as the speed loop meets it, from the vehicle's package. */
export interface Hull {
  /** Mass and surge added mass, kg: what the loop multiplies an acceleration by. */
  massKg: number;
  /** Surge drag, N per m/s and N per (m/s)². */
  linear: number;
  quadratic: number;
}

/** A hull read out of a vehicle's dynamics; a mid-sized one when it says nothing. */
export function hullOf(dynamics: unknown): Hull {
  const d = (dynamics ?? {}) as Record<string, unknown>;
  const first = (key: string): number => {
    const v = d[key];
    const list = Array.isArray(v) ? v : (v as { diagonal?: number[] } | undefined)?.diagonal;
    return Math.abs(Number(list?.[0] ?? 0));
  };
  const mass = Number(d["massKg"] ?? 0);
  if (!(mass > 0)) return { massKg: 30, linear: 5, quadratic: 40 };
  return { massKg: mass + first("addedMass"), linear: first("linearDamping"), quadratic: first("quadraticDamping") };
}

/** What the planner makes of one stage: points in order, how close counts as
 *  each, a speed limit if it sets one, and time spent still. */
interface Route { points: P[]; arriveM: number; speedMs?: number; holdS: number }

/** plan.py's `_inside`: a share of what the task counts, never under a floor,
 *  never more than most of the task's own radius. */
function inside(radius: number, share: number, floor: number): number {
  return Math.min(Math.max(floor, radius * share), radius * 0.8);
}

/** Lanes across a rectangle, from its corner nearest the vehicle. */
function lanes(area: P[], spacing: number, from: P): P[] {
  const west = area[0]!.x, east = area[1]!.x, south = area[0]!.y, north = area[2]!.y;
  const startX = Math.abs(from.x - west) <= Math.abs(from.x - east) ? west : east;
  const startY = Math.abs(from.y - south) <= Math.abs(from.y - north) ? south : north;
  const count = Math.max(1, Math.ceil(Math.abs(north - south) / spacing));
  const step = (north - south) / count * (startY === south ? 1 : -1);
  const out: P[] = [];
  let x = startX;
  for (let k = 0; k <= count; k++) {
    const y = startY + k * step;
    const other = x === west ? east : west;
    out.push({ x, y }, { x: other, y });
    x = other;
  }
  return out;
}

function routeOf(stage: Stage, things: Drawn[], from: P, launch: P): Route {
  const g = geometryOf(stage, things, from);
  const num = (key: string, fallback: number) => (typeof stage[key] === "number" ? Number(stage[key]) : fallback);
  switch (stage.kind) {
    case "waypoints":
      return { points: g.route ?? [], arriveM: inside(num("radiusM", 1.0), 0.6, 0.25), holdS: 0 };
    case "revisit": {
      const marks = g.route ?? [];
      return { points: marks, arriveM: inside(num("radiusM", 1.0), 0.6, 0.25), holdS: (num("holdS", 0) + 1) * marks.length };
    }
    case "transect":
      return { points: g.line ? [...g.line] : [], arriveM: PURSUE.arriveM, holdS: 0 };
    case "survey":
      return { points: lanes(g.area!, Math.max(1, num("swathM", 3) * 0.85), from), arriveM: PURSUE.arriveM, holdS: 0 };
    case "inspect": {
      const r = g.ring ?? num("radiusM", 3), c = g.point!;
      const points = Array.from({ length: 25 }, (_, k) => ({ x: c.x + r * Math.cos((Math.PI * k) / 12), y: c.y + r * Math.sin((Math.PI * k) / 12) }));
      return { points, arriveM: Math.max(0.4, r * 0.2), holdS: 0 };
    }
    case "treat": {
      const r = g.ring ?? num("radiusM", 5), c = g.point!;
      const square = box([{ x: c.x - r, y: c.y - r }, { x: c.x + r, y: c.y + r }]);
      return { points: [c, ...lanes(square, Math.max(1, num("reachM", 1) * 1.6), c)], arriveM: PURSUE.arriveM, holdS: 0 };
    }
    case "reach":
      return { points: [g.point!], arriveM: inside(num("radiusM", 0.5), 0.5, 0.3), holdS: 0 };
    case "follow": {
      // From whichever end is nearer, every point of its route.
      const along = g.route ?? [];
      const near = along.length && Math.hypot(along[0]!.x - from.x, along[0]!.y - from.y)
        > Math.hypot(along[along.length - 1]!.x - from.x, along[along.length - 1]!.y - from.y);
      return { points: near ? [...along].reverse() : along, arriveM: 2.0, holdS: 0 };
    }
    case "dock":
      return { points: [g.point!], arriveM: 0.2, speedMs: 0.125, holdS: 0 };
    case "return":
      return { points: [launch], arriveM: PURSUE.arriveM, holdS: 0 };
    case "hold-station":
      return { points: [], arriveM: 0, holdS: num("seconds", 300) };
    case "wait":
      return { points: [], arriveM: 0, holdS: num("seconds", 0) };
    default:
      return { points: [], arriveM: 0, holdS: 0 };
  }
}

/** Where the vehicle is, which way it points, and how fast it is going. */
interface Flying { at: P; heading: number; speed: number }

/** Pursue along a route, a tenth of a second at a time: turn towards the
 *  point, ease off near it, and the speed the loop and the drag agree on. */
function pursue(state: Flying, route: Route, pilot: Pilot, hull: Hull): { seconds: number; metres: number; movingS: number } {
  const dt = 0.1;
  const cruise = Math.min(pilot.cruiseMs, route.speedMs ?? pilot.cruiseMs);
  const face = (pilot.faceFirstDeg * Math.PI) / 180;
  let seconds = 0, metres = 0, movingS = 0;
  for (const target of route.points) {
    // A day of steps is the most any one point gets: a point the vehicle
    // cannot settle on is not a reason to stop drawing.
    for (let steps = 0; steps < 200_000; steps++) {
      const dx = target.x - state.at.x, dy = target.y - state.at.y;
      const d = Math.hypot(dx, dy);
      if (d <= route.arriveM) break;
      const bearing = Math.atan2(dy, dx);
      let off = bearing - state.heading;
      off = Math.atan2(Math.sin(off), Math.cos(off));
      const turn = Math.max(-pilot.turnRadS * dt, Math.min(pilot.turnRadS * dt, off));
      state.heading += turn;
      const easing = Math.max(0, 1 - Math.abs(off - turn) / face);
      const wanted = cruise * Math.min(1, d / pilot.easeM) * easing;
      const v = state.speed;
      const force = pilot.speedKp * hull.massKg * (wanted - v) - (hull.linear * v + hull.quadratic * v * Math.abs(v));
      state.speed = v + (force / hull.massKg) * dt;
      const moved = Math.min(d, Math.max(0, state.speed) * dt);
      state.at = { x: state.at.x + (moved * dx) / d, y: state.at.y + (moved * dy) / d };
      metres += moved;
      seconds += dt;
      if (state.speed > 0.02) movingS += dt;
    }
  }
  return { seconds: seconds + route.holdS, metres, movingS };
}

/** One stage's share of the day. */
export interface Leg {
  from: P;
  to: P;
  metres: number;
  /** How long it takes, flown as pursue flies it. */
  flyS: number;
  /** How long the plan allows it. */
  allowS: number;
}

/** The whole plan, stage by stage, from the launch, flown by `pilot` in `hull`. */
export function legsOf(stages: Stage[], things: Drawn[], launch: P, hull: Hull, pilot: Pilot = PURSUE): Leg[] {
  const state: Flying = { at: launch, heading: 0, speed: 0 };
  return stages.map((stage) => {
    const from = state.at;
    const route = routeOf(stage, things, from, launch);
    const { seconds, metres } = pursue(state, route, pilot, hull);
    // Where the stage leaves it is its last point, not wherever "close
    // enough" happened to be — the next stage is drawn from there.
    const to = route.points.length ? route.points[route.points.length - 1]! : from;
    state.at = to;
    return { from, to, metres, flyS: seconds, allowS: Number(stage["timeLimitS"] ?? stage["seconds"] ?? 300) };
  });
}

/** Every point the plan touches, for a chart to open on. */
export function extentOf(stages: Stage[], things: Drawn[], legs: Leg[]): P[] {
  const points: P[] = legs.flatMap((l) => [l.from, l.to]);
  stages.forEach((stage, i) => {
    const g = geometryOf(stage, things, legs[i]?.from ?? { x: 0, y: 0 });
    points.push(...(g.route ?? []), ...(g.line ?? []), ...(g.area ?? []));
    if (g.point) {
      const r = g.ring ?? 0;
      points.push({ x: g.point.x - r, y: g.point.y - r }, { x: g.point.x + r, y: g.point.y + r });
    }
  });
  return points;
}

/** How far dead reckoning drifts, as a share of the distance flown. Measured
 *  once: Boxfish Luna, flown with nothing overhead at Looe Key on 4 October
 *  2026, was 4.8 m out after 203 m. */
export const DRIFT_SHARE = 4.8 / 203;

/** The stages that ask to be met closer than the vehicle will know where it is,
 *  flying with no fix: the drift by the end of each, against its radius. */
export function driftRisks(stages: Stage[], legs: Leg[]): { stage: number; radiusM: number; driftM: number }[] {
  const out: { stage: number; radiusM: number; driftM: number }[] = [];
  let flown = 0;
  stages.forEach((stage, i) => {
    flown += legs[i]?.metres ?? 0;
    const fallback = stage.kind === "reach" ? 0.5 : stage.kind === "waypoints" || stage.kind === "revisit" ? 1 : undefined;
    if (fallback === undefined) return;
    const radiusM = typeof stage["radiusM"] === "number" ? Number(stage["radiusM"]) : fallback;
    const driftM = flown * DRIFT_SHARE;
    if (driftM > radiusM) out.push({ stage: i, radiusM, driftM });
  });
  return out;
}

/** The speed pursue's loop and the hull's drag agree on at cruise: the loop
 *  pushes in proportion to what it is short of, the drag pushes back. */
export function settledMs(hull: Hull, pilot: Pilot = PURSUE): number {
  const k = pilot.speedKp * hull.massKg, c = pilot.cruiseMs;
  // k (c - v) = linear v + quadratic v², solved for v.
  const a = hull.quadratic, b = hull.linear + k;
  return a > 0 ? (-b + Math.sqrt(b * b + 4 * a * k * c)) / (2 * a) : (k * c) / b;
}

/** The least a vehicle can draw flying at its settled speed: the hotel load and
 *  the drag's power through a propeller a third efficient. Flown runs have drawn
 *  two to three times this — holding depth and heading costs more than moving. */
export function floorWatts(hull: Hull, hotelW: number, pilot: Pilot = PURSUE): number {
  const v = settledMs(hull, pilot);
  return hotelW + ((hull.linear * v + hull.quadratic * v * v) * v) / 0.3;
}

/** What one run of a vehicle drew, on average, in watts: its energy over its
 *  time, from the runs that say both. */
export function wattsOf(outcomes: (Record<string, unknown> | undefined)[]): { watts: number; runs: number } | undefined {
  const each: number[] = [];
  for (const outcome of outcomes) {
    if (!outcome) continue;
    const task = outcome["task"] as Record<string, unknown> | undefined;
    const battery = outcome["battery"] as Record<string, unknown> | undefined;
    const wh = Number(task?.["energyWh"] ?? outcome["energyWh"] ?? battery?.["spentWh"] ?? NaN);
    const s = Number(task?.["seconds"] ?? outcome["seconds"] ?? NaN);
    if (wh > 0 && s > 5) each.push((wh * 3600) / s);
  }
  if (each.length === 0) return undefined;
  each.sort((a, b) => a - b);
  // The middle one: a run that sat on the bottom with its thrusters off, or
  // spent a minute pinned to the glass, is not what the next one will draw.
  return { watts: each[Math.floor(each.length / 2)]!, runs: each.length };
}

/** Rounded to the place's scale: a centimetre in a tank, a metre on a reef. */
export function snap(v: number, acrossM: number): number {
  const step = 10 ** Math.floor(Math.log10(Math.max(1e-3, acrossM / 500)));
  return Math.round(v / step) * step;
}
