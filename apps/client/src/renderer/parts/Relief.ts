// A picture of a place drawn from its own seabed, for a place that has no
// photograph: shaded relief, sand above the water, pale in the shallows and
// deep blue as it falls away. It is the place's measured or derived ground and
// nothing else, so it cannot show a reef that is not there.

import { useEffect, useState } from "react";

import type { PlacePackage } from "../platform/packages.js";
import { groundOf, type Ground } from "./SiteChart.js";

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

function draw(ground: Ground): string {
  const { rows, columns, depth, acrossM } = ground;
  let deepest = 0.5;
  for (const d of depth) if (Number.isFinite(d) && d > deepest) deepest = d;
  const at = (c: number, r: number): number => {
    const v = depth[Math.min(rows - 1, Math.max(0, r)) * columns + Math.min(columns - 1, Math.max(0, c))];
    return v !== undefined && Number.isFinite(v) ? v : 0;
  };
  // Relief exaggerated by how flat the place is, so a tank and a reef slope
  // both read as shapes rather than one being a flat colour.
  const cell = acrossM / Math.max(1, columns - 1);
  const lift = Math.min(12, Math.max(2, (acrossM / deepest) * 0.08)) / cell;
  // Cropped to the card's shape from the middle of the square.
  const scale = Math.max(WIDE / columns, HIGH / rows);
  const offX = (columns * scale - WIDE) / 2;
  const offY = (rows * scale - HIGH) / 2;

  const canvas = document.createElement("canvas");
  canvas.width = WIDE; canvas.height = HIGH;
  const g = canvas.getContext("2d");
  if (!g) return "";
  const pixels = g.createImageData(WIDE, HIGH);
  for (let py = 0; py < HIGH; py++) {
    // North up: the chart draws the last row at the top.
    const r = rows - 1 - Math.floor((py + offY) / scale);
    for (let px = 0; px < WIDE; px++) {
      const c = Math.floor((px + offX) / scale);
      const d = at(c, r);
      // Light from the north-west, on the surface the depths make.
      const dx = (at(c + 1, r) - at(c - 1, r)) * lift;
      const dy = (at(c, r + 1) - at(c, r - 1)) * lift;
      const shade = Math.min(1.25, Math.max(0.35, 0.85 + (dx - dy) * 0.35 / Math.sqrt(1 + dx * dx + dy * dy)));
      let red: number, green: number, blue: number;
      if (d < 0.05) {
        [red, green, blue] = [200, 184, 146];
      } else {
        const t = Math.sqrt(Math.min(1, d / deepest));
        red = 70 - 62 * t;
        green = 196 - 160 * t;
        blue = 200 - 128 * t;
      }
      const i = (py * WIDE + px) * 4;
      pixels.data[i] = Math.min(255, red * shade);
      pixels.data[i + 1] = Math.min(255, green * shade);
      pixels.data[i + 2] = Math.min(255, blue * shade);
      pixels.data[i + 3] = 255;
    }
  }
  g.putImageData(pixels, 0, 0);
  return canvas.toDataURL("image/jpeg", 0.85);
}
