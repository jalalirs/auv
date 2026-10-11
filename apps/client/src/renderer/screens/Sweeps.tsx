// What a mission did against everything that could go wrong with it.
//
// Asking for a sweep is Fly's now — a sweep is a dive with doubts ticked — so
// this file is the reading: the list of what has been swept, and one sweep's
// answer.
//
// What comes back is a paragraph and a small table. It was a grid of numbers
// once and nobody could read it: seventy-two rows of scores, every one of them
// true and none of them an answer. The reading matters more than the running,
// so the reading is what this page is.

import { useCallback, useEffect, useState } from "react";

import type { Cost, Findings, Platform, Sweep } from "@coral-city/api";

import type { Held } from "./Deck.js";
import { Empty, PageHead, Pill, Row } from "./parts.js";

/** Every sweep, newest first, kept fresh while somebody is looking. */
/** Every sweep the institution has asked for, newest first, kept fresh while
 *  somebody is looking — they fly for hours and the counts move. */
export function useSweeps(platform: Platform, held: Held): Sweep[] {
  const [sweeps, setSweeps] = useState<Sweep[]>([]);
  const read = useCallback(() => {
    if (held.institution === undefined) return;
    void platform.sweepsOf(held.institution.id).then(setSweeps).catch(() => undefined);
  }, [platform, held.institution]);
  useEffect(read, [read]);
  useEffect(() => {
    const again = setInterval(read, 15_000);
    return () => clearInterval(again);
  }, [read]);
  return sweeps;
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
                  `${one.flown ?? 0} of ${one.runs ?? 0} flown${flying ? `, ${flying} in the water` : ""}`}
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
      <Cheapest found={found} />
    </>
  );
}

/** Each doubt's settings by what the runs that did the job cost. For where the
 *  vehicle goes in and which way it faces, this is the best launch. */
function Cheapest({ found }: { found: Findings }): React.JSX.Element | null {
  const ranked = found.cheapest ?? [];
  const whole = found.cheapestScenario;
  if (ranked.length === 0 && !whole) return null;
  return (
    <>
      {whole ? (
        <p className="lead" title="of the scenarios most of whose runs did the job, the one whose runs used least energy">
          Cheapest way to do it: <b>{(whole.label ?? "").replaceAll(":", ": ")}</b>, {(whole.meanWh ?? 0).toFixed(1)} Wh a run
          {(whole.candidates ?? 0) > 1
            ? `, ${(whole.savesWh ?? 0).toFixed(1)} Wh less than the dearest of the ${whole.candidates} that did the job`
            : ", the only scenario that did the job"}.
        </p>
      ) : null}
      {ranked.map((one) => {
        const costs = (one.settings ?? []).map((s) => s.meanWh).filter((w): w is number => typeof w === "number");
        const dearest = costs.length ? Math.max(...costs) : 1;
        return (
          <div className="doubt-rates by-energy" key={one.dimension}>
            <div className="doubt-head">
              <strong>{one.dimension}, by energy</strong>
              <span className="quiet">
                cheapest: {one.best}, {(one.bestWh ?? 0).toFixed(1)} Wh a run,{" "}
                {(one.savesWh ?? 0).toFixed(1)} Wh less than the dearest that also did the job
              </span>
            </div>
            {(one.settings ?? []).map((s) => (
              <div className="rate" key={s.value}
                   title={typeof s.meanWh === "number" ? "mean energy of the runs that did the job"
                     : "no run of this setting did the job, so it has no cost to rank"}>
                <span className="setting-name">{s.value === one.best ? <b>{s.value}</b> : s.value}</span>
                <span className="share">
                  <span style={{ width: `${typeof s.meanWh === "number" ? (s.meanWh / dearest) * 100 : 0}%` }} />
                </span>
                <span className="tally">
                  {typeof s.meanWh === "number" ? `${s.meanWh.toFixed(1)} Wh` : "failed"} · {s.survived}/{s.of}
                </span>
              </div>
            ))}
          </div>
        );
      })}
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
        <Row of="the work" is={`${(cost.energyWh ?? 0).toFixed(1)} Wh · ${((cost.hours ?? 0) * 60).toFixed(0)} min`}
             note={`Priced on the ${cost.survived} that did the job — the failures are the cheap ones.`} />
        <Row of="the whole dive"
             is={`${(cost.diveEnergyWh ?? 0).toFixed(1)} Wh · ${((cost.diveHours ?? 0) * 60).toFixed(0)} min`}
             note={cost.workingShare
               ? `Descent and both transits included. ${Math.round((cost.workingShare ?? 0) * 100)}% of it is the work.`
               : "Descent and both transits included."} />
        <Row of="at the ninetieth percentile"
             is={`${(cost.worstEnergyWh ?? 0).toFixed(1)} Wh · ${((cost.worstHours ?? 0) * 60).toFixed(0)} min`}
             note="What to size a plan by. The single worst dive anybody flew is one bad seed; the mean runs out one day in two." />
        <Row of="on a charge" is={`${Math.floor(cost.perCharge ?? 0)} runs`}
             note={`${(cost.usableWh ?? 0).toFixed(0)} usable Wh — ${(cost.capacityWh ?? 0).toFixed(0)} less a ${((cost.reserveFraction ?? 0) * 100).toFixed(0)}% reserve, which is not yours.`} />
        <Row of="in a working day" is={`${Math.floor(cost.perDay ?? 0)} runs`}
             note={`Held back by ${cost.heldBackBy}. A working day is ${cost.workingDayHours ?? 8} hours, and it pays for the whole dive rather than the work.`} />
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
