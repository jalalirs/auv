// Laying out a place: what can be put there and how each thing meets the
// bottom. The editor itself is the place designer (PlaceDesigner.tsx).
//
// A dive happens in a site somebody arranged — an array laid in a pattern, a
// ship holding station, nursery frames where they are — and none of that is in
// any survey. This is where it is put there.
//
// It is not a three-dimensional editor and does not want to be. Everything in
// the sea sits on a bottom whose depth is already known at every point, so a
// plan view and a depth under the cursor are enough to place anything: the
// operator works in two dimensions and each tool resolves the third from the
// ground beneath it. A 3-D scene editor would cost a year and a modelling
// skill nobody running a reef programme has.
//
// One tool to begin with. The chain — place, layout, dive, record — matters
// more than the size of the palette, and each further tool is a landing rule
// and a glyph once the chain holds.

import { groundAt, type Ground, type Thing as Charted } from "../parts/SiteChart.js";

/** One end of something, or one thing. */
export interface Point { x: number; y: number; z?: number; groundM?: number }

/** One thing in the water, as the document carries it (the chart's own shape). */
export interface Thing extends Point, Omit<Charted, "x" | "y" | "z" | "groundM" | "ends"> {
  id: string;
  kind: string;
  /** Both ends, for something that spans. */
  ends?: Point[];
  /** The route, for something laid along the bottom. */
  route?: { x: number; y: number }[];
  /** How much longer than the gap the line is: 0 is taut. */
  slack?: number;
  /** The outline, for a plot drawn on the chart. */
  corners?: { x: number; y: number }[];
}

/** How a thing meets the bottom — the only part the editor has to resolve, and
 * the part a layout would otherwise mean two different depths for.
 *
 *   ground   sits on the seabed and stands up from it
 *   surface  floats: depth zero, and the body hangs down
 *   span     two ends, each landed by its own rule, a line between them
 *   region   an area on the chart, which is not in the water at all
 *   laid     a route along the bottom, clicked point by point: a pipeline,
 *            which the runtime rests on the seabed and lets bridge the hollows
 */
export type Lands = "ground" | "surface" | "span" | "region" | "laid";

export interface Tool {
  name: string;
  lands: Lands;
  /** What a click resolves to, said before it is committed. */
  says: (d: number) => string;
  /** What the end of a span lands on, first end then second. */
  endsOn?: [Lands, Lands];
  slack?: number;
}

export const TOOLS: Record<string, Tool> = {
  transponder: { name: "Transponder", lands: "ground",
    says: (d) => `on the bottom at ${d.toFixed(1)} m` },
  "mooring-block": { name: "Mooring block", lands: "ground",
    says: (d) => `on the bottom at ${d.toFixed(1)} m` },
  "nursery-frame": { name: "Nursery frame", lands: "ground",
    says: (d) => `standing on the bottom at ${d.toFixed(1)} m` },
  "marker-post": { name: "Marker post", lands: "ground",
    says: (d) => `three metres up from ${d.toFixed(1)} m` },
  ship: { name: "Ship", lands: "surface",
    says: () => "holding station at the surface, three metres of hull under it" },
  buoy: { name: "Buoy", lands: "surface",
    says: () => "on the surface" },
  dredger: { name: "Dredger", lands: "surface",
    says: () => "working at the surface, losing 20 kg/s at its overflow: a plume the current carries" },
  "mooring-line": { name: "Mooring line", lands: "span", endsOn: ["ground", "surface"],
    slack: 0.02,
    says: (d) => `one end on the bottom at ${d.toFixed(1)} m, the other at the surface` },
  pipeline: { name: "Pipeline", lands: "laid",
    says: () => "laid along the bottom: click its route, double-click the last point; it rests on the high ground and bridges the hollows" },
  "restoration-cell": { name: "Restoration cell", lands: "region",
    says: () => "a plot on the chart — something to work inside, not something to hit" },
};

/** The palette, in the order the panel shows it: by landing rule, because that
 * is what the editor resolves and what tells you where a thing will end up. */
export const GROUPS: { title: string; lands: Lands }[] = [
  { title: "Sits on the ground", lands: "ground" },
  { title: "Floats", lands: "surface" },
  { title: "Runs between two points", lands: "span" },
  { title: "Laid along the bottom", lands: "laid" },
  { title: "Drawn on the chart", lands: "region" },
];

export const DESCRIBED_BY = "coral-city/layout/v1";

// Said in the document rather than known by whoever reads it. A layout is read
// by the editor, the runtime, a replay and one day a sonar, and a frame that
// each of them has to guess is a frame three of them will get wrong.
export const FRAME = "metres, origin at the middle of the site, +x east, +y north";

