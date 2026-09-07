// Putting a place in the water onto the picture of it.
//
// The sim writes down, for every frame, where the camera was, which way its
// axes pointed and how wide it saw. That is everything needed to do what the
// renderer did: take a point in the world and work out the pixel it fell on.
// With it, a station circle can be drawn on the seabed where the station
// actually is, rather than in a box beside the picture with an arrow.
//
// The arithmetic is the same three lines every game uses. What matters here is
// the conventions, which are ours and not a graphics library's: the world is x
// east, y north, z up, in metres; the camera basis is right/up/forward in that
// same world; and the field of view is written down by the sim rather than
// inferred, because inferring it is how an overlay ends up wrong by four
// degrees in a way that looks like a drawing bug.

/** Where a frame was seen from. Written into every pose by the runtime. */
export interface Looking {
  basis: { right: number[]; up: number[]; forward: number[] };
  eye: number[];
  horizontalFovDeg: number;
  verticalFovDeg: number;
  view?: string;
  upAxis?: string;
}

/** A point on the picture, in the frame's own coordinates, plus its range. */
export interface OnScreen {
  x: number;
  y: number;
  /** Metres in front of the camera. Always positive: behind is not on screen. */
  awayM: number;
}

/** The frame the HUD draws in. The picture's shape, not the window's. */
export const WIDE = 1280;
export const TALL = 720;

function dot(a: number[], b: number[]): number {
  return a[0]! * b[0]! + a[1]! * b[1]! + a[2]! * b[2]!;
}

/** How the camera sees, worked out once per frame rather than per point. */
export class Lens {
  private readonly eye: number[];
  private readonly right: number[];
  private readonly up: number[];
  private readonly forward: number[];
  private readonly tx: number;
  private readonly ty: number;

  constructor(looking: Looking) {
    this.eye = looking.eye;
    this.right = looking.basis.right;
    this.up = looking.basis.up;
    this.forward = looking.basis.forward;
    this.tx = Math.tan((looking.horizontalFovDeg * Math.PI) / 180 / 2);
    this.ty = Math.tan((looking.verticalFovDeg * Math.PI) / 180 / 2);
  }

  /** Where a place in the water falls on the picture, or nothing if behind. */
  at(place: number[]): OnScreen | null {
    const d = [place[0]! - this.eye[0]!, place[1]! - this.eye[1]!, place[2]! - this.eye[2]!];
    const away = dot(d, this.forward);
    if (away <= 0.05) return null;
    const x = dot(d, this.right) / away / this.tx;
    const y = dot(d, this.up) / away / this.ty;
    return { x: (0.5 + x / 2) * WIDE, y: (0.5 - y / 2) * TALL, awayM: away };
  }

  /**
   * A run of points as a path, cut where it passes behind the camera.
   *
   * Dropping the points behind and joining what is left would draw a line
   * across the picture between two things that are nowhere near each other —
   * so the crossing point is worked out and the path stops there.
   */
  path(places: number[][], close = false): string {
    // Kept to a few frames' worth either side. A point a hundred and fifty
    // metres away and nearly edge-on projects to tens of thousands of units,
    // and a renderer asked to draw that has to reason about a canvas that size.
    const near_enough = (v: number): string => Math.max(-4000, Math.min(4000, v)).toFixed(1);
    const ahead = (p: number[]): number =>
      dot([p[0]! - this.eye[0]!, p[1]! - this.eye[1]!, p[2]! - this.eye[2]!], this.forward);
    const near = 0.06;
    const run = close ? [...places, places[0]!] : places;
    let d = "";
    let drawing = false;
    for (let i = 0; i < run.length; i += 1) {
      const here = run[i]!;
      const on = this.at(here);
      if (on !== null) {
        d += `${drawing ? "L" : "M"}${near_enough(on.x)} ${near_enough(on.y)}`;
        drawing = true;
        continue;
      }
      // Behind. If the neighbour is in front, walk to the crossing and stop
      // there, so the line reaches the edge of the picture and no further.
      const next = run[i + 1];
      const previous = run[i - 1];
      for (const other of [previous, next]) {
        if (other === undefined) continue;
        const there = ahead(other);
        if (there <= near) continue;
        const mine = ahead(here);
        const share = (near - mine) / (there - mine);
        const edge = this.at([
          here[0]! + (other[0]! - here[0]!) * share,
          here[1]! + (other[1]! - here[1]!) * share,
          here[2]! + (other[2]! - here[2]!) * share,
        ]);
        if (edge === null) continue;
        d += `${drawing ? "L" : "M"}${near_enough(edge.x)} ${near_enough(edge.y)}`;
        drawing = other === next ? false : true;
      }
      if (next === undefined || ahead(next) <= near) drawing = false;
    }
    return d;
  }

  /** A horizontal ring in the water: a circle drawn where a circle is. */
  ring(centre: number[], radiusM: number, sides = 48): string {
    const round: number[][] = [];
    for (let i = 0; i < sides; i += 1) {
      const a = (i / sides) * Math.PI * 2;
      round.push([centre[0]! + radiusM * Math.cos(a), centre[1]! + radiusM * Math.sin(a), centre[2]!]);
    }
    return this.path(round, true);
  }

  /** How many pixels a metre covers at that distance, for sizing a marker. */
  metresAcross(awayM: number): number {
    return WIDE / (2 * this.tx * Math.max(0.1, awayM));
  }
}

/** Whether a point landed inside the picture rather than off its edge. */
export function inFrame(on: OnScreen | null, margin = 0): on is OnScreen {
  return on !== null && on.x >= -margin && on.x <= WIDE + margin
    && on.y >= -margin && on.y <= TALL + margin;
}

/**
 * Held to the picture's edge, so a marker off-screen still says which way.
 *
 * `keepOut` is somewhere it must not land — the task card, in practice. A
 * transponder a hundred metres behind the vehicle is always off screen, so its
 * marker is always pinned, and pinned to the top left is exactly where the
 * card is: it would sit under the card's text every frame of every dive.
 */
export function heldInside(on: OnScreen, margin = 26, keepOut: Box[] = []): OnScreen {
  const x = Math.max(margin, Math.min(WIDE - margin, on.x));
  let y = Math.max(margin, Math.min(TALL - margin, on.y));
  for (const box of keepOut) {
    if (x > box.x && x < box.x + box.wide && y > box.y && y < box.y + box.tall) {
      y = box.y + box.tall + 14;
    }
  }
  return { ...on, x, y };
}

/** Somewhere a pinned marker must not land: a card, a button. */
export interface Box { x: number; y: number; wide: number; tall: number }

/** Which side of the picture a marker is on, for writing its label inwards. */
export function writtenFrom(on: OnScreen): { anchor: "start" | "end"; dx: number } {
  return on.x > WIDE * 0.62 ? { anchor: "end", dx: -12 } : { anchor: "start", dx: 12 };
}
