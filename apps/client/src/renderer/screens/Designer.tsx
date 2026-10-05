// A plan of work, on its place's chart.
//
// A mission is a place, the arrangement it was planned over, and the work in
// order. It used to be written as a list with nothing to look at: a survey was
// "sixty by thirty metres ahead of wherever the vehicle begins", and where that
// fell on the reef was found out by flying it. Here every stage is drawn where
// it happens — the route as clicked points, a survey as the rectangle it
// covers, a transect as its line, an inspection as a ring round what is
// inspected — in the place's own frame, which is the frame the runtime flies a
// drawn stage in.
//
// It opens to read. Editing is a choice, and every save is a new version:
// runs pin a version, and a result has to keep meaning what it meant.

import React, { useCallback, useEffect, useMemo, useState } from "react";

import type { AssetVersion, Layout, Mission, Platform } from "@coral-city/api";

import { TASKS, type Task } from "../catalog/tasks.js";
import {
  drawMode, drawnInto, drawPrompt, extentOf, floorWatts, geometryOf, hullOf, legsOf, settledMs, snap, wattsOf,
  type Drawn, type P, type Stage,
} from "../catalog/stages.js";
import { centreOf, groundOf, SiteChart, type Frame, type Ground, type Thing } from "../parts/SiteChart.js";
import { drawStages } from "../parts/StagesLayer.js";
import { TaskArt } from "../parts/TaskArt.js";
import { newestOf } from "../platform/packages.js";
import type { Held, Packages } from "./Deck.js";
import { Empty, PageHead, Pill } from "./parts.js";

/** What a plan of work says. */
interface Plan {
  cityVersionId?: string;
  layoutVersionId?: string;
  /** Where the vehicle goes in: a drawn thing, or a point. */
  launch?: { from?: string; x?: number; y?: number };
  stages: Stage[];
}

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

/** Where the dive begins, on the chart. */
function launchAt(plan: Plan, things: Drawn[], fallback: P): P {
  const named = plan.launch?.from ? things.find((t) => t.id === plan.launch!.from) : undefined;
  if (named) return { x: named.x, y: named.y };
  if (typeof plan.launch?.x === "number" && typeof plan.launch?.y === "number") return { x: plan.launch.x, y: plan.launch.y };
  return fallback;
}

