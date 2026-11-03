// A place's seabed from above, shaded by depth, with where a reconstruction
// could go drawn over it: each candidate the strip's own outline, turned and
// moved as it would be laid, and the swim's start.

import { useEffect, useMemo, useRef, useState } from "react";

import { paintDepths } from "./Relief.js";

export type Spot = { at: [number, number]; headingDeg: number; startAt?: number[] };

export function FitMap({ heightsUrl, rows, columns, acrossM, extentM, spots, chosen, start, onChoose, size = 520 }: {
  heightsUrl?: string;
  rows: number;
  columns: number;
  acrossM: number;
  /** The strip's length and width, in its own frame. */
  extentM: [number, number];
  spots: Spot[];
  chosen?: number;
  /** Where the video was said to start, in the place's metres. */
  start?: [number, number] | null;
  onChoose?: (index: number) => void;
  size?: number;
}): React.JSX.Element {
  const canvas = useRef<HTMLCanvasElement>(null);
  const [heights, setHeights] = useState<Float32Array | undefined>();
  const [trouble, setTrouble] = useState("");
  const [whole, setWhole] = useState(false);
  // The window drawn: close round the candidates and the start, or the
  // whole place. A 100 m reef on a 3 km place is a few pixels.
  const view = useMemo(() => {
    const half = acrossM / 2;
    const xs = spots.map((s) => s.at[0]).concat(start ? [start[0]] : []);
    const ys = spots.map((s) => s.at[1]).concat(start ? [start[1]] : []);
    if (whole || xs.length === 0) return { x0: -half, y0: -half, side: acrossM };
    const pad = Math.max(extentM[0], 120);
    const x0 = Math.min(...xs) - pad, x1 = Math.max(...xs) + pad;
    const y0 = Math.min(...ys) - pad, y1 = Math.max(...ys) + pad;
    const side = Math.min(acrossM, Math.max(x1 - x0, y1 - y0, 300));
    const cx = Math.min(Math.max((x0 + x1) / 2, -half + side / 2), half - side / 2);
    const cy = Math.min(Math.max((y0 + y1) / 2, -half + side / 2), half - side / 2);
    return { x0: cx - side / 2, y0: cy - side / 2, side };
  }, [spots, start, acrossM, extentM, whole]);

  useEffect(() => {
    if (!heightsUrl) return;
    let stale = false;
    fetch(heightsUrl).then((r) => r.arrayBuffer())
      .then((b) => { if (!stale) setHeights(new Float32Array(b)); })
      .catch(() => setTrouble("could not read the place's seabed"));
    return () => { stale = true; };
  }, [heightsUrl]);

  const toPixel = (x: number, y: number): [number, number] =>
    [((x - view.x0) / view.side) * size, (1 - (y - view.y0) / view.side) * size];

  useEffect(() => {
    const c = canvas.current;
    if (!c) return;
    const g = c.getContext("2d")!;
    g.clearRect(0, 0, size, size);
    if (heights && heights.length === rows * columns) {
      // Shaded over what the window shows, so a few metres of relief there
      // are not lost in the place's whole range.
      let lo = Infinity, hi = -Infinity;
      const c0 = Math.max(0, Math.floor((view.x0 / acrossM + 0.5) * columns));
      const c1 = Math.min(columns, Math.ceil(((view.x0 + view.side) / acrossM + 0.5) * columns));
      const r0 = Math.max(0, Math.floor((view.y0 / acrossM + 0.5) * rows));
      const r1 = Math.min(rows, Math.ceil(((view.y0 + view.side) / acrossM + 0.5) * rows));
      for (let r = r0; r < r1; r++) {
        for (let k = c0; k < c1; k++) {
          const h = heights[r * columns + k]!;
          if (Number.isFinite(h) && h <= 0) { lo = Math.min(lo, h); hi = Math.max(hi, h); }
        }
      }
      // Charted as every seabed is (Relief.ts): the blue ramp over what the
      // window shows, lit from the north-west, with thin contours.
      const depths = new Float32Array(rows * columns);
      for (let r = 0; r < rows; r++) {
        for (let k = 0; k < columns; k++) {
          // Row 0 is the south edge; the picture's top is north.
          depths[(rows - 1 - r) * columns + k] = -heights[r * columns + k]!;
        }
      }
      const image = g.createImageData(columns, rows);
      paintDepths(depths, columns, rows, Number.isFinite(lo) ? Math.max(0.5, -lo) : 1, acrossM / columns, image.data,
                  Math.min(12, Math.max(2, (acrossM / Math.max(0.5, -lo)) * 0.08)));
      const off = new OffscreenCanvas(columns, rows);
      off.getContext("2d")!.putImageData(image, 0, 0);
      g.imageSmoothingEnabled = true;
      // The window's part of the heightfield: its columns from the west,
      // its rows from the top of the picture, which is north.
      const sx = ((view.x0 / acrossM) + 0.5) * columns, sw = (view.side / acrossM) * columns;
      const sy = (0.5 - (view.y0 + view.side) / acrossM) * rows, sh = (view.side / acrossM) * rows;
      g.drawImage(off, sx, sy, sw, sh, 0, 0, size, size);
    }
    const [L, W] = extentM;
    spots.forEach((spot, i) => {
      const t = (spot.headingDeg * Math.PI) / 180;
      const c0 = Math.cos(t), s0 = Math.sin(t);
      const corners = [[-L / 2, -W / 2], [L / 2, -W / 2], [L / 2, W / 2], [-L / 2, W / 2]]
        .map(([u, v]) => toPixel(spot.at[0] + c0 * u! - s0 * v!, spot.at[1] + s0 * u! + c0 * v!));
      g.beginPath();
      corners.forEach(([x, y], j) => (j === 0 ? g.moveTo(x, y) : g.lineTo(x, y)));
      g.closePath();
      const mine = i === chosen;
      g.fillStyle = mine ? "rgba(255, 200, 60, 0.55)" : "rgba(255, 255, 255, 0.25)";
      g.strokeStyle = mine ? "#ffc83c" : "rgba(255, 255, 255, 0.8)";
      g.lineWidth = mine ? 2 : 1;
      g.fill();
      g.stroke();
      const [lx, ly] = toPixel(spot.at[0], spot.at[1]);
      g.fillStyle = mine ? "#ffc83c" : "#fff";
      g.font = "12px system-ui";
      g.fillText(String(i + 1), lx + 8, ly - 8);
      if (spot.startAt) {
        const [sx, sy] = toPixel(spot.startAt[0]!, spot.startAt[1]!);
        g.beginPath();
        g.arc(sx, sy, 3, 0, 2 * Math.PI);
        g.fillStyle = "#50ff78";
        g.fill();
      }
    });
    if (start) {
      const [sx, sy] = toPixel(start[0], start[1]);
      g.strokeStyle = "#50ff78";
      g.lineWidth = 2;
      g.beginPath();
      g.moveTo(sx - 7, sy); g.lineTo(sx + 7, sy); g.moveTo(sx, sy - 7); g.lineTo(sx, sy + 7);
      g.stroke();
    }
  }, [heights, rows, columns, acrossM, extentM, spots, chosen, start, size, view]);

  return (
    <div className="fitmap">
      <canvas ref={canvas} width={size} height={size}
              onClick={(e) => {
                if (!onChoose || spots.length === 0) return;
                const box = e.currentTarget.getBoundingClientRect();
                const px = ((e.clientX - box.left) / box.width) * size, py = ((e.clientY - box.top) / box.height) * size;
                let best = 0, bestD = Infinity;
                spots.forEach((spot, i) => {
                  const [x, y] = toPixel(spot.at[0], spot.at[1]);
                  const d = Math.hypot(x - px, y - py);
                  if (d < bestD) { bestD = d; best = i; }
                });
                onChoose(best);
              }} />
      {trouble ? <p className="trouble">{trouble}</p> : null}
      <p className="note">
        <a onClick={() => setWhole((w) => !w)}>{whole ? "close in" : "the whole place"}</a>
        {" · "}The seabed from above, shallow light and deep dark, {view.side >= 1000 ? `${(view.side / 1000).toFixed(1)} km` : `${view.side.toFixed(0)} m`} across, north up. Each outline is where the reef would lie; the green cross is where the video was said to start, the dots where its swim would start.</p>
    </div>
  );
}
