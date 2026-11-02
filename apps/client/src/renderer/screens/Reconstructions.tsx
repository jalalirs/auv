// Reefs rebuilt from dive videos.
//
// Somebody uploads a video of a swim over a reef; the platform finds where
// the camera was in every frame, trains the reef as Gaussian splats, takes the
// survey tape out, and keeps the result as the institution's own asset. A
// reconstruction is in its own frame and on no map: putting it on one is a
// second step, on its own page, because where it goes is a choice (a map of
// its own, or a fit to a place's seabed somebody checks before it is laid).

import { useEffect, useMemo, useRef, useState } from "react";
import type { Asset, Platform, Reconstruction, StructureType } from "@coral-city/api";
import { kindSaid } from "./AssetDetail.js";
import type { Held } from "./Deck.js";
import { Card, Empty, Pill, ago } from "./parts.js";
import { Button, Dialog, Page, SkeletonCards } from "../ui/components.js";
import { PLACES_TABS } from "./placesTabs.js";

const VIDEO = /\.(mp4|mov|mkv)$/i;
const MODEL = /\.(glb|gltf|obj)$/i;
const SURVEY = /\.(tif|tiff|xyz|csv|txt)$/i;

type Making = "video" | "survey" | "model" | "route";
const MAKING: { key: Making; label: string }[] = [
  { key: "video", label: "A reef from a dive video" },
  { key: "survey", label: "A seabed survey file" },
  { key: "model", label: "A structure from a 3D model" },
  { key: "route", label: "A pipeline from its route" },
];
const STRUCTURES: { key: StructureType; label: string }[] = [
  { key: "platform", label: "platform" }, { key: "wind-foundation", label: "wind foundation" },
  { key: "pipeline", label: "pipeline" }, { key: "other", label: "other" },
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

export function Reconstructions({ platform, held, onOpen, onOpenAsset, onBack, onTab }: {
  platform: Platform;
  held: Held;
  onOpen: (id: string) => void;
  /** A structure's or a survey's own page. */
  onOpenAsset?: (id: string) => void;
  onBack: () => void;
  /** To Places' other tabs. */
  onTab?: (tab: string) => void;
}): React.JSX.Element {
  const institution = held.institution;
  const [list, setList] = useState<Reconstruction[] | undefined>();
  const [assets, setAssets] = useState<Asset[]>([]);
  const [making, setMaking] = useState<Making>("video");
  const [datum, setDatum] = useState("MSL");
  const [errorM, setErrorM] = useState("0.3");
  const [structure, setStructure] = useState<StructureType>("platform");
  const [scale, setScale] = useState("1");
  const [up, setUp] = useState<"y" | "z">("y");
  const [route, setRoute] = useState("");
  const [diameter, setDiameter] = useState("0.5");
  const [burial, setBurial] = useState("0.3");
  const [pictures, setPictures] = useState<Record<string, string>>({});
  const [file, setFile] = useState<File | undefined>();
  const [label, setLabel] = useState("");
  const [height, setHeight] = useState("");
  const [start, setStart] = useState("");
  const [sent, setSent] = useState<{ stage: string; done: number } | undefined>();
  const [trouble, setTrouble] = useState("");
  const [adding, setAdding] = useState(false);
  const [showing, setShowing] = useState<"all" | "making" | "failed">("all");

  // Done uploading without a complaint: the dialog has done its job.
  const wasSending = useRef(false);
  useEffect(() => {
    if (wasSending.current && !sent && !trouble) setAdding(false);
    wasSending.current = !!sent;
  }, [sent, trouble]);

  const read = useMemo(() => async () => {
    if (!institution) return;
    try {
      const [reefs, all] = await Promise.all([platform.reconstructionsOf(institution.id), platform.listAssets(institution.id)]);
      setList(reefs);
      setAssets(all.filter((a) => a.kind !== "reef"));
    } catch (problem) {
      setTrouble(problem instanceof Error ? problem.message : "could not read the reconstructions");
    }
  }, [platform, institution]);

  useEffect(() => { void read(); }, [read]);
  // Kept fresh while any is still being made: a reconstruction takes hours,
  // so every half minute is often enough.
  useEffect(() => {
    if (![...(list ?? []), ...assets].some((one) => one.state !== "ready" && one.state !== "failed")) return;
    const again = setInterval(() => void read(), 30_000);
    return () => clearInterval(again);
  }, [list, assets, read]);

  // The picture from above, for each one that has it.
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

  // Reefs rebuilt from video and every other asset, as one list of cards.
  const everything = useMemo(() => [
    ...assets.map((one) => {
      const state = stateOf(one as unknown as Reconstruction);
      return { id: one.id, name: one.name, createdAt: one.createdAt, state,
               picture: one.preview && one.state === "ready" ? one.preview : undefined, reading: false, kind: kindSaid(one),
               detail: `${kindSaid(one)} · ${ago(one.createdAt)}`, specs: [] as string[],
               open: () => onOpenAsset?.(one.id) };
    }),
    ...(list ?? []).map((one) => {
      const state = stateOf(one);
      const m = one.manifest as { extentM?: number[] } | undefined;
      return { id: one.id, name: one.name, createdAt: one.createdAt, state,
               picture: pictures[one.id] || undefined, reading: one.state === "ready" && pictures[one.id] === undefined,
               kind: "a reef from a dive video",
               detail: `a reef from a dive video · ${ago(one.createdAt)}`,
               specs: m?.extentM ? [`${m.extentM[0]!.toFixed(0)} by ${m.extentM[1]!.toFixed(0)} m`] : [],
               open: () => onOpen(one.id) };
    }),
  ].sort((a, b) => (a.createdAt < b.createdAt ? 1 : -1)), [assets, list, pictures, onOpen, onOpenAsset]);
  const which = (one: { state: { kind?: string } }): "all" | "making" | "failed" =>
    one.state.kind === "bad" ? "failed" : one.state.kind === "good" ? "all" : "making";
  const counts = { all: 0, making: 0, failed: 0 };
  for (const one of everything) counts[which(one)]++;
  const shown = everything.filter((one) => which(one) === showing);

  const startAt = useMemo(() => {
    const found = start.match(/^\s*(-?\d+(?:\.\d+)?)\s*[, ]\s*(-?\d+(?:\.\d+)?)\s*$/);
    if (!found) return undefined;
    const lat = Number(found[1]), lon = Number(found[2]);
    return Math.abs(lat) <= 90 && Math.abs(lon) <= 180 ? { lat, lon } : undefined;
  }, [start]);
  const heightM = height.trim() === "" ? undefined : Number(height);
  const heightOk = heightM === undefined || (Number.isFinite(heightM) && heightM > 0.2 && heightM <= 20);
  const ready = !!file && !!institution && !sent && heightOk && (start.trim() === "" || !!startAt);

  // A route typed as one "lat, lon" a line.
  const routePoints = useMemo(() => route.split(/\n+/).map((line) => line.match(/^\s*(-?\d+(?:\.\d+)?)\s*[, ]\s*(-?\d+(?:\.\d+)?)\s*$/))
    .filter((m): m is RegExpMatchArray => !!m).map((m) => [Number(m[1]), Number(m[2])]), [route]);
  const otherReady = !!institution && !sent && (
    making === "survey" ? !!file && SURVEY.test(file.name) && datum.trim() !== "" && Number(errorM) > 0
    : making === "model" ? !!file && MODEL.test(file.name) && Number(scale) > 0
    : making === "route" ? routePoints.length >= 2 && Number(diameter) > 0 && Number(burial) >= 0 && Number(burial) <= 1
    : false);

  const beginOther = async () => {
    if (!institution) return;
    setTrouble("");
    try {
      let object: string | undefined;
      if (file && making !== "route") {
        setSent({ stage: "hashing", done: 0 });
        object = (await platform.upload(institution.id, file, { onProgress: (stage, done) => setSent({ stage, done }) })).id;
      }
      const named = label.trim() ? { label: label.trim() } : {};
      const made = await platform.createAsset(institution.id,
        making === "survey" ? { kind: "bathymetry", object, datum: datum.trim(), errorM: Number(errorM), ...named,
                                file: { name: file!.name, format: /\.tiff?$/i.test(file!.name) ? "geotiff" : "xyz" } }
        : making === "model" ? { kind: "structure", type: structure, meets: "stands", object, ...named,
                                 model: { name: file!.name, format: file!.name.split(".").pop()!.toLowerCase() as "glb" | "gltf" | "obj", scale: Number(scale), up } }
        : { kind: "structure", type: "pipeline", meets: "drapes", ...named,
            route: { points: routePoints, diameterM: Number(diameter), burial: Number(burial) } });
      setFile(undefined); setLabel(""); setRoute("");
      setAssets((was) => [made, ...was]);
      onOpenAsset?.(made.id);
    } catch (problem) {
      setTrouble(problem instanceof Error ? problem.message : "the asset could not be started");
    } finally {
      setSent(undefined);
    }
  };

  const begin = async () => {
    if (!file || !institution) return;
    setTrouble("");
    setSent({ stage: "hashing", done: 0 });
    try {
      const stored = await platform.upload(institution.id, file, {
        onProgress: (stage, done) => setSent({ stage, done }),
      });
      const made = await platform.startReconstruction(institution.id, {
        video: { objectId: stored.id, name: file.name },
        ...(label.trim() ? { label: label.trim() } : {}),
        ...(heightM !== undefined ? { cameraHeightM: heightM } : {}),
        ...(startAt ? { start: startAt } : {}),
      });
      setFile(undefined);
      setLabel("");
      setHeight("");
      setStart("");
      setList((was) => [made, ...(was ?? [])]);
      onOpen(made.id);
    } catch (problem) {
      setTrouble(problem instanceof Error ? problem.message : "the reconstruction could not be started");
    } finally {
      setSent(undefined);
    }
  };

  return (
    <Page title="Places" subtitle="Assets: reefs and structures made on their own, ready to compose into a place."
          info="Upload a swim over a reef and the platform rebuilds the reef in 3D: where the camera was in every frame, the reef as splats, the survey tape painted out. It is your institution's, in its own frame; putting it on a map is the next step, on its page."
          tabs={PLACES_TABS} tab="assets" onTab={(key) => onTab?.(key)}
          actions={institution ? <Button kind="primary" onClick={() => setAdding(true)}>New asset</Button> : undefined}>
      <div className="asset-tools">
        <div className="segmented" role="tablist">
          {(["all", "making", "failed"] as const).map((key) => (
            <button key={key} type="button" role="tab" aria-selected={showing === key} onClick={() => setShowing(key)}>
              {key === "all" ? "Ready" : key === "making" ? "Being made" : "Failed"}
              <small>{counts[key]}</small>
            </button>
          ))}
        </div>
      </div>
      {list === undefined ? <SkeletonCards /> : shown.length === 0 ? (
        showing === "all"
          ? <Empty title="No assets yet">Make one with New asset: a reef from a dive video, a survey, a model or a pipeline route.</Empty>
          : <Empty title={showing === "making" ? "Nothing being made" : "Nothing failed"}>{showing === "making" ? "Every asset has finished." : "Every asset that was started was made."}</Empty>
      ) : (
        <div className="cards">
          {shown.map((one) => (
            <Card key={one.id} name={one.name} detail={one.detail} picture={one.picture}
                  reading={one.reading}
                  art={one.picture === undefined
                    ? <span className="asset-state">{one.state.kind === "good" ? one.kind : one.state.doing ?? one.state.said}</span> : undefined}
                  specs={one.specs} corner={<Pill kind={one.state.kind}>{one.state.said}</Pill>}
                  onOpen={one.open} actions={<Button onClick={one.open}>Open</Button>} />
          ))}
        </div>
      )}
      {adding ? (
        <Dialog title="New asset" onClose={() => { if (!sent) setAdding(false); }}>
          <div className="new-asset">
          <label className="asset-making">Made from
            <select value={making} onChange={(e) => { setMaking(e.target.value as Making); setFile(undefined); setTrouble(""); }}>
              {MAKING.map((m) => <option key={m.key} value={m.key}>{m.label}</option>)}
            </select>
          </label>
          {!institution ? <p className="note">You belong to no institution, and an asset is made for one.</p> : making !== "video" ? (
            <div className="builder-side">
              {making !== "route" ? (
                <label className="builder-add">
                  <input type="file" accept={making === "survey" ? ".tif,.tiff,.xyz,.csv,.txt" : ".glb,.gltf,.obj"}
                         onChange={(e) => { const f = e.target.files?.[0]; if (f) setFile(f); e.target.value = ""; }} />
                  <span>{file ? `${file.name} · ${megabytes(file.size)}` : making === "survey"
                    ? "Choose a survey (GeoTIFF, or soundings as latitude, longitude, depth)" : "Choose a model (GLB, glTF or OBJ)"}</span>
                </label>
              ) : null}
              <label>Name
                <input value={label} onChange={(e) => setLabel(e.target.value)} placeholder={file ? file.name.replace(/\.[^.]+$/, "") : "e.g. Export line A"} />
              </label>
              {making === "survey" ? (<>
                <label>Vertical datum<input value={datum} onChange={(e) => setDatum(e.target.value)} placeholder="MSL, LAT, ..." /></label>
                <label>Error, metres<input value={errorM} onChange={(e) => setErrorM(e.target.value)} /></label>
              </>) : null}
              {making === "model" ? (<>
                <label>What it is
                  <select value={structure} onChange={(e) => setStructure(e.target.value as StructureType)}>
                    {STRUCTURES.filter((s) => s.key !== "pipeline").map((s) => <option key={s.key} value={s.key}>{s.label}</option>)}
                  </select>
                </label>
                <label>Scale to metres<input value={scale} onChange={(e) => setScale(e.target.value)} /></label>
                <label>Up axis
                  <select value={up} onChange={(e) => setUp(e.target.value as "y" | "z")}><option value="y">y (glTF)</option><option value="z">z</option></select>
                </label>
                <p className="note">It stands on the seabed. Where it goes is chosen when it is put in a place.</p>
              </>) : null}
              {making === "route" ? (<>
                <label>Route, one &ldquo;latitude, longitude&rdquo; a line
                  <textarea rows={5} value={route} onChange={(e) => setRoute(e.target.value)} placeholder={"22.3001, 38.9502\n22.3010, 38.9530"} />
                </label>
                <p className="note">{routePoints.length} points read.</p>
                <label>Diameter, metres<input value={diameter} onChange={(e) => setDiameter(e.target.value)} /></label>
                <label>Buried, share of its diameter (0 to 1)<input value={burial} onChange={(e) => setBurial(e.target.value)} /></label>
              </>) : null}
              {trouble ? <p className="trouble">{trouble}</p> : null}
              <button className="big" disabled={!otherReady} onClick={() => void beginOther()}>
                {sent ? `${sent.stage} ${file ? Math.round(100 * sent.done / Math.max(file.size, 1)) : 0}%` : making === "route" ? "Make it" : "Upload and make it"}
              </button>
            </div>
          ) : (
            <div className="builder-side">
              <label className="builder-add">
                <input type="file" accept="video/*,.mp4,.mov,.mkv"
                       onChange={(e) => { const f = e.target.files?.[0]; if (f) setFile(f); e.target.value = ""; }} />
                <span>{file ? `${file.name} · ${megabytes(file.size)}` : "Choose a dive video (MP4, MOV or MKV)"}</span>
              </label>
              {file && !VIDEO.test(file.name) && !file.type.startsWith("video/")
                ? <p className="trouble">That does not look like a video.</p> : null}
              <label>Name
                <input value={label} onChange={(e) => setLabel(e.target.value)} placeholder={file ? file.name.replace(/\.[^.]+$/, "") : "e.g. Al Fahal south transect"} />
              </label>
              <label>Camera height over the reef, metres
                <input value={height} onChange={(e) => setHeight(e.target.value)} placeholder="if you know it; 1.92 is assumed" />
              </label>
              {!heightOk ? <p className="trouble">Between 0.2 and 20 m.</p> : null}
              <p className="note">The height gives the reef its scale. Without it the reef is as big as a camera 1.92 m up would make it, and its page says so.</p>
              <label>Where the video starts
                <input value={start} onChange={(e) => setStart(e.target.value)} placeholder="latitude, longitude, if you know it" />
              </label>
              {start.trim() && !startAt ? <p className="trouble">Two numbers: latitude, longitude.</p> : null}
              {trouble ? <p className="trouble">{trouble}</p> : null}
              <button className="big" disabled={!ready} onClick={() => void begin()}>
                {sent ? `${sent.stage} ${file ? Math.round(100 * sent.done / Math.max(file.size, 1)) : 0}%` : "Upload and rebuild"}
              </button>
              <p className="note">A six-minute swim takes the platform's GPU about an hour. The video goes up in 32 MB parts and resumes if the connection drops.</p>
            </div>
          )}
          </div>
        </Dialog>
      ) : null}
    </Page>
  );
}
