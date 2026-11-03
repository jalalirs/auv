// The screens that plan and fly work, against a pretend platform.
//
// A development harness: the real Missions, Designer and Fly components,
// mounted over an in-memory platform that holds two real places (copied in by
// tools/client-harness-fixtures) and two missions drawn on them. It exists so
// the screens can be seen and clicked without signing in to anybody's
// platform. Not built into the application: only index.html is.
//
//   npm run dev  →  http://localhost:5173/harness.html?page=missions

import { StrictMode, useState } from "react";
import { createRoot } from "react-dom/client";

import "../styles.css";
import type { Held, Packages } from "../screens/Deck.js";
import { Designer } from "../screens/Designer.js";
import { Fly } from "../screens/Fly.js";
import { Dive } from "../screens/Dive.js";
import { Missions } from "../screens/Missions.js";
import { Runs } from "../screens/Runs.js";
import { PlaceDesigner } from "../screens/PlaceDesigner.js";
import { Compose } from "../screens/Compose.js";
import { ManyRun } from "../screens/Run.js";
import { Replay } from "../screens/Replay.js";
import { Reconstructions } from "../screens/Reconstructions.js";
import { ReconstructionPage } from "../screens/Reconstruction.js";
import { Places } from "../screens/Places.js";
import { Store } from "../screens/Store.js";
import { Fleet } from "../screens/Fleet.js";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const ASSETS: any[] = [
    { id: "recon_s1", orgId: "org_1", jobId: "job_s1", name: "Al Fahal multibeam 2025", kind: "bathymetry", madeFrom: "survey", state: "ready", jobState: "succeeded",
      footprint: { bbox: [22.28, 38.95, 22.29, 38.97] }, stats: { shallowestM: 1.2, deepestM: 31.5, cellM: [0.5, 0.5], datum: "LAT", errorM: 0.15 },
      brief: {}, steps: [], createdBy: "p", createdAt: new Date(Date.now() - 3_600_000).toISOString() },
    { id: "recon_p1", orgId: "org_1", jobId: "job_p1", name: "Export line A", kind: "structure", type: "pipeline", meets: "drapes", madeFrom: "route", state: "ready", jobState: "succeeded",
      footprint: { bbox: [22.281, 38.951, 22.284, 38.958] }, stats: { lengthM: 742.3, diameterM: 0.5 }, brief: {}, steps: [], createdBy: "p", createdAt: new Date(Date.now() - 7_200_000).toISOString() },
    { id: "recon_m1", orgId: "org_1", jobId: "job_m1", name: "Monopile WTG-04", kind: "structure", type: "wind-foundation", meets: "stands", madeFrom: "model", state: "running", jobState: "running",
      brief: {}, steps: [{ at: "", step: "usd", say: "writing the model as USD" }], createdBy: "p", createdAt: new Date().toISOString() },
    { id: "recon_v1", orgId: "org_1", jobId: "job_v1", name: "SubPipe outfall pipeline, run 3 (Oceanscan-MST, CC BY 4.0)", kind: "structure", type: "pipeline", meets: "drapes", madeFrom: "video", state: "ready", jobState: "succeeded",
      brief: {}, steps: [], createdBy: "p", createdAt: new Date(Date.now() - 9_000_000).toISOString() },
    { id: "recon_j1", orgId: "org_1", jobId: "job_j1", name: "Jacket platform", kind: "structure", type: "platform", meets: "stands", madeFrom: "model", state: "ready", jobState: "succeeded",
      footprint: { sizeM: [14, 14, 15] }, stats: { sizeM: [14, 14, 15], triangles: 60 }, brief: {}, steps: [], createdBy: "p", createdAt: new Date(Date.now() - 12_000_000).toISOString() },
    { id: "recon_f1", orgId: "org_1", jobId: "job_f1", name: "Test export line", kind: "structure", type: "pipeline", meets: "drapes", madeFrom: "route", state: "failed", jobState: "failed",
      failure: "the route leaves the place's seabed", brief: {}, steps: [], createdBy: "p", createdAt: new Date(Date.now() - 20_000_000).toISOString() },
  ];
import { Autonomy } from "../screens/Autonomy.js";
import { ControllerDetail } from "../screens/ControllerDetail.js";
import { AssetDetail } from "../screens/AssetDetail.js";

const now = () => new Date().toISOString();
let counter = 0;
const id = (kind: string) => `${kind}_${(++counter).toString().padStart(4, "0")}`;

type Doc = Record<string, unknown>;
interface Version { id: string; ordinal: number; createdAt: string; document: Doc; label?: string }

const places = [
  { id: "city_tank", slug: "iocean-tank-1", name: "iocean tank", fixture: "iocean-tank-1" },
  { id: "city_looe", slug: "looe-key", name: "Looe Key", fixture: "looe-key" },
  { id: "city_fahal", slug: "al-fahal", name: "Al Fahal", fixture: "al-fahal" },
];

