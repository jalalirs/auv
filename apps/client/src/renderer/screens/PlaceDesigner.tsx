// The place designer: a place's seabed in the middle, what can go on it down
// the side, and whatever is chosen described beside it.
//
// Two kinds of thing go on a place. Equipment (transponders, mooring blocks,
// frames, ships, lines, pipelines, plots) is an arrangement: saved as the
// place's layout, pinned by a dive, drawn by the runtime from its kind.
// Objects (a reef rebuilt from a video, a platform from its model, a pipeline
// from its route) are the organisation's own and are laid into the place
// itself: a new version of it, the object's own mesh in the seabed.
//
// Both are fitted to the ground as they are put down, from the place's own
// heightfield: how deep, how far it leans, how much daylight is under it, and
// for a pipe where it bridges a hollow. A thing can also be dropped from the
// surface and watched sink, drift with the current and settle. That is the
// arithmetic of a rigid body in a steady current, done here so the answer is
// there before the click; the coupled engine is what a dive runs.

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type { Asset, Layout as LayoutRecord, LayoutDocument, Mapping, Platform } from "@coral-city/api";
import type { Held, Packages } from "./Deck.js";
import { centreOf, groundAt, groundOf, SiteChart, type Frame, type Ground, type Thing as Charted } from "../parts/SiteChart.js";
import { drape, fall, restOn, type Body, type Draped, type Fall, type Rest } from "../parts/landing.js";
import { ObjectArt } from "../parts/ObjectArt.js";
import { ResolveChoice, useVersionGround, type Candidate } from "../parts/ResolveChoice.js";
import { whereIs } from "../platform/packages.js";
import { artOf } from "./Reconstructions.js";
import { DESCRIBED_BY, FRAME, GROUPS, TOOLS, landed, named, saysOf, shifted, spanBetween, cellBetween,
         type Thing } from "./Layout.js";
import { Button, Dialog, Page, Status } from "../ui/components.js";
import { Empty } from "./parts.js";

/** One of the organisation's objects, put on the place. */
export interface Placed {
  id: string;
  assetId: string;
  name: string;
  /** How it meets the seabed: stands on a base, drapes along its own route, or is a reef found by a search. */
  meets: "stands" | "drapes" | "reef";
  x: number;
  y: number;
  headingDeg: number;
  /** Across, along and up, metres. */
  sizeM: [number, number, number];
  /** Its own route, for one that drapes. */
  route?: { x: number; y: number }[];
  /** Weight and drag, for dropping it. */
  massKg?: number;
  /** Laid into the place's own version, by which mapping. */
  laidBy?: string;
}

/** The size and the stuff of each piece of equipment that sits on the bottom, for fitting and dropping it. */
const BUILT: Record<string, { wideM: number; longM: number; body: Body }> = {
  transponder: { wideM: 0.5, longM: 0.5, body: { massKg: 40, volumeM3: 0.02, dragAreaM2: 0.12 } },
  "mooring-block": { wideM: 1, longM: 1, body: { massKg: 2000, volumeM3: 0.83, dragAreaM2: 1.05 } },
  "nursery-frame": { wideM: 2, longM: 1, body: { massKg: 60, volumeM3: 0.008, dragAreaM2: 1.2 } },
  "marker-post": { wideM: 0.3, longM: 0.3, body: { massKg: 15, volumeM3: 0.004, dragAreaM2: 0.06 } },
};

const STEEL = 7850;

/** An object's body, guessed from its size when nobody has said its weight: a steel frame a twentieth solid. */
function bodyOf(one: Placed): Body {
  const [w, l, h] = one.sizeM;
  const solid = Math.max(0.01, w * l * h * 0.05);
  const mass = one.massKg ?? solid * STEEL;
  return { massKg: mass, volumeM3: mass / STEEL, dragAreaM2: Math.max(0.1, w * l * 0.6) };
}

function sizeOf(asset: Asset): [number, number, number] {
  const s = (asset.footprint as { sizeM?: number[] } | undefined)?.sizeM
    ?? (asset.manifest as { extentM?: number[] } | undefined)?.extentM;
  return [Math.max(0.2, s?.[0] ?? 3), Math.max(0.2, s?.[1] ?? 3), Math.max(0.1, s?.[2] ?? 1)];
}

function meetsOf(asset: Asset): Placed["meets"] {
  if (asset.kind === "reef") return "reef";
  return asset.meets === "drapes" ? "drapes" : "stands";
}

/** Metres in the site to degrees, and back, about the place's middle. */
function earthOf(centre: { latitude: number; longitude: number }) {
  const perLon = 111_320 * Math.max(Math.cos(centre.latitude * Math.PI / 180), 1e-6);
  return {
    toLatLon: (x: number, y: number) => ({ lat: centre.latitude + y / 111_320, lon: centre.longitude + x / perLon }),
    toSite: (lat: number, lon: number) => ({ x: (lon - centre.longitude) * perLon, y: (lat - centre.latitude) * 111_320 }),
  };
}

/** What the fit says about a standing thing, in one line, and whether it is a worry. */
function fitSaid(rest: Rest): { says: string; worry: boolean } {
  const lean = rest.tiltDeg >= 0.5 ? `leans ${rest.tiltDeg.toFixed(0)}°` : "level";
  const gap = rest.clearM >= 0.05 ? `, ${rest.clearM.toFixed(1)} m clear under one side` : "";
  return { says: `on the bottom at ${rest.depthM.toFixed(1)} m, ${lean}${gap}`, worry: rest.tiltDeg > 5 || rest.clearM > 0.3 };
}