export function Designer({ platform, held, packages, mission, place, onBack, onFly }: {
  platform: Platform;
  held: Held;
  packages: Packages;
  mission: string;
  place: string;
  onBack: () => void;
  onFly: (mission: string) => void;
}): React.JSX.Element {
  const [found, setFound] = useState<Mission | undefined>();
  const [missing, setMissing] = useState(false);
  const [ground, setGround] = useState<Ground | undefined>();
  const [layouts, setLayouts] = useState<Layout[]>([]);
  const [layoutVersions, setLayoutVersions] = useState<Map<string, AssetVersion>>(new Map());
  const [cityVersion, setCityVersion] = useState("");
  const [saved, setSaved] = useState<AssetVersion[]>([]);

  const [layout, setLayout] = useState("");
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

  useEffect(() => {
    let stale = false;
    void platform.mission(mission).then((one) => { if (!stale) setFound(one); })
      .catch(() => { if (!stale) setMissing(true); });
    return () => { stale = true; };
  }, [platform, mission]);

  // Which vehicle each run flew: a run names a version, and the estimate wants
  // every run of a vehicle, whichever version of it.
  useEffect(() => {
    let stale = false;
    void Promise.all(held.vehicles.map(async (one) =>
      (await platform.versionsOfVehicle(one.id).catch((): AssetVersion[] => [])).map((v) => [v.id, one.id] as const)))
      .then((pairs) => { if (!stale) setVehicleOf(new Map(pairs.flat())); });
    return () => { stale = true; };
  }, [platform, held.vehicles]);

  // The place, pinned, and every arrangement of it with what it holds.
  useEffect(() => {
    let stale = false;
    void (async () => {
      const [cities, made] = await Promise.all([
        platform.versionsOfPlace(place).catch((): AssetVersion[] => []),
        platform.layoutsOf(place).catch((): Layout[] => []),
      ]);
      if (stale) return;
      setCityVersion(newestOf(cities)?.id ?? "");
      setPlaceVersions(new Set(cities.map((one) => one.id)));
      setLayouts(made);
      const newest = new Map<string, AssetVersion>();
      for (const one of made) {
        const versions = await platform.versionsOfLayout(one.id).catch((): AssetVersion[] => []);
        if (versions[0] !== undefined) newest.set(one.id, versions[0]);
      }
      if (!stale) setLayoutVersions(newest);
    })();
    return () => { stale = true; };
  }, [platform, place]);

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

  // The arrangement it was saved over, once the arrangements are known.
  // Pinned: the version the plan names, not whatever that arrangement says now.
  const [pinnedThings, setPinnedThings] = useState<Thing[] | undefined>();
  useEffect(() => {
    if (!plan.layoutVersionId) { setPinnedThings(undefined); return; }
    const owner = layouts.find((one) => layoutVersions.get(one.id)?.id === plan.layoutVersionId);
    if (owner && layout === "") setLayout(owner.id);
    let stale = false;
    void (async () => {
      for (const one of layouts) {
        const versions = await platform.versionsOfLayout(one.id).catch((): AssetVersion[] => []);
        const pinned = versions.find((v) => v.id === plan.layoutVersionId);
        if (pinned) {
          if (!stale) {
            setLayout((was) => was || one.id);
            setPinnedThings(((pinned.document as { things?: Thing[] } | undefined)?.things) ?? []);
          }
          return;
        }
      }
    })();
    return () => { stale = true; };
  }, [platform, layouts, layoutVersions, plan.layoutVersionId]); // eslint-disable-line react-hooks/exhaustive-deps

  // What is laid out: the pinned version when reading; the newest of the
  // chosen arrangement when that has been changed while editing.
  const things: Thing[] = useMemo(() => {
    const chosenVersion = layoutVersions.get(layout);
    if (chosenVersion && chosenVersion.id !== plan.layoutVersionId) {
      return ((chosenVersion.document as { things?: Thing[] } | undefined)?.things) ?? [];
    }
    return pinnedThings ?? [];
  }, [layout, layoutVersions, plan.layoutVersionId, pinnedThings]);
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
  const legs = useMemo(() => legsOf(plan.stages, drawn, launch, hull),
    [plan.stages, drawn, launch.x, launch.y, hull]); // eslint-disable-line react-hooks/exhaustive-deps
  const flyS = legs.reduce((s, l) => s + l.flyS, 0);
  const allowS = legs.reduce((s, l) => s + l.allowS, 0);
  const usableWh = (dyn?.power?.capacityWh ?? 0) * (1 - (dyn?.power?.reserveFraction ?? 0.1));
  // What it draws: the middle of what its runs here drew, or anywhere if it
  // has not flown here; a floor from its hull when it has never flown.
  const ofIt = held.runs.filter((r) => vehicleOf.get(r.vehicleVersion ?? "") === checkWith);
  const here = ofIt.filter((r) => placeVersions.has(r.placeVersion ?? ""));
  const drew = wattsOf((here.length ? here : ofIt).map((r) => r.run.outcome as Record<string, unknown> | undefined));
  const watts = drew?.watts ?? (dyn?.power?.hotelW !== undefined ? floorWatts(hull, dyn.power.hotelW) : undefined);
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
    const clicks = [...drawing, p];
    if ((mode === "point" && clicks.length >= 1) || ((mode === "line" || mode === "area") && clicks.length >= 2)) {
      finishDrawing(clicks);
      return;
    }
    setDrawing(clicks);
  }, [acrossM, placingLaunch, drawing, legs, mode, finishDrawing]);

  // The plan over the chart: the transit between stages dashed, each stage
  // drawn as what it is, the chosen one in the vehicle's colour, numbered.
  const overlay = useCallback((g: CanvasRenderingContext2D, frame: Frame) => {
    drawStages(g, frame, plan.stages, legs, drawn, chosen, launch);
    const { toX, toY } = frame;

    // What is being drawn, before it is finished.
    if (drawing?.length) {
      g.strokeStyle = "#f0a84f"; g.fillStyle = "#f0a84f"; g.lineWidth = 2; g.setLineDash([2, 3]);
      g.beginPath();
      drawing.forEach((p, k) => (k === 0 ? g.moveTo(toX(p.x), toY(p.y)) : g.lineTo(toX(p.x), toY(p.y))));
      g.stroke(); g.setLineDash([]);
      drawing.forEach((p) => { g.beginPath(); g.arc(toX(p.x), toY(p.y), 4, 0, Math.PI * 2); g.fill(); });
    }
  }, [plan.stages, legs, drawn, chosen, drawing, launch.x, launch.y]); // eslint-disable-line react-hooks/exhaustive-deps

  const save = useCallback(async () => {
    const pinned = layoutVersions.get(layout);
    setSaying("saving"); setTrouble("");
    try {
      const version = await platform.saveMission(mission, {
        describedBy: "coral-city/mission/v1",
        cityVersionId: cityVersion,
        layoutVersionId: pinned?.id ?? plan.layoutVersionId ?? "",
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
  }, [platform, mission, cityVersion, layoutVersions, layout, plan, readSaved]);

  if (missing) return <Empty title="Not a plan you have">It may have been archived, or you were never granted it.</Empty>;

  const numbers = at === undefined ? [] : [...(NUMBERS[at.kind] ?? []), ALLOW];
  const newest = saved[0];

  return (
    <>
      <PageHead title={found?.name ?? "A plan of work"}
                says={`${site?.name ?? "a place"}${newest ? ` · version ${newest.ordinal}` : " · not saved yet"}${found?.summary ? ` · ${found.summary}` : ""}`}
                back="Missions" onBack={onBack}
                aside={<span className="designer-acts">
                  <Pill>{minutes(flyS)} flying · {minutes(allowS)} allowed</Pill>
                  {editing
                    ? <button type="button" className="quiet" onClick={() => { setEditing(false); setDrawing(undefined); readSaved(); }}>Discard</button>
                    : <button type="button" className="quiet" onClick={() => setEditing(true)}>Edit</button>}
                  {!editing && newest ? <button type="button" onClick={() => onFly(mission)}>Fly it</button> : null}
                </span>} />

      <section className={editing ? "designer editing" : "designer"}>
        <div className="palette">
          <h3>Over which arrangement</h3>
          {editing ? (
            <select value={layout} onChange={(e) => setLayout(e.target.value)}>
              <option value="">none — bare ground</option>
              {layouts.map((one) => (
                <option key={one.id} value={one.id} disabled={!layoutVersions.has(one.id)}>
                  {one.name}{layoutVersions.has(one.id) ? "" : " (nothing saved)"}
                </option>
              ))}
            </select>
          ) : <p className="said">{layouts.find((one) => one.id === layout)?.name ?? "bare ground"}</p>}
          <p className="quiet">Pinned: it is flown over the arrangement as it was when the plan was saved.</p>

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
                <option value="@">a point on the chart…</option>
              </select>
              {placingLaunch ? <p className="hint">click the chart where it goes in</p> : null}
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
                  <span className="mark"><TaskArt kind={kindOf(one)} /></span>{one.name}
                </button>
              ))}
            </>
          ) : null}
        </div>

        <div className="chart">
          <SiteChart ground={ground} things={things} faintThings overlay={overlay} redraw={plan} key={mission}
                     fit={plan.stages.length ? extentOf(plan.stages, drawn, legs) : things.map(centreOf)}
                     cursor={drawing !== undefined || placingLaunch ? "crosshair" : "default"}
                     onPick={(where) => pick(where)}
                     onDoublePick={() => { if (drawing !== undefined && mode === "route") finishDrawing(drawing); }}
                     onHover={(_, depth) => setUnder(depth)} />
          <div className="readout">
            <span>ground <b>{under === undefined ? "—" : `${under.toFixed(acrossM < 20 ? 2 : 1)} m`}</b></span>
            <span className="resolves">
              {placingLaunch ? "click where it goes in"
                : drawing !== undefined && at ? drawPrompt(at.kind, drawing.length)
                : editing ? "choose a stage, then Draw it" : "reading — Edit to change it"}
            </span>
            {drawing !== undefined && mode === "route" && drawing.length > 0 ? (
              <button type="button" className="finish" onClick={() => finishDrawing(drawing)}>Done</button>
            ) : null}
          </div>
          {ground === undefined ? <p className="no-chart">This place&rsquo;s chart is still loading, or its package has no seabed.</p> : null}
        </div>

        <div className="stages">
          <h3>The work, in order</h3>
          {plan.stages.length === 0 ? (
            <p className="quiet">{editing ? "No stages yet: add one on the left, then draw it on the chart." : "Nothing planned yet. Edit to add stages."}</p>
          ) : plan.stages.map((one, i) => {
            const leg = legs[i];
            const geo = leg ? geometryOf(one, drawn, leg.from) : undefined;
            return (
              <div key={i} className={i === chosen ? "stage on" : "stage"} onClick={() => { setChosen(i); setDrawing(undefined); }}>
                <span className="ordinal">{i + 1}</span>
                <span className="what">
                  <strong>{nameOf(one.kind)}</strong>
                  <small>
                    {one.over ? `over ${one.over.slice(0, 22)}` : geo?.drawn ? "drawn on the chart" : drawMode(one.kind) === "none" ? "where it is" : "not drawn yet"}
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
              Flown the way the pursue controller flies it: turning to face each point, easing off
              near it, at the {settledMs(hull).toFixed(2)} m/s this hull settles at.{" "}
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
