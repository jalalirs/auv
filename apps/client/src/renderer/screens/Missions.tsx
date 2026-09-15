// What work is planned, and where.
//
// A mission is the thing a reef programme actually owns: this place, arranged
// this way, these stages in this order. Until it existed here, a plan of work
// lived inside one dive's objective and died with that dive — which meant two
// people could not fly the same round, and nothing could be compared.
//
// Unlike a layout, this *is* a top-level noun. A layout is an arrangement of
// somewhere and means nothing away from it; a plan of work is the unit of work
// itself, the thing somebody comes in to write and comes back to fly. It pins
// a place and an arrangement of it — that is what makes two runs comparable —
// but it is not filed under either.

import { useCallback, useEffect, useMemo, useState } from "react";

import type { AssetVersion, Layout, Mission, Platform } from "@coral-city/api";

import { TASKS, type Task } from "../catalog/tasks.js";
import { TaskArt } from "../parts/TaskArt.js";
import { newestOf } from "../platform/packages.js";
import type { Held } from "./Deck.js";
import { Empty, PageHead, Pill } from "./parts.js";

/** One thing somebody drew, as a stage can point at it. */
interface Drawn { id: string; kind: string }

/** One stage of a plan, as the document carries it. */
type Stage = Record<string, unknown> & { kind: string; over?: string };

/** What a plan of work says. */
interface Plan {
  cityVersionId?: string;
  layoutVersionId?: string;
  stages: Stage[];
}

/** The stages a person can add, in the order the palette offers them. */
const STAGES: Task[] = TASKS.filter((one) => one.unavailable === undefined);

/** Which numbers are worth showing on a stage row, per kind of work. */
const NUMBERS: Record<string, { field: string; label: string; unit: string }[]> = {
  survey: [{ field: "altitudeM", label: "altitude", unit: "m" },
           { field: "timeLimitS", label: "allow", unit: "s" }],
  transect: [{ field: "lengthM", label: "length", unit: "m" },
             { field: "altitudeM", label: "altitude", unit: "m" },
             { field: "timeLimitS", label: "allow", unit: "s" }],
  inspect: [{ field: "radiusM", label: "stand off", unit: "m" },
            { field: "timeLimitS", label: "allow", unit: "s" }],
  treat: [{ field: "altitudeM", label: "altitude", unit: "m" },
          { field: "timeLimitS", label: "allow", unit: "s" }],
  outplant: [{ field: "timeLimitS", label: "allow", unit: "s" }],
  monitor: [{ field: "altitudeM", label: "altitude", unit: "m" },
            { field: "timeLimitS", label: "allow", unit: "s" }],
};
const ALLOW_ONLY = [{ field: "timeLimitS", label: "allow", unit: "s" }];

/** How long a plan will take, which is what decides how long the dive gets. */
function howLong(stages: Stage[]): number {
  return stages.reduce((total, one) => {
    const limit = Number(one["timeLimitS"] ?? one["seconds"] ?? 300);
    return total + (Number.isFinite(limit) ? limit : 300);
  }, 0);
}

function minutes(seconds: number): string {
  if (seconds < 90) return `${Math.round(seconds)} s`;
  return `${Math.round(seconds / 60)} min`;
}

// ── the list ─────────────────────────────────────────────────────────────────

export function Missions({ platform, held, onOpen }: {
  platform: Platform;
  held: Held;
  onOpen: (mission: string, place: string) => void;
}): React.JSX.Element {
  const [missions, setMissions] = useState<{ place: string; of: Mission[] }[]>([]);
  const [where, setWhere] = useState<string>(() => held.places[0]?.id ?? "");
  const [naming, setNaming] = useState("");
  const [trouble, setTrouble] = useState("");

  const read = useCallback(() => {
    let stale = false;
    void Promise.all(held.places.map(async (place) => ({
      place: place.id,
      of: await platform.missionsOf(place.id).catch((): Mission[] => []),
    }))).then((found) => { if (!stale) setMissions(found); });
    return () => { stale = true; };
  }, [platform, held.places]);
  useEffect(read, [read]);

  const all = missions.flatMap((one) =>
    one.of.map((mission) => ({ mission, place: one.place })));

  return (
    <>
      <PageHead title="Missions" says="A place, an arrangement of it, and the work in order — written once, flown by anybody, and comparable across both."
                aside={<Pill>{all.length} {all.length === 1 ? "plan" : "plans"}</Pill>} />

      <section>
        {all.length === 0 ? (
          <p className="quiet">
            Nothing is planned yet. A mission pins a place and a layout of it,
            so the first step is a place that has been laid out — Places, then
            an arrangement, then come back here.
          </p>
        ) : (
          <div className="rows">
            {all.map(({ mission, place }) => (
              <button key={mission.id} type="button" className="row open"
                      onClick={() => onOpen(mission.id, place)}>
                <span className="what">{mission.name}</span>
                <span className="quiet">
                  {held.places.find((p) => p.id === place)?.name ?? "somewhere"}
                  {mission.summary ? ` · ${mission.summary}` : ""}
                </span>
              </button>
            ))}
          </div>
        )}

        <form className="naming" onSubmit={(event) => {
          event.preventDefault();
          const name = naming.trim();
          if (!name || !where) return;
          const slug = name.toLowerCase().replace(/[^a-z0-9]+/g, "-")
            .replace(/^-+|-+$/g, "").slice(0, 62);
          void platform.startMission(where, { slug, name })
            .then((made) => { setNaming(""); setTrouble(""); onOpen(made.id, where); })
            .catch((thrown: unknown) =>
              setTrouble(thrown instanceof Error ? thrown.message : "it would not start"));
        }}>
          <select value={where} onChange={(e) => setWhere(e.target.value)}>
            {held.places.map((one) => <option key={one.id} value={one.id}>{one.name}</option>)}
          </select>
          <input value={naming} onChange={(e) => setNaming(e.target.value)}
                 placeholder="name a new plan of work" />
          <button type="submit" disabled={!naming.trim() || !where}>Plan one</button>
        </form>
        {trouble ? <p className="trouble">{trouble}</p> : null}
      </section>
    </>
  );
}

