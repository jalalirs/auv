// A place's chart: the seabed from its own survey, what is laid out on it, and
// whatever the page drawing it wants to add over the top.
//
// One chart for every page that draws on a place — the layout editor puts
// things on it, the mission designer draws the work over them — because two
// charts of one place that disagreed about where north is, or how deep a spot
// is, would be two places.
//
// The frame is the one everything uses: metres, origin at the middle of the
// site, +x east, +y north. The heightfield runs south to north then west to
// east, as the site's own note says and the runtime reads it.

import React, { useCallback, useEffect, useRef, useState } from "react";

import type { PlacePackage } from "../platform/packages.js";

/** The seabed, read from the package's own heightfield. */
export interface Ground {
  rows: number;
  columns: number;
  acrossM: number;
  /** Metres below the surface, positive down. */
  depth: Float32Array;
}

export async function groundOf(pkg: PlacePackage | undefined): Promise<Ground | undefined> {
  const field = pkg?.site?.mesh?.heightfield;
  const across = pkg?.site?.from?.acrossMetres;
  if (!field || !across) return undefined;
  const file = pkg.files.find((f) => f.path === field.file);
  if (!file) return undefined;
  const bytes = await (await fetch(file.url)).arrayBuffer();
  const heights = new Float32Array(bytes);
  // Heights are metres above the surface, so depth is the other way round.
  const depth = new Float32Array(heights.length);
  for (let i = 0; i < heights.length; i++) depth[i] = -heights[i]!;
  return { rows: field.rows, columns: field.columns, acrossM: across, depth };
}

/** How deep the ground is at a point. */
export function groundAt(ground: Ground, x: number, y: number): number {
  const { rows, columns, acrossM, depth } = ground;
  const fx = Math.min(columns - 1.001, Math.max(0, (x / acrossM + 0.5) * (columns - 1)));
  const fy = Math.min(rows - 1.001, Math.max(0, (y / acrossM + 0.5) * (rows - 1)));
  const x0 = Math.floor(fx), y0 = Math.floor(fy);
  const tx = fx - x0, ty = fy - y0;
  const at = (cx: number, cy: number) => depth[cy * columns + cx] ?? 0;
  return at(x0, y0) * (1 - tx) * (1 - ty) + at(x0 + 1, y0) * tx * (1 - ty)
       + at(x0, y0 + 1) * (1 - tx) * ty + at(x0 + 1, y0 + 1) * tx * ty;
}

/** What part of the site the chart shows: a square, its middle and its width. */
export interface View { x: number; y: number; acrossM: number }

/** Where the shown square is on the canvas: centred, as large as fits. */
export interface Frame {
  side: number;
  padX: number;
  padY: number;
  /** Metres across the shown square. */
  acrossM: number;
  /** Metres across the whole site, which may be more than is shown. */
  siteM: number;
  view: View;
  toX: (m: number) => number;
  toY: (m: number) => number;
  /** Pixels a metre is, for sizing marks that mean metres. */
  perM: number;
}

export function frameOf(width: number, height: number, siteM: number, view?: View): Frame {
  const shown = view ?? { x: 0, y: 0, acrossM: siteM };
  const side = Math.min(width, height);
  const padX = (width - side) / 2, padY = (height - side) / 2;
  const acrossM = shown.acrossM;
  return {
    side, padX, padY, acrossM, siteM, view: shown, perM: side / acrossM,
    toX: (m) => padX + ((m - shown.x) / acrossM + 0.5) * side,
    toY: (m) => padY + (0.5 - (m - shown.y) / acrossM) * side,
  };
}

/** A point on the canvas, in the site's frame; nothing when off the site. */
export function siteAt(frame: Frame, px: number, py: number): { x: number; y: number } | undefined {
  const x = frame.view.x + ((px - frame.padX) / frame.side - 0.5) * frame.acrossM;
  const y = frame.view.y + (0.5 - (py - frame.padY) / frame.side) * frame.acrossM;
  const half = frame.siteM / 2;
  if (Math.abs(x) > half || Math.abs(y) > half) return undefined;
  return { x, y };
}

/** The view that shows some points with room round them, never more than the site. */
export function viewOver(points: { x: number; y: number }[], siteM: number): View {
  if (points.length === 0) return { x: 0, y: 0, acrossM: siteM };
  const xs = points.map((p) => p.x), ys = points.map((p) => p.y);
  const west = Math.min(...xs), east = Math.max(...xs), south = Math.min(...ys), north = Math.max(...ys);
  const across = Math.min(siteM, Math.max(east - west, north - south, siteM / 50) * 1.5);
  return clampView({ x: (west + east) / 2, y: (south + north) / 2, acrossM: across }, siteM);
}

