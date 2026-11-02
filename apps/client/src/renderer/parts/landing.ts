// Where a thing ends up on the seabed, worked out while it is being placed.
//
// Three answers, each from the place's own heightfield and nothing else:
//
//   restOn   a rigid base set down on the ground: the depth at its middle,
//            how far it tilts, and the most daylight under any part of it
//   drape    a pipe laid along a route: where it rests and where it bridges
//            a hollow, with its stiffness (bend radius) deciding which
//   fall     a thing let go at the surface: it sinks against drag, drifts
//            with the current, and lands where the ground catches it
//
// None of this is the coupled engine. It is the arithmetic a person would do
// on the back of an envelope, done at every mouse move so the answer is there
// before the click rather than after a build.

import { groundAt, type Ground } from "./SiteChart.js";

const WATER = 1025;
const G = 9.81;

/** Metres along a route of points. */
export function lengthOf(route: { x: number; y: number }[]): number {
  let total = 0;
  for (let i = 1; i < route.length; i++) total += Math.hypot(route[i]!.x - route[i - 1]!.x, route[i]!.y - route[i - 1]!.y);
  return total;
}

export interface Rest {
  /** Depth under the middle of the base, metres. */
  depthM: number;
  /** How far the base leans from level, degrees. */
  tiltDeg: number;
  /** The widest gap between the base and the ground under it, metres. */
  clearM: number;
  /** How far the ground under it rises and falls, metres. */
  reliefM: number;
}

/**
 * A rigid flat base of `wideM` by `longM`, turned to `headingDeg`, let down at
 * (x, y) until it stops. It stops on the highest ground under it: the plane
 * that is above every point of the ground beneath and has the lowest middle,
 * which is where gravity leaves a stiff base (it rocks onto three points, or
 * fewer when the ground is kind).
 */
export function restOn(ground: Ground, x: number, y: number, wideM: number, longM: number, headingDeg = 0): Rest {
  const n = 5;
  const turn = headingDeg * Math.PI / 180;
  const along = { x: Math.sin(turn), y: Math.cos(turn) }, across = { x: Math.cos(turn), y: -Math.sin(turn) };
  const under: { u: number; v: number; e: number }[] = [];
  for (let i = 0; i < n; i++) {
    for (let j = 0; j < n; j++) {
      const u = (i / (n - 1) - 0.5) * wideM, v = (j / (n - 1) - 0.5) * longM;
      const px = x + across.x * u + along.x * v, py = y + across.y * u + along.y * v;
      under.push({ u, v, e: -groundAt(ground, px, py) });
    }
  }
  const highest = Math.max(...under.map((p) => p.e)), lowest = Math.min(...under.map((p) => p.e));
  // Level on the highest point is always possible; anything lower is better.
  let best = { a: highest, b: 0, c: 0 };
  const above = (a: number, b: number, c: number) => under.every((p) => a + b * p.u + c * p.v >= p.e - 1e-6);
  for (let i = 0; i < under.length; i++) {
    for (let j = i + 1; j < under.length; j++) {
      for (let k = j + 1; k < under.length; k++) {
        const p = under[i]!, q = under[j]!, r = under[k]!;
        // The plane through three points of the ground, if it is a plane.
        const det = (q.u - p.u) * (r.v - p.v) - (r.u - p.u) * (q.v - p.v);
        if (Math.abs(det) < 1e-9) continue;
        const b = ((q.e - p.e) * (r.v - p.v) - (r.e - p.e) * (q.v - p.v)) / det;
        const c = ((q.u - p.u) * (r.e - p.e) - (r.u - p.u) * (q.e - p.e)) / det;
        const a = p.e - b * p.u - c * p.v;
        if (a < best.a - 1e-9 && above(a, b, c)) best = { a, b, c };
      }
    }
  }
  const clear = Math.max(...under.map((p) => best.a + best.b * p.u + best.c * p.v - p.e));
  return { depthM: -best.a, tiltDeg: Math.atan(Math.hypot(best.b, best.c)) * 180 / Math.PI,
           clearM: clear, reliefM: highest - lowest };
}

export interface Draped {
  /** Along the route: distance, the ground and the pipe, both as depths. */
  samples: { s: number; x: number; y: number; groundM: number; pipeM: number }[];
  /** Where the pipe is off the bottom by more than a tenth of a metre. */
  spans: { from: number; to: number; gapM: number }[];
  lengthM: number;
}

/**
 * A pipe laid along `route` with a bend radius it cannot be bent tighter than.
 *
 * It lies as low as it can, never under the ground, never sagging into a
 * hollow tighter than `bendRadiusM`: so it follows a broad hollow down and
 * bridges a narrow one. Solved by raising the pipe until every sag limit
 * holds, which only ever lifts it, so it stops at the lowest pipe possible.
 * Over a sharp crest it is drawn on the ground; a stiff pipe would lift off
 * either side, so the spans it reports are the least there will be.
 */
