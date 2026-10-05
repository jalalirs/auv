// The screens as the promo films them: the harness (harness.tsx) over the
// Red Sea place, its pipeline and its dredger, with the run list taken from
// dives actually flown on the box on 5 October 2026.
//
//   http://localhost:5173/promo.html?page=layout|designer|fly|results
//
// window.promo.run(id, patch) changes a run's state, so the film can show a
// dive going from queued to flown on a GPU host the way the real one did.

import { StrictMode, useEffect, useState } from "react";
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

const places = [{ id: "city_red", slug: "red-sea", name: "Red Sea fringing reef", fixture: "red-sea" }];

const pipeline = { id: "pipeline-1", kind: "pipeline", x: 150, y: -20, radiusM: 0.16, bendRadiusM: 150,
                   route: [{ x: 0, y: -40 }, { x: 150, y: -20 }, { x: 450, y: 0 }] };
const dredger = { id: "dredger-1", kind: "dredger", x: 200, y: -150, z: 0, releaseKgPerS: 20, finesShare: 0.4, releaseDepthM: 6 };

const store = {
  missions: new Map<string, { mission: Doc; place: string; versions: Version[] }>(),
  layouts: new Map<string, { layout: Doc; place: string; versions: Version[] }>(),
};
function addLayout(slug: string, name: string, things: Doc[]) {
  const layoutId = id("layout");
  store.layouts.set(layoutId, {
    layout: { id: layoutId, slug, name, summary: "" }, place: "city_red",
    versions: [{ id: id("version"), ordinal: 1, createdAt: now(), document: { things } }],
  });
  return layoutId;
}
const laid = addLayout("pipeline-landfall", "Pipeline landfall", [pipeline]);
const proposed = addLayout("proposed-works", "Proposed works", [dredger]);
function addMission(name: string, stages: Doc[], launch: Doc, layoutId: string) {
  const missionId = id("mission");
  store.missions.set(missionId, {
    mission: { id: missionId, slug: name.toLowerCase().replace(/[^a-z0-9]+/g, "-"), name, summary: "", cityId: "city_red" },
    place: "city_red",
    versions: [{ id: id("version"), ordinal: 1, createdAt: now(), document: {
      cityVersionId: "city_red-v1", layoutVersionId: store.layouts.get(layoutId)!.versions[0]!.id, launch, stages } }],
  });
  return missionId;
}
const inspect = addMission("Inspect the landfall for free spans",
  [{ kind: "follow", over: "pipeline-1", altitudeM: 4.5, altitudeBandM: 2, swathM: 12, timeLimitS: 1500 }],
  { x: -10, y: -40 }, laid);

const minutesAgo = (m: number) => new Date(Date.now() - m * 60_000).toISOString();
const run = (rid: string, name: string, m: number, state: string, vehicle: string, task?: Doc, extra: Doc = {}) => ({
  dive: `dive_${rid}`, name, flownBy: "Demo", vehicleVersion: `${vehicle}-v1`, placeVersion: "city_red-v1",
  run: { id: rid, state, mode: "batch", requestedAt: minutesAgo(m), physicsVersion: 3,
         ...(task ? { outcome: { task } } : {}), ...extra },
});
// What was flown on 5 October, as the platform recorded it.
const flown = [
  run("run_pipe", "Pipeline landfall · REMUS 100", 95, "succeeded", "veh_remus",
      { name: "Follow a line", score: 1, done: true, seconds: 308.4 }),
  run("run_dredge", "Dredging beside the reef · Boxfish Luna", 240, "succeeded", "veh_luna"),
  run("run_fahal", "Al Fahal among Red Sea fish · Boxfish Luna", 180, "succeeded", "veh_luna"),
  run("run_shushah", "Shushah among Red Sea fish · Boxfish Luna", 181, "succeeded", "veh_luna"),
];

const delay = <T,>(v: T) => new Promise<T>((r) => setTimeout(() => r(v), 30));
const said: string[] = [];
const platform = {
  missionsOf: () => delay([...store.missions.values()].map((m) => m.mission)),
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
    return delay(version);
  },
  saveMission: (missionId: string, document: Doc, label = "") => {
    const one = store.missions.get(missionId)!;
    const version = { id: id("version"), ordinal: one.versions.length + 1, createdAt: now(), document, label };
    one.versions.push(version);
    return delay(version);
  },
  archiveMission: (missionId: string) => delay(store.missions.get(missionId)!.mission),
  missionCost: () => delay({ runs: 0, survived: 0, notEnough: true }),
  versionsOfPlace: (city: string) => delay([{ id: `${city}-v1`, ordinal: 14, createdAt: now(), publishedAt: now() }]),
  layoutsOf: () => delay([...store.layouts.values()].map((l) => l.layout)),
  versionsOfLayout: (layoutId: string) => delay([...(store.layouts.get(layoutId)?.versions ?? [])].reverse()),
  versionsOfVehicle: (vehicle: string) => delay([{ id: `${vehicle}-v1`, ordinal: 1, createdAt: now(), publishedAt: now() }]),
  defineConditions: (_org: string, c: Doc) => { said.push(`conditions ${JSON.stringify(c)}`); return delay({ id: id("cond") }); },
  defineDive: (_org: string, d: Doc) => { said.push(`dive ${JSON.stringify(d)}`); return delay({ id: id("dive") }); },
  ask: (dive: string, r: Doc) => { said.push(`run of ${dive} ${JSON.stringify(r)}`); return delay({ id: id("run") }); },
  sweepsOf: () => delay([]),
  cancel: () => delay(undefined),
  startSweep: (_org: string, s: Doc) => { said.push(`sweep ${JSON.stringify(s)}`); return delay({ id: id("sweep") }); },
};

