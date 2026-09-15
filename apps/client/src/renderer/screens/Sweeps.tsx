// A mission against everything that could go wrong with it.
//
// This is the rehearsal, and it is the screen the whole application has been
// building towards: lay out a site, plan the work over it, then ask what
// breaks it — and be told what to do about Tuesday.
//
// What comes back is a paragraph and a small table. It was a grid of numbers
// once and nobody could read it: seventy-two rows of scores, every one of them
// true and none of them an answer. The reading matters more than the running,
// so the reading is what this page is.

import { useCallback, useEffect, useMemo, useState } from "react";

import type { AssetVersion, Cost, Findings, Mission, Platform, Sweep } from "@coral-city/api";

import { DOUBTS, doubtsFrom, scenariosIn } from "../catalog/doubts.js";
import { newestOf } from "../platform/packages.js";
import type { Held } from "./Deck.js";
import { Empty, PageHead, Pill, Row, ago } from "./parts.js";

/** How long a sweep will take, when the mission has been flown before. */
function willTake(cost: Cost | undefined, scenarios: number, machines: number): string | undefined {
  if (cost === undefined || !cost.hours || scenarios === 0) return undefined;
  const hours = (cost.hours * scenarios) / Math.max(1, machines);
  return hours < 1.5 ? `${Math.round(hours * 60)} minutes of machine time`
    : `${hours.toFixed(hours < 10 ? 1 : 0)} hours of machine time on ${machines} machine${machines === 1 ? "" : "s"}`;
}

// ── the list, and asking for one ─────────────────────────────────────────────