export function drape(ground: Ground, route: { x: number; y: number }[], bendRadiusM = 150): Draped {
  const total = lengthOf(route);
  if (route.length < 2 || total < 0.5) return { samples: [], spans: [], lengthM: total };
  const ds = Math.min(5, Math.max(0.5, total / 500));
  const points: { s: number; x: number; y: number }[] = [];
  let walked = 0;
  for (let i = 1; i < route.length; i++) {
    const a = route[i - 1]!, b = route[i]!;
    const leg = Math.hypot(b.x - a.x, b.y - a.y);
    for (let t = points.length === 0 ? 0 : (ds - (walked % ds)) % ds; t < leg; t += ds) {
      points.push({ s: walked + t, x: a.x + (b.x - a.x) * t / leg, y: a.y + (b.y - a.y) * t / leg });
    }
    walked += leg;
  }
  points.push({ s: total, ...route[route.length - 1]! });
  const n = points.length;
  const ground_ = points.map((p) => -groundAt(ground, p.x, p.y));
  const pipe = ground_.slice();
  const bend = ds * ds / bendRadiusM;
  for (let pass = 0; pass < 4000; pass++) {
    let moved = 0;
    for (let i = 0; i < n; i++) {
      let low = ground_[i]!;
      // Its bend into a hollow: no tighter than the radius.
      if (i > 0 && i < n - 1) low = Math.max(low, (pipe[i - 1]! + pipe[i + 1]!) / 2 - bend / 2);
      if (low > pipe[i]!) { moved = Math.max(moved, low - pipe[i]!); pipe[i] = low; }
    }
    if (moved < 1e-4) break;
  }
  const samples = points.map((p, i) => ({ ...p, groundM: -ground_[i]!, pipeM: -pipe[i]! }));
  const spans: Draped["spans"] = [];
  let open: { from: number; gapM: number } | undefined;
  for (const one of samples) {
    const gap = one.groundM - one.pipeM;
    if (gap > 0.1) {
      open = open ? { from: open.from, gapM: Math.max(open.gapM, gap) } : { from: one.s, gapM: gap };
    } else if (open) {
      spans.push({ ...open, to: one.s });
      open = undefined;
    }
  }
  if (open) spans.push({ ...open, to: total });
  return { samples, spans, lengthM: total };
}

/** What a thing is, for sinking it. */
export interface Body {
  massKg: number;
  /** The water it pushes aside, cubic metres. */
  volumeM3: number;
  /** Area times drag coefficient, square metres: what the water pushes on. */
  dragAreaM2: number;
}

export interface Fall {
  /** Every 0.1 s of it: where it is, metres in the site and metres down. */
  path: { t: number; x: number; y: number; z: number }[];
  /** Where it landed, or nothing when it floats. */
  landed?: { x: number; y: number; depthM: number; t: number; speed: number };
  floats: boolean;
  /** How fast it would sink with nothing to stop it. */
  terminalMs: number;
}

/**
 * A thing let go at `fromDepthM` over (x, y), sinking through still water
 * moving at `current` (metres a second, east and north). Weight in water
 * against quadratic drag, with half its displaced water carried along as
 * added mass; it drifts until its relative speed matches the current.
 */
export function fall(ground: Ground, x: number, y: number, body: Body,
                     current: { east: number; north: number }, fromDepthM = 0): Fall {
  const weight = (body.massKg - WATER * body.volumeM3) * G;
  const mass = body.massKg + 0.5 * WATER * body.volumeM3;
  const k = 0.5 * WATER * Math.max(body.dragAreaM2, 1e-4);
  const terminal = weight > 0 ? Math.sqrt(weight / k) : 0;
  if (weight <= 0) return { path: [{ t: 0, x, y, z: fromDepthM }], floats: true, terminalMs: 0 };
  const dt = 0.01;
  let t = 0, px = x, py = y, z = fromDepthM, vx = 0, vy = 0, vz = 0;
  const path: Fall["path"] = [{ t, x: px, y: py, z }];
  for (let step = 0; step < 600_000; step++) {
    const rx = current.east - vx, ry = current.north - vy;
    const rel = Math.hypot(rx, ry, vz);
    vx += (k * rx * rel) / mass * dt;
    vy += (k * ry * rel) / mass * dt;
    vz += (weight - k * vz * rel) / mass * dt;
    px += vx * dt; py += vy * dt; z += vz * dt; t += dt;
    const floor = groundAt(ground, px, py);
    if (z >= floor) {
      path.push({ t, x: px, y: py, z: floor });
      return { path, landed: { x: px, y: py, depthM: floor, t, speed: vz }, floats: false, terminalMs: terminal };
    }
    if (step % 10 === 9) path.push({ t, x: px, y: py, z });
  }
  return { path, floats: false, terminalMs: terminal };
}