const baseHeld = {
  you: { id: "p1", displayName: "Demo", email: "demo@example.test" },
  institution: { id: "org_1", name: "iocean" },
  places: places.map((p) => ({ id: p.id, slug: p.slug, name: p.name })),
  vehicles: [{ id: "veh_remus", slug: "remus-100", name: "REMUS 100" }, { id: "veh_luna", slug: "boxfish-luna", name: "Boxfish Luna" }],
  queues: [{ id: "queue_1", name: "GPU hosts, Jeddah", free: 2, devices: 2, runtimes: ["isaac-6.0.1+oceansim"] }],
  runs: flown, stacks: [], controllers: [],
};

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
  for (const [vid, slug] of [["veh_remus", "remus-100"], ["veh_luna", "boxfish-luna"]] as const) {
    vehicles.set(vid, { version: { id: `${vid}-v1` }, dynamics: await (await fetch(`./harness/fixtures/${slug}/dynamics.json`)).json() });
  }
  return { places: placePackages, vehicles } as unknown as Packages;
}

function Promo({ packages }: { packages: Packages }) {
  const query = new URLSearchParams(location.search);
  const [where, setWhere] = useState<{ page: string; mission?: string; place?: string }>(
    { page: query.get("page") ?? "missions", mission: inspect, place: "city_red" });
  const [held, setHeld] = useState(baseHeld);
  useEffect(() => {
    Object.assign(window, {
      said, store,
      promo: {
        go: (page: string) => setWhere((w) => ({ ...w, page })),
        run: (rid: string, patch: Doc, name?: string) => setHeld((h) => {
          const exists = h.runs.some((one) => one.run.id === rid);
          const runs = exists
            ? h.runs.map((one) => one.run.id === rid ? { ...one, run: { ...one.run, ...patch } } : one)
            : [run(rid, name ?? "A dive", 0, "queued", "veh_remus", undefined, patch), ...h.runs];
          return { ...h, runs };
        }),
      },
    });
  }, []);
  const p = platform as never;
  const h = held as unknown as Held;
  const layoutId = query.get("layout") === "proposed" ? proposed : laid;
  return (
    <div className="sea">
    <div className="chrome" />
    <div className="deck">
      <nav>
        <div className="here"><strong>iocean</strong></div>
        {["missions", "designer", "fly", "results", "layout"].map((page) => (
          <a key={page} aria-current={where.page === page ? "page" : undefined} onClick={() => setWhere((w) => ({ ...w, page }))}>{page}</a>
        ))}
      </nav>
      <main>
        {where.page === "missions" ? (
          <Missions platform={p} held={h} onOpen={(mission, place) => setWhere({ page: "designer", mission, place })}
                    onFly={(mission) => setWhere((w) => ({ ...w, page: "fly", mission }))} />
        ) : where.page === "designer" ? (
          <Designer platform={p} held={h} packages={packages} mission={where.mission!} place={where.place!}
                    onBack={() => setWhere((w) => ({ ...w, page: "missions" }))}
                    onFly={(mission) => setWhere((w) => ({ ...w, page: "fly", mission }))} />
        ) : where.page === "layout" ? (
          <LayoutEditor platform={p} pkg={packages.places.get("city_red") as never}
                        layout={store.layouts.get(layoutId)!.layout as never}
                        onBack={() => setWhere((w) => ({ ...w, page: "missions" }))} />
        ) : where.page === "results" ? (
          <Runs platform={p} held={h} onChanged={() => undefined}
                onReplay={(d, r) => said.push(`replay ${d} ${r}`)} onSweep={(s) => said.push(`read sweep ${s}`)} />
        ) : (
          <Fly platform={p} held={h} packages={packages} mission={where.mission}
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
  createRoot(document.getElementById("root")!).render(<StrictMode><Promo packages={packages} /></StrictMode>));