const layoutThings: Record<string, Doc[]> = {
  city_tank: [
    { id: "buoy-dock", kind: "buoy", x: -0.8, y: 0.3, z: 0, groundM: 0.85 },
    { id: "nursery-frame-1", kind: "nursery-frame", x: 0.45, y: -0.25, z: -0.8, groundM: 0.8 },
  ],
  city_looe: [
    { id: "ship-1", kind: "ship", x: 140, y: -60, z: 0, groundM: 4 },
    { id: "cell-b7", kind: "restoration-cell", x: 0, y: 0,
      corners: [{ x: -20, y: 40 }, { x: 40, y: 40 }, { x: 40, y: 80 }, { x: -20, y: 80 }] },
    { id: "frame-3", kind: "nursery-frame", x: 90, y: 30, z: -6, groundM: 6 },
  ],
};

const store = {
  missions: new Map<string, { mission: Doc; place: string; versions: Version[] }>(),
  layouts: new Map<string, { layout: Doc; place: string; versions: Version[] }>(),
};
for (const place of places) {
  const layoutId = id("layout");
  store.layouts.set(layoutId, {
    layout: { id: layoutId, slug: "as-laid", name: `${place.name}, as laid`, summary: "" }, place: place.id,
    versions: [{ id: id("version"), ordinal: 1, createdAt: now(), document: { things: layoutThings[place.id] } }],
  });
}
function addMission(place: string, name: string, stages: Doc[], launch?: Doc) {
  const missionId = id("mission");
  const layout = [...store.layouts.values()].find((l) => l.place === place)!;
  store.missions.set(missionId, {
    mission: { id: missionId, slug: name.toLowerCase().replace(/[^a-z0-9]+/g, "-"), name, summary: "", cityId: place },
    place,
    versions: [{ id: id("version"), ordinal: 1, createdAt: now(), document: {
      cityVersionId: `${place}-v1`, layoutVersionId: layout.versions[0]!.id,
      ...(launch ? { launch } : {}), stages } }],
  });
}
addMission("city_tank", "Round the tank", [
  { kind: "waypoints", radiusM: 0.08, depthM: 0.34, timeLimitS: 150,
    points: [{ x: 0.55, y: 0.15, depthM: 0.34 }, { x: -0.55, y: 0.15, depthM: 0.34 }, { x: -0.55, y: -0.15, depthM: 0.34 }, { x: 0.3, y: -0.15, depthM: 0.34 }] },
  { kind: "inspect", over: "nursery-frame-1", radiusM: 0.2, timeLimitS: 120 },
  { kind: "return", timeLimitS: 120 },
]);
addMission("city_looe", "The September plot round", [
  { kind: "waypoints", radiusM: 2, timeLimitS: 900, points: [{ x: 120, y: -40 }, { x: 60, y: 20 }] },
  { kind: "transect", altitudeM: 2, from: { x: 120, y: -40 }, to: { x: 60, y: 20 }, timeLimitS: 600 },
  { kind: "survey", over: "cell-b7", altitudeM: 2, swathM: 4, timeLimitS: 1500 },
  { kind: "inspect", over: "frame-3", radiusM: 6, timeLimitS: 600 },
  { kind: "return", timeLimitS: 900 },
], { from: "ship-1" });

const hoursAgo = (h: number) => new Date(Date.now() - h * 3600_000).toISOString();
const runOf = (id: string, name: string, h: number, extra: Doc = {}, vehicle = "veh_mini", place = "city_tank") => ({
  dive: `dive_${id}`, name, flownBy: "Harness", vehicleVersion: `${vehicle}-v1`, placeVersion: `${place}-v1`,
  run: { id, state: "succeeded", mode: "batch", requestedAt: hoursAgo(h), physicsVersion: 3,
         outcome: { task: { name: "Waypoints", score: 0.92, done: true, energyWh: 0.709, seconds: 59.7,
           ride: { effort: { meanShare: 0.21, peakShare: 0.87, flatOutShare: 0.02 },
                   rollDeg: { typical: 1.1, worst: 4.2 }, pitchDeg: { typical: 2.3, worst: 9.6 },
                   offLine: { thresholdM: 1, secondsOnTheLine: 48, secondsOff: 3.5, worstM: 1.4, meanM: 0.3 } } } },
         ...extra },
});
// ?slow=3000 holds every answer that long, to look at what a page shows while it waits.
const SLOW = Number(new URLSearchParams(location.search).get("slow") ?? 30);
const delay = <T,>(v: T) => new Promise<T>((r) => setTimeout(() => r(v), SLOW));
const said: string[] = [];

