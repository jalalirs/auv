// Objects: everything somebody puts in the sea, in one grid.
//
// A reef rebuilt from a dive video, a platform from a 3D model, a pipeline
// drawn on the map, a seabed survey. Each is made in its own frame and on no
// place; putting it in one is a later step. The grid is filtered by kind and
// searched by name, not split into a tab per kind, and a card says only the
// short name: where it came from and its licence are on its own page.
//
// New object starts with what you are adding, as pictures, and then asks the
// few things that kind needs. The rest has a default and sits under "more".

import { useEffect, useMemo, useState } from "react";
import type { Asset, Platform, Reconstruction, StructureType } from "@coral-city/api";
import { ObjectArt, type ObjectKind } from "../parts/ObjectArt.js";
import { WorldMap, type LatLon } from "../parts/WorldMap.js";
import { kindSaid, nameAndSource } from "./AssetDetail.js";
import type { Held } from "./Deck.js";
import { Card, Empty } from "./parts.js";
import { Button, Dialog, Page, Segmented, SkeletonCards, Status, type Tone } from "../ui/components.js";

const VIDEO = /\.(mp4|mov|mkv)$/i;
const MODEL = /\.(glb|gltf|obj)$/i;
const SURVEY = /\.(tif|tiff|xyz|csv|txt)$/i;

type Making = "model" | "video" | "route" | "survey";
const MAKING: { key: Making; art: ObjectKind; label: string; says: string }[] = [
  { key: "model", art: "model", label: "A 3D model", says: "A platform, a wreck, anything you have as GLB, glTF or OBJ" },
  { key: "video", art: "video", label: "A reef from video", says: "A swim over a reef, rebuilt in 3D" },
  { key: "route", art: "pipeline", label: "A pipeline", says: "Drawn on the map, point by point" },
  { key: "survey", art: "survey", label: "A seabed survey", says: "Depths you measured, as ground for a place" },
];
const STRUCTURES: { key: StructureType; label: string }[] = [
  { key: "platform", label: "Platform" }, { key: "wind-foundation", label: "Wind foundation" }, { key: "other", label: "Something else" },
];

type Filter = "all" | "reef" | "pipeline" | "structure" | "survey";
const FILTERS: { key: Filter; label: string }[] = [
  { key: "all", label: "Everything" }, { key: "reef", label: "Reefs" }, { key: "pipeline", label: "Pipelines" },
  { key: "structure", label: "Structures" }, { key: "survey", label: "Surveys" },
];

function megabytes(bytes: number): string {
  return bytes >= 1 << 30 ? `${(bytes / (1 << 30)).toFixed(1)} GB` : `${(bytes / (1 << 20)).toFixed(0)} MB`;
}

/** The state of a reconstruction as somebody waiting for it would put it. */
export function stateOf(one: Reconstruction): { kind?: "good" | "bad" | "busy"; said: string; doing?: string } {
  const last = one.steps[one.steps.length - 1];
  const doing = last ? `${last.say}${last.of ? ` (${last.n} of ${last.of})` : ""}` : undefined;
  switch (one.state) {
    case "ready": return { kind: "good", said: "ready" };
    case "failed": return { kind: "bad", said: "failed", doing: one.failure };
    case "queued": return { kind: "busy", said: "waiting for a GPU" };
    case "recording": return { kind: "busy", said: "storing" };
    default: return { kind: "busy", said: last ? last.step : "starting", doing };
  }
}

/** Which drawing an object gets, and which filter it falls under. */
export function artOf(one: Pick<Asset, "kind" | "type">): ObjectKind {
  if (one.kind === "reef") return "reef";
  if (one.kind === "bathymetry") return "survey";
  return one.type === "pipeline" || one.type === "platform" || one.type === "wind-foundation" ? one.type : "structure";
}

function filterOf(art: ObjectKind): Filter {
  return art === "reef" || art === "pipeline" || art === "survey" ? art : "structure";
}