function drapeSaid(laid: Draped): { says: string; worry: boolean } {
  if (laid.spans.length === 0) return { says: `${laid.lengthM.toFixed(0)} m, on the bottom all the way`, worry: false };
  const longest = Math.max(...laid.spans.map((s) => s.to - s.from));
  const highest = Math.max(...laid.spans.map((s) => s.gapM));
  return { says: `${laid.lengthM.toFixed(0)} m, ${laid.spans.length} free span${laid.spans.length === 1 ? "" : "s"}: longest ${longest.toFixed(0)} m, up to ${highest.toFixed(1)} m off the bottom`,
           worry: longest > 20 || highest > 1 };
}

type Layers = { shade: boolean; slope: boolean; equipment: boolean; objects: boolean };
const LAYERS: { key: keyof Layers; name: string }[] = [
  { key: "shade", name: "Depth" }, { key: "slope", name: "Steep ground" },
  { key: "equipment", name: "Equipment" }, { key: "objects", name: "Objects" },
];

/** A drop in progress: what fell, how, and when the watching began. */
type Dropping = { id: string; fell: Fall; began: number; from: { x: number; y: number } };

/** How much faster than it happens a drop is shown: in real time when that is 2.5 to 8 seconds, squeezed or stretched into that otherwise. */
function rateOf(fell: Fall): number {
  const end = fell.path[fell.path.length - 1]!.t;
  return end / Math.min(8, Math.max(2.5, end));
}