const platform = {
  missionsOf: (city: string) => delay([...store.missions.values()].filter((m) => m.place === city).map((m) => m.mission)),
  mission: (missionId: string) => delay(store.missions.get(missionId)!.mission),
  versionsOfMission: (missionId: string) => delay([...(store.missions.get(missionId)?.versions ?? [])].reverse()),
  startMission: (city: string, asked: Doc) => {
    const missionId = id("mission");
    store.missions.set(missionId, { mission: { id: missionId, ...asked, summary: "", cityId: city }, place: city, versions: [] });
    return delay(store.missions.get(missionId)!.mission);
  },
  saveLayout: (layoutId: string, document: Doc, label = "") => {
    const one = store.layouts.get(layoutId)!;
    const version = { id: id("version"), ordinal: one.versions.length + 1, createdAt: now(), document, label };
    one.versions.push(version);
    said.push(`saved layout ${layoutId} v${version.ordinal}: ${JSON.stringify(document)}`);
    return delay(version);
  },
  saveMission: (missionId: string, document: Doc, label = "") => {
    const one = store.missions.get(missionId)!;
    const version = { id: id("version"), ordinal: one.versions.length + 1, createdAt: now(), document, label };
    one.versions.push(version);
    said.push(`saved ${missionId} v${version.ordinal}`);
    return delay(version);
  },
  archiveMission: (missionId: string) => { const m = store.missions.get(missionId)!; store.missions.delete(missionId); said.push(`archived ${missionId}`); return delay(m.mission); },
  missionCost: () => delay({ runs: 0, survived: 0, notEnough: true }),
  versionsOfPlace: (city: string) => delay([{ id: `${city}-v1`, ordinal: 1, createdAt: now(), publishedAt: now() }]),
  layoutsOf: (city: string) => delay([...store.layouts.values()].filter((l) => l.place === city).map((l) => l.layout)),
  versionsOfLayout: (layoutId: string) => delay([...(store.layouts.get(layoutId)?.versions ?? [])].reverse()),
  versionsOfVehicle: (vehicle: string) => delay([{ id: `${vehicle}-v1`, ordinal: 1, createdAt: now(), publishedAt: now() }]),
  defineConditions: (_org: string, c: Doc) => { said.push(`conditions ${JSON.stringify(c)}`); return delay({ id: id("cond") }); },
  defineDive: (_org: string, d: Doc) => { said.push(`dive ${JSON.stringify(d)}`); return delay({ id: id("dive") }); },
  ask: (dive: string, r: Doc) => { said.push(`run of ${dive} ${JSON.stringify(r)}`); return delay({ id: id("run") }); },
  sweepsOf: () => delay([{ id: "sweep_a", name: "Round the tank ~ October 4", createdAt: hoursAgo(2), runs: 6, flown: 4, flying: 2 }]),
  cancel: () => delay(undefined),
  startSweep: (_org: string, s: Doc) => { said.push(`sweep ${JSON.stringify(s)}`); return delay({ id: id("sweep") }); },
  sweep: () => delay({ id: "sweep_a", name: "Best launch: pipeline landfall", createdAt: hoursAgo(2), runs: 6, flown: 6, flying: 0,
                       repeats: 1, good: 0.8, doubts: {} }),
  findings: () => delay({
    scenarios: 6, flown: 6, flownRuns: 6, flying: 0, survived: 5, marginal: 0, repeats: 1, good: 0.8,
    matters: [{ name: "where it goes in", changes: 0.5, rates: [
      { value: "as planned", survived: 2, of: 2, failedShare: 0 },
      { value: "20 m north", survived: 1, of: 2, failedShare: 0.5 },
      { value: "20 m east", survived: 2, of: 2, failedShare: 0 }] }],
    madeNoDifference: ["which way it faces"], physics: [3],
    turnsOn: "where it goes in", at: "20 m north", failsOf: [1, 2], noRescue: true,
    cost: { runs: 6, survived: 5, energyWh: 6.1, hours: 0.21, diveEnergyWh: 9.8, diveHours: 0.36, workingShare: 0.62,
            worstEnergyWh: 11.9, worstHours: 0.44, capacityWh: 120, reserveFraction: 0.2, usableWh: 96,
            perCharge: 9.8, workingDayHours: 8, perDay: 22.2, heldBackBy: "the battery" },
    cheapest: [
      { dimension: "where it goes in", best: "20 m east", bestWh: 31.4, savesWh: 6.2, settings: [
        { value: "as planned", meanWh: 35.9, survived: 2, of: 2 },
        { value: "20 m north", meanWh: 37.6, survived: 1, of: 2 },
        { value: "20 m east", meanWh: 31.4, survived: 2, of: 2 }] },
      { dimension: "which way it faces", best: "east", bestWh: 33.0, savesWh: 1.9, settings: [
        { value: "east", meanWh: 33.0, survived: 3, of: 3 },
        { value: "west", meanWh: 34.9, survived: 2, of: 3 }] }],
    cheapestScenario: { label: "where it goes in:20 m east · which way it faces:west", meanWh: 8.3, survived: 1, of: 1,
                        savesWh: 10.2, candidates: 3, chosen: {} },
    scenariosFlown: [
      ["as planned", "east", 0.94, 1], ["as planned", "west", 0.91, 1], ["20 m north", "east", 0.86, 1],
      ["20 m north", "west", 0.41, 0], ["20 m east", "east", 0.97, 1], ["20 m east", "west", 0.95, 1],
    ].map(([inAt, faces, score, ok]) => ({
      label: `where it goes in:${inAt} · which way it faces:${faces}`,
      chosen: { "where it goes in": inAt, "which way it faces": faces },
      runs: 1, survivedRuns: ok, survived: ok === 1, marginal: false, score, worst: score, best: score })),
    runs: [] }),
  // A recording of a minute: a lap of the tank, as data so nothing is fetched.
  artefacts: () => {
    const poses = Array.from({ length: 300 }, (_, i) => {
      const t = i / 5, a = t / 60 * Math.PI * 2;
      return JSON.stringify({ t, position: [0.6 * Math.cos(a), 0.3 * Math.sin(a), -0.5], headingDeg: (a * 180 / Math.PI + 90) % 360,
                              depthM: 0.5 + 0.05 * Math.sin(a * 3), altitudeM: 0.45, velocity: [0.06, 0.03, 0] });
    }).join("\n");
    const task = Array.from({ length: 60 }, (_, t) => JSON.stringify({ t, name: "Waypoints", kind: "waypoints", score: Math.min(0.92, t / 55), done: t >= 55 })).join("\n");
    const manifest = { poses: 300, frames: 0, seconds: 59.7, beganAt: [0.6, 0, -0.5], task: { name: "Waypoints", kind: "waypoints", score: 0.92, done: true } };
    const data = (type: string, body: string) => `data:${type},${encodeURIComponent(body)}`;
    return delay([
      { path: "manifest.json", url: data("application/json", JSON.stringify(manifest)), sizeBytes: 300 },
      { path: "poses.jsonl", url: data("text/plain", poses), sizeBytes: poses.length },
      { path: "task.jsonl", url: data("text/plain", task), sizeBytes: task.length },
    ]);
  },
};
// A build that walks through what a real one said, a step every second.
const builtSteps = [
  { step: "plan", say: "4 sources, 0 models" },
  { step: "left-out", say: "icesat2: this platform has no NASA Earthdata token, so the laser's depths were not fetched" },
  { step: "source", say: "reading sentinel2-stumpf", n: 1, of: 4 },
  { step: "source", say: "reading sentinel2-median", n: 2, of: 4 },
  { step: "source", say: "reading allen-coral-atlas", n: 3, of: 4 },
  { step: "source", say: "reading gebco", n: 4, of: 4 },
  { step: "fuse", say: "fusing 2 depth layers, cell by cell" },
  { step: "scene", say: "writing the seabed" },
  { step: "package", say: "packing the place" },
  { step: "done", say: "built" },
];
let buildStarted = 0;
const buildView = () => {
  const shown = Math.min(builtSteps.length, Math.floor((Date.now() - buildStarted) / 1000));
  const done = shown >= builtSteps.length;
  return { id: "bld_1", cityId: "city_new", orgId: "org_1", jobId: "job_1", brief: {}, createdBy: "p1",
    createdAt: now(), state: done ? "ready" : shown === 0 ? "queued" : "running", jobState: done ? "succeeded" : "running",
    steps: builtSteps.slice(0, shown).map((s) => ({ at: now(), ...s })),
    ...(done ? { versionId: "ver_new", result: { deepestM: 60, depth: {
      sources: [{ source: "sentinel2-stumpf", kind: "derived", share: 1 }],
      weak: { errorM: { median: 10, p90: 10, worst: 10 } } } } } : {}) };
};
Object.assign(platform, {
  buildSources: () => delay({ sources: {
    gebco: "the global depth grid (GEBCO): everywhere, coarse",
    sentinel2: "satellite imagery (Sentinel-2): depth estimated from colour in clear shallow water",
    icesat2: "the laser altimeter's depths (ICESat-2): measured, along tracks",
    "allen-coral-atlas": "the Allen Coral Atlas: where reef, sand and seagrass are",
    "learned-depth": "the learned depth model: depth from imagery, corrected by the laser's depths" },
    fileUses: { raster: "a depth map (GeoTIFF or any grid GDAL reads)", points: "soundings (XYZ or CSV)",
                ortho: "a photo mosaic (orthomosaic GeoTIFF)" } }),
  upload: async (_org: string, file: File, o: { onProgress?: (s: string, d: number, n: number) => void }) => {
    for (const stage of ["hashing", "sending"]) for (let k = 1; k <= 4; k++) {
      await delay(0); o.onProgress?.(stage, file.size * k / 4, file.size);
    }
    said.push(`uploaded ${file.name}`);
    return { id: id("obj") };
  },
  foundPlace: (org: string, body: Doc) => { said.push(`founded for ${org}: ${JSON.stringify(body)}`); return delay({ id: "city_new", ...body }); },
  startBuild: (city: string, brief: Doc) => { said.push(`build ${city}: ${JSON.stringify(brief)}`); buildStarted = Date.now(); return delay(buildView()); },
  build: () => delay(buildView()),
  // A built ground reads as Al Fahal's: its site record and its seabed.
  files: () => delay([{ path: "weak.png", url: "./harness/fixtures/built/weak.png" },
    { path: "site.json", url: "./harness/fixtures/al-fahal/site.json" },
    { path: "seabed.f32", url: "./harness/fixtures/al-fahal/seabed.f32" }]),
  publishVersion: (v: string) => { said.push(`published ${v}`); return delay({ id: v }); },
  retirePlace: (city: string) => { said.push(`retired ${city}`); return delay({ id: city, retiredAt: new Date().toISOString(), retiredBy: "p1" }); },
  unretirePlace: (city: string) => { said.push(`unretired ${city}`); return delay({ id: city }); },
});
// A reconstruction that walks through its steps, then a mapping of it.
const reconSteps = [
  { step: "frames", say: "756 frames at 1600x900", frames: 756 },
  { step: "cameras", say: "756 of 756 frames placed" },
  { step: "tape", say: "a tape in 610 of 756 frames; finding it in 3D" },
  { step: "pieces", say: "training piece-2 (frames 223 to 534)", n: 2, of: 3 },
];
// The real asset the job made of the Red Sea video (fixtures/recon, from the box).
let reconManifest: Doc = {};
void fetch("./harness/fixtures/recon/reconstruction.json").then((r) => r.json()).then((m) => { reconManifest = m; });
const recon = (ready: boolean) => ({ id: "recon_1", orgId: "org_1", jobId: "job_r", name: "Red Sea transect",
  brief: { video: { objectId: "obj_v", name: "GX_SINGLE_VIDEO.MP4" } },
  createdBy: "p1", createdAt: now(), state: ready ? "ready" : "running", jobState: ready ? "succeeded" : "running",
  steps: reconSteps.map((s) => ({ at: now(), ...s })), ...(ready ? { manifest: reconManifest } : {}) });