/** A name that will not collide with the one made a millisecond ago. */
export function named(kind: string): string {
  return `${kind}-${Date.now().toString(36)}-${Math.floor(Math.random() * 4096).toString(36)}`;
}

/** Where a click puts something, by its landing rule, resolved now and kept. */
export function landed(lands: Lands, ground: Ground, x: number, y: number): Point {
  const deep = groundAt(ground, x, y);
  const at = { x: Math.round(x * 10) / 10, y: Math.round(y * 10) / 10,
               groundM: Math.round(deep * 10) / 10 };
  // Something floating is at the surface whatever the bottom is doing; the
  // depth under it is still worth keeping, because that is what decides
  // whether a line from it can reach.
  return { ...at, z: lands === "surface" ? 0 : Math.round(-deep * 10) / 10 };
}

/** What the listing says about a thing, which is not always one depth. */
export function saysOf(thing: Thing): string {
  if (thing.route && thing.route.length >= 2) {
    const r = thing.route;
    return `${Math.round(r.slice(1).reduce((s, p, i) => s + Math.hypot(p.x - r[i]!.x, p.y - r[i]!.y), 0))} m long`;
  }
  if (thing.ends?.length === 2) {
    const [a, b] = thing.ends as [Point, Point];
    return `${Math.round(Math.hypot(b.x - a.x, b.y - a.y))} m long`;
  }
  if (thing.corners?.length === 4) {
    const xs = thing.corners.map((c) => c.x), ys = thing.corners.map((c) => c.y);
    const wide = Math.max(...xs) - Math.min(...xs), tall = Math.max(...ys) - Math.min(...ys);
    return `${Math.round(wide)} × ${Math.round(tall)} m`;
  }
  if (TOOLS[thing.kind]?.lands === "surface") return "at the surface";
  return `${(thing.groundM ?? 0).toFixed(1)} m`;
}

/** A copy, moved, with every part of it landed again where it now is.
 *
 * A copy is a new thing. Copying the reference instead is how a duplicated
 * array turns out to be one transponder in eight places, and it is found much
 * later than it is made — and a duplicate that kept the original's depths
 * would be a thing floating above or buried in the bottom it was moved to.
 */
export function shifted(thing: Thing, dx: number, dy: number, ground: Ground | undefined): Thing {
  const copy: Thing = { ...thing, id: named(thing.kind), x: thing.x + dx, y: thing.y + dy };
  const lands = TOOLS[thing.kind]?.lands ?? "ground";
  if (thing.ends) {
    const [firstOn, secondOn] = TOOLS[thing.kind]?.endsOn ?? ["ground", "ground"];
    copy.ends = thing.ends.map((end, i) => {
      const moved = { x: end.x + dx, y: end.y + dy };
      return ground ? landed(i === 0 ? firstOn : secondOn, ground, moved.x, moved.y)
                    : { ...end, ...moved };
    });
  }
  if (thing.corners) copy.corners = thing.corners.map((c) => ({ x: c.x + dx, y: c.y + dy }));
  if (ground && !thing.ends) Object.assign(copy, landed(lands, ground, copy.x, copy.y));
  return copy;
}

/** A line between two clicks, each end landed by its own rule. */
export function spanBetween(kind: string, what: Tool, ground: Ground,
                     from: { x: number; y: number }, to: { x: number; y: number }): Thing | undefined {
  if (Math.hypot(to.x - from.x, to.y - from.y) < 1) return undefined;
  const [firstOn, secondOn] = what.endsOn ?? ["ground", "ground"];
  const ends = [landed(firstOn, ground, from.x, from.y), landed(secondOn, ground, to.x, to.y)];
  return { id: named(kind), kind, x: (ends[0]!.x + ends[1]!.x) / 2,
           y: (ends[0]!.y + ends[1]!.y) / 2, ends, slack: what.slack ?? 0 };
}

/** A plot between two clicks: the rectangle they bound, wound anticlockwise. */
export function cellBetween(kind: string, ground: Ground,
                     from: { x: number; y: number }, to: { x: number; y: number }): Thing | undefined {
  const west = Math.min(from.x, to.x), east = Math.max(from.x, to.x);
  const south = Math.min(from.y, to.y), north = Math.max(from.y, to.y);
  if (east - west < 1 || north - south < 1) return undefined;
  const round = (v: number) => Math.round(v * 10) / 10;
  const corners = [{ x: round(west), y: round(south) }, { x: round(east), y: round(south) },
                   { x: round(east), y: round(north) }, { x: round(west), y: round(north) }];
  const middle = { x: (west + east) / 2, y: (south + north) / 2 };
  return { id: named(kind), kind, ...middle, corners,
           groundM: Math.round(groundAt(ground, middle.x, middle.y) * 10) / 10 };
}
