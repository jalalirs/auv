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

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type { Layout as LayoutRecord, LayoutDocument, Platform } from "@coral-city/api";
import type { PlacePackage } from "../platform/packages.js";
import { Empty, PageHead, Pill } from "./parts.js";

/** One thing in the water, as the document carries it. */
interface Thing {
  id: string;
  kind: string;
  x: number;
  y: number;
  z?: number;
  groundM?: number;
}

/** How each kind of thing meets the bottom. The only part the editor resolves. */
const TOOLS: Record<string, { name: string; lands: "ground" | "float"; says: (d: number) => string }> = {
  transponder: {
    name: "Transponder", lands: "ground",
    says: (d) => `on the bottom at ${d.toFixed(1)} m`,
  },
};

const DESCRIBED_BY = "coral-city/layout/v1";

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

/** How deep the ground is at a point, in site metres from the south-west. */
function groundAt(ground: Ground, x: number, y: number): number {
  const { rows, columns, acrossM, depth } = ground;
  const fx = Math.min(columns - 1.001, Math.max(0, (x / acrossM) * (columns - 1)));
  const fy = Math.min(rows - 1.001, Math.max(0, (y / acrossM) * (rows - 1)));
  const x0 = Math.floor(fx), y0 = Math.floor(fy);
  const tx = fx - x0, ty = fy - y0;
  const at = (cx: number, cy: number) => depth[(rows - 1 - cy) * columns + cx] ?? 0;
  return at(x0, y0) * (1 - tx) * (1 - ty) + at(x0 + 1, y0) * tx * (1 - ty)
       + at(x0, y0 + 1) * (1 - tx) * ty + at(x0 + 1, y0 + 1) * tx * ty;
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
    const side = Math.min(box.width, box.height);
    const padX = (box.width - side) / 2, padY = (box.height - side) / 2;
    const x = ((event.clientX - box.left - padX) / side) * ground.acrossM;
    const y = (1 - (event.clientY - box.top - padY) / side) * ground.acrossM;
    if (x < 0 || y < 0 || x > ground.acrossM || y > ground.acrossM) return;

    if (tool === undefined) {
      const near = things.find((t) => Math.hypot(t.x - x, t.y - y) < ground.acrossM / 60);
      setChosen(near?.id);
      return;
    }
    // The landing rule, applied where it belongs: when the thing is drawn,
    // against this seabed. A layout then means the same thing to the editor,
    // the runtime and the record.
    const deep = groundAt(ground, x, y);
    const made: Thing = {
      id: `${tool}-${Date.now().toString(36)}`,
      kind: tool,
      x: Math.round(x * 10) / 10,
      y: Math.round(y * 10) / 10,
      groundM: Math.round(deep * 10) / 10,
      z: TOOLS[tool]!.lands === "float" ? 0 : Math.round(-deep * 10) / 10,
    };
    setThings((was) => [...was, made]);
    setChosen(made.id);
  }, [ground, things, tool]);

  const watch = useCallback((event: React.MouseEvent<HTMLCanvasElement>) => {
    const box = canvas.current?.getBoundingClientRect();
    if (!box || !ground) { setUnder(undefined); return; }
    const side = Math.min(box.width, box.height);
    const padX = (box.width - side) / 2, padY = (box.height - side) / 2;
    const x = ((event.clientX - box.left - padX) / side) * ground.acrossM;
    const y = (1 - (event.clientY - box.top - padY) / side) * ground.acrossM;
    setUnder(x < 0 || y < 0 || x > ground.acrossM || y > ground.acrossM
      ? undefined : groundAt(ground, x, y));
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
        const deep = groundAt(ground, (px / side) * ground.acrossM,
                              (1 - py / side) * ground.acrossM);
        const t = Math.min(1, Math.max(0, deep / 30));
        const shade = deep < 0.2
          ? "rgb(216,201,168)"
          : `rgb(${Math.round(238 - 210 * t)},${Math.round(226 - 140 * t)},${Math.round(190 - 80 * t)})`;
        g.fillStyle = shade;
        g.fillRect(padX + px, padY + py, step, step);
      }
    }

    const toX = (m: number) => padX + (m / ground.acrossM) * side;
    const toY = (m: number) => padY + (1 - m / ground.acrossM) * side;
    for (const thing of things) {
      const on = thing.id === chosen;
      g.beginPath();
      g.arc(toX(thing.x), toY(thing.y), on ? 7 : 5.5, 0, Math.PI * 2);
      g.fillStyle = "rgba(255,255,255,.9)";
      g.fill();
      g.lineWidth = on ? 2.6 : 1.6;
      g.strokeStyle = on ? "#c25a15" : "#10222a";
      g.stroke();
    }
  }, [ground, things, chosen]);

  const save = useCallback(async () => {
    setSaving("saving"); setTrouble("");
    try {
      const document = { describedBy: DESCRIBED_BY, things } as unknown as LayoutDocument;
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
          <h3>Sits on the ground</h3>
          {Object.entries(TOOLS).map(([key, what]) => (
            <button key={key} type="button" className={tool === key ? "tool on" : "tool"}
                    aria-pressed={tool === key}
                    onClick={() => setTool(tool === key ? undefined : key)}>
              {what.name}
            </button>
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
                <span className="depth">{(thing.groundM ?? 0).toFixed(1)} m</span>
              </div>
            ))}
          <div className="acts">
            <button type="button" disabled={!selected} onClick={() => {
              if (!selected) return;
              // A copy is a new thing. Copying the reference instead is how a
              // duplicated array turns out to be one transponder in eight
              // places, and it is found much later than it is made.
              const copy: Thing = { ...selected, id: `${selected.kind}-${Date.now().toString(36)}`,
                                    x: selected.x + 25, y: selected.y - 25 };
              if (ground) {
                copy.groundM = Math.round(groundAt(ground, copy.x, copy.y) * 10) / 10;
                copy.z = Math.round(-copy.groundM * 10) / 10;
              }
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
