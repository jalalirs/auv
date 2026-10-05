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
import { Missions } from "../screens/Missions.js";
import { Runs } from "../screens/Runs.js";
import { LayoutEditor } from "../screens/Layout.js";

const now = () => new Date().toISOString();
let counter = 0;
const id = (kind: string) => `${kind}_${(++counter).toString().padStart(4, "0")}`;

type Doc = Record<string, unknown>;
interface Version { id: string; ordinal: number; createdAt: string; document: Doc; label?: string }

const places = [
  { id: "city_tank", slug: "iocean-tank-1", name: "iocean tank", fixture: "iocean-tank-1" },
  { id: "city_looe", slug: "looe-key", name: "Looe Key", fixture: "looe-key" },
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
         outcome: { task: { name: "Waypoints", score: 0.92, done: true, energyWh: 0.709, seconds: 59.7 } }, ...extra },
});
const delay = <T,>(v: T) => new Promise<T>((r) => setTimeout(() => r(v), 30));
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
};
Object.assign(window, { said, store });

const held = {
  you: { id: "p1", displayName: "Harness", email: "harness@example.test" },
  institution: { id: "org_1", name: "Harness" },
  places: places.map((p) => ({ id: p.id, slug: p.slug, name: p.name })),
  vehicles: [{ id: "veh_mini", slug: "mini-hoot", name: "mini-hoot" }, { id: "veh_luna", slug: "boxfish-luna", name: "Boxfish Luna" }],
  queues: [{ id: "queue_1", free: 1, devices: 1, runtimes: ["isaac-6.0.1+oceansim"] }],
  runs: [
    runOf("run_1", "Round the tank · mini-hoot", 1, { mode: "interactive" }),
    runOf("run_2", "Round the tank ~ October 4 · still", 1.5, { sweepId: "sweep_a" }),
    runOf("run_3", "Round the tank ~ October 4 · gentle", 1.6, { sweepId: "sweep_a" }),
    runOf("run_4", "The September plot round · Boxfish Luna", 26, { state: "failed", outcome: undefined }, "veh_luna", "city_looe"),
  ], stacks: [], controllers: [],
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
        {["missions", "designer", "fly", "results", "layout"].map((page) => (
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
          <LayoutEditor platform={p} pkg={packages.places.get(where.place ?? "city_tank") as never}
                        layout={[...store.layouts.values()].find((l) => l.place === (where.place ?? "city_tank"))!.layout as never}
                        onBack={() => setWhere((w) => ({ ...w, page: "missions" }))} />
        ) : where.page === "results" ? (
          <Runs platform={p} held={held} onChanged={() => undefined}
                onReplay={(d, r) => said.push(`replay ${d} ${r}`)} onSweep={(s) => said.push(`read sweep ${s}`)} />
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