/** The one line of numbers a card has room for. */
function specsOf(stats: Record<string, unknown> | undefined): string[] {
  const n = (k: string) => typeof stats?.[k] === "number" ? stats[k] as number : undefined;
  const size = stats?.["sizeM"] as number[] | undefined;
  const extent = stats?.["extentM"] as number[] | undefined;
  return [
    n("lengthM") !== undefined ? `${n("lengthM")!.toFixed(0)} m long` : "",
    n("diameterM") !== undefined ? `${n("diameterM")} m across` : "",
    Array.isArray(size) ? `${size.map((v) => +v.toFixed(1)).join(" × ")} m` : "",
    Array.isArray(extent) ? `${extent[0]!.toFixed(0)} by ${extent[1]!.toFixed(0)} m` : "",
  ].filter(Boolean);
}

/** Metres along a drawn route, near enough on a sphere the size of the Earth. */
function lengthOf(points: LatLon[]): number {
  let total = 0;
  for (let i = 1; i < points.length; i++) {
    const a = points[i - 1]!, b = points[i]!;
    const lat = ((a.lat + b.lat) / 2) * Math.PI / 180;
    total += Math.hypot((b.lat - a.lat) * 111_320, (b.lon - a.lon) * 111_320 * Math.cos(lat));
  }
  return total;
}

export function Reconstructions({ platform, held, onOpen, onOpenAsset }: {
  platform: Platform;
  held: Held;
  onOpen: (id: string) => void;
  /** A structure's or a survey's own page. */
  onOpenAsset?: (id: string) => void;
}): React.JSX.Element {
  const institution = held.institution;
  const [list, setList] = useState<Reconstruction[] | undefined>();
  const [assets, setAssets] = useState<Asset[]>([]);
  const [pictures, setPictures] = useState<Record<string, string>>({});
  const [filter, setFilter] = useState<Filter>("all");
  const [words, setWords] = useState("");
  const [adding, setAdding] = useState(false);
  const [trouble, setTrouble] = useState("");

  const read = useMemo(() => async () => {
    if (!institution) return;
    try {
      const [reefs, all] = await Promise.all([platform.reconstructionsOf(institution.id), platform.listAssets(institution.id)]);
      setList(reefs);
      setAssets(all.filter((a) => a.kind !== "reef"));
    } catch (problem) {
      setTrouble(problem instanceof Error ? problem.message : "could not read your objects");
    }
  }, [platform, institution]);

  useEffect(() => { void read(); }, [read]);
  // Kept fresh while any is still being made: a reef takes hours, so every
  // half minute is often enough.
  useEffect(() => {
    if (![...(list ?? []), ...assets].some((one) => one.state !== "ready" && one.state !== "failed")) return;
    const again = setInterval(() => void read(), 30_000);
    return () => clearInterval(again);
  }, [list, assets, read]);

  // The picture from above, for each reef that has one.
  useEffect(() => {
    for (const one of list ?? []) {
      if (one.state !== "ready" || pictures[one.id] !== undefined) continue;
      // "" once looked for and not there, so its card stops waiting for one.
      void platform.reconstructionObjects(one.id).then((objects) => {
        const url = objects.find((o) => o.path === "preview.jpg")?.url;
        setPictures((was) => ({ ...was, [one.id]: url ?? "" }));
      }).catch(() => setPictures((was) => ({ ...was, [one.id]: "" })));
    }
  }, [platform, list, pictures]);

  const everything = useMemo(() => [
    ...assets.map((one) => ({
      id: one.id, name: one.name, createdAt: one.createdAt, state: stateOf(one as unknown as Reconstruction),
      art: artOf(one), kind: kindSaid(one), specs: specsOf({ ...(one.footprint ?? {}), ...(one.stats ?? {}) }),
      picture: one.preview && one.state === "ready" ? one.preview : undefined, reading: false,
      open: () => onOpenAsset?.(one.id),
    })),
    ...(list ?? []).map((one) => ({
      id: one.id, name: one.name, createdAt: one.createdAt, state: stateOf(one),
      art: "reef" as ObjectKind, kind: "reef from a video", specs: specsOf(one.manifest as Record<string, unknown> | undefined),
      picture: pictures[one.id] || undefined, reading: one.state === "ready" && pictures[one.id] === undefined,
      open: () => onOpen(one.id),
    })),
  ].sort((a, b) => (a.createdAt < b.createdAt ? 1 : -1)), [assets, list, pictures, onOpen, onOpenAsset]);

  const counts = Object.fromEntries(FILTERS.map((f) => [f.key, 0])) as Record<Filter, number>;
  for (const one of everything) { counts.all++; counts[filterOf(one.art)]++; }
  const looking = words.trim().toLowerCase();
  const shown = everything.filter((one) => (filter === "all" || filterOf(one.art) === filter)
    && (!looking || `${one.name} ${one.kind}`.toLowerCase().includes(looking)));

  return (
    <Page title="Objects" subtitle="What goes into a place: reefs, structures, pipelines, surveys."
          info="An object is made on its own and goes into any place later. A reef comes from a dive video, a structure from a 3D model, a pipeline from a line drawn on the map."
          actions={institution ? <Button kind="primary" onClick={() => setAdding(true)}>New object</Button> : undefined}
          toolbar={<>
            <Segmented label="Kind" value={filter} onChange={setFilter}
                       options={FILTERS.filter((f) => f.key === "all" || counts[f.key] > 0 || f.key === filter)
                         .map((f) => ({ ...f, count: counts[f.key] }))} />
            <input className="dt-search" type="search" placeholder="Search objects" aria-label="Search objects"
                   value={words} onChange={(e) => setWords(e.target.value)} />
          </>}>
      {trouble ? <p className="trouble">{trouble}</p> : null}
      {list === undefined ? <SkeletonCards /> : everything.length === 0 ? (
        <Empty title="No objects yet">Add one with New object: a 3D model, a reef from a dive video, or a pipeline drawn on the map.</Empty>
      ) : shown.length === 0 ? (
        <Empty title="Nothing matches">Try another kind, or fewer words.</Empty>
      ) : (
        <div className="cards">
          {shown.map((one) => {
            const tone: Tone = one.state.kind === "bad" ? "bad" : "busy";
            return (
              <Card key={one.id} name={nameAndSource(one.name).name} detail={one.kind} picture={one.picture}
                    reading={one.reading} art={<ObjectArt kind={one.art} />}
                    specs={one.state.kind === "good" ? one.specs : [one.state.doing ?? one.state.said]}
                    corner={one.state.kind === "good" ? undefined : <Status tone={tone}>{one.state.said}</Status>}
                    onOpen={one.open} actions={<Button onClick={one.open}>Open</Button>} />
            );
          })}
        </div>
      )}
      {adding && institution ? (
        <NewObject platform={platform} org={institution.id} onClose={() => setAdding(false)}
                   onMade={(made, reef) => {
                     setAdding(false);
                     void read();
                     if (reef) onOpen(made); else onOpenAsset?.(made);
                   }} />
      ) : null}
    </Page>
  );
}