// A real Resolve of that asset onto Al Fahal, the whole place searched (no
// start is known for the video).
let candidates: Doc[] = [];
void fetch("./harness/fixtures/recon/candidates.json").then((r) => r.json()).then((d) => { candidates = d.candidates; });
let mapping: Doc | undefined;
let mappingAt = 0;
const mappingView = () => {
  if (!mapping) return mapping;
  if (mapping.state === "laying" && Date.now() - mappingAt > 4000) {
    mapping = { ...mapping, state: "ready", versionId: "ver_laid",
                steps: [...(mapping.steps as Doc[]), { at: now(), step: "done", say: "red-sea-transect laid into the place" }] };
  }
  return mapping;
};
Object.assign(platform, {
  reconstructionsOf: () => delay([recon(true), { ...recon(false), id: "recon_2", name: "North wall swim" }]),
  listAssets: () => delay(ASSETS),
  getAsset: (id: string) => delay(ASSETS.find((a) => a.id === id) ?? ASSETS[0]!),
  storeObjects: () => delay([{ ...ASSETS.find((a) => a.id === "recon_v1"), id: "store_obj_1" }]),
  copyStoreObject: (_org: string, from: string) => { said.push(`copied object ${from}`); return delay({ ...ASSETS[0], id: id("recon") }); },
  copyStorePlace: (_org: string, city: string) => { said.push(`copied place ${city}`); return delay({ id: id("city"), name: "copy" }); },
  archiveAsset: (id: string) => {
    const at = ASSETS.findIndex((a) => a.id === id);
    const gone = at >= 0 ? ASSETS.splice(at, 1)[0] : undefined;
    said.push(`archived ${id}`);
    return delay(gone);
  },
  createAsset: (_org: string, brief: { label?: string; kind: string; type?: string; meets?: string }) => delay({
    id: "recon_new", orgId: "org_1", jobId: "job_new", name: brief.label ?? "new asset", kind: brief.kind, type: brief.type, meets: brief.meets,
    madeFrom: brief.kind === "bathymetry" ? "survey" : brief.type === "pipeline" ? "route" : "model", state: "queued", jobState: "queued",
    brief: {}, steps: [], createdBy: "p", createdAt: new Date().toISOString() }),
  reconstruction: (rid: string) => delay(rid === "recon_2" ? { ...recon(false), id: "recon_2", name: "North wall swim" } : recon(true)),
  reconstructionObjects: () => delay([
    { path: "preview.jpg", url: "./harness/fixtures/recon/preview.jpg" },
    ...[1, 2, 3, 4, 5, 6].map((k) => ({ path: `previews/frame-${k}.jpg`, url: `./harness/fixtures/recon/frame-${k}.jpg` }))]),
  startReconstruction: (org: string, brief: Doc) => { said.push(`reconstruct for ${org}: ${JSON.stringify(brief)}`); return delay(recon(false)); },
  mappingsOf: () => delay(mapping ? [mappingView()] : []),
  mapping: () => delay(mappingView()),
  startMapping: (rid: string, body: Doc) => {
    said.push(`map ${rid}: ${JSON.stringify(body)}`);
    mapping = body.mode === "onto"
      ? { id: "map_1", reconstructionId: rid, cityId: body.cityId, mode: "onto", state: "choosing", candidates,
          start: null, steps: [{ at: now(), step: "done", say: "5 places it fits; the best 0.41 m rms at (998, -1457), -11.5 m deep", phase: "resolve" }] }
      : { id: "map_1", reconstructionId: rid, cityId: "city_new", mode: "own", state: "laying",
          steps: [{ at: now(), step: "plan", say: "a flat seabed at 8 m", phase: "base" }] };
    mappingAt = Date.now();
    return delay(mapping);
  },
  startPlaceMapping: (city: string, body: Doc) => {
    said.push(`lay into ${city}: ${JSON.stringify(body)}`);
    mapping = { id: "map_2", cityId: city, mode: "onto", state: "laying",
                steps: [{ at: now(), step: "bake", say: "laying the objects into the place", phase: "lay" }] };
    mappingAt = Date.now();
    return delay(mapping);
  },
  acceptMapping: (mid: string, body: Doc) => {
    said.push(`accept ${mid}: ${JSON.stringify(body)}`);
    mapping = { ...mapping, state: "laying", steps: [{ at: now(), step: "bake", say: "part 1 into the place's frame", n: 1, of: 3, phase: "lay" }] };
    mappingAt = Date.now();
    return delay(mapping);
  },
});
// The map store: Al Fahal and Looe Key as iOcean publishes them.
const storeList = [
  { id: "city_fahal", slug: "al-fahal", name: "Al Fahal", summary: "A fringing reef off Thuwal, three kilometres square.",
    extent: { west: 38.9475, south: 22.2705, east: 38.9765, north: 22.2975 }, versionId: "ver_fahal", deepestM: 38,
    surveyed: false, surveyedFraction: 0.04, colonies: 1039632, picture: true, adopted: false },
  { id: "city_looe", slug: "looe-key", name: "Looe Key", summary: "A spur-and-groove reef in the Florida Keys.",
    extent: { west: -81.42, south: 24.54, east: -81.40, north: 24.556 }, versionId: "ver_looe", deepestM: 34,
    surveyed: true, surveyedFraction: 0.92, colonies: 83055, picture: false, adopted: true },
];
Object.assign(platform, {
  storePlaces: (near?: { lat: number; lon: number }) => delay(near
    ? storeList.filter((s) => near.lat > s.extent.south - 0.02 && near.lat < s.extent.north + 0.02 && near.lon > s.extent.west - 0.02 && near.lon < s.extent.east + 0.02)
    : storeList),
  adoptStorePlace: (org: string, city: string) => { said.push(`adopt ${city} for ${org}`); storeList.forEach((s) => { if (s.id === city) s.adopted = true; }); return delay({}); },
  unadoptStorePlace: (org: string, city: string) => { said.push(`unadopt ${city} for ${org}`); storeList.forEach((s) => { if (s.id === city) s.adopted = false; }); return delay({}); },
});
// Controller builds that walk through a real build's steps.
const buildSteps = [
  { step: "source", say: "cloning https://github.com/jalalirs/iocean-controllers" },
  { step: "source", say: "at commit c3f8af443781" },
  { step: "find", say: "4 controllers: station-hold, go-around-things, learned-hold, sawtooth" },
  { step: "check", say: "station-hold: the tank: 20 s, 0.00 m from where it began" },
  { step: "check", say: "go-around-things: the tank: 20 s, 5.04 m from where it began" },
  { step: "check", say: "learned-hold: the tank: 20 s, 0.17 m from where it began" },
  { step: "check", say: "sawtooth: the tank: 20 s, 0.20 m from where it began" },
];
const foundIn = [
  { slug: "station-hold", name: "Station hold", entry: "controllers/station-hold/controller.py:StationHold" },
  { slug: "go-around-things", name: "Go around things", entry: "controllers/go-around-things/controller.py:GoAroundThings" },
  { slug: "learned-hold", name: "Learned hold", entry: "controllers/learned-hold/controller.py:LinearHold" },
  { slug: "sawtooth", name: "Sawtooth (glider)", entry: "controllers/sawtooth/controller.py:Sawtooth" },
];
const controllerBuilds: Doc[] = [];
const viewOf = (b: Doc) => {
  const shown = Math.min(buildSteps.length, Math.floor((Date.now() - (b.started as number)) / 1500));
  const done = shown >= buildSteps.length;
  return { ...b, state: done ? "ready" : shown === 0 ? "queued" : "running", jobState: done ? "succeeded" : "running",
           steps: buildSteps.slice(0, shown).map((s) => ({ at: now(), ...s })),
           ...(done ? { report: { ok: true, source: { kind: "git", commit: "c3f8af4437815c5d" },
             controllers: foundIn.map((c) => ({ ok: true, slug: c.slug, name: c.name, controller: c.entry,
               vehicle: c.slug === "sawtooth" ? "Seaglider" : "BlueROV2", checks: { vehicle: { ok: true, problems: [] },
               tank: { ok: true, said: "20 s in the tank, held" } } })) } } : {}) };
};
Object.assign(platform, {
  startControllerBuild: (org: string, brief: Doc) => {
    said.push(`controller build for ${org}: ${JSON.stringify(brief)}`);
    const b = { id: id("ctlb"), orgId: org, jobId: "job_c", brief, slug: "iocean-controllers", createdBy: "p1", createdAt: now(), started: Date.now() };
    controllerBuilds.unshift(b);
    return delay(viewOf(b));
  },
  controllerBuildsOf: () => delay(controllerBuilds.map(viewOf)),
  lookControllerSource: (url: string) => delay(url.includes("iocean-controllers")
    ? { controllers: foundIn } : { controllers: [], said: "no iocean.toml and no controllers/ folders; the build will look for one controller" }),
  controllerBuild: (bid: string) => delay(viewOf(controllerBuilds.find((b) => b.id === bid)!)),
  controllerBuildAgain: (bid: string) => {
    said.push(`again ${bid}`);
    const old = controllerBuilds.find((b) => b.id === bid)!;
    const b = { ...old, id: id("ctlb"), createdAt: now(), started: Date.now() };
    controllerBuilds.unshift(b);
    return delay(viewOf(b));
  },
});
Object.assign(window, { said, store });

