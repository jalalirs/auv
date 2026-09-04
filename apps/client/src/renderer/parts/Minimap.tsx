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
  /** Where the coral is, world x and y, thinned for drawing. */
  coral?: number[][];
}

export interface Fix { x: number; y: number }

/** What a task asks for, as the runtime describes it for drawing. */
export interface Geometry {
  circle?: { x: number; y: number; radiusM: number };
  points?: { x: number; y: number; depthM: number }[];
  reached?: number;
  line?: { x: number; y: number }[];
  rectangle?: { x: number; y: number }[];
}

export function Minimap({ site, track, position, headingDeg, beganAt, geometry, current, large }: {
  site: Site | undefined;
  track: Fix[];
  position: number[] | undefined;
  headingDeg: number | undefined;
  beganAt: number[] | undefined;
  geometry?: Geometry;
  /** The water's own motion, world x and y, metres per second. */
  current?: number[];
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

    // The coral, as it stands on the bottom. Round and half-transparent, so
    // two thousand colonies read as reef rather than as a solid smear.
    if (site?.coral && site.coral.length > 0) {
      ink.fillStyle = "rgba(250, 208, 96, 0.62)";
      const r = (large ? 1.5 : 0.9) * devicePixelRatio;
      ink.beginPath();
      for (const [cx, cy] of site.coral) {
        const [x, y] = toScreen(cx!, cy!);
        ink.moveTo(x + r, y);
        ink.arc(x, y, r, 0, Math.PI * 2);
      }
      ink.fill();
    }

    // Where it began.
    if (beganAt !== undefined && beganAt.length >= 2) {
      const [bx, by] = toScreen(beganAt[0]!, beganAt[1]!);
      ink.strokeStyle = "#9fb3cc";
      ink.lineWidth = devicePixelRatio;
      ink.beginPath(); ink.arc(bx, by, 4 * devicePixelRatio, 0, Math.PI * 2); ink.stroke();
    }

    // What the task asks for.
    if (geometry !== undefined) {
      ink.strokeStyle = "#f4c542";
      ink.fillStyle = "#f4c542";
      ink.lineWidth = 1.5 * devicePixelRatio;
      ink.setLineDash([4 * devicePixelRatio, 3 * devicePixelRatio]);
      if (geometry.circle) {
        const [cx, cy] = toScreen(geometry.circle.x, geometry.circle.y);
        const r = Math.max(3 * devicePixelRatio, (geometry.circle.radiusM / across) * side);
        ink.beginPath(); ink.arc(cx, cy, r, 0, Math.PI * 2); ink.stroke();
      }
      if (geometry.line && geometry.line.length >= 2) {
        ink.beginPath();
        geometry.line.forEach((p, i) => { const [x, y] = toScreen(p.x, p.y); if (i === 0) ink.moveTo(x, y); else ink.lineTo(x, y); });
        ink.stroke();
      }
      if (geometry.rectangle && geometry.rectangle.length >= 3) {
        ink.beginPath();
        geometry.rectangle.forEach((p, i) => { const [x, y] = toScreen(p.x, p.y); if (i === 0) ink.moveTo(x, y); else ink.lineTo(x, y); });
        ink.closePath(); ink.stroke();
      }
      ink.setLineDash([]);
      if (geometry.points) {
        geometry.points.forEach((p, i) => {
          const [x, y] = toScreen(p.x, p.y);
          const reached = i < (geometry.reached ?? 0);
          ink.beginPath(); ink.arc(x, y, 4 * devicePixelRatio, 0, Math.PI * 2);
          if (reached) ink.fill(); else ink.stroke();
          if (large) {
            ink.font = `${10 * devicePixelRatio}px system-ui, sans-serif`;
            ink.textBaseline = "middle";
            ink.fillText(String(i + 1), x + 7 * devicePixelRatio, y);
          }
        });
      }
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
      const [ax, ay] = toScreen(track[0]!.x, track[0]!.y);
      const [bx, by] = toScreen(track[track.length - 1]!.x, track[track.length - 1]!.y);
      const age = ink.createLinearGradient(ax, ay, bx, by);
      age.addColorStop(0, "rgba(64, 199, 244, 0.18)");
      age.addColorStop(1, "rgba(110, 220, 255, 0.95)");
      ink.strokeStyle = age;
      ink.lineWidth = 1.8 * devicePixelRatio;
      ink.lineJoin = "round";
      ink.lineCap = "round";
      ink.stroke();
    }

    // The vehicle, pointing where it points.
    if (position !== undefined && position.length >= 2) {
      const [vx, vy] = toScreen(position[0]!, position[1]!);
      const heading = ((headingDeg ?? 0) * Math.PI) / 180;
      const size = (large ? 9 : 6) * devicePixelRatio;
      ink.save();
      ink.translate(vx, vy);
      ink.beginPath();
      ink.arc(0, 0, size * 1.9, 0, Math.PI * 2);
      ink.fillStyle = "rgba(255, 122, 92, 0.16)";
      ink.fill();
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

    // The current, as an arrow where a chart puts one, with its speed.
    if (current !== undefined && current.length >= 2) {
      const speed = Math.hypot(current[0]!, current[1]!);
      if (speed > 0.01) {
        const ax = left + side - 30 * devicePixelRatio;
        const ay = top + 30 * devicePixelRatio;
        const ux = current[0]! / speed, uy = -current[1]! / speed;   // screen y is down
        const len = 18 * devicePixelRatio;
        ink.strokeStyle = "#7fd3ff"; ink.fillStyle = "#7fd3ff"; ink.lineWidth = 2 * devicePixelRatio;
        ink.beginPath(); ink.moveTo(ax - ux * len, ay - uy * len); ink.lineTo(ax + ux * len, ay + uy * len); ink.stroke();
        ink.beginPath();
        ink.moveTo(ax + ux * len, ay + uy * len);
        ink.lineTo(ax + ux * len * 0.55 - uy * 5 * devicePixelRatio, ay + uy * len * 0.55 + ux * 5 * devicePixelRatio);
        ink.lineTo(ax + ux * len * 0.55 + uy * 5 * devicePixelRatio, ay + uy * len * 0.55 - ux * 5 * devicePixelRatio);
        ink.closePath(); ink.fill();
        ink.font = `${10 * devicePixelRatio}px system-ui, sans-serif`;
        ink.textBaseline = "top"; ink.textAlign = "right";
        ink.fillText(`${(speed / 0.5144).toFixed(1)} kn`, left + side - 8 * devicePixelRatio, ay + 22 * devicePixelRatio);
        ink.textAlign = "left";
      }
    }

    // North, as a needle in the corner rather than two characters of text.
    const nx = left + side - 16 * devicePixelRatio;
    const ny = top + 18 * devicePixelRatio;
    ink.save();
    ink.translate(nx, ny);
    ink.beginPath();
    ink.moveTo(0, -9 * devicePixelRatio);
    ink.lineTo(4 * devicePixelRatio, 5 * devicePixelRatio);
    ink.lineTo(0, 2 * devicePixelRatio);
    ink.lineTo(-4 * devicePixelRatio, 5 * devicePixelRatio);
    ink.closePath();
    ink.fillStyle = "rgba(159, 179, 204, 0.75)";
    ink.fill();
    ink.restore();
    ink.fillStyle = "rgba(159, 179, 204, 0.75)";
    ink.font = `${9 * devicePixelRatio}px system-ui, sans-serif`;
    ink.textAlign = "center";
    ink.textBaseline = "top";
    ink.fillText("N", nx, ny + 7 * devicePixelRatio);
    ink.textAlign = "left";

    // The scale, on a strip of its own so it reads over any bottom.
    const bar = niceBar(across);
    const barPx = (bar / across) * side;
    const bx = left + side - barPx - 12 * devicePixelRatio;
    const by = top + side - 13 * devicePixelRatio;
    const label = `${bar} m`;
    ink.font = `${10 * devicePixelRatio}px system-ui, sans-serif`;
    const wide = ink.measureText(label).width;
    ink.fillStyle = "rgba(4, 8, 15, 0.55)";
    ink.fillRect(bx - 6 * devicePixelRatio, by - 15 * devicePixelRatio,
                 Math.max(barPx, wide) + 12 * devicePixelRatio, 22 * devicePixelRatio);
    ink.strokeStyle = "#c9d6e6";
    ink.lineWidth = 1.5 * devicePixelRatio;
    ink.beginPath(); ink.moveTo(bx, by); ink.lineTo(bx + barPx, by); ink.stroke();
    ink.beginPath();
    ink.moveTo(bx, by - 3 * devicePixelRatio); ink.lineTo(bx, by + 3 * devicePixelRatio);
    ink.moveTo(bx + barPx, by - 3 * devicePixelRatio); ink.lineTo(bx + barPx, by + 3 * devicePixelRatio);
    ink.stroke();
    ink.fillStyle = "#c9d6e6";
    ink.textBaseline = "bottom";
    ink.fillText(label, bx, by - 4 * devicePixelRatio);
  }, [site, track, position, headingDeg, beganAt, geometry, current, large, track.length]);

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
      // A little relief, lit from the north west, so a reef reads as ground
      // and not as a wash of blue. The slope is the difference to the
      // neighbours a light would come from.
      const west = site.heights[row * site.columns + Math.max(0, column - 1)] ?? h;
      const north = site.heights[Math.min(site.rows - 1, row + 1) * site.columns + column] ?? h;
      const relief = Math.max(-0.18, Math.min(0.18, ((h - west) + (h - north)) / Math.max(0.5, span) * 5));
      const lit = 1 + relief;
      // Depth as a ramp with its shallow end held back: lighting the whole
      // kilometre made the reef read as fog rather than as ground.
      const ramp = share * share * 0.75 + share * 0.25;
      // Rows count up with y; the image counts down. Flip so north is up.
      const at = ((site.rows - 1 - row) * site.columns + column) * 4;
      pixels.data[at] = Math.round(Math.min(255, (6 + 74 * ramp) * lit));
      pixels.data[at + 1] = Math.round(Math.min(255, (22 + 104 * ramp) * lit));
      pixels.data[at + 2] = Math.round(Math.min(255, (44 + 96 * ramp) * lit));
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
