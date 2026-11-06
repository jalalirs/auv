// A plan of work, in its world.
//
// A mission is a place, the arrangement it was planned over, and the work in
// order. It used to be written as a list with nothing to look at: a survey was
// "sixty by thirty metres ahead of wherever the vehicle begins", and where that
// fell on the reef was found out by flying it. Here every stage is drawn where
// it happens, in the world in three dimensions and at the height it is flown —
// the route as clicked points at its depth, a survey as the rectangle it
// covers and its lanes over the ground, a transect as its line, an inspection
// as a ring round what is inspected — in the place's own frame, which is the
// frame the runtime flies a drawn stage in. The chosen stage's points are
// taken hold of and dragged.
//
// It opens to read. Editing is a choice, and every save is a new version:
// runs pin a version, and a result has to keep meaning what it meant.

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type { AssetVersion, Mission, Platform } from "@coral-city/api";

import { TASKS, type Task } from "../catalog/tasks.js";
import {
  drawMode, drawnInto, drawPrompt, extentOf, floorWatts, geometryOf, handleMoved, hullOf, launchAt, legsOf, pilotOf,
  settledMs, snap, wattsOf, type Drawn, type P, type Plan, type Stage,
} from "../catalog/stages.js";
import { centreOf, groundAt, groundOf, type Ground, type Thing } from "../parts/SiteChart.js";
import type { PlanIn3D } from "../parts/StagesIn3D.js";
import { TaskArt } from "../parts/TaskArt.js";
import { World3D, type Glass, type Shown, type View3D, type ViewName } from "../parts/World3D.js";
import { newestOf } from "../platform/packages.js";
import { itemsOf } from "../platform/scene.js";
import { layerOf, readWorld, type WorldOf } from "../platform/world.js";
import type { Held, Packages } from "./Deck.js";
import { Empty, PageHead, Pill } from "./parts.js";
import "../parts/world.css";

const STAGES: Task[] = TASKS.filter((one) => one.unavailable === undefined && one.key !== "mission");

const kindOf = (task: Task) => String(task.objective?.["kind"] ?? task.key);
const nameOf = (kind: string) => STAGES.find((s) => kindOf(s) === kind)?.name ?? kind;

/** The numbers worth editing on a stage, by kind. */
const NUMBERS: Record<string, { field: string; label: string; unit: string }[]> = {
  "hold-station": [{ field: "seconds", label: "hold for", unit: "s" }, { field: "radiusM", label: "within", unit: "m" }],
  waypoints: [{ field: "depthM", label: "depth", unit: "m" }, { field: "radiusM", label: "arrive within", unit: "m" }],
  transect: [{ field: "altitudeM", label: "altitude", unit: "m" }],
  survey: [{ field: "altitudeM", label: "altitude", unit: "m" }, { field: "swathM", label: "lane spacing", unit: "m" }],
  reach: [{ field: "radiusM", label: "arrive within", unit: "m" }],
  inspect: [{ field: "radiusM", label: "stand off", unit: "m" }],
  treat: [{ field: "radiusM", label: "patch radius", unit: "m" }, { field: "altitudeM", label: "altitude", unit: "m" }],
  revisit: [{ field: "holdS", label: "sample for", unit: "s" }],
  dock: [{ field: "toleranceM", label: "within", unit: "m" }],
  wait: [{ field: "seconds", label: "wait", unit: "s" }],
};
const ALLOW = { field: "timeLimitS", label: "allow", unit: "s" };

const LAUNCHES = new Set(["ship", "buoy", "marker-post", "mooring-block"]);

function minutes(seconds: number): string {
  if (!Number.isFinite(seconds)) return "—";
  if (seconds < 90) return `${Math.round(seconds)} s`;
  if (seconds < 5400) return `${Math.round(seconds / 60)} min`;
  return `${(seconds / 3600).toFixed(1)} h`;
}