// ── writing one ──────────────────────────────────────────────────────────────

export function Planning({ platform, held, mission, place, onBack }: {
  platform: Platform;
  held: Held;
  mission: string;
  place: string;
  onBack: () => void;
}): React.JSX.Element {
  const [found, setFound] = useState<Mission | undefined>();
  const [missing, setMissing] = useState(false);
  const [layouts, setLayouts] = useState<Layout[]>([]);
  // The newest saved version of each arrangement, and what is drawn in it.
  const [versions, setVersions] = useState<Map<string, AssetVersion>>(new Map());
  const [cityVersion, setCityVersion] = useState<string>("");
  const [layout, setLayout] = useState<string>("");
  const [stages, setStages] = useState<Stage[]>([]);
  const [chosen, setChosen] = useState(0);
  const [saving, setSaving] = useState("");
  const [trouble, setTrouble] = useState("");

  useEffect(() => {
    let stale = false;
    void platform.mission(mission)
      .then((one) => { if (!stale) setFound(one); })
      .catch(() => { if (!stale) setMissing(true); });
    return () => { stale = true; };
  }, [platform, mission]);

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
      setLayouts(made);
      const newest = new Map<string, AssetVersion>();
      for (const one of made) {
        const saved = await platform.versionsOfLayout(one.id).catch((): AssetVersion[] => []);
        if (saved[0] !== undefined) newest.set(one.id, saved[0]);
      }
      if (!stale) setVersions(newest);
    })();
    return () => { stale = true; };
  }, [platform, place]);

  // What was written last, so opening a plan shows it.
  useEffect(() => {
    let stale = false;
    void platform.versionsOfMission(mission).then((saved) => {
      const document = saved[0]?.document as Plan | undefined;
      if (stale || document === undefined) return;
      setStages(document.stages ?? []);
      const was = layouts.find((one) => versions.get(one.id)?.id === document.layoutVersionId);
      if (was !== undefined) setLayout(was.id);
    }).catch(() => undefined);
    return () => { stale = true; };
  }, [platform, mission, layouts, versions]);

  // Which arrangement this is over, and what is drawn in it for a stage to
  // point at. Nothing is offered that is not in the water.
  const drawn: Drawn[] = useMemo(() => {
    const document = versions.get(layout)?.document as { things?: Drawn[] } | undefined;
    return document?.things ?? [];
  }, [versions, layout]);

  const save = useCallback(async () => {
    const pinned = versions.get(layout);
    setSaving("saving"); setTrouble("");
    try {
      const version = await platform.saveMission(mission, {
        describedBy: "coral-city/mission/v1",
        cityVersionId: cityVersion,
        layoutVersionId: pinned?.id ?? "",
        stages,
      } as never, `${stages.length} stages`);
      setSaving(`saved as version ${version.ordinal}`);
    } catch (thrown) {
      setSaving("");
      setTrouble(thrown instanceof Error ? thrown.message : "it would not save");
    }
  }, [platform, mission, cityVersion, versions, layout, stages]);

  if (missing) {
    return <Empty title="Not a plan you have">It may have been withdrawn, or you were never granted it.</Empty>;
  }
  const at = stages[chosen];
  const numbers = at === undefined ? [] : (NUMBERS[at.kind] ?? ALLOW_ONLY);
  const site = held.places.find((p) => p.id === place);

  return (
    <>
      <PageHead title={found?.name ?? "A plan of work"}
                says={found?.summary || `over ${site?.name ?? "a place"}`}
                back="Missions" onBack={onBack}
                aside={<Pill>{minutes(howLong(stages))} of work</Pill>} />

      <section className="planning">
        <div className="tools">
          <h3>Over which arrangement</h3>
          <select value={layout} onChange={(e) => setLayout(e.target.value)}>
            <option value="">none — bare ground</option>
            {layouts.map((one) => (
              <option key={one.id} value={one.id} disabled={!versions.has(one.id)}>
                {one.name}{versions.has(one.id) ? "" : " (nothing saved)"}
              </option>
            ))}
          </select>
          <p className="quiet">Pinned, not followed: September gets the site as
            it was in March.</p>
          <h3>Add a stage</h3>
          {STAGES.map((one) => (
            <button key={one.key} type="button" className="tool"
                    title={one.asks}
                    onClick={() => {
                      const made: Stage = { ...(one.objective ?? {}), kind: String(one.objective?.["kind"] ?? one.key) };
                      setStages((was) => [...was, made]);
                      setChosen(stages.length);
                    }}>
              {one.name}
            </button>
          ))}
        </div>

        <div className="order">
          {stages.length === 0 ? (
            <p className="quiet">
              No stages yet. A plan is what to do, in order — pick from the left.
            </p>
          ) : stages.map((one, at_) => (
            <div key={at_} className={at_ === chosen ? "stage on" : "stage"}
                 onClick={() => setChosen(at_)}>
              <span className="mark"><TaskArt kind={one.kind} /></span>
              <span className="what">
                <strong>{STAGES.find((s) => String(s.objective?.["kind"] ?? s.key) === one.kind)?.name ?? one.kind}</strong>
                <small>
                  {one.over ? `over ${one.over}` : "where the vehicle is"}
                  {" · "}{minutes(Number(one["timeLimitS"] ?? one["seconds"] ?? 300))}
                </small>
              </span>
              <span className="ordinal">{at_ + 1}</span>
            </div>
          ))}
        </div>

        <div className="detail">
          {at === undefined ? (
            <p className="quiet">Pick a stage to say what it is over.</p>
          ) : (
            <>
              <h3>What it is over</h3>
              <select value={String(at.over ?? "")}
                      onChange={(e) => {
                        const over = e.target.value;
                        setStages((was) => was.map((one, i) => i !== chosen ? one
                          : over === "" ? withoutOver(one) : { ...one, over }));
                      }}>
                <option value="">nothing — where the vehicle is</option>
                {drawn.map((one) => (
                  <option key={one.id} value={one.id}>{one.id} · {one.kind}</option>
                ))}
              </select>
              {layout === "" ? (
                <p className="quiet">
                  Choose an arrangement on the left and its things can be
                  pointed at by name.
                </p>
              ) : null}

              <h3>Numbers</h3>
              {numbers.map(({ field, label, unit }) => (
                <label key={field} className="number">
                  <span>{label}</span>
                  <input type="number" value={String(at[field] ?? "")}
                         onChange={(e) => {
                           const said = e.target.value === "" ? undefined : Number(e.target.value);
                           setStages((was) => was.map((one, i) => i !== chosen ? one
                             : { ...one, [field]: said }));
                         }} />
                  <em>{unit}</em>
                </label>
              ))}

              <div className="acts">
                <button type="button" disabled={chosen === 0}
                        onClick={() => { setStages((was) => swapped(was, chosen, chosen - 1)); setChosen(chosen - 1); }}>
                  Earlier
                </button>
                <button type="button" disabled={chosen >= stages.length - 1}
                        onClick={() => { setStages((was) => swapped(was, chosen, chosen + 1)); setChosen(chosen + 1); }}>
                  Later
                </button>
              </div>
              <div className="acts">
                <button type="button" onClick={() => {
                  setStages((was) => [...was.slice(0, chosen + 1), { ...at }, ...was.slice(chosen + 1)]);
                  setChosen(chosen + 1);
                }}>Duplicate</button>
                <button type="button" onClick={() => {
                  setStages((was) => was.filter((_, i) => i !== chosen));
                  setChosen(Math.max(0, chosen - 1));
                }}>Delete</button>
              </div>
            </>
          )}
          <button type="button" className="save" disabled={stages.length === 0 || cityVersion === ""}
                  onClick={() => void save()}>Save</button>
          {saving ? <p className="quiet">{saving}</p> : null}
          {trouble ? <p className="trouble">{trouble}</p> : null}
          {cityVersion === "" ? <p className="quiet">This place has no published package to pin.</p> : null}
        </div>
      </section>
    </>
  );
}

function withoutOver(stage: Stage): Stage {
  const { over: _over, ...rest } = stage;
  return rest as Stage;
}

function swapped<T>(all: T[], a: number, b: number): T[] {
  const out = [...all];
  [out[a], out[b]] = [out[b]!, out[a]!];
  return out;
}