export function Sweeps({ platform, held, onOpen, onChanged }: {
  platform: Platform;
  held: Held;
  onOpen: (sweep: string) => void;
  onChanged: () => void;
}): React.JSX.Element {
  const [sweeps, setSweeps] = useState<Sweep[]>([]);
  const [missions, setMissions] = useState<{ mission: Mission; version: AssetVersion; place: string }[]>([]);
  const [mission, setMission] = useState<string>("");
  const [vehicle, setVehicle] = useState<string>(() => held.vehicles[0]?.id ?? "");
  const [picked, setPicked] = useState<Record<string, string[]>>({
    current: ["still", "half knot"], fix: ["array", "nothing"],
  });
  // Three: enough that one unlucky seed cannot carry a dimension on its own.
  const [repeats, setRepeats] = useState(3);
  const [cost, setCost] = useState<Cost | undefined>();
  const [asking, setAsking] = useState(false);
  const [trouble, setTrouble] = useState("");

  const read = useCallback(() => {
    if (held.institution === undefined) return;
    void platform.sweepsOf(held.institution.id).then(setSweeps).catch(() => undefined);
  }, [platform, held.institution]);
  useEffect(read, [read]);
  // Kept fresh while somebody is watching one fly.
  useEffect(() => {
    const again = setInterval(read, 15_000);
    return () => clearInterval(again);
  }, [read]);

  // Every plan of work that has something saved: a sweep doubts a mission.
  useEffect(() => {
    let stale = false;
    void (async () => {
      const found: { mission: Mission; version: AssetVersion; place: string }[] = [];
      for (const where of held.places) {
        for (const one of await platform.missionsOf(where.id).catch((): Mission[] => [])) {
          const saved = await platform.versionsOfMission(one.id).catch((): AssetVersion[] => []);
          if (saved[0] !== undefined) found.push({ mission: one, version: saved[0], place: where.id });
        }
      }
      if (stale) return;
      setMissions(found);
      if (found[0] !== undefined) setMission((was) => was || found[0]!.mission.id);
    })();
    return () => { stale = true; };
  }, [platform, held.places]);

  // What this plan has cost before, so the page can say what the sweep will
  // take before somebody asks for ninety dives.
  useEffect(() => {
    if (mission === "") { setCost(undefined); return; }
    let stale = false;
    void platform.missionCost(mission)
      .then((one) => { if (!stale) setCost(one); })
      .catch(() => { if (!stale) setCost(undefined); });
    return () => { stale = true; };
  }, [platform, mission]);

  const scenarios = useMemo(() => scenariosIn(picked), [picked]);
  const chosen = missions.find((one) => one.mission.id === mission);
  const takes = willTake(cost, scenarios * repeats, held.queues[0]?.devices ?? 1);

  async function go(): Promise<void> {
    const queue = held.queues[0];
    if (held.institution === undefined || chosen === undefined || queue === undefined) return;
    setAsking(true); setTrouble("");
    try {
      // The published version, not the vehicle: a sweep pins bytes, the way a
      // dive does, so that ninety runs are ninety runs of one vehicle even if
      // somebody publishes a newer one while they fly.
      const published = newestOf(await platform.versionsOfVehicle(vehicle));
      if (published === undefined) {
        setTrouble("That vehicle has no published package yet.");
        return;
      }
      const made = await platform.startSweep(held.institution.id, {
        name: `${chosen.mission.name} ~ ${new Date().toLocaleDateString(undefined,
          { day: "numeric", month: "long" })}`,
        missionVersionId: chosen.version.id,
        vehicleVersionId: published.id,
        doubts: doubtsFrom(picked) as never,
        repeats,
        queueId: queue.id,
        runtimeVersion: queue.runtimes?.[0] ?? "",
      });
      onChanged();
      onOpen(made.id);
    } catch (thrown) {
      setTrouble(thrown instanceof Error ? thrown.message : "it would not start");
    } finally {
      setAsking(false);
    }
  }

  return (
    <>
      <PageHead title="Sweeps"
                says="A mission against everything nobody can promise about it: which of them break it, what fixes the most of them, and what the weather costs."
                aside={<Pill>{sweeps.length} {sweeps.length === 1 ? "sweep" : "sweeps"}</Pill>} />

      <section>
        <h2>Ask one</h2>
        {missions.length === 0 ? (
          <p className="quiet">
            A sweep doubts a plan of work, so there has to be one first —
            Missions, then come back.
          </p>
        ) : (
          <div className="sweeping">
            <div className="of">
              <label>
                <span>The plan</span>
                <select value={mission} onChange={(e) => setMission(e.target.value)}>
                  {missions.map(({ mission: one, place }) => (
                    <option key={one.id} value={one.id}>
                      {one.name} · {held.places.find((p) => p.id === place)?.name ?? ""}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                <span>Flown in</span>
                <select value={vehicle} onChange={(e) => setVehicle(e.target.value)}>
                  {held.vehicles.map((one) => (
                    <option key={one.id} value={one.id}>{one.name}</option>
                  ))}
                </select>
              </label>
              <label>
                <span>Each scenario, how many times</span>
                <select value={repeats} onChange={(e) => setRepeats(Number(e.target.value))}>
                  {[1, 3, 5, 10].map((one) => (
                    <option key={one} value={one}>
                      {one === 1 ? "once — a coin flip looks like a finding" : `${one} times`}
                    </option>
                  ))}
                </select>
              </label>
            </div>

            <div className="doubts">
              {DOUBTS.map((doubt) => {
                const on = picked[doubt.key] ?? [];
                return (
                  <div key={doubt.key} className={on.length > 1 ? "doubt on" : "doubt"}>
                    <strong>{doubt.name}</strong>
                    <small>{doubt.says}</small>
                    <div className="settings">
                      {doubt.settings.map((one) => (
                        <button key={one.key} type="button"
                                className={on.includes(one.key) ? "setting on" : "setting"}
                                aria-pressed={on.includes(one.key)}
                                onClick={() => setPicked((was) => {
                                  const had = was[doubt.key] ?? [];
                                  return { ...was, [doubt.key]: had.includes(one.key)
                                    ? had.filter((k) => k !== one.key) : [...had, one.key] };
                                })}>
                          {one.name}
                        </button>
                      ))}
                    </div>
                    {on.length === 1 ? (
                      <small className="quiet">
                        One setting is a decision, not a doubt — pick another, or none.
                      </small>
                    ) : null}
                  </div>
                );
              })}
            </div>

            <div className="acts">
              <span className="quiet">
                {scenarios === 0 ? "Nothing is in doubt yet."
                  : `${scenarios} scenarios × ${repeats} = ${scenarios * repeats} runs${takes ? ` · about ${takes}` : ""}.`}
                {cost === undefined || cost.notEnough
                  ? scenarios > 0 ? " This plan has not been flown before, so how long it will take is not known." : ""
                  : ""}
              </span>
              <button className="big" disabled={asking || scenarios < 2 || chosen === undefined}
                      onClick={() => void go()}>
                {asking ? "Asking for water…" : "Sweep it"}
              </button>
            </div>
            {trouble ? <p className="trouble">{trouble}</p> : null}
          </div>
        )}
      </section>

      <section>
        <h2>What has been swept</h2>
        {sweeps.length === 0 ? (
          <Empty title="Nothing swept yet">
            A sweep flies one plan every way the doubts could resolve, and comes
            back with the one change that saves the most of them.
          </Empty>
        ) : (
          <div className="rows">
            {sweeps.map((one) => (
              <button key={one.id} type="button" className="row open"
                      onClick={() => onOpen(one.id)}>
                <span className="what">{one.name}</span>
                <span className="quiet">
                  {one.flown ?? 0} of {one.scenarios ?? 0} flown
                  {one.flying ? ` · ${one.flying} in the water` : ""} · {ago(one.createdAt)}
                </span>
              </button>
            ))}
          </div>
        )}
      </section>
    </>
  );
}

// ── reading one ──────────────────────────────────────────────────────────────

export function Swept({ platform, sweep, onBack }: {
  platform: Platform;
  sweep: string;
  onBack: () => void;
}): React.JSX.Element {
  const [one, setOne] = useState<Sweep | undefined>();
  const [found, setFound] = useState<Findings | undefined>();
  const [missing, setMissing] = useState(false);

  const read = useCallback(() => {
    void platform.sweep(sweep).then(setOne).catch(() => setMissing(true));
    void platform.findings(sweep).then(setFound).catch(() => undefined);
  }, [platform, sweep]);
  useEffect(read, [read]);
  // While it is still in the water: the answer so far is worth having at two
  // in the morning, which is when somebody is watching this.
  useEffect(() => {
    if (one !== undefined && one.flying === 0) return;
    const again = setInterval(read, 15_000);
    return () => clearInterval(again);
  }, [read, one]);

  if (missing) {
    return <Empty title="Not a sweep you have">It may have been withdrawn, or you were never granted it.</Empty>;
  }
  const flying = one?.flying ?? 0;

  return (
    <>
      <PageHead title={one?.name ?? "A sweep"}
                says={one === undefined ? "" :
                  `${one.flown ?? 0} of ${one.scenarios ?? 0} flown${flying ? `, ${flying} in the water` : ""}`}
                back="Sweeps" onBack={onBack}
                aside={<Pill kind={flying > 0 ? "busy" : "good"}>
                  {flying > 0 ? "flying" : "done"}
                </Pill>} />

      {found === undefined || found.flown === 0 ? (
        <section>
          <p className="quiet">
            {flying > 0 ? "Nothing has come back yet. The answer appears as the scenarios land."
              : "Nothing flown."}
          </p>
        </section>
      ) : (
        <>
          <section>
            <h2>The answer</h2>
            <Answer found={found} flying={flying} />
          </section>
          <section>
            <h2>What it costs</h2>
            <Costs cost={found.cost} />
          </section>
          <section>
            <h2>Every scenario</h2>
            <Scenarios found={found} />
          </section>
        </>
      )}
    </>
  );
}

/** The paragraph and the small table. */
function Answer({ found, flying }: { found: Findings; flying: number }): React.JSX.Element {
  const matters = found.matters ?? [];
  const failed = found.failsOf ?? [0, 0];
  const rescued = found.rescueOf ?? [0, 0];
  return (
    <>
      <p className="lead">
        Survives <b>{found.survived}</b> of <b>{found.flown}</b> scenarios
        {(found.repeats ?? 1) > 1
          ? `, each flown ${found.repeats} times`
          : ""}
        {flying > 0 ? `, with ${flying} still in the water` : ""}
        {" "}(a mission counts as done at {(found.good * 100).toFixed(0)}%
        {(found.repeats ?? 1) > 1 ? ", and a scenario when more than half its runs did" : ""}).
      </p>
      {(found.physics ?? []).length > 1 ? (
        <p className="aside warn">
          These were not all computed by the same simulator — physics{" "}
          {(found.physics ?? []).join(" and ")}. A change to the physics changes
          the answer, so this is not one table.
        </p>
      ) : null}

      {found.marginal ? (
        <p className="aside warn">
          {found.marginal} of the scenarios could have gone either way — some of
          their runs did the job and some did not. What counts as done is
          sitting inside the spread.
        </p>
      ) : null}

      {found.survived === found.flown ? (
        <p className="lead">Nothing in the doubt list breaks it.</p>
      ) : (
        <>
          {matters.map((one) => (
            <div className="doubt-rates" key={one.name}>
              <div className="doubt-head">
                <strong>{one.name}</strong>
                <span className="quiet">
                  changes the outcome by {((one.changes ?? 0) * 100).toFixed(0)}%
                  {one.onACoinFlip ? ", on coin flips" : ""}
                </span>
              </div>
              {one.onACoinFlip ? (
                <p className="aside warn">
                  Every scenario this separates is one that could have gone
                  either way, so the difference is where the coins landed and
                  not what the setting did.
                </p>
              ) : null}
              {(one.rates ?? []).map((rate) => (
                <div className="rate" key={rate.value}>
                  <span className="setting-name">{rate.value}</span>
                  <span className="share">
                    <span style={{ width: `${(1 - (rate.failedShare ?? 0)) * 100}%` }} />
                  </span>
                  <span className="tally">{rate.survived}/{rate.of}</span>
                </div>
              ))}
            </div>
          ))}
          {(found.madeNoDifference ?? []).length > 0 ? (
            <p className="aside">Made no difference: {(found.madeNoDifference ?? []).join(", ")}.</p>
          ) : null}
          {found.nothingDecided ? (
            <p className="lead">
              Nothing in the doubt list is decided. Every difference rests on
              scenarios that could have gone either way: either move what counts
              as done off the spread, or fly each scenario more times, or doubt
              something this mission is actually sensitive to.
            </p>
          ) : found.turnsOn ? (
            <p className="lead">
              The mission turns on <b>{found.turnsOn}</b>. At <b>{found.at}</b> it
              fails {failed[0]} times out of {failed[1]}.
              {found.rescue
                ? <> Setting <b>{found.rescue}</b> saves {rescued[0]} of those {rescued[1]}.</>
                : found.noRescue
                  ? <> Nothing else in the doubt list rescues them: if the {found.turnsOn} is {found.at}, do not go.</>
                  : null}
            </p>
          ) : (
            <p className="lead">Nothing in the doubt list explains the failures on its own.</p>
          )}
          {found.heldBack ? (
            <p className="aside">
              {found.heldBack} of the failures were the vehicle held back by its own
              hull rather than by the plan — a better plan will not fix those.
            </p>
          ) : null}
        </>
      )}
    </>
  );
}

/** What a day of this takes, and what the weather adds. */
function Costs({ cost }: { cost: Cost | undefined }): React.JSX.Element {
  if (cost === undefined || cost.notEnough) {
    return <p className="quiet">Nothing did the job, so there is nothing to price.</p>;
  }
  return (
    <>
      <div className="kvs">
        <Row of="a run" is={`${(cost.energyWh ?? 0).toFixed(1)} Wh · ${((cost.hours ?? 0) * 60).toFixed(0)} min`}
             note={`Priced on the ${cost.survived} that did the job — the failures are the cheap ones.`} />
        <Row of="at the ninetieth percentile"
             is={`${(cost.worstEnergyWh ?? 0).toFixed(1)} Wh · ${((cost.worstHours ?? 0) * 60).toFixed(0)} min`}
             note="What to size a plan by. The single worst dive anybody flew is one bad seed; the mean runs out one day in two." />
        <Row of="on a charge" is={`${Math.floor(cost.perCharge ?? 0)} runs`}
             note={`${(cost.usableWh ?? 0).toFixed(0)} usable Wh — ${(cost.capacityWh ?? 0).toFixed(0)} less a ${((cost.reserveFraction ?? 0) * 100).toFixed(0)}% reserve, which is not yours.`} />
        <Row of="in a working day" is={`${Math.floor(cost.perDay ?? 0)} runs`}
             note={`Held back by ${cost.heldBackBy}. A working day is ${cost.workingDayHours ?? 8} hours.`} />
      </div>
      {cost.says ? <p className="lead">{cost.says}</p> : null}
    </>
  );
}

/** Every scenario and how it went, for whoever wants the rows. */
function Scenarios({ found }: { found: Findings }): React.JSX.Element {
  const flown = (found.scenariosFlown ?? []) as {
    label: string; score: number; survived: boolean; says?: string;
    runs: number; survivedRuns: number; worst: number; best: number;
    marginal?: boolean;
  }[];
  return (
    <div className="ledger runs">
      {flown.map((one) => (
        <div className="row" key={one.label}>
          <div className="who">
            <strong>{one.label}</strong>
            <span className="when">
              {one.runs > 1
                ? `${one.survivedRuns} of ${one.runs} runs did the job · ${((one.worst ?? 0) * 100).toFixed(0)}% to ${((one.best ?? 0) * 100).toFixed(0)}%${one.marginal ? " — could have gone either way" : ""}`
                : (one.says ?? "")}
            </span>
          </div>
          <span className="result" title={one.runs > 1 ? "the median of its runs" : ""}>
            <b>{((one.score ?? 0) * 100).toFixed(0)}%</b>
          </span>
          <Pill kind={one.survived ? "good" : "bad"}>{one.survived ? "survives" : "fails"}</Pill>
        </div>
      ))}
    </div>
  );
}
