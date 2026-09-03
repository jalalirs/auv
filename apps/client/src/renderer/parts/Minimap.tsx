// The site from above, with the vehicle on it and where it has been.
//
// Drawn on the client from the pose and a coarse height grid the dive hands
// over once, because a chart is a chart: nothing in it needs the renderer, and
// a chart that waited on a frame would be a chart that stalled with the
// picture. North is up, the vehicle points where it points, and the track is
// what it has actually done — the only honest summary of a dive there is.

import { useEffect, useRef } from "react";

export interface Site {
  acrossM: number;
  rows: number;
  columns: number;
  heights: number[];
  deepestM: number;
  shallowestM: number;
}

export interface Fix { x: number; y: number }

export function Minimap({ site, track, position, headingDeg, beganAt, large }: {
  site: Site | undefined;
  track: Fix[];
  position: number[] | undefined;
  headingDeg: number | undefined;
  beganAt: number[] | undefined;
  large: boolean;
}): React.JSX.Element {
  const canvas = useRef<HTMLCanvasElement>(null);
  const shaded = useRef<{ site: Site; image: HTMLCanvasElement } | undefined>(undefined);

  useEffect(() => {
    const surface = canvas.current;
    if (surface === null) return;
    const width = Math.max(1, Math.floor(surface.clientWidth * devicePixelRatio));
    const height = Math.max(1, Math.floor(surface.clientHeight * devicePixelRatio));
    if (surface.width !== width) surface.width = width;
    if (surface.height !== height) surface.height = height;
    const ink = surface.getContext("2d");
    if (ink === null) return;

    // The chart is square in the world; the pane is not. Fit the site in it.
    const side = Math.min(width, height);
    const left = (width - side) / 2;
    const top = (height - side) / 2;
    const across = site?.acrossM && site.acrossM > 0 ? site.acrossM : 100;
    const toScreen = (x: number, y: number): [number, number] => [
      left + (x / across + 0.5) * side,
      top + (1 - (y / across + 0.5)) * side,
    ];

    ink.fillStyle = "#050a12";
    ink.fillRect(0, 0, width, height);

    // The bottom, shaded by depth, rendered once per site and then blitted.
    if (site !== undefined && site.rows > 1 && site.columns > 1) {
      if (shaded.current?.site !== site) shaded.current = { site, image: shade(site) };
      ink.imageSmoothingEnabled = true;
      ink.drawImage(shaded.current.image, left, top, side, side);
    } else {
      ink.strokeStyle = "#13233a";
      ink.lineWidth = devicePixelRatio;
      for (let i = 0; i <= 10; i += 1) {
        const at = i / 10;
        ink.beginPath(); ink.moveTo(left + at * side, top); ink.lineTo(left + at * side, top + side); ink.stroke();
        ink.beginPath(); ink.moveTo(left, top + at * side); ink.lineTo(left + side, top + at * side); ink.stroke();
      }
    }
    ink.strokeStyle = "#2a4160";
    ink.lineWidth = devicePixelRatio;
    ink.strokeRect(left, top, side, side);

    // Where it began.
    if (beganAt !== undefined && beganAt.length >= 2) {
      const [bx, by] = toScreen(beganAt[0]!, beganAt[1]!);
      ink.strokeStyle = "#9fb3cc";
      ink.lineWidth = devicePixelRatio;
      ink.beginPath(); ink.arc(bx, by, 4 * devicePixelRatio, 0, Math.PI * 2); ink.stroke();
    }

    // The track.
    if (track.length > 1) {
      ink.beginPath();
      const [sx, sy] = toScreen(track[0]!.x, track[0]!.y);
      ink.moveTo(sx, sy);
      for (let i = 1; i < track.length; i += 1) {
        const [x, y] = toScreen(track[i]!.x, track[i]!.y);
        ink.lineTo(x, y);
      }
      ink.strokeStyle = "rgba(64, 199, 244, 0.85)";
      ink.lineWidth = 1.5 * devicePixelRatio;
      ink.lineJoin = "round";
      ink.stroke();
    }

    // The vehicle, pointing where it points.
    if (position !== undefined && position.length >= 2) {
      const [vx, vy] = toScreen(position[0]!, position[1]!);
      const heading = ((headingDeg ?? 0) * Math.PI) / 180;
      const size = (large ? 9 : 6) * devicePixelRatio;
      ink.save();
      ink.translate(vx, vy);
      // Heading is measured from +x towards +y in the world; on screen y is down.
      ink.rotate(-heading);
      ink.beginPath();
      ink.moveTo(size * 1.4, 0);
      ink.lineTo(-size * 0.8, size * 0.7);
      ink.lineTo(-size * 0.5, 0);
      ink.lineTo(-size * 0.8, -size * 0.7);
      ink.closePath();
      ink.fillStyle = "#ff7a5c";
      ink.fill();
      ink.restore();
    }

    // North, and a scale.
    ink.fillStyle = "#9fb3cc";
    ink.font = `${11 * devicePixelRatio}px system-ui, sans-serif`;
    ink.textBaseline = "top";
    ink.fillText("N ↑", left + 8 * devicePixelRatio, top + 6 * devicePixelRatio);
    const bar = niceBar(across);
    const barPx = (bar / across) * side;
    const bx = left + side - barPx - 10 * devicePixelRatio;
    const by = top + side - 14 * devicePixelRatio;
    ink.strokeStyle = "#9fb3cc";
    ink.lineWidth = 2 * devicePixelRatio;
    ink.beginPath(); ink.moveTo(bx, by); ink.lineTo(bx + barPx, by); ink.stroke();
    ink.textBaseline = "bottom";
    ink.fillText(`${bar} m`, bx, by - 3 * devicePixelRatio);
  }, [site, track, position, headingDeg, beganAt, large, track.length]);

  return <canvas ref={canvas} className="minimap" />;
}

/** The height grid as an image: deep is dark, shallow is pale. */
function shade(site: Site): HTMLCanvasElement {
  const image = document.createElement("canvas");
  image.width = site.columns;
  image.height = site.rows;
  const ink = image.getContext("2d")!;
  const pixels = ink.createImageData(site.columns, site.rows);
  const low = -site.deepestM;
  const high = -site.shallowestM;
  const span = Math.max(0.01, high - low);
  for (let row = 0; row < site.rows; row += 1) {
    for (let column = 0; column < site.columns; column += 1) {
      const h = site.heights[row * site.columns + column] ?? low;
      const share = Math.max(0, Math.min(1, (h - low) / span));
      // Rows count up with y; the image counts down. Flip so north is up.
      const at = ((site.rows - 1 - row) * site.columns + column) * 4;
      pixels.data[at] = Math.round(12 + 90 * share);
      pixels.data[at + 1] = Math.round(38 + 120 * share);
      pixels.data[at + 2] = Math.round(70 + 110 * share);
      pixels.data[at + 3] = 255;
    }
  }
  ink.putImageData(pixels, 0, 0);
  return image;
}

function niceBar(across: number): number {
  const target = across / 5;
  for (const step of [1, 2, 5, 10, 20, 50, 100, 200, 500, 1000]) {
    if (step >= target) return step;
  }
  return 1000;
}