/** Kept inside the site: no wider than it, and not wandered off its edge. */
function clampView(view: View, siteM: number): View {
  const acrossM = Math.min(siteM, Math.max(siteM / 400, view.acrossM));
  const room = (siteM - acrossM) / 2;
  return { acrossM, x: Math.min(room, Math.max(-room, view.x)), y: Math.min(room, Math.max(-room, view.y)) };
}

/** One thing laid out, as an arrangement's document carries it. */
export interface Thing {
  id: string;
  kind: string;
  x: number;
  y: number;
  z?: number;
  groundM?: number;
  ends?: { x: number; y: number; z?: number; groundM?: number }[];
  slack?: number;
  corners?: { x: number; y: number }[];
  /** Laid along the bottom: a pipeline's route. */
  route?: { x: number; y: number }[];
}

/** The kinds that float, drawn hollow: they are not on the bottom the chart shows. */
const FLOATS = new Set(["ship", "buoy", "dredger"]);

/** One point on a thing, for picking it and drawing it. */
export function centreOf(thing: Thing): { x: number; y: number } {
  if (thing.route?.length) return thing.route[Math.floor(thing.route.length / 2)]!;
  if (thing.ends?.length === 2) {
    return { x: (thing.ends[0]!.x + thing.ends[1]!.x) / 2, y: (thing.ends[0]!.y + thing.ends[1]!.y) / 2 };
  }
  if (thing.corners?.length) {
    const xs = thing.corners.map((c) => c.x), ys = thing.corners.map((c) => c.y);
    return { x: (Math.min(...xs) + Math.max(...xs)) / 2, y: (Math.min(...ys) + Math.max(...ys)) / 2 };
  }
  return { x: thing.x, y: thing.y };
}

/** The seabed as an image of what is shown: pale in the shallows, deep blue off the edge. */
function seabedImage(ground: Ground, side: number, view: View): HTMLCanvasElement {
  const image = document.createElement("canvas");
  const n = Math.max(1, Math.round(side));
  image.width = n; image.height = n;
  const g = image.getContext("2d");
  if (!g) return image;
  const pixels = g.createImageData(n, n);
  // Coloured on the deepest point in the site rather than a fixed 30 m, so a
  // tank a metre deep and a reef forty deep both use the whole ramp.
  // The same ramp whatever is shown, so zooming in does not recolour the reef.
  let deepest = 0.5;
  for (const d of ground.depth) if (Number.isFinite(d) && d > deepest) deepest = d;
  for (let py = 0; py < n; py++) {
    for (let px = 0; px < n; px++) {
      const deep = groundAt(ground, view.x + (px / n - 0.5) * view.acrossM, view.y + (0.5 - py / n) * view.acrossM);
      const t = Math.min(1, Math.max(0, deep / deepest));
      const i = (py * n + px) * 4;
      if (deep < 0.05) {
        pixels.data[i] = 216; pixels.data[i + 1] = 201; pixels.data[i + 2] = 168;
      } else {
        pixels.data[i] = Math.round(222 - 200 * t);
        pixels.data[i + 1] = Math.round(222 - 150 * t);
        pixels.data[i + 2] = Math.round(196 - 90 * t);
      }
      pixels.data[i + 3] = 255;
    }
  }
  g.putImageData(pixels, 0, 0);
  return image;
}

/** What is laid out, drawn as what it is: a line as its run, a plot as its extent. */
export function drawThings(g: CanvasRenderingContext2D, frame: Frame, things: Thing[],
                           chosen?: string, faint = false): void {
  const { toX, toY } = frame;
  for (const thing of things) {
    const on = thing.id === chosen;
    g.globalAlpha = faint && !on ? 0.55 : 1;
    g.lineWidth = on ? 2.6 : 1.6;
    g.strokeStyle = on ? "#c25a15" : "#10222a";
    g.fillStyle = "rgba(255,255,255,.9)";
    if (thing.corners?.length) {
      g.beginPath();
      thing.corners.forEach((c, i) => (i === 0 ? g.moveTo(toX(c.x), toY(c.y)) : g.lineTo(toX(c.x), toY(c.y))));
      g.closePath();
      g.fillStyle = on ? "rgba(194,90,21,.18)" : "rgba(16,34,42,.12)";
      g.fill();
      g.setLineDash([6, 4]);
      g.stroke();
      g.setLineDash([]);
      continue;
    }
    if (thing.route && thing.route.length >= 2) {
      g.beginPath();
      thing.route.forEach((p, i) => (i === 0 ? g.moveTo(toX(p.x), toY(p.y)) : g.lineTo(toX(p.x), toY(p.y))));
      g.lineWidth = on ? 4 : 3;
      g.strokeStyle = on ? "#c25a15" : "#8a5a1e";
      g.stroke();
      continue;
    }
    if (thing.ends?.length === 2) {
      const [a, b] = thing.ends as [{ x: number; y: number }, { x: number; y: number }];
      g.beginPath();
      g.moveTo(toX(a.x), toY(a.y));
      g.lineTo(toX(b.x), toY(b.y));
      g.stroke();
      for (const end of [a, b]) {
        g.beginPath();
        g.arc(toX(end.x), toY(end.y), 3.5, 0, Math.PI * 2);
        g.fillStyle = on ? "#c25a15" : "#10222a";
        g.fill();
      }
      continue;
    }
    g.beginPath();
    g.arc(toX(thing.x), toY(thing.y), on ? 7 : 5.5, 0, Math.PI * 2);
    g.fill();
    g.stroke();
    if (FLOATS.has(thing.kind)) {
      g.beginPath();
      g.arc(toX(thing.x), toY(thing.y), on ? 10 : 8.5, 0, Math.PI * 2);
      g.stroke();
    }
  }
  g.globalAlpha = 1;
}