const held = {
  you: { id: "p1", displayName: "Harness", email: "harness@example.test" },
  institution: { id: "org_1", name: "Harness" },
  organisations: [{ id: "org_1", name: "Harness" }],
  // The tank is the institution's own, so Places offers to retire it.
  places: places.map((p) => ({ id: p.id, slug: p.slug, name: p.name, ...(p.id === "city_tank" ? { ownedByOrg: "org_1" } : {}) })),
  yourPlaces: places.map((p) => ({ id: p.id, slug: p.slug, name: p.name, ...(p.id === "city_tank" ? { ownedByOrg: "org_1" } : {}) })),
  vehicles: [{ id: "veh_mini", slug: "mini-hoot", name: "mini-hoot" }, { id: "veh_luna", slug: "boxfish-luna", name: "Boxfish Luna" }],
  queues: [{ id: "queue_1", free: 1, devices: 1, runtimes: ["isaac-6.0.1+oceansim"] }],
  runsRead: new URLSearchParams(location.search).get("runs") !== "reading",
  runs: [
    runOf("run_1", "Round the tank · mini-hoot", 1, { mode: "interactive" }),
    runOf("run_2", "Round the tank ~ October 4 · still", 1.5, { sweepId: "sweep_a" }),
    runOf("run_3", "Round the tank ~ October 4 · gentle", 1.6, { sweepId: "sweep_a" }),
    runOf("run_4", "The September plot round · Boxfish Luna", 26, { state: "failed", outcome: undefined }, "veh_luna", "city_looe"),
  ], stacks: [], controllers: [
    { slug: "station-hold", name: "Station hold (SDK example)",
      newest: { id: "stack_1", imageDigest: "sha256:5d6b894df3b6aa", createdAt: "2026-09-26T10:00:00Z", needs: {} },
      builds: [{ id: "stack_1" }, { id: "stack_0" }] },
    { slug: "learned-hold", name: "Learned hold (trained across waters)",
      newest: { id: "stack_2", imageDigest: "sha256:cf884945687baa", createdAt: "2026-09-27T10:00:00Z", needs: { gpu: true, gpuMemoryBytes: 8589934592 } },
      builds: [{ id: "stack_2" }] },
  ],
} as unknown as Held;

