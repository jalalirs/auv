// Laying out a place: the editor.
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

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type { Layout as LayoutRecord, LayoutDocument, Platform } from "@coral-city/api";
import type { PlacePackage } from "../platform/packages.js";
import { Empty, PageHead, Pill } from "./parts.js";

/** One end of something, or one thing. */
interface Point { x: number; y: number; z?: number; groundM?: number }

/** One thing in the water, as the document carries it. */
interface Thing extends Point {
  id: string;
  kind: string;
  /** Both ends, for something that spans. */
  ends?: Point[];
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
 */
type Lands = "ground" | "surface" | "span" | "region";

interface Tool {
  name: string;
  lands: Lands;
  /** What a click resolves to, said before it is committed. */
  says: (d: number) => string;
  /** What the end of a span lands on, first end then second. */
  endsOn?: [Lands, Lands];
  slack?: number;
}

const TOOLS: Record<string, Tool> = {
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
  "mooring-line": { name: "Mooring line", lands: "span", endsOn: ["ground", "surface"],
    slack: 0.02,
    says: (d) => `one end on the bottom at ${d.toFixed(1)} m, the other at the surface` },
  "restoration-cell": { name: "Restoration cell", lands: "region",
    says: () => "a plot on the chart — something to work inside, not something to hit" },
};

/** The palette, in the order the panel shows it: by landing rule, because that
 * is what the editor resolves and what tells you where a thing will end up. */
const GROUPS: { title: string; lands: Lands }[] = [
  { title: "Sits on the ground", lands: "ground" },
  { title: "Floats", lands: "surface" },
  { title: "Runs between two points", lands: "span" },
  { title: "Drawn on the chart", lands: "region" },
];

const DESCRIBED_BY = "coral-city/layout/v1";

// Said in the document rather than known by whoever reads it. A layout is read
// by the editor, the runtime, a replay and one day a sonar, and a frame that
// each of them has to guess is a frame three of them will get wrong.
const FRAME = "metres, origin at the middle of the site, +x east, +y north";

/** The seabed, read from the package's own heightfield. */
interface Ground {
  rows: number;
  columns: number;
  acrossM: number;
  depth: Float32Array;
}

async function groundOf(pkg: PlacePackage | undefined): Promise<Ground | undefined> {
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

/** How deep the ground is at a point, in the frame everything else uses.
 *
 * The one frame: metres, origin at the middle of the site, +x east, +y north —
 * the same coordinates the vehicle's own positions are in, so a transponder
 * drawn here and a vehicle flown there are talking about one place. The
 * heightfield runs south to north then west to east, which the site's own note
 * says and the runtime reads the same way; this is that sampling, in
 * TypeScript.
 */
function groundAt(ground: Ground, x: number, y: number): number {
  const { rows, columns, acrossM, depth } = ground;
  const fx = Math.min(columns - 1.001, Math.max(0, (x / acrossM + 0.5) * (columns - 1)));
  const fy = Math.min(rows - 1.001, Math.max(0, (y / acrossM + 0.5) * (rows - 1)));
  const x0 = Math.floor(fx), y0 = Math.floor(fy);
  const tx = fx - x0, ty = fy - y0;
  const at = (cx: number, cy: number) => depth[cy * columns + cx] ?? 0;
  return at(x0, y0) * (1 - tx) * (1 - ty) + at(x0 + 1, y0) * tx * (1 - ty)
       + at(x0, y0 + 1) * (1 - tx) * ty + at(x0 + 1, y0 + 1) * tx * ty;
}

/** Where a pointer is, in that frame. Nothing when it is off the site. */
function pointerAt(box: DOMRect, ground: Ground, clientX: number, clientY: number) {
  const side = Math.min(box.width, box.height);
  const padX = (box.width - side) / 2, padY = (box.height - side) / 2;
  const half = ground.acrossM / 2;
  const x = ((clientX - box.left - padX) / side) * ground.acrossM - half;
  const y = (1 - (clientY - box.top - padY) / side) * ground.acrossM - half;
  if (Math.abs(x) > half || Math.abs(y) > half) return undefined;
  return { x, y };
}

/** A name that will not collide with the one made a millisecond ago. */
function named(kind: string): string {
  return `${kind}-${Date.now().toString(36)}-${Math.floor(Math.random() * 4096).toString(36)}`;
}

/** Where a click puts something, by its landing rule, resolved now and kept. */
function landed(lands: Lands, ground: Ground, x: number, y: number): Point {
  const deep = groundAt(ground, x, y);
  const at = { x: Math.round(x * 10) / 10, y: Math.round(y * 10) / 10,
               groundM: Math.round(deep * 10) / 10 };
  // Something floating is at the surface whatever the bottom is doing; the
  // depth under it is still worth keeping, because that is what decides
  // whether a line from it can reach.
  return { ...at, z: lands === "surface" ? 0 : Math.round(-deep * 10) / 10 };
}

/** One point on a thing, for picking it and drawing it. */
function centreOf(thing: Thing): { x: number; y: number } {
  if (thing.ends?.length === 2) {
    return { x: (thing.ends[0]!.x + thing.ends[1]!.x) / 2,
             y: (thing.ends[0]!.y + thing.ends[1]!.y) / 2 };
  }
  if (thing.corners?.length) {
    const xs = thing.corners.map((c) => c.x), ys = thing.corners.map((c) => c.y);
    return { x: (Math.min(...xs) + Math.max(...xs)) / 2,
             y: (Math.min(...ys) + Math.max(...ys)) / 2 };
  }
  return { x: thing.x, y: thing.y };
}

/** What the listing says about a thing, which is not always one depth. */
function saysOf(thing: Thing): string {
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
function shifted(thing: Thing, dx: number, dy: number, ground: Ground | undefined): Thing {
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
function spanBetween(kind: string, what: Tool, ground: Ground,
                     from: { x: number; y: number }, to: { x: number; y: number }): Thing | undefined {
  if (Math.hypot(to.x - from.x, to.y - from.y) < 1) return undefined;
  const [firstOn, secondOn] = what.endsOn ?? ["ground", "ground"];
  const ends = [landed(firstOn, ground, from.x, from.y), landed(secondOn, ground, to.x, to.y)];
  return { id: named(kind), kind, x: (ends[0]!.x + ends[1]!.x) / 2,
           y: (ends[0]!.y + ends[1]!.y) / 2, ends, slack: what.slack ?? 0 };
}

/** A plot between two clicks: the rectangle they bound, wound anticlockwise. */
function cellBetween(kind: string, ground: Ground,
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

export function LayoutEditor({ platform, pkg, layout, onBack }: {
  platform: Platform;
  pkg: PlacePackage | undefined;
  layout: LayoutRecord;
  onBack: () => void;
}): React.JSX.Element {
  const [ground, setGround] = useState<Ground | undefined>();
  const [things, setThings] = useState<Thing[]>([]);
  const [tool, setTool] = useState<string | undefined>();
  const [chosen, setChosen] = useState<string | undefined>();
  // The first click of a two-click tool, while the second has not happened.
  const [first, setFirst] = useState<{ x: number; y: number } | undefined>();
  const [under, setUnder] = useState<number | undefined>();
  const [saving, setSaving] = useState("");
  const [trouble, setTrouble] = useState("");
  const canvas = useRef<HTMLCanvasElement>(null);

  useEffect(() => { void groundOf(pkg).then(setGround); }, [pkg]);

  // What was saved last, so opening an arrangement shows it rather than a
  // blank chart. A layout somebody spent an afternoon on is not a draft.
  useEffect(() => {
    let stale = false;
    void platform.versionsOfLayout(layout.id).then((versions) => {
      const newest = versions[0];
      const document = newest?.document as LayoutDocument | undefined;
      if (!stale && document?.things) setThings(document.things as Thing[]);
    }).catch(() => undefined);
    return () => { stale = true; };
  }, [platform, layout.id]);

  const place = useCallback((event: React.MouseEvent<HTMLCanvasElement>) => {
    const box = canvas.current?.getBoundingClientRect();
    if (!box || !ground) return;
    const where = pointerAt(box, ground, event.clientX, event.clientY);
    if (!where) return;
    const { x, y } = where;

    if (tool === undefined) {
      const near = things.find((t) => Math.hypot(centreOf(t).x - x, centreOf(t).y - y)
                                      < ground.acrossM / 60);
      setChosen(near?.id);
      return;
    }
    const what = TOOLS[tool]!;

    // Two-click tools: a line needs both its ends and a plot needs two corners,
    // so the first click is remembered and the second makes the thing. Shown
    // on the chart while it is half-drawn, because a tool that silently
    // swallows a click is a tool people click twice in the same place.
    if (what.lands === "span" || what.lands === "region") {
      if (!first) { setFirst({ x, y }); return; }
      const made = what.lands === "span"
        ? spanBetween(tool, what, ground, first, { x, y })
        : cellBetween(tool, ground, first, { x, y });
      setFirst(undefined);
      if (made) { setThings((was) => [...was, made]); setChosen(made.id); }
      return;
    }

    // The landing rule, applied where it belongs: when the thing is drawn,
    // against this seabed. A layout then means the same thing to the editor,
    // the runtime and the record.
    const made: Thing = { id: named(tool), kind: tool, ...landed(what.lands, ground, x, y) };
    setThings((was) => [...was, made]);
    setChosen(made.id);
  }, [ground, things, tool, first]);

  const watch = useCallback((event: React.MouseEvent<HTMLCanvasElement>) => {
    const box = canvas.current?.getBoundingClientRect();
    if (!box || !ground) { setUnder(undefined); return; }
    const where = pointerAt(box, ground, event.clientX, event.clientY);
    setUnder(where === undefined ? undefined : groundAt(ground, where.x, where.y));
  }, [ground]);

  // The chart, drawn from the survey: pale in the shallows, deep blue off the
  // edge, the way a chart is.
  useEffect(() => {
    const element = canvas.current;
    if (!element || !ground) return;
    const ratio = window.devicePixelRatio || 1;
    const box = element.getBoundingClientRect();
    element.width = box.width * ratio;
    element.height = box.height * ratio;
    const g = element.getContext("2d");
    if (!g) return;
    g.setTransform(ratio, 0, 0, ratio, 0, 0);
    g.clearRect(0, 0, box.width, box.height);

    const side = Math.min(box.width, box.height);
    const padX = (box.width - side) / 2, padY = (box.height - side) / 2;
    const step = Math.max(1, Math.round(side / 260));
    for (let py = 0; py < side; py += step) {
      for (let px = 0; px < side; px += step) {
        const deep = groundAt(ground, (px / side - 0.5) * ground.acrossM,
                              (0.5 - py / side) * ground.acrossM);
        const t = Math.min(1, Math.max(0, deep / 30));
        const shade = deep < 0.2
          ? "rgb(216,201,168)"
          : `rgb(${Math.round(238 - 210 * t)},${Math.round(226 - 140 * t)},${Math.round(190 - 80 * t)})`;
        g.fillStyle = shade;
        g.fillRect(padX + px, padY + py, step, step);
      }
    }

    const toX = (m: number) => padX + (m / ground.acrossM + 0.5) * side;
    const toY = (m: number) => padY + (0.5 - m / ground.acrossM) * side;
    // Drawn as what it is. A line shown as a dot at its middle is a line
    // nobody can see the run of, and a plot shown as a dot is a plot nobody
    // can see the extent of — which is the whole reason for drawing it.
    for (const thing of things) {
      const on = thing.id === chosen;
      g.lineWidth = on ? 2.6 : 1.6;
      g.strokeStyle = on ? "#c25a15" : "#10222a";
      g.fillStyle = "rgba(255,255,255,.9)";

      if (thing.corners?.length) {
        g.beginPath();
        thing.corners.forEach((c, i) =>
          i === 0 ? g.moveTo(toX(c.x), toY(c.y)) : g.lineTo(toX(c.x), toY(c.y)));
        g.closePath();
        g.fillStyle = on ? "rgba(194,90,21,.18)" : "rgba(16,34,42,.12)";
        g.fill();
        g.setLineDash([6, 4]);
        g.stroke();
        g.setLineDash([]);
        continue;
      }

      if (thing.ends?.length === 2) {
        const [a, b] = thing.ends as [Point, Point];
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
      // Something floating is drawn hollow: it is not on the bottom the
      // chart is showing, and a ship drawn like a transponder reads as one.
      if (TOOLS[thing.kind]?.lands === "surface") {
        g.beginPath();
        g.arc(toX(thing.x), toY(thing.y), on ? 10 : 8.5, 0, Math.PI * 2);
        g.stroke();
      }
    }

    // The click that has happened, while the one that finishes it has not.
    if (first) {
      g.beginPath();
      g.arc(toX(first.x), toY(first.y), 4, 0, Math.PI * 2);
      g.strokeStyle = "#c25a15";
      g.lineWidth = 2;
      g.stroke();
    }
  }, [ground, things, chosen, first]);

  const save = useCallback(async () => {
    setSaving("saving"); setTrouble("");
    try {
      const document = { describedBy: DESCRIBED_BY, frame: FRAME, things } as unknown as LayoutDocument;
      const version = await platform.saveLayout(layout.id, document, `${things.length} things`);
      setSaving(`saved as version ${version.ordinal}`);
    } catch (thrown) {
      setSaving("");
      setTrouble(thrown instanceof Error ? thrown.message : "it would not save");
    }
  }, [platform, layout.id, things]);

  const selected = useMemo(
    () => things.find((t) => t.id === chosen), [things, chosen]);

  if (pkg === undefined) {
    return <Empty title="No package for this place">A layout is an arrangement of ground, and this place has none yet.</Empty>;
  }

  return (
    <>
      <PageHead title={layout.name} says={layout.summary} back="the place" onBack={onBack}
                aside={<Pill>{things.length} {things.length === 1 ? "thing" : "things"}</Pill>} />
      <section className="laying-out">
        <div className="tools">
          {GROUPS.map((group) => (
            <React.Fragment key={group.lands}>
              <h3>{group.title}</h3>
              {Object.entries(TOOLS).filter(([, what]) => what.lands === group.lands)
                .map(([key, what]) => (
                  <button key={key} type="button" className={tool === key ? "tool on" : "tool"}
                          aria-pressed={tool === key}
                          onClick={() => { setFirst(undefined); setTool(tool === key ? undefined : key); }}>
                    {what.name}
                  </button>
                ))}
            </React.Fragment>
          ))}
          <p className="quiet">
            Grouped by how a thing meets the bottom, not by what it is — because
            that is the only part the editor has to resolve for you.
          </p>
        </div>

        <div className="chart">
          <canvas ref={canvas} onClick={place} onMouseMove={watch}
                  onMouseLeave={() => setUnder(undefined)} />
          <div className="readout">
            <span>ground <b>{under === undefined ? "—" : `${under.toFixed(1)} m`}</b></span>
            <span className="resolves">
              {tool === undefined ? "pick a tool, or click a thing"
                : under === undefined ? "click the chart"
                : first !== undefined ? (TOOLS[tool]!.lands === "span"
                    ? "click the other end" : "click the opposite corner")
                : TOOLS[tool]!.says(under)}
            </span>
          </div>
        </div>

        <div className="listing">
          {things.length === 0
            ? <p className="quiet">Nothing here yet.</p>
            : things.map((thing) => (
              <div key={thing.id} className={thing.id === chosen ? "one on" : "one"}
                   onClick={() => setChosen(thing.id)}>
                <span>{TOOLS[thing.kind]?.name ?? thing.kind}</span>
                <span className="depth">{saysOf(thing)}</span>
              </div>
            ))}
          <div className="acts">
            <button type="button" disabled={!selected} onClick={() => {
              if (!selected) return;
              // A copy is a new thing. Copying the reference instead is how a
              // duplicated array turns out to be one transponder in eight
              // places, and it is found much later than it is made.
              const copy: Thing = shifted(selected, 25, -25, ground);
              setThings((was) => [...was, copy]);
              setChosen(copy.id);
            }}>Duplicate</button>
            <button type="button" disabled={!selected} onClick={() => {
              setThings((was) => was.filter((t) => t.id !== chosen));
              setChosen(undefined);
            }}>Delete</button>
          </div>
          <button type="button" className="save" onClick={() => void save()}
                  disabled={things.length === 0}>Save</button>
          {saving ? <p className="quiet">{saving}</p> : null}
          {trouble ? <p className="trouble">{trouble}</p> : null}
        </div>
      </section>
    </>
  );
}

/**
 * An arrangement, fetched by id so the editor can be reached by a route rather
 * than only by having been clicked.
 */
export function LayingOut({ platform, packages, place, layout, onBack }: {
  platform: Platform;
  packages: { places: Map<string, PlacePackage | null> };
  place: string;
  layout: string;
  onBack: () => void;
}): React.JSX.Element {
  const [found, setFound] = useState<LayoutRecord | undefined>();
  const [missing, setMissing] = useState(false);

  useEffect(() => {
    let stale = false;
    void platform.layout(layout)
      .then((one) => { if (!stale) setFound(one); })
      .catch(() => { if (!stale) setMissing(true); });
    return () => { stale = true; };
  }, [platform, layout]);

  if (missing) {
    return <Empty title="No such arrangement">It may have been withdrawn.</Empty>;
  }
  if (found === undefined) return <Empty title="Opening the chart…">{""}</Empty>;
  return <LayoutEditor platform={platform} pkg={packages.places.get(place) ?? undefined}
                       layout={found} onBack={onBack} />;
}
