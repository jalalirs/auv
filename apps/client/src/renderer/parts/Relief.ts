// A picture of a place drawn from its own seabed, for a place that has no
// photograph, coloured as a nautical chart is: one blue ramp from pale in the
// shallows to navy in the deep, lit from the north-west, with thin depth
// contours at a round interval. It is the place's measured or derived ground
// and nothing else, so it cannot show a reef that is not there.
//
// The ramp and the painter are shared: the place's chart (SiteChart), the
// fit map and the 3D editor colour depth with the same function, so a spot is
// the same blue wherever it is drawn.

import { useEffect, useState } from "react";

import type { PlacePackage } from "../platform/packages.js";
import { groundAt, groundOf, type Ground } from "./SiteChart.js";

const WIDE = 480;
const HIGH = 270;

const drawn = new WeakMap<PlacePackage, Promise<string | undefined>>();

/** The relief of a package's seabed as an image address, or nothing if it has no seabed. */
export function reliefOf(pkg: PlacePackage): Promise<string | undefined> {
  let one = drawn.get(pkg);
  if (one === undefined) {
    one = groundOf(pkg).then((ground) => (ground ? draw(ground) : undefined)).catch(() => undefined);
    drawn.set(pkg, one);
  }
  return one;
}

/**
 * A place's picture: its own photograph if it has one, otherwise its relief.
 * Undefined while it is still being read or drawn; null when there is none.
 */
export function usePlacePicture(pkg: PlacePackage | null | undefined): string | null | undefined {
  const [relief, setRelief] = useState<{ of: PlacePackage; url: string | undefined } | undefined>();
  useEffect(() => {
    if (!pkg || pkg.pictureUrl) return;
    let stale = false;
    void reliefOf(pkg).then((url) => { if (!stale) setRelief({ of: pkg, url }); });
    return () => { stale = true; };
  }, [pkg]);
  if (pkg === null) return null;
  if (pkg === undefined) return undefined;
  if (pkg.pictureUrl) return pkg.pictureUrl;
  if (relief?.of !== pkg) return undefined;
  return relief.url ?? null;
}

// ── the nautical ramp ──────────────────────────────────────────────────────

/** Stops from the waterline down, as a fraction of the deepest: pale blue to navy. */
const RAMP: [number, number, number, number][] = [
  [0, 218, 236, 244],
  [0.12, 178, 216, 236],
  [0.3, 122, 178, 214],
  [0.55, 62, 122, 178],
  [0.8, 30, 72, 128],
  [1, 14, 38, 82],
];

/** Ground above the water: a pale grey, not sand, so a chart is one ramp. */
const DRY: [number, number, number] = [226, 231, 233];

/**
 * The colour of a depth on a chart, as 0–255 RGB: pale in the shallows, navy
 * at `maxDepthM` and beyond, the pale grey of dry ground at or above the
 * surface. Square-rooted, so the shallows, where most of the work is, get
 * most of the ramp.
 */
export function nauticalColour(depthM: number, maxDepthM: number): [number, number, number] {
  if (!Number.isFinite(depthM) || depthM < 0.05) return [...DRY];
  const t = Math.sqrt(Math.min(1, Math.max(0, depthM / Math.max(0.1, maxDepthM))));
  let i = 1;
  while (i < RAMP.length - 1 && RAMP[i]![0] < t) i++;
  const [t0, r0, g0, b0] = RAMP[i - 1]!;
  const [t1, r1, g1, b1] = RAMP[i]!;
  const f = (t - t0) / Math.max(1e-6, t1 - t0);
  return [r0 + (r1 - r0) * f, g0 + (g1 - g0) * f, b0 + (b1 - b0) * f];
}

/** A round interval between contours, about eight of them over the depth range. */
export function contourStep(maxDepthM: number): number {
  const want = Math.max(0.05, maxDepthM / 8);
  const step = 10 ** Math.floor(Math.log10(want));
  return [1, 2, 5, 10].map((k) => k * step).find((s) => s >= want) ?? step * 10;
}