/** New object: what it is, as pictures, then the few things that kind needs. */
function NewObject({ platform, org, onClose, onMade }: {
  platform: Platform;
  org: string;
  onClose: () => void;
  onMade: (id: string, reef: boolean) => void;
}): React.JSX.Element {
  const [making, setMaking] = useState<Making | undefined>();
  const [file, setFile] = useState<File | undefined>();
  const [label, setLabel] = useState("");
  // A model
  const [structure, setStructure] = useState<StructureType>("platform");
  const [scale, setScale] = useState("1");
  const [up, setUp] = useState<"y" | "z">("y");
  // A reef
  const [height, setHeight] = useState("");
  const [start, setStart] = useState("");
  // A pipeline
  const [route, setRoute] = useState<LatLon[]>([]);
  const [view, setView] = useState({ centre: { lat: 22.3, lon: 39.0 }, zoom: 11 });
  const [diameter, setDiameter] = useState("0.5");
  const [burial, setBurial] = useState("0.3");
  // A survey
  const [datum, setDatum] = useState("MSL");
  const [errorM, setErrorM] = useState("0.3");

  const [sent, setSent] = useState<{ stage: string; done: number } | undefined>();
  const [trouble, setTrouble] = useState("");
  const busy = sent !== undefined;

  const startAt = useMemo(() => {
    const found = start.match(/^\s*(-?\d+(?:\.\d+)?)\s*[, ]\s*(-?\d+(?:\.\d+)?)\s*$/);
    if (!found) return undefined;
    const lat = Number(found[1]), lon = Number(found[2]);
    return Math.abs(lat) <= 90 && Math.abs(lon) <= 180 ? { lat, lon } : undefined;
  }, [start]);
  const heightM = height.trim() === "" ? undefined : Number(height);
  const heightOk = heightM === undefined || (Number.isFinite(heightM) && heightM > 0.2 && heightM <= 20);

  const fileOk = !!file && (making === "video" ? VIDEO.test(file.name) || file.type.startsWith("video/")
    : making === "model" ? MODEL.test(file.name) : making === "survey" ? SURVEY.test(file.name) : true);
  const ready = !busy && (
    making === "video" ? fileOk && heightOk && (start.trim() === "" || !!startAt)
    : making === "model" ? fileOk && Number(scale) > 0
    : making === "survey" ? fileOk && datum.trim() !== "" && Number(errorM) > 0
    : making === "route" ? route.length >= 2 && Number(diameter) > 0 && Number(burial) >= 0 && Number(burial) <= 1
    : false);

  const make = async () => {
    if (!making) return;
    setTrouble("");
    try {
      let object: string | undefined;
      if (file && making !== "route") {
        setSent({ stage: "hashing", done: 0 });
        object = (await platform.upload(org, file, { onProgress: (stage, done) => setSent({ stage, done }) })).id;
      }
      const named = label.trim() ? { label: label.trim() } : {};
      if (making === "video") {
        const made = await platform.startReconstruction(org, {
          video: { objectId: object!, name: file!.name }, ...named,
          ...(heightM !== undefined ? { cameraHeightM: heightM } : {}),
          ...(startAt ? { start: startAt } : {}),
        });
        onMade(made.id, true);
        return;
      }
      setSent({ stage: "starting", done: 0 });
      const made = await platform.createAsset(org,
        making === "survey" ? { kind: "bathymetry", object, datum: datum.trim(), errorM: Number(errorM), ...named,
                                file: { name: file!.name, format: /\.tiff?$/i.test(file!.name) ? "geotiff" : "xyz" } }
        : making === "model" ? { kind: "structure", type: structure, meets: "stands", object, ...named,
                                 model: { name: file!.name, format: file!.name.split(".").pop()!.toLowerCase() as "glb" | "gltf" | "obj", scale: Number(scale), up } }
        : { kind: "structure", type: "pipeline", meets: "drapes", ...named,
            route: { points: route.map((p) => [p.lat, p.lon]), diameterM: Number(diameter), burial: Number(burial) } });
      onMade(made.id, false);
    } catch (problem) {
      setTrouble(problem instanceof Error ? problem.message : "it could not be started");
    } finally {
      setSent(undefined);
    }
  };

  const chosen = MAKING.find((m) => m.key === making);
  const progress = sent === undefined ? undefined
    : sent.stage === "starting" ? "Starting…"
    : `${sent.stage === "hashing" ? "Checking" : "Uploading"} ${file ? Math.round(100 * sent.done / Math.max(file.size, 1)) : 0}%`;

  if (chosen === undefined) {
    return (
      <Dialog title="New object" onClose={onClose}>
        <div className="object-kinds">
          {MAKING.map((m) => (
            <button key={m.key} type="button" className="object-kind" onClick={() => setMaking(m.key)}>
              <ObjectArt kind={m.art} size={48} />
              <strong>{m.label}</strong>
              <span>{m.says}</span>
            </button>
          ))}
        </div>
      </Dialog>
    );
  }

  const fileField = (accept: string, ask: string) => (
    <label className="object-file">
      <input type="file" accept={accept}
             onChange={(e) => { const f = e.target.files?.[0]; if (f) setFile(f); e.target.value = ""; }} />
      <ObjectArt kind={chosen.art} size={32} />
      <span>{file ? `${file.name} · ${megabytes(file.size)}` : ask}</span>
    </label>
  );

  return (
    <Dialog title={chosen.label} wide={making === "route"} onClose={() => { if (!busy) onClose(); }}
            actions={<>
              <Button kind="ghost" disabled={busy} onClick={() => { setMaking(undefined); setFile(undefined); setTrouble(""); }}>Back</Button>
              <Button kind="primary" disabled={!ready} onClick={() => void make()}>
                {progress ?? (making === "video" ? "Upload and rebuild" : making === "route" ? "Make it" : "Upload")}
              </Button>
            </>}>
      {making === "model" ? (<>
        {fileField(".glb,.gltf,.obj", "Choose a model: GLB, glTF or OBJ")}
        {file && !fileOk ? <p className="trouble">That is not a GLB, glTF or OBJ file.</p> : null}
        <label className="field"><span>What it is</span>
          <select value={structure} onChange={(e) => setStructure(e.target.value as StructureType)}>
            {STRUCTURES.map((s) => <option key={s.key} value={s.key}>{s.label}</option>)}
          </select>
        </label>
        <details className="object-more">
          <summary>If it comes in the wrong size or lying down</summary>
          <label className="field"><span>Metres per model unit</span><input value={scale} onChange={(e) => setScale(e.target.value)} /></label>
          <label className="field"><span>Which axis is up</span>
            <select value={up} onChange={(e) => setUp(e.target.value as "y" | "z")}><option value="y">y (glTF)</option><option value="z">z</option></select>
          </label>
        </details>
      </>) : null}

      {making === "video" ? (<>
        {fileField("video/*,.mp4,.mov,.mkv", "Choose a dive video: MP4, MOV or MKV")}
        {file && !fileOk ? <p className="trouble">That does not look like a video.</p> : null}
        <details className="object-more">
          <summary>If you know the camera height or where it starts</summary>
          <label className="field"><span>Camera height over the reef, m</span>
            <input value={height} onChange={(e) => setHeight(e.target.value)} placeholder="1.92 if left empty" />
          </label>
          {!heightOk ? <p className="trouble">Between 0.2 and 20 m.</p> : null}
          <label className="field"><span>Where the video starts</span>
            <input value={start} onChange={(e) => setStart(e.target.value)} placeholder="latitude, longitude" />
          </label>
          {start.trim() && !startAt ? <p className="trouble">Two numbers: latitude, longitude.</p> : null}
        </details>
        <p className="note">About an hour of the platform's GPU for a six-minute swim.</p>
      </>) : null}

      {making === "route" ? (<>
        <div className="object-map">
          <WorldMap view={view} onView={setView} chosen={undefined} acrossM={0} line={route}
                    onChoose={(at) => setRoute((was) => [...was, at])} />
        </div>
        <div className="object-route">
          <span>{route.length === 0 ? "Click where the pipeline starts, then at each bend."
            : `${route.length} point${route.length === 1 ? "" : "s"} · ${lengthOf(route).toFixed(0)} m`}</span>
          <Button kind="ghost" disabled={route.length === 0} onClick={() => setRoute((was) => was.slice(0, -1))}>Undo</Button>
          <Button kind="ghost" disabled={route.length === 0} onClick={() => setRoute([])}>Clear</Button>
        </div>
        <div className="inline-fields">
          <label className="field"><span>Diameter, m</span><input value={diameter} onChange={(e) => setDiameter(e.target.value)} /></label>
          <label className="field"><span>Buried, share of its diameter</span><input value={burial} onChange={(e) => setBurial(e.target.value)} /></label>
        </div>
      </>) : null}

      {making === "survey" ? (<>
        {fileField(".tif,.tiff,.xyz,.csv,.txt", "Choose a survey: GeoTIFF, or soundings as latitude, longitude, depth")}
        {file && !fileOk ? <p className="trouble">That is not a GeoTIFF or a soundings file.</p> : null}
        <div className="inline-fields">
          <label className="field"><span>Vertical datum</span><input value={datum} onChange={(e) => setDatum(e.target.value)} placeholder="MSL, LAT" /></label>
          <label className="field"><span>Error, m</span><input value={errorM} onChange={(e) => setErrorM(e.target.value)} /></label>
        </div>
      </>) : null}

      <label className="field"><span>Name</span>
        <input value={label} onChange={(e) => setLabel(e.target.value)}
               placeholder={file ? file.name.replace(/\.[^.]+$/, "") : making === "route" ? "e.g. Export line A" : "e.g. Al Fahal south transect"} />
      </label>
      {trouble ? <p className="trouble">{trouble}</p> : null}
    </Dialog>
  );
}