export function Designer({ platform, held, packages, mission, place, onBack, onFly, onMade }: {
  platform: Platform;
  held: Held;
  packages: Packages;
  /** The mission, or "new" to start one in this world. */
  mission: string;
  place: string;
  onBack: () => void;
  onFly: (mission: string) => void;
  /** A new mission was started: its id, to open it. */
  onMade?: (id: string) => void;
}): React.JSX.Element {
  const [found, setFound] = useState<Mission | undefined>();
  const [missing, setMissing] = useState(false);
  const [ground, setGround] = useState<Ground | undefined>();
  const [world, setWorld] = useState<WorldOf | undefined>();
  const [worldVersions, setWorldVersions] = useState<AssetVersion[]>([]);
  const [cityVersion, setCityVersion] = useState("");
  const [saved, setSaved] = useState<AssetVersion[]>([]);

  const [plan, setPlan] = useState<Plan>({ stages: [] });
  const [chosen, setChosen] = useState(0);
  const [editing, setEditing] = useState(false);
  const [drawing, setDrawing] = useState<P[] | undefined>();
  const [placingLaunch, setPlacingLaunch] = useState(false);
  const [under, setUnder] = useState<number | undefined>();
  // Which vehicle the estimate is for: chosen, or the one last flown here.
  const [picked, setPicked] = useState<string | undefined>();
  const [placeVersions, setPlaceVersions] = useState<Set<string>>(new Set());
  const [vehicleOf, setVehicleOf] = useState<Map<string, string>>(new Map());
  const [saying, setSaying] = useState("");
  const [trouble, setTrouble] = useState("");

  const pkg = packages.places.get(place) ?? undefined;
  useEffect(() => { void groundOf(pkg).then(setGround); }, [pkg]);
  const glass = useMemo(() => {
    const site = pkg?.site as unknown as { enclosed?: boolean; interior?: Glass } | undefined;
    return site?.enclosed && site.interior ? site.interior : undefined;
  }, [pkg]);
  const view = useRef<View3D>(null);
  // A point of the chosen stage in hand: the stage as it was when taken hold of.
  const holding = useRef<Stage | undefined>(undefined);

  useEffect(() => {
    let stale = false;
    if (mission === "new") {
      // A mission belongs to the world it is written in, so it is started
      // here, in it, and opened.
      const slug = `mission-${Date.now().toString(36)}`;
      void platform.startMission(place, { slug, name: "New mission" })
        .then((made) => { if (!stale) onMade?.(made.id); })
        .catch(() => { if (!stale) setMissing(true); });
      return () => { stale = true; };
    }
    void platform.mission(mission).then((one) => { if (!stale) setFound(one); })
      .catch(() => { if (!stale) setMissing(true); });
    return () => { stale = true; };
  }, [platform, mission]); // eslint-disable-line react-hooks/exhaustive-deps

  // Which vehicle each run flew: a run names a version, and the estimate wants
  // every run of a vehicle, whichever version of it.
  useEffect(() => {
    let stale = false;
    void Promise.all(held.vehicles.map(async (one) =>
      (await platform.versionsOfVehicle(one.id).catch((): AssetVersion[] => [])).map((v) => [v.id, one.id] as const)))
      .then((pairs) => { if (!stale) setVehicleOf(new Map(pairs.flat())); });
    return () => { stale = true; };
  }, [platform, held.vehicles]);

  // The world it is written in, at its newest version, and the package that
  // version was baked into.
  useEffect(() => {
    let stale = false;
    const city = held.places.find((p) => p.id === place);
    void (async () => {
      const cities = await platform.versionsOfPlace(place).catch((): AssetVersion[] => []);
      const read = city ? await readWorld(platform, city, pkg) : undefined;
      const versions = read?.world ? await platform.versionsOfWorld(read.world.id).catch((): AssetVersion[] => []) : [];
      if (stale) return;
      setCityVersion(read?.document.bake?.version ?? newestOf(cities)?.id ?? "");
      setPlaceVersions(new Set(cities.map((one) => one.id)));
      setWorld(read);
      setWorldVersions(versions);
    })();
    return () => { stale = true; };
  }, [platform, place, pkg?.version.id]); // eslint-disable-line react-hooks/exhaustive-deps

  // What was written last.
  const readSaved = useCallback(() => {
    let stale = false;
    void platform.versionsOfMission(mission).then((versions) => {
      if (stale) return;
      setSaved(versions);
      const document = versions[0]?.document as Plan | undefined;
      if (document) setPlan({ ...document, stages: document.stages ?? [] });
    }).catch(() => undefined);
    return () => { stale = true; };
  }, [platform, mission]);
  useEffect(readSaved, [readSaved]);

  // What is in the world: the version the mission was saved against when
  // reading, so a stage points at what was there; the newest when editing,
  // which is what a save pins.
  const pinnedVersion = worldVersions.find((v) => v.id === plan.layoutVersionId);
  const inWorld = (editing || !pinnedVersion ? world?.document : pinnedVersion.document) as WorldOf["document"] | undefined;
  const things: Thing[] = useMemo(() => {
    const items = (inWorld && layerOf(inWorld, "structures")?.items) ?? [];
    return items.filter((t) => t.kind !== "object") as unknown as Thing[];
  }, [inWorld]);
  // Everything in the world, drawn as the world's editor draws it.
  const shown = useMemo((): Shown[] => [...itemsOf(inWorld).values()]
    .filter((t) => !t.hidden && (typeof t.x === "number" || t.route || t.ends || t.corners))
    .map((t) => ({ ...(t as unknown as Shown), x: Number(t.x ?? 0), y: Number(t.y ?? 0) })), [inWorld]);
  const worldMoved = pinnedVersion !== undefined && world?.version !== undefined && pinnedVersion.id !== world.version.id;
  const drawn: Drawn[] = things as unknown as Drawn[];

  const begin = pkg?.site?.beginAt;
  const launch = launchAt(plan, drawn, { x: Number(begin?.[0] ?? 0), y: Number(begin?.[1] ?? 0) });

  // The vehicle it is checked against, and how it flies: pursue in this hull.
  const lastHere = held.runs.find((r) => placeVersions.has(r.placeVersion ?? "") && vehicleOf.has(r.vehicleVersion ?? ""));
  const checkWith = picked ?? (lastHere ? vehicleOf.get(lastHere.vehicleVersion!)! : held.vehicles[0]?.id ?? "");
  const vehicle = packages.vehicles.get(checkWith) ?? undefined;
  const dyn = vehicle?.dynamics as unknown as {
    power?: { capacityWh?: number; hotelW?: number; reserveFraction?: number };
  } | undefined;
  const hull = useMemo(() => hullOf(vehicle?.dynamics), [vehicle]);
  const pilot = useMemo(() => pilotOf(vehicle?.dynamics), [vehicle]);
  const legs = useMemo(() => legsOf(plan.stages, drawn, launch, hull, pilot),
    [plan.stages, drawn, launch.x, launch.y, hull, pilot]); // eslint-disable-line react-hooks/exhaustive-deps
  const flyS = legs.reduce((s, l) => s + l.flyS, 0);
  const allowS = legs.reduce((s, l) => s + l.allowS, 0);
  const usableWh = (dyn?.power?.capacityWh ?? 0) * (1 - (dyn?.power?.reserveFraction ?? 0.1));
  // What it draws: the middle of what its runs here drew, or anywhere if it
  // has not flown here; a floor from its hull when it has never flown.
  const ofIt = held.runs.filter((r) => vehicleOf.get(r.vehicleVersion ?? "") === checkWith);
  const here = ofIt.filter((r) => placeVersions.has(r.placeVersion ?? ""));
  const drew = wattsOf((here.length ? here : ofIt).map((r) => r.run.outcome as Record<string, unknown> | undefined));
  const watts = drew?.watts ?? (dyn?.power?.hotelW !== undefined ? floorWatts(hull, dyn.power.hotelW, pilot) : undefined);
  const spentWh = watts !== undefined ? (watts * flyS) / 3600 : undefined;

  const at = plan.stages[chosen];
  const mode = at ? drawMode(at.kind) : "none";
  const acrossM = ground?.acrossM ?? 100;
  const site = held.places.find((p) => p.id === place);

  const setStage = useCallback((index: number, next: Stage) => {
    setPlan((was) => ({ ...was, stages: was.stages.map((one, i) => (i === index ? next : one)) }));
  }, []);

  const finishDrawing = useCallback((clicks: P[]) => {
    if (at === undefined || clicks.length === 0) { setDrawing(undefined); return; }
    // A double-click that finishes a route has already clicked its last point
    // once, or twice; a point the same as the one before it is not a new one.
    const kept = clicks.filter((p, i) => i === 0 || p.x !== clicks[i - 1]!.x || p.y !== clicks[i - 1]!.y);
    setStage(chosen, drawnInto(at, kept));
    setDrawing(undefined);
  }, [at, chosen, setStage]);

  const pick = useCallback((where: P) => {
    const p = { x: snap(where.x, acrossM), y: snap(where.y, acrossM) };
    if (placingLaunch) {
      setPlan((was) => ({ ...was, launch: { x: p.x, y: p.y } }));
      setPlacingLaunch(false);
      return;
    }
    if (drawing === undefined) {
      // Not drawing: a click near a stage's mark chooses that stage.
      let best = -1, bestD = acrossM / 40;
      legs.forEach((leg, i) => {
        const d = Math.hypot(leg.to.x - where.x, leg.to.y - where.y);
        if (d < bestD) { best = i; bestD = d; }
      });
      if (best >= 0) setChosen(best);
      return;
    }
    // An inspection is of something: the nearest thing in the world to the
    // click, not a circle on open ground.
    if (at?.kind === "inspect") {
      let best: Drawn | undefined, bestD = acrossM / 25;
      for (const one of drawn) {
        const c = centreOf(one as unknown as Thing);
        const d = Math.hypot(c.x - where.x, c.y - where.y);
        if (d < bestD) { best = one; bestD = d; }
      }
      if (!best) { setTrouble("click a thing in the world to inspect it"); return; }
      const c = centreOf(best as unknown as Thing);
      setTrouble("");
      setStage(chosen, { ...at, over: best.id, target: { x: c.x, y: c.y } });
      setDrawing(undefined);
      return;
    }
    const clicks = [...drawing, p];
    if ((mode === "point" && clicks.length >= 1) || ((mode === "line" || mode === "area") && clicks.length >= 2)) {
      finishDrawing(clicks);
      return;
    }
    setDrawing(clicks);
  }, [acrossM, placingLaunch, drawing, legs, mode, finishDrawing, at, drawn, chosen, setStage]);

  // The plan in the world.
  const in3D = useMemo((): PlanIn3D => ({ stages: plan.stages, legs, drawn, chosen, launch, drawing, editing }),
    [plan.stages, legs, drawn, chosen, launch.x, launch.y, drawing, editing]); // eslint-disable-line react-hooks/exhaustive-deps

  // A point of the chosen stage dragged over the ground: from where the stage
  // was when it was taken hold of, so a corner dragged past the one across
  // from it is still that corner.
  const handle = useCallback((k: number, where: P, phase: "start" | "move" | "end") => {
    if (at === undefined) return;
    if (phase === "start") holding.current = at;
    const base = holding.current ?? at;
    if (Number.isFinite(where.x)) setStage(chosen, handleMoved(base, k, { x: snap(where.x, acrossM), y: snap(where.y, acrossM) }));
    if (phase === "end") holding.current = undefined;
  }, [at, chosen, acrossM, setStage]);

  // Open on the work, or on the world when there is none yet; once for each
  // ground the view is made for.
  const framed = useRef<Ground | undefined>(undefined);
  useEffect(() => {
    if (!ground || framed.current === ground || (plan.stages.length === 0 && things.length === 0)) return;
    framed.current = ground;
    const points = plan.stages.length ? extentOf(plan.stages, drawn, legs) : things.map(centreOf);
    view.current?.frameOn(points);
  }, [ground, plan.stages.length, things.length]); // eslint-disable-line react-hooks/exhaustive-deps

  const save = useCallback(async () => {
    const pinned = world?.version;
    setSaying("saving"); setTrouble("");
    try {
      const version = await platform.saveMission(mission, {
        describedBy: "coral-city/mission/v1",
        cityVersionId: cityVersion,
        layoutVersionId: pinned?.id ?? "",
        ...(plan.launch ? { launch: plan.launch } : {}),
        stages: plan.stages,
      } as never, `${plan.stages.length} stages`);
      setSaying(`saved as version ${version.ordinal}`);
      setEditing(false);
      readSaved();
    } catch (thrown) {
      setSaying("");
      setTrouble(thrown instanceof Error ? thrown.message : "it would not save");
    }
  }, [platform, mission, cityVersion, world, plan, readSaved]);

  if (missing) return <Empty title="Not a mission you have">It may have been archived, or you were never granted it.</Empty>;
  if (mission === "new") return <Empty title="Starting a mission">In {held.places.find((p) => p.id === place)?.name ?? "this world"}.</Empty>;

  const numbers = at === undefined ? [] : [...(NUMBERS[at.kind] ?? []), ALLOW];
  const newest = saved[0];

  return (
    <>
      <PageHead title={found?.name ?? "A mission"}
                says={`${newest ? `version ${newest.ordinal}` : "not saved yet"}${worldMoved ? " · the world has changed since: save to fly it in the newest" : ""}`}
                back={site?.name ?? "World"} onBack={onBack}
                aside={<span className="designer-acts">
                  <Pill>{minutes(flyS)} flying · {minutes(allowS)} allowed</Pill>
                  {editing
                    ? <button type="button" className="quiet" onClick={() => { setEditing(false); setDrawing(undefined); readSaved(); }}>Discard</button>
                    : <button type="button" className="quiet" onClick={() => setEditing(true)}>Edit</button>}
                  {!editing && newest ? <button type="button" onClick={() => onFly(mission)}>Fly it</button> : null}
                </span>} />

      <section className={editing ? "designer editing" : "designer"}>
        <div className="palette">
          <h3>In this world</h3>
          <p className="said">{site?.name ?? "this world"}{(editing ? world?.version : pinnedVersion ?? world?.version)
            ? `, version ${(editing ? world?.version : pinnedVersion ?? world?.version)!.ordinal}` : ""} · {things.length} things to work with</p>

          <h3>Where it goes in</h3>
          {editing ? (
            <>
              <select value={plan.launch?.from ?? (plan.launch?.x !== undefined ? "@" : "")}
                      onChange={(e) => {
                        const v = e.target.value;
                        if (v === "@") { setPlacingLaunch(true); return; }
                        setPlan((was) => ({ ...was, launch: v ? { from: v } : undefined }));
                      }}>
                <option value="">where the place says</option>
                {drawn.filter((one) => LAUNCHES.has(one.kind)).map((one) => (
                  <option key={one.id} value={one.id}>{one.kind} · {one.id.slice(0, 18)}</option>
                ))}
                <option value="@">a point in the world…</option>
              </select>
              {placingLaunch ? <p className="hint">click the ground where it goes in</p> : null}
            </>
          ) : <p className="said">{plan.launch?.from ? plan.launch.from : plan.launch?.x !== undefined ? `${plan.launch.x}, ${plan.launch.y}` : "where the place says"}</p>}

          {editing ? (
            <>
              <h3>Add a stage</h3>
              {STAGES.map((one) => (
                <button key={one.key} type="button" className="tool" title={one.asks}
                        onClick={() => {
                          const made: Stage = { ...(one.objective ?? {}), kind: kindOf(one) };
                          setPlan((was) => ({ ...was, stages: [...was.stages, made] }));
                          setChosen(plan.stages.length);
                          setDrawing(drawMode(made.kind) === "none" ? undefined : []);
                        }}>
                  <span className="mark"><TaskArt kind={kindOf(one)} /></span>
                  <span className="tool-says"><strong>{one.name}</strong><small>{one.asks}</small></span>
                </button>
              ))}
            </>
          ) : null}
        </div>

        <div className={drawing !== undefined || placingLaunch ? "chart drawing" : "chart"}
             onDoubleClick={() => { if (drawing !== undefined && mode === "route") finishDrawing(drawing); }}>
          {ground ? (
            <World3D ground={ground} glass={glass} items={shown} selected={[]} mode="place" snap={false} grid={false}
                     showing={{ terrain: true, water: true, structures: true, reef: true }} plan={in3D} api={view}
                     onPick={(where, how) => {
                       if (how.stage !== undefined && drawing === undefined && !placingLaunch) setChosen(how.stage);
                       else pick(where);
                     }}
                     onSelect={() => undefined} onTransformStart={() => undefined} onTransform={() => undefined} onTransformEnd={() => undefined}
                     onHover={(where) => setUnder(where ? groundAt(ground, where.x, where.y) : undefined)}
                     onHandle={editing ? handle : undefined} />
          ) : null}
          <div className="views">
            {(["top", "persp"] as ViewName[]).map((one) => (
              <button key={one} type="button" className="quiet" onClick={() => view.current?.view(one)}>{one === "top" ? "Top" : "3D"}</button>
            ))}
            <button type="button" className="quiet"
                    onClick={() => view.current?.frameOn(plan.stages.length ? extentOf(plan.stages, drawn, legs) : things.map(centreOf))}>Frame</button>
          </div>
          <div className="readout">
            <span>ground <b>{under === undefined ? "—" : `${under.toFixed(acrossM < 20 ? 2 : 1)} m`}</b></span>
            <span className="resolves">
              {placingLaunch ? "click where it goes in"
                : drawing !== undefined && at?.kind === "inspect" ? "click the thing to inspect"
                : drawing !== undefined && at ? drawPrompt(at.kind, drawing.length)
                : editing ? (at && drawMode(at.kind) !== "none" ? "drag the stage's points, or Draw it again" : "choose a stage, then Draw it")
                : "reading — Edit to change it"}
            </span>
            {drawing !== undefined && mode === "route" && drawing.length > 0 ? (
              <button type="button" className="finish" onClick={() => finishDrawing(drawing)}>Done</button>
            ) : null}
          </div>
          {ground === undefined ? <p className="no-chart">This world&rsquo;s terrain is still loading, or its package has no seabed.</p> : null}
        </div>

        <div className="stages">
          <h3>The work, in order</h3>
          {plan.stages.length === 0 ? (
            <p className="quiet">{editing ? "No stages yet: add one on the left, then draw it in the world." : "Nothing planned yet. Edit to add stages."}</p>
          ) : plan.stages.map((one, i) => {
            const leg = legs[i];
            const geo = leg ? geometryOf(one, drawn, leg.from) : undefined;
            return (
              <div key={i} className={i === chosen ? "stage on" : "stage"} onClick={() => { setChosen(i); setDrawing(undefined); }}>
                <span className="ordinal">{i + 1}</span>
                <span className="what">
                  <strong>{nameOf(one.kind)}</strong>
                  <small>
                    {one.over ? `over ${one.over.slice(0, 22)}` : geo?.drawn ? "drawn in the world" : drawMode(one.kind) === "none" ? "where it is" : "not drawn yet"}
                    {leg ? ` · ${leg.metres < 1000 ? `${leg.metres.toFixed(leg.metres < 10 ? 1 : 0)} m` : `${(leg.metres / 1000).toFixed(1)} km`} · ${minutes(leg.flyS)}` : ""}
                    {/* The runtime stops a stage at its allowance, unfinished. */}
                    {leg && leg.flyS > leg.allowS ? <span className="warn"> — stopped at {minutes(leg.allowS)}</span> : null}
                  </small>
                </span>
              </div>
            );
          })}

          {at !== undefined ? (
            <div className="detail">
              <h3>{nameOf(at.kind)} · stage {chosen + 1}</h3>
              {editing && mode !== "none" && mode !== "thing" ? (
                <button type="button" className={drawing !== undefined ? "draw on" : "draw"}
                        onClick={() => setDrawing(drawing === undefined ? [] : undefined)}>
                  {drawing !== undefined ? "Stop drawing" : geometryOf(at, drawn, legs[chosen]?.from ?? launch).drawn ? "Draw it again" : "Draw it"}
                </button>
              ) : null}
              {editing && (mode === "point" || mode === "area" || mode === "thing") && drawn.length > 0 ? (
                <label className="number">
                  <span>{mode === "thing" ? "follows" : "or over"}</span>
                  <select value={String(at.over ?? "")}
                          onChange={(e) => {
                            const over = e.target.value;
                            const { over: _o, ...rest } = at;
                            setStage(chosen, over ? { ...rest, over } as Stage : rest as Stage);
                          }}>
                    <option value="">{mode === "thing" ? "choose one" : "nothing drawn"}</option>
                    {drawn.filter((one) => (mode !== "area" || one.corners?.length) && (mode !== "thing" || one.route?.length)).map((one) => (
                      <option key={one.id} value={one.id}>{one.kind} · {one.id.slice(0, 16)}</option>
                    ))}
                  </select>
                </label>
              ) : null}
              {numbers.map(({ field, label, unit }) => (
                <label key={field} className="number">
                  <span>{label}</span>
                  <input type="number" disabled={!editing} value={String(at[field] ?? "")}
                         onChange={(e) => {
                           const said = e.target.value === "" ? undefined : Number(e.target.value);
                           let next: Stage = { ...at, [field]: said };
                           // A route's depth is each of its points' depth.
                           if (field === "depthM" && Array.isArray(at["points"])) {
                             next = { ...next, points: (at["points"] as P[]).map((p) => ({ ...p, depthM: said })) };
                           }
                           setStage(chosen, next);
                         }} />
                  <em>{unit}</em>
                </label>
              ))}
              {editing ? (
                <>
                  <div className="acts">
                    <button type="button" disabled={chosen === 0}
                            onClick={() => { setPlan((was) => ({ ...was, stages: swapped(was.stages, chosen, chosen - 1) })); setChosen(chosen - 1); }}>Earlier</button>
                    <button type="button" disabled={chosen >= plan.stages.length - 1}
                            onClick={() => { setPlan((was) => ({ ...was, stages: swapped(was.stages, chosen, chosen + 1) })); setChosen(chosen + 1); }}>Later</button>
                  </div>
                  <div className="acts">
                    <button type="button" onClick={() => {
                      setPlan((was) => ({ ...was, stages: [...was.stages.slice(0, chosen + 1), { ...at }, ...was.stages.slice(chosen + 1)] }));
                      setChosen(chosen + 1);
                    }}>Duplicate</button>
                    <button type="button" onClick={() => {
                      setPlan((was) => ({ ...was, stages: was.stages.filter((_, i) => i !== chosen) }));
                      setChosen(Math.max(0, chosen - 1)); setDrawing(undefined);
                    }}>Remove</button>
                  </div>
                </>
              ) : null}
            </div>
          ) : null}

          <div className="estimate">
            <h3>Checked against</h3>
            <select value={checkWith} onChange={(e) => setPicked(e.target.value)}>
              {held.vehicles.map((one) => <option key={one.id} value={one.id}>{one.name}</option>)}
            </select>
            <p>
              <b>{minutes(flyS)}</b> of flying
              {allowS > flyS ? <> · {minutes(allowS)} allowed</> : <span className="warn"> · more than the {minutes(allowS)} allowed</span>}
            </p>
            {spentWh !== undefined && usableWh > 0 ? (
              <p>
                {drew ? null : "at least "}
                <b>{spentWh < 1 ? spentWh.toFixed(2) : spentWh < 10 ? spentWh.toFixed(1) : Math.round(spentWh)} Wh</b> of {Math.round(usableWh)} usable
                {" "}({(100 * spentWh) / usableWh < 1 ? "under 1" : Math.round((100 * spentWh) / usableWh)}%)
                {spentWh > usableWh ? <span className="warn"> — more than the battery holds</span> : null}
              </p>
            ) : <p className="quiet">This vehicle&rsquo;s package does not say its battery.</p>}
            <p className="quiet">
              {pilot.holdsSpeed
                ? <>Flown the way the fins controller flies it: turning while it goes, at most ten degrees a second, at {settledMs(hull, pilot).toFixed(1)} m/s.{" "}</>
                : <>Flown the way the pursue controller flies it: turning to face each point, easing off
                  near it, at the {settledMs(hull).toFixed(2)} m/s this hull settles at.{" "}</>}
              {drew
                ? <>Battery at the {Math.round(drew.watts)} W it drew in the middle of its {drew.runs} run{drew.runs === 1 ? "" : "s"}{here.length ? " here" : " elsewhere"}.</>
                : <>It has not flown yet, so the battery is a floor — hotel load and drag; flown runs have drawn two to three times that.</>}
              {" "}Not counted: walls, a tether caught on something, a current, and how far its idea of where it is drifts.
            </p>
          </div>

          {editing ? (
            <>
              <button type="button" className="save" disabled={plan.stages.length === 0 || cityVersion === ""}
                      onClick={() => void save()}>
                Save as version {(newest?.ordinal ?? 0) + 1}
              </button>
              {cityVersion === "" ? <p className="quiet">This place has no published package to pin.</p> : null}
            </>
          ) : null}
          {saying ? <p className="quiet">{saying}</p> : null}
          {trouble ? <p className="trouble">{trouble}</p> : null}
        </div>
      </section>
    </>
  );
}

function swapped<T>(all: T[], a: number, b: number): T[] {
  const out = [...all];
  [out[a], out[b]] = [out[b]!, out[a]!];
  return out;
}