/**
 * The chart itself: sized to its box, the seabed under everything, the
 * arrangement over it, and `overlay` over that — the page's own layer.
 * `onPick` and `onHover` are given points in the site's frame.
 */
export function SiteChart({ ground, things, chosen, faintThings, overlay, onPick, onHover, onDoublePick,
                            cursor = "crosshair", redraw, fit }: {
  ground: Ground | undefined;
  things: Thing[];
  chosen?: string;
  faintThings?: boolean;
  overlay?: (g: CanvasRenderingContext2D, frame: Frame) => void;
  onPick?: (at: { x: number; y: number }, event: React.MouseEvent) => void;
  onDoublePick?: (at: { x: number; y: number }) => void;
  onHover?: (at: { x: number; y: number } | undefined, depth: number | undefined) => void;
  cursor?: string;
  /** Anything else the overlay depends on, so a change redraws. */
  redraw?: unknown;
  /** Points the chart opens showing — the work, on a site far wider than it. */
  fit?: { x: number; y: number }[];
}): React.JSX.Element {
  const canvas = useRef<HTMLCanvasElement>(null);
  const [size, setSize] = useState<{ w: number; h: number }>({ w: 0, h: 0 });
  const image = useRef<{ key: string; canvas: HTMLCanvasElement } | undefined>(undefined);
  const [view, setView] = useState<View | undefined>(undefined);
  // A press that moves is a pan, not a pick.
  const press = useRef<{ x: number; y: number; view: View; moved: boolean } | undefined>(undefined);
  const panned = useRef(false);

  const siteM = ground?.acrossM ?? 1;
  // The work, as a key: a new array every render must not mean a new view.
  const fitKey = (fit ?? []).map((p) => `${p.x.toFixed(2)},${p.y.toFixed(2)}`).join(" ");
  const fitted = useCallback(() => {
    const points = fitKey ? fitKey.split(" ").map((p) => { const [x, y] = p.split(",").map(Number); return { x: x!, y: y! }; }) : [];
    return points.length ? viewOver(points, siteM) : { x: 0, y: 0, acrossM: siteM };
  }, [fitKey, siteM]);
  // Opens on the work, and follows it as it arrives — the arrangement may load
  // after the stages — until the person zooms, pans or clicks; then the view is theirs.
  const settled = useRef(false);
  useEffect(() => {
    if (ground && !settled.current) setView(fitted());
  }, [ground, fitted]);

  useEffect(() => {
    const element = canvas.current;
    if (!element) return;
    const watch = new ResizeObserver(() => {
      const box = element.getBoundingClientRect();
      setSize({ w: box.width, h: box.height });
    });
    watch.observe(element);
    return () => watch.disconnect();
  }, []);

  useEffect(() => {
    const element = canvas.current;
    if (!element || !ground || size.w === 0) return;
    const ratio = window.devicePixelRatio || 1;
    element.width = size.w * ratio;
    element.height = size.h * ratio;
    const g = element.getContext("2d");
    if (!g) return;
    g.setTransform(ratio, 0, 0, ratio, 0, 0);
    g.clearRect(0, 0, size.w, size.h);
    const frame = frameOf(size.w, size.h, ground.acrossM, view);
    const shown = frame.view;
    const key = `${ground.rows}x${ground.columns}:${Math.round(frame.side * ratio)}:${shown.x},${shown.y},${shown.acrossM}`;
    if (image.current?.key !== key) {
      image.current = { key, canvas: seabedImage(ground, frame.side * ratio, shown) };
    }
    g.drawImage(image.current.canvas, frame.padX, frame.padY, frame.side, frame.side);
    g.save();
    g.beginPath();
    g.rect(frame.padX, frame.padY, frame.side, frame.side);
    g.clip();
    drawThings(g, frame, things, chosen, faintThings);
    overlay?.(g, frame);
    g.restore();
    drawScale(g, frame);
  }, [ground, size, view, things, chosen, faintThings, overlay, redraw]);

  const frameNow = useCallback(() => {
    const box = canvas.current?.getBoundingClientRect();
    if (!box || !ground) return undefined;
    return { box, frame: frameOf(box.width, box.height, ground.acrossM, view) };
  }, [ground, view]);

  const pointAt = useCallback((event: { clientX: number; clientY: number }) => {
    const now = frameNow();
    return now ? siteAt(now.frame, event.clientX - now.box.left, event.clientY - now.box.top) : undefined;
  }, [frameNow]);

  // Wheel zooms about the point under the cursor, which stays where it is.
  useEffect(() => {
    const element = canvas.current;
    if (!element) return;
    const wheel = (event: WheelEvent) => {
      const now = frameNow();
      if (!now) return;
      event.preventDefault();
      settled.current = true;
      const { box, frame } = now;
      const px = event.clientX - box.left, py = event.clientY - box.top;
      const atX = frame.view.x + ((px - frame.padX) / frame.side - 0.5) * frame.acrossM;
      const atY = frame.view.y + (0.5 - (py - frame.padY) / frame.side) * frame.acrossM;
      const across = frame.acrossM * Math.exp(event.deltaY * 0.0015);
      const scale = across / frame.acrossM;
      setView(clampView({ x: atX - (atX - frame.view.x) * scale, y: atY - (atY - frame.view.y) * scale, acrossM: across },
                        frame.siteM));
    };
    element.addEventListener("wheel", wheel, { passive: false });
    return () => element.removeEventListener("wheel", wheel);
  }, [frameNow]);

  const zoom = (by: number) => (settled.current = true, setView((v) => v && clampView({ ...v, acrossM: v.acrossM * by }, siteM)));

  return (
    <div className="site-chart">
      <canvas ref={canvas} style={{ cursor: press.current?.moved ? "grabbing" : cursor }}
              onMouseDown={(event) => {
                if (view) press.current = { x: event.clientX, y: event.clientY, view, moved: false };
                settled.current = true;
              }}
              onMouseUp={() => { panned.current = press.current?.moved ?? false; press.current = undefined; }}
              onClick={(event) => {
                settled.current = true;
                if (panned.current) { panned.current = false; return; }
                const at = pointAt(event); if (at) onPick?.(at, event);
              }}
              onDoubleClick={(event) => { const at = pointAt(event); if (at) onDoublePick?.(at); }}
              onMouseMove={(event) => {
                const held = press.current, now = frameNow();
                if (held && now && (held.moved || Math.hypot(event.clientX - held.x, event.clientY - held.y) > 4)) {
                  held.moved = true;
                  const perPx = now.frame.acrossM / now.frame.side;
                  setView(clampView({ acrossM: held.view.acrossM,
                                      x: held.view.x - (event.clientX - held.x) * perPx,
                                      y: held.view.y + (event.clientY - held.y) * perPx }, now.frame.siteM));
                  return;
                }
                const at = pointAt(event);
                onHover?.(at, at && ground ? groundAt(ground, at.x, at.y) : undefined);
              }}
              onMouseLeave={() => { press.current = undefined; onHover?.(undefined, undefined); }} />
      {ground ? (
        <div className="zoom">
          <button type="button" title="closer" onClick={() => zoom(1 / 1.6)}>+</button>
          <button type="button" title="further" onClick={() => zoom(1.6)}>−</button>
          {fitKey ? <button type="button" title="back to the work" onClick={() => setView(fitted())}>work</button> : null}
          <button type="button" title="the whole place" onClick={() => setView({ x: 0, y: 0, acrossM: siteM })}>all</button>
        </div>
      ) : null}
    </div>
  );
}

/** A scale bar in the corner: a round number of metres, about a fifth of the width. */
function drawScale(g: CanvasRenderingContext2D, frame: Frame): void {
  const want = frame.acrossM / 5;
  const step = 10 ** Math.floor(Math.log10(want));
  const metres = [1, 2, 5, 10].map((k) => k * step).filter((m) => m <= want).pop() ?? step;
  const px = metres * frame.perM;
  const x = frame.padX + frame.side - 12 - px, y = frame.padY + frame.side - 14;
  g.strokeStyle = "rgba(16,34,42,.85)"; g.lineWidth = 2;
  g.beginPath(); g.moveTo(x, y - 4); g.lineTo(x, y); g.lineTo(x + px, y); g.lineTo(x + px, y - 4); g.stroke();
  g.fillStyle = "rgba(16,34,42,.9)"; g.font = "11px ui-monospace, monospace";
  g.fillText(metres >= 1 ? `${metres} m` : `${Math.round(metres * 100)} cm`, x, y - 6);
}
