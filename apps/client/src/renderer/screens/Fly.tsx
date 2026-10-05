// Fly a mission: once, or under everything that could go differently.
//
// Dive and Sweeps were two pages for one act. A sweep is a dive flown many
// times — once for each way the day could go — and a person could not tell
// that from two screens with two names. Here it is one page that starts from a
// plan of work:
//
//   what could go differently?  each card, one setting or several.
//     one setting is a decision: every run is flown that way.
//     two or more is a doubt: one run for each, and the runs multiply.
//
// Nothing in doubt is one dive, watched live if wanted. Anything in doubt is a
// sweep, read afterwards as which doubt breaks the plan and what saves it.
// A single task without a plan is the quick path beside it (the old Dive).

import React, { useCallback, useEffect, useMemo, useState } from "react";

import type { AssetVersion, Cost, Mission, Platform } from "@coral-city/api";

import { DOUBTS } from "../catalog/doubts.js";
import { driftRisks, DRIFT_SHARE, extentOf, hullOf, legsOf, pilotOf, type Drawn, type P, type Stage } from "../catalog/stages.js";
import { groundOf, SiteChart, type Frame, type Ground, type Thing } from "../parts/SiteChart.js";
import { drawStages } from "../parts/StagesLayer.js";
import { newestOf } from "../platform/packages.js";
import type { Held, Packages } from "./Deck.js";
import { BUILT_IN, MANUAL } from "./Dive.js";
import { PageHead } from "./parts.js";

interface Flyable { mission: Mission; version: AssetVersion; place: string }

/** The settings that change the world or the plan, not the water. */
const ELSEWHERE = new Set(["world", "objective"]);

function changesMoreThanWater(does: Record<string, unknown>): boolean {
  return Object.keys(does).some((k) => ELSEWHERE.has(k));
}

/** What was ticked, split three ways. */
export function split(picked: Record<string, string[]>): {
  water: Record<string, unknown>;
  decided: Record<string, Record<string, Record<string, unknown>>>;
  doubts: Record<string, Record<string, Record<string, unknown>>>;
  scenarios: number;
} {
  const water: Record<string, unknown> = {};
  const decided: Record<string, Record<string, Record<string, unknown>>> = {};
  const doubts: Record<string, Record<string, Record<string, unknown>>> = {};
  let scenarios = 1;
  for (const doubt of DOUBTS) {
    const on = doubt.settings.filter((s) => (picked[doubt.key] ?? []).includes(s.key));
    if (on.length === 1) {
      // A decision: water goes in the water; a moved mooring or a longer day
      // is a one-setting dimension, which the platform lays over the plan.
      if (changesMoreThanWater(on[0]!.does)) decided[doubt.key] = { [on[0]!.key]: on[0]!.does };
      else Object.assign(water, on[0]!.does);
    } else if (on.length > 1) {
      doubts[doubt.key] = Object.fromEntries(on.map((s) => [s.key, s.does]));
      scenarios *= on.length;
    }
  }
  return { water, decided, doubts, scenarios: Object.keys(doubts).length ? scenarios : 0 };
}