export function PlaceDesigner({ platform, held, packages, place, layout: layoutId, onBack, onChanged, onOpenLayout }: {
  platform: Platform;
  held: Held;
  packages: Packages;
  place: string;
  layout?: string;
  onBack: () => void;
  onChanged: () => void;
  onOpenLayout: (id: string) => void;
}): React.JSX.Element {
  const city = held.places.find((p) => p.id === place);
  const pkg = packages.places.get(place) ?? undefined;
  const centre = whereIs(city?.extent, pkg?.site);
  const earth = useMemo(() => centre ? earthOf(centre) : undefined, [centre?.latitude, centre?.longitude]); // eslint-disable-line react-hooks/exhaustive-deps
  const org = held.institution?.id;

  const [ground, setGround] = useState<Ground | undefined>();
  const [layouts, setLayouts] = useState<LayoutRecord[]>([]);
  const [layout, setLayout] = useState<LayoutRecord | undefined>();
  const [things, setThings] = useState<Thing[]>([]);
  const [objects, setObjects] = useState<Placed[]>([]);
  const [assets, setAssets] = useState<Asset[]>([]);
  const [tool, setTool] = useState<string | undefined>();
  const [chosen, setChosen] = useState<string | undefined>();
  const [first, setFirst] = useState<{ x: number; y: number } | undefined>();
  const [route, setRoute] = useState<{ x: number; y: number }[]>([]);
  const [hover, setHover] = useState<{ x: number; y: number } | undefined>();
  const [layers, setLayers] = useState<Layers>({ shade: true, slope: false, equipment: true, objects: true });
  const [current, setCurrent] = useState({ speed: "0.2", towards: "90" });
  const [dropping, setDropping] = useState<Dropping | undefined>();
  const [said, setSaid] = useState("");
  const [trouble, setTrouble] = useState("");
  const [busy, setBusy] = useState(false);
  const [mapping, setMapping] = useState<Mapping | undefined>();
  const [changed, setChanged] = useState(false);
  const frame = useRef<Frame | undefined>(undefined);
  const [, tick] = useState(0);

  useEffect(() => { void groundOf(pkg).then(setGround); }, [pkg]);
  useEffect(() => {
    if (!org) return;
    platform.listAssets(org).then((all) => setAssets(all.filter((a) => a.state === "ready" && a.kind !== "bathymetry")))
      .catch(() => undefined);
  }, [platform, org]);

  // The arrangements of this place, and the one being designed: the one asked
  // for, or the newest, or none until the first save makes one.
  useEffect(() => {
    let stale = false;
    void platform.layoutsOf(place).then((found) => {
      if (stale) return;
      setLayouts(found);
      setLayout(found.find((l) => l.id === layoutId) ?? (layoutId ? undefined : found[found.length - 1]));
    }).catch(() => undefined);
    return () => { stale = true; };
  }, [platform, place, layoutId]);
  useEffect(() => {
    if (!layout) return;
    let stale = false;
    void platform.versionsOfLayout(layout.id).then((versions) => {
      const document = versions[0]?.document as (LayoutDocument & { objects?: Placed[] }) | undefined;
      if (stale) return;
      setThings((document?.things ?? []) as Thing[]);
      setObjects(document?.objects ?? []);
      setChanged(false);
    }).catch(() => undefined);
    return () => { stale = true; };
  }, [platform, layout]);

  const edit = (then: () => void) => { then(); setChanged(true); setSaid(""); };

  const toolOf = tool && !tool.startsWith("object:") ? TOOLS[tool] : undefined;
  const assetOf = tool?.startsWith("object:") ? assets.find((a) => `object:${a.id}` === tool) : undefined;

  const near = useCallback((at: { x: number; y: number }): string | undefined => {
    const reach = 12 / (frame.current?.perM ?? 1);
    const objectHit = layers.objects ? objects.find((o) => {
      if (o.route) return o.route.some((p) => Math.hypot(p.x - at.x, p.y - at.y) < reach);
      return Math.hypot(o.x - at.x, o.y - at.y) < Math.max(reach, Math.max(o.sizeM[0], o.sizeM[1]) / 2);
    }) : undefined;
    if (objectHit) return objectHit.id;
    if (!layers.equipment) return undefined;
    return things.find((t) => {
      if (t.route) return t.route.some((p) => Math.hypot(p.x - at.x, p.y - at.y) < reach);
      const c = centreOf(t as Charted);
      return Math.hypot(c.x - at.x, c.y - at.y) < reach;
    })?.id;
  }, [objects, things, layers]);

  const put = useCallback((at: { x: number; y: number }) => {
    if (!ground) return;
    const { x, y } = at;
    if (assetOf) {
      const one: Placed = { id: named("object"), assetId: assetOf.id, name: assetOf.name, meets: meetsOf(assetOf),
                            x: Math.round(x * 10) / 10, y: Math.round(y * 10) / 10, headingDeg: 0, sizeM: sizeOf(assetOf) };
      edit(() => setObjects((was) => [...was, one]));
      setChosen(one.id);
      setTool(undefined);
      return;
    }
    if (!tool || !toolOf) { setChosen(near(at)); return; }
    if (toolOf.lands === "laid") { setRoute((was) => [...was, { x: Math.round(x * 10) / 10, y: Math.round(y * 10) / 10 }]); return; }
    if (toolOf.lands === "span" || toolOf.lands === "region") {
      if (!first) { setFirst({ x, y }); return; }
      const made = toolOf.lands === "span" ? spanBetween(tool, toolOf, ground, first, { x, y }) : cellBetween(tool, ground, first, { x, y });
      setFirst(undefined);
      if (made) { edit(() => setThings((was) => [...was, made])); setChosen(made.id); }
      return;
    }
    const made: Thing = { id: named(tool), kind: tool, ...landed(toolOf.lands, ground, x, y) };
    edit(() => setThings((was) => [...was, made]));
    setChosen(made.id);
  }, [ground, tool, toolOf, assetOf, first, near]);

  const finishRoute = useCallback(() => {
    if (!tool || toolOf?.lands !== "laid") return;
    const kept = route.filter((p, i) => i === 0 || p.x !== route[i - 1]!.x || p.y !== route[i - 1]!.y);
    setRoute([]);
    if (kept.length < 2) return;
    const middle = kept[Math.floor(kept.length / 2)]!;
    const made = { id: named(tool), kind: tool, x: middle.x, y: middle.y, route: kept, radiusM: 0.16, bendRadiusM: 150 } as Thing;
    edit(() => setThings((was) => [...was, made]));
    setChosen(made.id);
  }, [tool, toolOf, route]);

  // A drag moves what was taken hold of, landed again where it now is.
  const drag = useCallback((at: { x: number; y: number }) => {
    if (!ground || !chosen) return;
    const object = objects.find((o) => o.id === chosen);
    if (object) {
      if (object.route) return;
      edit(() => setObjects((was) => was.map((o) => o.id === chosen ? { ...o, x: Math.round(at.x * 10) / 10, y: Math.round(at.y * 10) / 10, laidBy: undefined } : o)));
      return;
    }
    const thing = things.find((t) => t.id === chosen);
    if (!thing || thing.route || thing.ends || thing.corners) return;
    const lands = TOOLS[thing.kind]?.lands ?? "ground";
    edit(() => setThings((was) => was.map((t) => t.id === chosen ? { ...t, ...landed(lands, ground, at.x, at.y) } : t)));
  }, [ground, chosen, objects, things]);

  const selectedThing = things.find((t) => t.id === chosen);
  const selectedObject = objects.find((o) => o.id === chosen);

  // The fit, for what is chosen and for what the cursor would put down.
  const fitOf = useCallback((x: number, y: number, wide: number, long: number, heading: number) =>
    ground ? restOn(ground, x, y, wide, long, heading) : undefined, [ground]);
  const chosenFit = useMemo(() => {
    if (!ground) return undefined;
    if (selectedObject && selectedObject.meets === "stands") {
      return fitOf(selectedObject.x, selectedObject.y, selectedObject.sizeM[0], selectedObject.sizeM[1], selectedObject.headingDeg);
    }
    const built = selectedThing && BUILT[selectedThing.kind];
    if (selectedThing && built) {
      return fitOf(selectedThing.x, selectedThing.y, built.wideM, built.longM, (selectedThing as { headingDeg?: number }).headingDeg ?? 0);
    }
    return undefined;
  }, [ground, selectedObject, selectedThing, fitOf]);
  const chosenDrape = useMemo(() => {
    const along = selectedThing?.route ?? selectedObject?.route;
    if (!ground || !along) return undefined;
    return drape(ground, along, (selectedThing as { bendRadiusM?: number } | undefined)?.bendRadiusM ?? 150);
  }, [ground, selectedThing, selectedObject]);
  // Every pipe's spans, drawn on the chart whatever is chosen.
  const drapes = useMemo(() => {
    if (!ground) return [];
    return [...things.filter((t) => t.route).map((t) => t.route!), ...objects.filter((o) => o.route).map((o) => o.route!)]
      .map((r) => drape(ground, r));
  }, [ground, things, objects]);
  const drawing = useMemo(() => (ground && route.length && hover) ? drape(ground, [...route, hover]) : undefined,
                          [ground, route, hover]);

  const hoverSays = useMemo((): { says: string; worry?: boolean } => {
    if (!ground || !hover) return { says: tool ? "click the chart" : "choose something to put down, or click a thing" };
    const depth = groundAt(ground, hover.x, hover.y);
    if (assetOf) {
      const m = meetsOf(assetOf), size = sizeOf(assetOf);
      if (m === "reef") return { says: `a reef: iOcean searches within 50 m of here for where its own seabed fits` };
      if (m === "drapes") return { says: "follows its own route; click anywhere to add it" };
      return fitSaid(restOn(ground, hover.x, hover.y, size[0], size[1], 0));
    }
    if (!toolOf) return { says: "click a thing to choose it, drag it to move it" };
    if (first) return { says: toolOf.lands === "span" ? "click the other end" : "click the opposite corner" };
    if (toolOf.lands === "laid") return drawing ? drapeSaid(drawing) : { says: toolOf.says(depth) };
    const built = tool ? BUILT[tool] : undefined;
    if (built) return fitSaid(restOn(ground, hover.x, hover.y, built.wideM, built.longM, 0));
    return { says: toolOf.says(depth) };
  }, [ground, hover, tool, toolOf, assetOf, first, drawing]);

  // Drop: run the fall, then watch it, in real time when that is a few seconds.
  const drop = () => {
    if (!ground) return;
    const speed = Number(current.speed) || 0, towards = (Number(current.towards) || 0) * Math.PI / 180;
    const flow = { east: speed * Math.sin(towards), north: speed * Math.cos(towards) };
    const target = selectedObject ?? selectedThing;
    if (!target) return;
    const body = selectedObject ? bodyOf(selectedObject) : BUILT[selectedThing!.kind]?.body;
    if (!body) return;
    const fell = fall(ground, target.x, target.y, body, flow);
    setDropping({ id: target.id, fell, began: performance.now(), from: { x: target.x, y: target.y } });
  };
  useEffect(() => {
    if (!dropping) return;
    const end = dropping.fell.path[dropping.fell.path.length - 1]!.t;
    let raf = 0;
    const step = () => {
      tick((n) => n + 1);
      if ((performance.now() - dropping.began) / 1000 * rateOf(dropping.fell) < end) raf = requestAnimationFrame(step);
      else if (dropping.fell.landed && ground) {
        const at = dropping.fell.landed;
        const id = dropping.id;
        edit(() => {
          setObjects((was) => was.map((o) => o.id === id ? { ...o, x: Math.round(at.x * 10) / 10, y: Math.round(at.y * 10) / 10, laidBy: undefined } : o));
          setThings((was) => was.map((t) => t.id === id ? { ...t, ...landed(TOOLS[t.kind]?.lands ?? "ground", ground, at.x, at.y) } : t));
        });
      }
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [dropping, ground]);
  const dropAt = (one: Dropping) => {
    const t = Math.min((performance.now() - one.began) / 1000 * rateOf(one.fell), one.fell.path[one.fell.path.length - 1]!.t);
    return one.fell.path.find((p) => p.t >= t) ?? one.fell.path[one.fell.path.length - 1]!;
  };

  const overlay = useCallback((g: CanvasRenderingContext2D, f: Frame) => {
    frame.current = f;
    if (!ground) return;
    if (layers.slope) {
      // Ground steeper than ten degrees, in cells a fortieth of what is shown.
      const cell = f.acrossM / 40;
      g.fillStyle = "rgba(194,60,40,.35)";
      for (let i = 0; i < 40; i++) {
        for (let j = 0; j < 40; j++) {
          const x = f.view.x - f.acrossM / 2 + (i + 0.5) * cell, y = f.view.y - f.acrossM / 2 + (j + 0.5) * cell;
          const dx = groundAt(ground, x + cell / 2, y) - groundAt(ground, x - cell / 2, y);
          const dy = groundAt(ground, x, y + cell / 2) - groundAt(ground, x, y - cell / 2);
          if (Math.hypot(dx, dy) / cell > Math.tan(10 * Math.PI / 180)) {
            g.fillRect(f.toX(x - cell / 2), f.toY(y + cell / 2), cell * f.perM + 0.5, cell * f.perM + 0.5);
          }
        }
      }
    }
    // Free spans on every pipe, red where it is off the bottom.
    const spansOf = (laid: Draped) => {
      g.lineWidth = 5;
      g.strokeStyle = "#d0342c";
      for (const span of laid.spans) {
        const on = laid.samples.filter((s) => s.s >= span.from && s.s <= span.to);
        if (on.length < 2) continue;
        g.beginPath();
        on.forEach((s, i) => (i === 0 ? g.moveTo(f.toX(s.x), f.toY(s.y)) : g.lineTo(f.toX(s.x), f.toY(s.y))));
        g.stroke();
      }
    };
    if (layers.equipment || layers.objects) drapes.forEach(spansOf);
    if (layers.objects) {
      for (const one of objects) {
        const on = one.id === chosen;
        if (one.route) {
          g.beginPath();
          one.route.forEach((p, i) => (i === 0 ? g.moveTo(f.toX(p.x), f.toY(p.y)) : g.lineTo(f.toX(p.x), f.toY(p.y))));
          g.lineWidth = on ? 4 : 3;
          g.strokeStyle = on ? "#c25a15" : "#3b5f8a";
          g.stroke();
          continue;
        }
        const falling = dropping?.id === one.id ? dropAt(dropping) : undefined;
        const at = falling ?? one;
        const turn = one.headingDeg * Math.PI / 180;
        const w = Math.max(one.sizeM[0] * f.perM, 8), l = Math.max(one.sizeM[1] * f.perM, 8);
        g.save();
        g.translate(f.toX(at.x), f.toY(at.y));
        g.rotate(turn);
        g.fillStyle = one.meets === "reef" ? "rgba(214,120,90,.45)" : "rgba(59,95,138,.4)";
        g.strokeStyle = on ? "#c25a15" : one.meets === "reef" ? "#a4553a" : "#3b5f8a";
        g.lineWidth = on ? 2.6 : 1.6;
        if (one.meets === "reef") g.setLineDash([5, 3]);
        g.fillRect(-w / 2, -l / 2, w, l);
        g.strokeRect(-w / 2, -l / 2, w, l);
        g.setLineDash([]);
        // Which way it faces: a tick on its forward edge.
        g.beginPath(); g.moveTo(0, -l / 2); g.lineTo(0, -l / 2 - 6); g.stroke();
        g.restore();
        g.fillStyle = "rgba(16,34,42,.9)";
        g.font = "11px system-ui, sans-serif";
        g.fillText(one.name.length > 28 ? `${one.name.slice(0, 27)}…` : one.name, f.toX(at.x) + w / 2 + 4, f.toY(at.y) + 4);
      }
    }
    // Equipment falling, where it is now.
    if (dropping && things.some((t) => t.id === dropping.id)) {
      const at = dropAt(dropping);
      g.beginPath();
      g.arc(f.toX(at.x), f.toY(at.y), 7, 0, Math.PI * 2);
      g.strokeStyle = "#c25a15"; g.lineWidth = 2; g.stroke();
    }
    if (route.length) {
      const along = hover ? [...route, hover] : route;
      g.beginPath();
      along.forEach((p, i) => (i === 0 ? g.moveTo(f.toX(p.x), f.toY(p.y)) : g.lineTo(f.toX(p.x), f.toY(p.y))));
      g.strokeStyle = "#c25a15"; g.lineWidth = 2; g.stroke();
      if (drawing) spansOf(drawing);
    }
    if (first) {
      g.beginPath();
      g.arc(f.toX(first.x), f.toY(first.y), 4, 0, Math.PI * 2);
      g.strokeStyle = "#c25a15"; g.lineWidth = 2; g.stroke();
    }
    // What the cursor would put down, at its size, before it is put.
    const ghost = assetOf ? sizeOf(assetOf) : tool && BUILT[tool] ? [BUILT[tool]!.wideM, BUILT[tool]!.longM] : undefined;
    if (hover && ghost && (!assetOf || meetsOf(assetOf) !== "drapes")) {
      const w = Math.max(ghost[0]! * f.perM, 8), l = Math.max(ghost[1]! * f.perM, 8);
      g.setLineDash([4, 3]);
      g.strokeStyle = hoverSays.worry ? "#d0342c" : "#1f7a4d";
      g.lineWidth = 1.6;
      g.strokeRect(f.toX(hover.x) - w / 2, f.toY(hover.y) - l / 2, w, l);
      g.setLineDash([]);
    }
  }, [ground, layers, objects, things, chosen, drapes, dropping, route, hover, drawing, first, assetOf, tool, hoverSays]);

  // Keys: R turns what is chosen, Delete takes it away, Escape puts the tool down.
  useEffect(() => {
    const key = (event: KeyboardEvent) => {
      if ((event.target as HTMLElement | null)?.closest("input, select, textarea")) return;
      if (event.key === "Escape") { setTool(undefined); setFirst(undefined); setRoute([]); return; }
      if (!chosen) return;
      if (event.key === "r" || event.key === "R") {
        const by = event.shiftKey ? -15 : 15;
        edit(() => setObjects((was) => was.map((o) => o.id === chosen ? { ...o, headingDeg: (o.headingDeg + by + 360) % 360, laidBy: undefined } : o)));
      }
      if (event.key === "Delete" || event.key === "Backspace") remove();
    };
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }); // eslint-disable-line react-hooks/exhaustive-deps

  const remove = () => {
    edit(() => {
      setThings((was) => was.filter((t) => t.id !== chosen));
      setObjects((was) => was.filter((o) => o.id !== chosen));
    });
    setChosen(undefined);
  };

  const save = async () => {
    setBusy(true); setTrouble("");
    try {
      let into = layout;
      if (!into) {
        for (let attempt = 1; attempt < 8 && !into; attempt++) {
          try {
            into = await platform.startLayout(place, { slug: attempt === 1 ? "design" : `design-${attempt}`, name: attempt === 1 ? "Design" : `Design ${attempt}` });
          } catch (refused) {
            if (!(refused instanceof Error) || !/exists/.test(refused.message)) throw refused;
          }
        }
        if (!into) throw new Error("could not make an arrangement for this place");
        setLayouts((was) => [...was, into!]);
        setLayout(into);
      }
      const document = { describedBy: DESCRIBED_BY, frame: FRAME, things, objects } as unknown as LayoutDocument;
      const version = await platform.saveLayout(into.id, document, `${things.length} equipment, ${objects.length} objects`);
      setSaid(`Saved, version ${version.ordinal}.`);
      setChanged(false);
    } catch (problem) {
      setTrouble(problem instanceof Error ? problem.message : "it would not save");
    } finally {
      setBusy(false);
    }
  };

  // Laying objects in: one mapping for every object not yet in the place.
  const unlaid = objects.filter((o) => !o.laidBy);
  const layIn = async () => {
    if (!earth || unlaid.length === 0) return;
    setBusy(true); setTrouble("");
    try {
      const made = await platform.startPlaceMapping(place, {
        assets: unlaid.map((o) => {
          const at = earth.toLatLon(o.x, o.y);
          if (o.meets === "stands") return { reconstructionId: o.assetId, placement: { lat: at.lat, lon: at.lon, headingDeg: o.headingDeg } };
          if (o.meets === "drapes") return { reconstructionId: o.assetId };
          return { reconstructionId: o.assetId, start: at, withinM: 50 };
        }),
      });
      setMapping(made);
    } catch (problem) {
      setTrouble(problem instanceof Error ? problem.message : "laying in could not start");
    } finally {
      setBusy(false);
    }
  };
  useEffect(() => {
    if (!mapping || mapping.state === "failed") return;
    if (mapping.state === "ready") {
      const versionId = mapping.versionId;
      const ids = new Set(unlaid.map((o) => o.id));
      setMapping(undefined);
      edit(() => setObjects((was) => was.map((o) => ids.has(o.id) ? { ...o, laidBy: mapping.id } : o)));
      if (versionId) {
        void platform.publishVersion(versionId).then(() => {
          setSaid("Laid into the place and published: dives fly with them now.");
          onChanged();
        }).catch((p) => setTrouble(p instanceof Error ? p.message : "laid, but it would not publish"));
      }
      return;
    }
    const again = setInterval(() => {
      platform.mapping(mapping.id).then(setMapping).catch(() => undefined);
    }, 3000);
    return () => clearInterval(again);
  }, [platform, mapping]); // eslint-disable-line react-hooks/exhaustive-deps
  const mappingAssets = (mapping as unknown as { assets?: { ordinal: number; reconstructionId: string; name?: string; state: string; candidates?: unknown[]; start?: [number, number] | null }[] } | undefined)?.assets ?? [];
  const choosing = mapping?.state === "choosing" ? mappingAssets.find((a) => a.state === "choosing") : undefined;
  const choiceGround = useVersionGround(platform, choosing ? (mapping as unknown as { baseVersionId?: string }).baseVersionId ?? pkg?.version.id : undefined);

  if (!city) return <Empty title="Not a place you have">It may have been withdrawn.</Empty>;
  if (pkg === undefined) return <Empty title="No ground yet">This place has no published version to design on. Build or copy one first.</Empty>;

  const reefsAndStructures = assets.filter((a) => a.kind === "reef" || a.kind === "structure");
  const lastStep = mapping?.steps?.[mapping.steps.length - 1]?.say;

  return (
    <Page title={city.name} crumb="the place" onCrumb={onBack} wide
          subtitle="Put equipment and your objects on the seabed; each is fitted to the ground as you place it."
          info="Equipment is saved as this place's arrangement, which a dive pins. Your objects are laid into the place itself: Lay in makes a new version with them in the seabed and publishes it. The fit, the pipe spans and the drop are worked out here from the place's own depths; a dive runs the coupled engine."
          actions={<>
            {unlaid.length > 0 ? (
              <Button disabled={busy || !!mapping || !earth} onClick={() => void layIn()}>
                {mapping ? "Laying in…" : `Lay ${unlaid.length} object${unlaid.length === 1 ? "" : "s"} in`}
              </Button>
            ) : null}
            <Button kind="primary" disabled={busy || (!changed && !!layout)} onClick={() => void save()}>{busy ? "Saving…" : "Save"}</Button>
          </>}
          toolbar={(
            <div className="designer-bar">
              <div className="layer-chips" role="group" aria-label="Layers">
                {LAYERS.map((one) => (
                  <button key={one.key} type="button" className={layers[one.key] ? "chip on" : "chip"} aria-pressed={layers[one.key]}
                          onClick={() => setLayers((was) => ({ ...was, [one.key]: !was[one.key] }))}>{one.name}</button>
                ))}
              </div>
              {layouts.length > 1 ? (
                <select value={layout?.id ?? ""} onChange={(e) => onOpenLayout(e.target.value)} aria-label="Arrangement">
                  {layouts.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
                </select>
              ) : null}
              <span className="note">{[said, changed ? "not saved" : !said ? (layout ? `Arrangement: ${layout.name}` : "Nothing saved yet") : ""].filter(Boolean).join(" · ")}</span>
            </div>
          )}>
      <section className="designer">
        <div className="palette">
          <h3>Your objects</h3>
          {reefsAndStructures.length === 0 ? <p className="note">None yet. Make one under Objects, or copy one from the Store.</p> : null}
          {reefsAndStructures.map((a) => {
            const key = `object:${a.id}`;
            return (
              <button key={a.id} type="button" className={tool === key ? "tool on" : "tool"} aria-pressed={tool === key}
                      title={a.name}
                      onClick={() => {
                        setFirst(undefined); setRoute([]);
                        // One that drapes goes along its own route: no click on the chart to wait for.
                        const route = (a.brief as { route?: { points?: number[][] } } | undefined)?.route?.points;
                        if (a.meets === "drapes" && earth && route?.length) {
                          const points = route.map((p) => earth.toSite(p[0]!, p[1]!));
                          const middle = points[Math.floor(points.length / 2)]!;
                          const one: Placed = { id: named("object"), assetId: a.id, name: a.name, meets: "drapes", ...middle,
                                                headingDeg: 0, sizeM: sizeOf(a), route: points };
                          edit(() => setObjects((was) => [...was, one]));
                          setChosen(one.id); setTool(undefined);
                          return;
                        }
                        setTool(tool === key ? undefined : key);
                      }}>
                <ObjectArt kind={artOf(a)} size={22} />
                <span>{a.name.replace(/\s*\([^()]*\)\s*$/, "")}</span>
              </button>
            );
          })}
          {GROUPS.map((group) => (
            <React.Fragment key={group.lands}>
              <h3>{group.title}</h3>
              {Object.entries(TOOLS).filter(([, what]) => what.lands === group.lands).map(([key, what]) => (
                <button key={key} type="button" className={tool === key ? "tool on" : "tool"} aria-pressed={tool === key}
                        onClick={() => { setFirst(undefined); setRoute([]); setTool(tool === key ? undefined : key); }}>
                  <span>{what.name}</span>
                </button>
              ))}
            </React.Fragment>
          ))}
        </div>

        <div className="canvas">
          <SiteChart ground={ground} things={(layers.equipment ? things : []) as Charted[]} chosen={chosen} shade={layers.shade}
                     fit={[...(things as Charted[]).flatMap((t) => t.corners ?? t.ends ?? t.route ?? [centreOf(t)]),
                           ...objects.flatMap((o) => o.route ?? [{ x: o.x, y: o.y }])]}
                     overlay={overlay} redraw={[hover, dropping, layers, objects]}
                     cursor={tool ? "crosshair" : "default"}
                     onPick={put} onDoublePick={finishRoute}
                     onHover={(at) => setHover(at)}
                     grabAt={(at) => { if (tool) return false; const hit = near(at); if (hit) setChosen(hit); return !!hit; }}
                     onDrag={(at) => drag(at)} />
          <div className={`readout${hoverSays.worry ? " worry" : ""}`}>
            {hover && ground ? <span>{groundAt(ground, hover.x, hover.y).toFixed(1)} m</span> : null}
            <span className="resolves">{hoverSays.says}</span>
          </div>
        </div>

        <div className="properties">
          {selectedObject || selectedThing ? (
            <Properties object={selectedObject} thing={selectedThing} fit={chosenFit} laid={chosenDrape} earth={earth}
                        current={current} onCurrent={setCurrent} dropping={dropping} ground={ground}
                        onTurn={(deg) => edit(() => setObjects((was) => was.map((o) => o.id === chosen ? { ...o, headingDeg: deg, laidBy: undefined } : o)))}
                        onMass={(kg) => edit(() => setObjects((was) => was.map((o) => o.id === chosen ? { ...o, massKg: kg } : o)))}
                        onDrop={drop}
                        onDuplicate={() => {
                          if (selectedThing) {
                            const copy = shifted(selectedThing, 25, -25, ground);
                            edit(() => setThings((was) => [...was, copy])); setChosen(copy.id);
                          } else if (selectedObject && !selectedObject.route) {
                            const copy = { ...selectedObject, id: named("object"), x: selectedObject.x + 10, y: selectedObject.y - 10, laidBy: undefined };
                            edit(() => setObjects((was) => [...was, copy])); setChosen(copy.id);
                          }
                        }}
                        onRemove={remove} />
          ) : (
            <div className="nothing-chosen">
              <h3>On this place</h3>
              {things.length + objects.length === 0 ? <p className="note">Nothing yet. Choose something on the left and click the seabed.</p> : null}
              {objects.map((o) => (
                <button key={o.id} type="button" className="one" onClick={() => setChosen(o.id)}>
                  <span>{o.name.replace(/\s*\([^()]*\)\s*$/, "")}</span><span className="depth">{o.laidBy ? "laid in" : "not laid in"}</span>
                </button>
              ))}
              {things.map((t) => (
                <button key={t.id} type="button" className="one" onClick={() => setChosen(t.id)}>
                  <span>{TOOLS[t.kind]?.name ?? t.kind}</span><span className="depth">{saysOf(t)}</span>
                </button>
              ))}
              <p className="note keys">Drag a thing to move it. R turns it, Delete removes it, Escape puts the tool down.</p>
            </div>
          )}
          {mapping ? (
            <div className="laying">
              <Status tone={mapping.state === "failed" ? "bad" : "busy"}>laying in: {mapping.state}</Status>
              {lastStep ? <span className="note">{lastStep}</span> : null}
              {mapping.state === "failed" ? <p className="trouble">{mapping.failure}</p> : null}
            </div>
          ) : null}
          {trouble ? <p className="trouble">{trouble}</p> : null}
        </div>
      </section>

      {choosing && mapping ? (
        <Dialog title={`Where ${choosing.name ?? "the reef"} fits`} wide onClose={() => undefined}>
          <ResolveChoice key={choosing.ordinal} candidates={(choosing.candidates ?? []) as Candidate[]} start={choosing.start}
                         ground={choiceGround} extentM={[50, 10]} busy={busy}
                         onAccept={(choice) => {
                           setBusy(true);
                           platform.acceptMapping(mapping.id, { ...choice, asset: choosing.ordinal })
                             .then(setMapping)
                             .catch((p) => setTrouble(p instanceof Error ? p.message : "could not choose it"))
                             .finally(() => setBusy(false));
                         }} />
        </Dialog>
      ) : null}
    </Page>
  );
}

/** What is chosen: what it is, where, how it sits, and dropping it. */
function Properties({ object, thing, fit, laid, earth, current, onCurrent, dropping, ground, onTurn, onMass, onDrop, onDuplicate, onRemove }: {
  object?: Placed;
  thing?: Thing;
  fit?: Rest;
  laid?: Draped;
  earth?: ReturnType<typeof earthOf>;
  current: { speed: string; towards: string };
  onCurrent: (c: { speed: string; towards: string }) => void;
  dropping?: Dropping;
  ground?: Ground;
  onTurn: (deg: number) => void;
  onMass: (kg: number | undefined) => void;
  onDrop: () => void;
  onDuplicate: () => void;
  onRemove: () => void;
}): React.JSX.Element {
  const name = object ? object.name.replace(/\s*\([^()]*\)\s*$/, "") : TOOLS[thing!.kind]?.name ?? thing!.kind;
  const at = object ?? thing!;
  const ll = earth?.toLatLon(at.x, at.y);
  const fitLine = fit ? fitSaid(fit) : undefined;
  const drapeLine = laid ? drapeSaid(laid) : undefined;
  const canDrop = object ? object.meets === "stands" : !!(thing && BUILT[thing.kind]);
  const body = object ? bodyOf(object) : thing ? BUILT[thing.kind]?.body : undefined;
  const mine = dropping && dropping.id === at.id ? dropping : undefined;
  const kindSaid = object ? (object.meets === "reef" ? "reef, found by a search near here"
    : object.meets === "drapes" ? "laid along its own route" : "stands on the seabed")
    : TOOLS[thing!.kind]?.says(thing!.groundM ?? 0) ?? "";

  return (
    <div className="chosen">
      <h3>{name}</h3>
      <p className="note">{kindSaid}</p>
      <dl className="run-facts">
        <div><dt>where</dt><dd>{at.x.toFixed(1)} m east, {at.y.toFixed(1)} m north</dd></div>
        {ll ? <div><dt>on the Earth</dt><dd>{ll.lat.toFixed(6)}, {ll.lon.toFixed(6)}</dd></div> : null}
        {object && !object.route ? <div><dt>size</dt><dd>{object.sizeM.map((v) => v.toFixed(1)).join(" × ")} m</dd></div> : null}
        {object ? <div><dt>in the place</dt><dd>{object.laidBy ? "laid in" : "not laid in yet"}</dd></div> : null}
      </dl>

      {object && object.meets !== "drapes" ? (
        <label className="field"><span>Heading, {object.headingDeg.toFixed(0)}°</span>
          <input type="range" min={0} max={359} step={1} value={object.headingDeg} onChange={(e) => onTurn(Number(e.target.value))} />
        </label>
      ) : null}

      {fitLine ? (
        <div className={`fit${fitLine.worry ? " worry" : ""}`}>
          <h4>How it sits</h4>
          <p>{fitLine.says}.</p>
          {fit ? <p className="note">The ground under it rises and falls {fit.reliefM.toFixed(1)} m.</p> : null}
        </div>
      ) : null}
      {drapeLine ? (
        <div className={`fit${drapeLine.worry ? " worry" : ""}`}>
          <h4>How it lies</h4>
          <p>{drapeLine.says}.</p>
          <p className="note">Bridges hollows tighter than a 150 m bend; spans are drawn red on the chart.</p>
        </div>
      ) : null}

      {canDrop && body ? (
        <div className="drop">
          <h4>Drop it from the surface</h4>
          <div className="inline-fields">
            <label>Current, m/s<input value={current.speed} onChange={(e) => onCurrent({ ...current, speed: e.target.value })} /></label>
            <label>Towards, °<input value={current.towards} onChange={(e) => onCurrent({ ...current, towards: e.target.value })} /></label>
            {object ? (
              <label>Weight, kg<input value={object.massKg ?? Math.round(body.massKg)} onChange={(e) => onMass(Number(e.target.value) || undefined)} /></label>
            ) : null}
          </div>
          <Button onClick={onDrop}>Drop</Button>
          {mine && ground ? <DropView fell={mine.fell} began={mine.began} from={mine.from} ground={ground} /> : null}
          {mine?.fell.landed ? (
            <p className="note">
              Landed {Math.hypot(mine.fell.landed.x - mine.from.x, mine.fell.landed.y - mine.from.y).toFixed(1)} m from where it was let go,
              after {mine.fell.landed.t.toFixed(0)} s, sinking at {mine.fell.terminalMs.toFixed(1)} m/s.
            </p>
          ) : mine?.fell.floats ? <p className="note">It floats: lighter than the water it moves.</p> : null}
          <p className="note">A rigid body sinking against drag in a steady current, worked out here. A dive runs the coupled engine.</p>
        </div>
      ) : null}

      <div className="acts">
        <Button kind="ghost" onClick={onDuplicate} disabled={!!object?.route}>Duplicate</Button>
        <Button kind="ghost" onClick={onRemove}>Remove</Button>
      </div>
    </div>
  );
}

/** The drop from the side: the water column, the seabed along the drift, and the thing on its way down. */
function DropView({ fell, began, from, ground }: { fell: Fall; began: number; from: { x: number; y: number }; ground: Ground }): React.JSX.Element {
  const canvas = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    let raf = 0;
    const draw = () => {
      const element = canvas.current;
      const g = element?.getContext("2d");
      if (!element || !g) return;
      const w = element.clientWidth, h = element.clientHeight, ratio = window.devicePixelRatio || 1;
      element.width = w * ratio; element.height = h * ratio;
      g.setTransform(ratio, 0, 0, ratio, 0, 0);
      const end = fell.path[fell.path.length - 1]!;
      const t = Math.min((performance.now() - began) / 1000 * rateOf(fell), end.t);
      const now = fell.path.find((p) => p.t >= t) ?? end;
      // Along the drift, from a little behind where it was let go to a little past where it lands.
      const dx = end.x - from.x, dy = end.y - from.y, drift = Math.hypot(dx, dy);
      const ux = drift > 0.01 ? dx / drift : 1, uy = drift > 0.01 ? dy / drift : 0;
      const span = Math.max(10, drift * 1.6 + 6), back = span * 0.2;
      const deepest = Math.max(end.z, ...Array.from({ length: 41 }, (_, i) => groundAt(ground, from.x + ux * (i / 40 * span - back), from.y + uy * (i / 40 * span - back)))) * 1.1;
      const toX = (s: number) => ((s + back) / span) * w, toY = (z: number) => (z / deepest) * (h - 4) + 2;
      g.fillStyle = "#dbe8ee"; g.fillRect(0, 0, w, h);
      g.beginPath(); g.moveTo(0, h);
      for (let i = 0; i <= 40; i++) {
        const s = i / 40 * span - back;
        g.lineTo(toX(s), toY(groundAt(ground, from.x + ux * s, from.y + uy * s)));
      }
      g.lineTo(w, h); g.closePath(); g.fillStyle = "#cdb98f"; g.fill();
      g.beginPath();
      fell.path.filter((p) => p.t <= t).forEach((p, i) => {
        const s = (p.x - from.x) * ux + (p.y - from.y) * uy;
        if (i === 0) g.moveTo(toX(s), toY(p.z)); else g.lineTo(toX(s), toY(p.z));
      });
      g.strokeStyle = "rgba(194,90,21,.6)"; g.setLineDash([3, 3]); g.lineWidth = 1; g.stroke(); g.setLineDash([]);
      const s = (now.x - from.x) * ux + (now.y - from.y) * uy;
      g.fillStyle = "#c25a15"; g.fillRect(toX(s) - 5, toY(now.z) - 8, 10, 8);
      g.fillStyle = "rgba(16,34,42,.85)"; g.font = "11px ui-monospace, monospace";
      g.fillText(`${now.z.toFixed(1)} m · ${now.t.toFixed(0)} s`, 6, 14);
      if (t < end.t) raf = requestAnimationFrame(draw);
    };
    raf = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(raf);
  }, [fell, began, from, ground]);
  return <canvas ref={canvas} className="drop-view" />;
}

