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
export interface Drawn { id: string; kind: string; x: number; y: number; corners?: P[]; ends?: P[] }

/**
 * How a stage is drawn on the chart:
 *   route  clicked points in order, finished by hand (waypoints, revisit)
 *   line   two clicks, start then end (a transect)
 *   area   two clicks, opposite corners (a survey)
 *   point  one click (reach, inspect, treat, dock)
 *   none   it happens where the vehicle already is (hold, wait, return)
 */
export type DrawMode = "route" | "line" | "area" | "point" | "none";

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

function dist(a: P, b: P): number { return Math.hypot(b.x - a.x, b.y - a.y); }

/** Where a stage leaves the vehicle, and how far it flies doing it. */
export function flown(stage: Stage, things: Drawn[], from: P, launch: P): { to: P; metres: number; holdS: number } {
  const g = geometryOf(stage, things, from);
  switch (stage.kind) {
    case "waypoints":
    case "revisit": {
      let at = from, metres = 0;
      for (const p of g.route ?? []) { metres += dist(at, p); at = p; }
      const hold = stage.kind === "revisit" ? Number(stage["holdS"] ?? 0) * (g.route?.length ?? 0) : 0;
      return { to: at, metres, holdS: hold };
    }
    case "transect": {
      const [a, b] = g.line!;
      return { to: b, metres: (g.drawn ? dist(from, a) : 0) + dist(a, b), holdS: 0 };
    }
    case "survey": {
      const area = g.area!;
      const w = Math.abs(area[1]!.x - area[0]!.x), h = Math.abs(area[2]!.y - area[1]!.y);
      const swath = Math.max(0.05, Number(stage["swathM"] ?? 3));
      const lanes = Math.max(1, Math.ceil(h / swath));
      // Lanes run east-west and step north-south, from the nearest corner;
      // an odd number of them ends on the other side.
      const start = area.reduce((best, c) => (dist(from, c) < dist(from, best) ? c : best), area[0]!);
      const west = area[0]!.x, east = area[1]!.x, south = area[0]!.y, north = area[2]!.y;
      const otherX = start.x === west ? east : west;
      const otherY = start.y === south ? north : south;
      const end = { x: lanes % 2 === 1 ? otherX : start.x, y: otherY };
      return { to: end, metres: dist(from, start) + lanes * w + (lanes - 1) * swath, holdS: 0 };
    }
    case "inspect": {
      const r = g.ring ?? 0;
      return { to: g.point!, metres: Math.max(0, dist(from, g.point!) - r) + 2 * Math.PI * r, holdS: 0 };
    }
    case "treat": {
      const r = g.ring ?? 0, reach = Math.max(0.1, Number(stage["reachM"] ?? 1.5));
      return { to: g.point!, metres: dist(from, g.point!) + (Math.PI * r * r) / (2 * reach), holdS: 0 };
    }
    case "reach":
    case "dock":
      return { to: g.point!, metres: dist(from, g.point!), holdS: 0 };
    case "return":
      return { to: launch, metres: dist(from, launch), holdS: 0 };
    case "hold-station":
      return { to: from, metres: 0, holdS: Number(stage["seconds"] ?? 300) };
    case "wait":
      return { to: from, metres: 0, holdS: Number(stage["seconds"] ?? 0) };
    default:
      return { to: from, metres: 0, holdS: 0 };
  }
}

/** One stage's share of the day. */
export interface Leg { from: P; to: P; metres: number; flyS: number; allowS: number }

/** The whole plan, stage by stage, from the launch, at a cruising speed. */
export function legsOf(stages: Stage[], things: Drawn[], launch: P, cruiseMs: number): Leg[] {
  let at = launch;
  return stages.map((stage) => {
    const { to, metres, holdS } = flown(stage, things, at, launch);
    const leg = { from: at, to, metres, flyS: metres / Math.max(0.01, cruiseMs) + holdS,
                  allowS: Number(stage["timeLimitS"] ?? stage["seconds"] ?? 300) };
    at = to;
    return leg;
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

/** What a vehicle spends flying it: the hotel load for the whole time and the
 * drag's power at cruise (quadratic surge damping times the speed cubed, over a
 * thruster efficiency, assumed 0.3) for the time spent moving. */
export function energyWh(legs: Leg[], cruiseMs: number, hotelW: number, surgeQuad: number): number {
  const moving = legs.reduce((s, l) => s + l.metres / Math.max(0.01, cruiseMs), 0);
  const total = legs.reduce((s, l) => s + l.flyS, 0);
  const drag = (Math.abs(surgeQuad) * cruiseMs ** 3) / 0.3;
  return (hotelW * total + drag * moving) / 3600;
}

/** Rounded to the place's scale: a centimetre in a tank, a metre on a reef. */
export function snap(v: number, acrossM: number): number {
  const step = 10 ** Math.floor(Math.log10(Math.max(1e-3, acrossM / 500)));
  return Math.round(v / step) * step;
}