async function packagesOf(): Promise<Packages> {
  const placePackages = new Map();
  for (const p of places) {
    const site = await (await fetch(`./harness/fixtures/${p.fixture}/site.json`)).json();
    placePackages.set(p.id, {
      version: { id: `${p.id}-v1` }, pictureUrl: undefined, credit: undefined, site,
      files: [{ path: site.mesh.heightfield.file, url: `./harness/fixtures/${p.fixture}/${site.mesh.heightfield.file}` }],
    });
  }
  const vehicles = new Map();
  for (const [id, slug] of [["veh_mini", "mini-hoot"], ["veh_luna", "boxfish-luna"]] as const) {
    vehicles.set(id, { version: { id: `${id}-v1` }, dynamics: await (await fetch(`./harness/fixtures/${slug}/dynamics.json`)).json() });
  }
  return { places: placePackages, vehicles } as unknown as Packages;
}

function Harness({ packages }: { packages: Packages }) {
  const query = new URLSearchParams(location.search);
  const first = [...store.missions.entries()][query.get("which") === "looe" ? 1 : 0]!;
  const [where, setWhere] = useState<{ page: string; mission?: string; place?: string }>(
    { page: query.get("page") ?? "missions", mission: first[0], place: first[1].place });
  const p = platform as never;
  return (
    <div className="sea">
    <div className="chrome" />
    <div className="deck">
      <nav>
        <div className="here"><strong>harness</strong></div>
        {["results", "fly", "missions", "places", "video", "fleet", "controllers", "store", "designer", "sweep", "layout", "build", "recon", "run"].map((page) => (
          <a key={page} aria-current={where.page === page ? "page" : undefined} onClick={() => setWhere((w) => ({ ...w, page }))}>{page}</a>
        ))}
      </nav>
      <main>
        {where.page === "missions" ? (
          <Missions platform={p} held={held} onOpen={(mission, place) => setWhere({ page: "designer", mission, place })}
                    onFly={(mission) => setWhere((w) => ({ ...w, page: "fly", mission }))} />
        ) : where.page === "designer" ? (
          <Designer platform={p} held={held} packages={packages} mission={where.mission!} place={where.place!}
                    onBack={() => setWhere((w) => ({ ...w, page: "missions" }))}
                    onFly={(mission) => setWhere((w) => ({ ...w, page: "fly", mission }))} />
        ) : where.page === "layout" ? (
          <PlaceDesigner platform={p} held={held} packages={packages} place={where.place ?? "city_looe"}
                         layout={[...store.layouts.values()].find((l) => l.place === (where.place ?? "city_looe"))?.layout.id as string | undefined}
                         onChanged={() => said.push("places read again")} onOpenLayout={(l) => said.push(`layout ${l}`)}
                         onBack={() => setWhere((w) => ({ ...w, page: "missions" }))} />
        ) : where.page === "run" ? (
          <Dive platform={p} held={held} packages={packages} free={1} devices={1}
                onDiving={(d, r) => said.push(`diving ${d} ${r}`)} onChanged={() => undefined}
                onOpen={(w) => said.push(`open ${JSON.stringify(w)}`)} />
        ) : where.page === "build" ? (
          <Compose platform={p} held={held} chosen={where.mission} onBack={() => said.push("back")} onOpen={(c) => said.push(`open ${c}`)}
                   onDesign={(c) => { said.push(`design ${c}`); setWhere((w) => ({ ...w, page: "layout" })); }} />
        ) : where.page === "places" ? (
          <Places platform={p} held={held} packages={packages}
                  onOpen={(c) => said.push(`open ${c}`)} onBuild={() => setWhere((w) => ({ ...w, page: "build" }))}
                  onStore={() => setWhere((w) => ({ ...w, page: "store" }))}
                  onChanged={() => { said.push("places read again"); }} />
        ) : where.page === "store" ? (
          <Store platform={p} held={held} packages={packages}
                 onOpenPlace={(c) => said.push(`open ${c}`)} onOpenVehicle={(v) => said.push(`vehicle ${v}`)}
                 onBuildOn={(c) => { said.push(`build on ${c}`); setWhere((w) => ({ ...w, page: "build" })); }}
                 onChanged={() => { said.push("places read again"); }} />
        ) : where.page === "fleet" ? (
          <Fleet held={held} packages={packages} onOpen={(v) => said.push(`vehicle ${JSON.stringify(v)}`)} />
        ) : where.page === "controllers" ? (
          <Autonomy platform={p} held={held} onFly={(s) => said.push(`fly with ${s}`)} onRuns={(b) => said.push(`runs by ${b}`)}
                    onOpen={(slug) => setWhere((w) => ({ ...w, page: "controller", mission: slug }))} />
        ) : where.page === "controller" ? (
          <ControllerDetail platform={p} held={held} slug={where.mission ?? ""} onBack={() => setWhere((w) => ({ ...w, page: "controllers" }))}
                            onFly={(s) => said.push(`fly with ${s}`)} onReplay={(d, r) => said.push(`replay ${d} ${r}`)} />
        ) : where.page === "asset" ? (
          <AssetDetail platform={p} id={where.mission ?? ""} places={held.places} onBack={() => setWhere((w) => ({ ...w, page: "video" }))}
                       onPlace={(a, place) => { said.push(`place ${a} in ${place}`); setWhere((w) => ({ ...w, page: "layout", place })); }}
                       onCompose={(a) => { said.push(`compose with ${a}`); setWhere((w) => ({ ...w, page: "build", mission: a })); }} />
        ) : where.page === "video" ? (
          <Reconstructions platform={p} held={held}
                           onOpen={(r) => setWhere((w) => ({ ...w, page: "recon", mission: r }))}
                           onOpenAsset={(a) => setWhere((w) => ({ ...w, page: "asset", mission: a }))} />
        ) : where.page === "recon" ? (
          <ReconstructionPage platform={p} held={held} packages={packages} id={where.mission === "recon_2" ? "recon_2" : "recon_1"}
                              onBack={() => setWhere((w) => ({ ...w, page: "video" }))} onOpenPlace={(c) => said.push(`open ${c}`)} />
        ) : where.page === "sweep" ? (
          <ManyRun platform={p} sweep="sweep_a" onBack={() => setWhere((w) => ({ ...w, page: "results" }))} />
        ) : where.page === "results" ? (
          <Runs platform={p} held={held} onNew={() => setWhere((w) => ({ ...w, page: "fly" }))} onChanged={() => undefined}
                onReplay={(d, r) => setWhere((w) => ({ ...w, page: "replay", place: d, mission: r }))}
                onSweep={() => setWhere((w) => ({ ...w, page: "sweep" }))} />
        ) : where.page === "replay" ? (
          <Replay platform={p} dive={where.place ?? "dive_run_1"} run={where.mission ?? "run_1"}
                  one={held.runs.find((r) => r.run.id === where.mission)}
                  onBack={() => setWhere((w) => ({ ...w, page: "results" }))} />
        ) : (
          <Fly platform={p} held={held} packages={packages} mission={where.mission}
               onDiving={(d, r) => said.push(`diving ${d} ${r}`)} onSwept={(s) => said.push(`swept ${s}`)}
               onSingleTask={() => said.push("single task")} onChanged={() => undefined}
               onDesign={(mission, place) => setWhere({ page: "designer", mission, place })} />
        )}
      </main>
    </div>
    </div>
  );
}

void packagesOf().then((packages) =>
  createRoot(document.getElementById("root")!).render(<StrictMode><Harness packages={packages} /></StrictMode>));