export function Fly({ platform, held, packages, mission: asked, onDiving, onSwept, onSingleTask, onDesign, onChanged }: {
  platform: Platform;
  held: Held;
  packages: Packages;
  mission?: string;
  onDiving: (dive: string, run: string) => void;
  onSwept: (sweep: string) => void;
  onSingleTask: () => void;
  onDesign: (mission: string, place: string) => void;
  onChanged: () => void;
}): React.JSX.Element {
  const [flyable, setFlyable] = useState<Flyable[] | undefined>();
  const [mission, setMission] = useState(asked ?? "");
  const [vehicle, setVehicle] = useState(() => held.vehicles[0]?.id ?? "");
  const [flownBy, setFlownBy] = useState(MANUAL);
  const [picked, setPicked] = useState<Record<string, string[]>>({ current: ["still"], fix: ["nothing"] });
  const [repeats, setRepeats] = useState(3);
  const [live, setLive] = useState(true);
  const [film, setFilm] = useState(false);
  const [cost, setCost] = useState<Cost | undefined>();
  const [ground, setGround] = useState<Ground | undefined>();
  const [things, setThings] = useState<Thing[]>([]);
  const [asking, setAsking] = useState(false);
  const [trouble, setTrouble] = useState("");

  // Every plan with something saved.
  useEffect(() => {
    let stale = false;
    void (async () => {
      const found: Flyable[] = [];
      for (const where of held.places) {
        for (const one of await platform.missionsOf(where.id).catch((): Mission[] => [])) {
          const saved = await platform.versionsOfMission(one.id).catch((): AssetVersion[] => []);
          if (saved[0] !== undefined) found.push({ mission: one, version: saved[0], place: where.id });
        }
      }
      if (stale) return;
      setFlyable(found);
      setMission((was) => was || found[0]?.mission.id || "");
    })();
    return () => { stale = true; };
  }, [platform, held.places]);

  const chosen = flyable?.find((one) => one.mission.id === mission);
  const plan = chosen?.version.document as { stages?: Stage[]; layoutVersionId?: string; launch?: { x?: number; y?: number } } | undefined;
  const pkg = chosen ? packages.places.get(chosen.place) ?? undefined : undefined;
  useEffect(() => { void groundOf(pkg).then(setGround); }, [pkg]);

  // The arrangement the plan pinned, to draw what it is over.
  useEffect(() => {
    setThings([]);
    if (!chosen || !plan?.layoutVersionId) return;
    let stale = false;
    void (async () => {
      for (const one of await platform.layoutsOf(chosen.place).catch(() => [])) {
        const versions = await platform.versionsOfLayout(one.id).catch((): AssetVersion[] => []);
        const pinned = versions.find((v) => v.id === plan.layoutVersionId);
        if (pinned) {
          if (!stale) setThings(((pinned.document as { things?: Thing[] } | undefined)?.things) ?? []);
          return;
        }
      }
    })();
    return () => { stale = true; };
  }, [platform, chosen, plan?.layoutVersionId]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!mission) { setCost(undefined); return; }
    let stale = false;
    void platform.missionCost(mission).then((one) => { if (!stale) setCost(one); })
      .catch(() => { if (!stale) setCost(undefined); });
    return () => { stale = true; };
  }, [platform, mission]);

  const stages = plan?.stages ?? [];
  const begin = pkg?.site?.beginAt;
  const launch: P = typeof plan?.launch?.x === "number" && typeof plan?.launch?.y === "number"
    ? { x: plan.launch.x, y: plan.launch.y } : { x: Number(begin?.[0] ?? 0), y: Number(begin?.[1] ?? 0) };
  const hull = useMemo(() => hullOf(packages.vehicles.get(vehicle)?.dynamics), [packages, vehicle]);
  const pilot = useMemo(() => pilotOf(packages.vehicles.get(vehicle)?.dynamics), [packages, vehicle]);
  const legs = useMemo(() => legsOf(stages, things as unknown as Drawn[], launch, hull, pilot),
    [stages, things, launch.x, launch.y, hull, pilot]); // eslint-disable-line react-hooks/exhaustive-deps
  const overlay = useCallback((g: CanvasRenderingContext2D, frame: Frame) =>
    drawStages(g, frame, stages, legs, things as unknown as Drawn[], undefined, launch),
  [stages, legs, things, launch.x, launch.y]); // eslint-disable-line react-hooks/exhaustive-deps

  const { water, decided, doubts, scenarios } = useMemo(() => split(picked), [picked]);
  // A tank is watched by its camera whatever is picked; open water is not.
  const enclosed = Boolean((pkg?.site as { enclosed?: boolean } | undefined)?.enclosed);
  const risks = !enclosed && (picked["fix"] ?? []).includes("nothing") ? driftRisks(stages, legs) : [];
  const once = scenarios === 0 && Object.keys(decided).length === 0;
  const runs = once ? 1 : Math.max(1, scenarios) * repeats;
  const stack = held.stacks.find((s) => s.id === flownBy);
  const builtIn = BUILT_IN.find((one) => one.key === flownBy)?.key;
  const chosenVehicle = held.vehicles.find((v) => v.id === vehicle);

  const go = useCallback(async () => {
    const queue = held.queues[0];
    if (!chosen || !chosenVehicle || held.institution === undefined || queue === undefined) return;
    const runtime = queue.runtimes?.[0];
    if (runtime === undefined) { setTrouble("No machine on that queue has said what it can run yet."); return; }
    setAsking(true); setTrouble("");
    try {
      const published = newestOf(await platform.versionsOfVehicle(chosenVehicle.id));
      if (published === undefined) { setTrouble(`${chosenVehicle.name} has no published package yet.`); return; }
      if (once) {
        const conditions = await platform.defineConditions(held.institution.id, {
          kind: "constructed", name: describe(picked), parameters: water,
        });
        const defined = await platform.defineDive(held.institution.id, {
          name: `${chosen.mission.name} · ${chosenVehicle.name}`,
          missionVersionId: chosen.version.id,
          vehicleVersionId: published.id,
          conditionsId: conditions.id,
          autonomyStackId: stack?.id,
          objective: {
            ...(builtIn === undefined ? {} : { controller: builtIn }),
            // Unwatched and not filmed: flown undrawn, fifteen times faster.
            ...(live ? {} : { pictures: film }),
          },
        });
        const run = await platform.ask(defined.id, { queueId: queue.id, mode: live ? "interactive" : "batch", runtimeVersion: runtime });
        onChanged();
        if (live) onDiving(defined.id, run.id);
        else setTrouble("Queued — it is in Results.");
        return;
      }
      const made = await platform.startSweep(held.institution.id, {
        name: `${chosen.mission.name} ~ ${new Date().toLocaleDateString(undefined, { day: "numeric", month: "long" })}`,
        missionVersionId: chosen.version.id,
        vehicleVersionId: published.id,
        water,
        doubts: { ...doubts, ...decided } as never,
        repeats: scenarios === 0 ? 1 : repeats,
        queueId: queue.id,
        runtimeVersion: runtime,
      });
      onChanged();
      onSwept(made.id);
    } catch (thrown) {
      setTrouble(thrown instanceof Error ? thrown.message : "it would not start");
    } finally {
      setAsking(false);
    }
  }, [platform, held, chosen, chosenVehicle, once, picked, water, doubts, decided, scenarios, repeats, stack, builtIn, live, film, onDiving, onSwept, onChanged]);

  const hours = cost?.hours && !cost.notEnough ? cost.hours : undefined;
  const machines = Math.max(1, held.queues[0]?.devices ?? 1);

  return (
    <>
      <PageHead title="Fly" says="A plan of work, flown once or under everything that could go differently on the day."
                aside={<button type="button" className="quiet" onClick={onSingleTask}>A single task instead</button>} />

      {flyable !== undefined && flyable.length === 0 ? (
        <section><p className="quiet">There is no plan with anything saved yet. Draw one in Missions, or fly a single task.</p></section>
      ) : (
        <section className="fly">
          <div className="what">
            <label><span>The plan</span>
              <select value={mission} onChange={(e) => setMission(e.target.value)}>
                {(flyable ?? []).map(({ mission: one, place, version }) => (
                  <option key={one.id} value={one.id}>{one.name} · {held.places.find((p) => p.id === place)?.name} · v{version.ordinal}</option>
                ))}
              </select>
            </label>
            <div className="preview">
              <SiteChart ground={ground} things={things} faintThings overlay={overlay} redraw={stages} cursor="default"
                         key={chosen?.mission.id} fit={extentOf(stages, things as unknown as Drawn[], legs)} />
            </div>
            {risks.length > 0 ? (
              <p className="warn">
                With nothing overhead it navigates by dead reckoning, which drifted {(DRIFT_SHARE * 100).toFixed(1)}% of
                the distance flown when it was measured. By stage {risks[0]!.stage + 1} that is about{" "}
                {risks[0]!.driftM.toFixed(risks[0]!.driftM < 10 ? 1 : 0)} m, wider than its {risks[0]!.radiusM} m radius
                {risks.length > 1 ? `, and ${risks.length - 1} more stage${risks.length > 2 ? "s" : ""} after it` : ""}:
                it will believe it is there and miss. Widen the radius, or give it a fix.
              </p>
            ) : null}
            {chosen ? (
              <p className="quiet">
                {stages.length} {stages.length === 1 ? "stage" : "stages"} ·{" "}
                {cost?.runs ? `flown ${cost.runs} ${cost.runs === 1 ? "time" : "times"}` : "never flown"} ·{" "}
                <a onClick={() => onDesign(chosen.mission.id, chosen.place)}>open on its chart</a>
              </p>
            ) : null}
            <label><span>Flown in</span>
              <select value={vehicle} onChange={(e) => setVehicle(e.target.value)}>
                {held.vehicles.map((one) => <option key={one.id} value={one.id}>{one.name}</option>)}
              </select>
            </label>
            {once ? (
              <label><span>Flown by</span>
                <select value={flownBy} onChange={(e) => setFlownBy(e.target.value)}>
                  <option value={MANUAL}>you, at the keys</option>
                  {BUILT_IN.map((one) => <option key={one.key} value={one.key}>{one.name}</option>)}
                  {held.stacks.map((one) => <option key={one.id} value={one.id}>{one.name}</option>)}
                </select>
              </label>
            ) : <p className="quiet">A sweep is flown by the plan&rsquo;s own controller, the same in every run.</p>}
          </div>

          <div className="day">
            <h2>What could go differently?</h2>
            <p className="quiet">One setting on a card is a decision, and every run is flown that way. Two or more is a doubt: one run for each, and the runs multiply.</p>
            <div className="doubts">
              {DOUBTS.map((doubt) => {
                const on = picked[doubt.key] ?? [];
                return (
                  <div key={doubt.key} className={on.length > 1 ? "doubt on" : on.length === 1 ? "doubt set" : "doubt"}>
                    <strong>{doubt.name}</strong>
                    <small>{doubt.says}</small>
                    <div className="settings">
                      {doubt.settings.map((one) => (
                        <button key={one.key} type="button" aria-pressed={on.includes(one.key)}
                                className={on.includes(one.key) ? "setting on" : "setting"}
                                onClick={() => setPicked((was) => {
                                  const had = was[doubt.key] ?? [];
                                  return { ...was, [doubt.key]: had.includes(one.key) ? had.filter((k) => k !== one.key) : [...had, one.key] };
                                })}>
                          {one.name}
                        </button>
                      ))}
                    </div>
                    <small className="state">{on.length === 0 ? "as the plan has it" : on.length === 1 ? "decided" : `in doubt · ${on.length} ways`}</small>
                  </div>
                );
              })}
            </div>
          </div>

          <div className="go">
            {once ? (
              <>
                <label className="check"><input type="checkbox" checked={live} onChange={(e) => setLive(e.target.checked)} /> watch it live</label>
                {!live ? <label className="check"><input type="checkbox" checked={film} onChange={(e) => setFilm(e.target.checked)} /> and make a film of it (much slower)</label> : null}
                <span className="quiet">One dive{hours ? `, about ${Math.round(hours * 60)} minutes` : ""}.</span>
              </>
            ) : (
              <>
                {scenarios > 0 ? (
                  <label><span>each way, how many times</span>
                    <select value={repeats} onChange={(e) => setRepeats(Number(e.target.value))}>
                      {[1, 3, 5, 10].map((n) => <option key={n} value={n}>{n === 1 ? "once — a coin flip looks like a finding" : `${n} times`}</option>)}
                    </select>
                  </label>
                ) : null}
                <span className="quiet">
                  {scenarios > 0 ? `${scenarios} ways × ${repeats} = ${runs} runs` : "One run, with the world or the plan changed as decided"}
                  {hours ? ` · about ${((hours * runs) / machines).toFixed(1)} hours on ${machines} machine${machines === 1 ? "" : "s"}` : ""}.
                </span>
              </>
            )}
            <button type="button" className="big" disabled={asking || !chosen || !chosenVehicle} onClick={() => void go()}>
              {asking ? "Asking for water…" : once ? (live ? "Fly it, watching" : "Fly it") : scenarios > 0 ? "Sweep it" : "Fly it"}
            </button>
          </div>
          {trouble ? <p className="trouble">{trouble}</p> : null}
        </section>
      )}
    </>
  );
}

/** A name for the water, from what was decided. */
function describe(picked: Record<string, string[]>): string {
  const said = DOUBTS.flatMap((d) => d.settings.filter((s) => (picked[d.key] ?? []).includes(s.key)).map((s) => s.name));
  return said.length ? said.join(" · ") : "As the plan has it";
}