/**
 * Paints depths as a chart into RGBA pixels: the ramp, a hillshade from the
 * north-west and a thin contour where the depth crosses a round interval.
 * `depths` is `wide × high`, row 0 at the top (north); `metresPerPixel` sizes
 * the slopes, and `lift` exaggerates them so a flat tank still reads as a shape.
 */
export function paintDepths(depths: Float32Array, wide: number, high: number, maxDepthM: number,
                            metresPerPixel: number, out: Uint8ClampedArray, lift = 1): void {
  const step = contourStep(maxDepthM);
  const at = (x: number, y: number): number => {
    const v = depths[Math.min(high - 1, Math.max(0, y)) * wide + Math.min(wide - 1, Math.max(0, x))]!;
    return Number.isFinite(v) ? v : 0;
  };
  const band = (d: number): number => (d < 0.05 ? -1 : Math.floor(d / step));
  // Light from the north-west and above; a flat bottom is lit at 1.
  const lx = -0.5, ly = 0.5, lz = Math.SQRT1_2;
  const k = lift / (2 * Math.max(1e-6, metresPerPixel));
  for (let y = 0; y < high; y++) {
    for (let x = 0; x < wide; x++) {
      const d = at(x, y);
      // Height is minus depth; east is +x, north is up the picture.
      const east = -(at(x + 1, y) - at(x - 1, y)) * k;
      const north = -(at(x, y - 1) - at(x, y + 1)) * k;
      const lambert = (-east * lx - north * ly + lz) / Math.sqrt(east * east + north * north + 1);
      const shade = Math.min(1.15, Math.max(0.62, 1 + 0.9 * (lambert / lz - 1)));
      let [r, g, b] = nauticalColour(d, maxDepthM);
      if (d >= 0.05) { r *= shade; g *= shade; b *= shade; }
      // A contour: this pixel's band differs from the one east or south of it.
      const here = band(d);
      if (here !== band(at(x + 1, y)) || here !== band(at(x, y + 1))) {
        const ink = here === -1 || band(at(x + 1, y)) === -1 || band(at(x, y + 1)) === -1 ? 0.45 : 0.72;
        r *= ink; g *= ink; b *= ink;
      }
      const i = (y * wide + x) * 4;
      out[i] = Math.min(255, r); out[i + 1] = Math.min(255, g); out[i + 2] = Math.min(255, b); out[i + 3] = 255;
    }
  }
}

function draw(ground: Ground): string {
  const { rows, columns, depth, acrossM } = ground;
  let deepest = 0.5;
  for (const d of depth) if (Number.isFinite(d) && d > deepest) deepest = d;
  // Cropped to the card's shape from the middle of the square.
  const scale = Math.max(WIDE / columns, HIGH / rows);
  const offX = (columns * scale - WIDE) / 2;
  const offY = (rows * scale - HIGH) / 2;
  // Sampled between the cells, so contours run smooth when the picture is
  // finer than the heightfield.
  const depths = new Float32Array(WIDE * HIGH);
  for (let py = 0; py < HIGH; py++) {
    // North up: the chart draws the last row at the top.
    const r = rows - 1 - (py + offY) / scale;
    const y = (r / Math.max(1, rows - 1) - 0.5) * acrossM;
    for (let px = 0; px < WIDE; px++) {
      const c = (px + offX) / scale;
      depths[py * WIDE + px] = groundAt(ground, (c / Math.max(1, columns - 1) - 0.5) * acrossM, y);
    }
  }
  const perPixel = acrossM / Math.max(1, columns - 1) / scale;
  // Relief exaggerated by how flat the place is, so a tank and a reef slope
  // both read as shapes rather than one being a flat colour.
  const lift = Math.min(12, Math.max(2, (acrossM / deepest) * 0.08));

  const canvas = document.createElement("canvas");
  canvas.width = WIDE; canvas.height = HIGH;
  const g = canvas.getContext("2d");
  if (!g) return "";
  const pixels = g.createImageData(WIDE, HIGH);
  paintDepths(depths, WIDE, HIGH, deepest, perPixel, pixels.data, lift);
  g.putImageData(pixels, 0, 0);
  return canvas.toDataURL("image/jpeg", 0.88);
}
