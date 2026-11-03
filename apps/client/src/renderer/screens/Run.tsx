// One page for any run.
//
// A run under one condition is a recording, so its page is the replay (in
// Replay.tsx). A run under several is a set of recordings, so its page is
// what they add up to: a grid of every condition against how it went, the one
// condition that decides it, and what it costs. Both open with the same
// strip of facts, and both go back to Runs.

import { useCallback, useEffect, useMemo, useState } from "react";

import type { Cost, Findings, Platform, Sweep } from "@coral-city/api";

import { Empty } from "./parts.js";
import { Page, SkeletonLines, Status, Table, type Tone } from "../ui/components.js";

/** The strip under a run's title: a few labelled values, the same for every run. */
export function RunFacts({ facts }: { facts: { label: string; value: React.ReactNode; note?: string }[] }): React.JSX.Element {
  return (
    <dl className="run-facts">
      {facts.map((f) => (
        <div key={f.label} title={f.note}><dt>{f.label}</dt><dd>{f.value}</dd></div>
      ))}
    </dl>
  );
}

/** One condition a run was flown under, as the control plane reports it. */
interface Flown {
  label: string;
  chosen?: Record<string, string>;
  runs: number;
  survivedRuns: number;
  survived: boolean;
  marginal?: boolean;
  score: number;
  worst?: number;
  best?: number;
  says?: string;
  heldBack?: boolean;
}

export function ManyRun({ platform, sweep, onBack }: {
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
  // Still in the water: the answer so far is worth having while it flies.
  useEffect(() => {
    if (one !== undefined && one.flying === 0) return;
    const again = setInterval(read, 15_000);
    return () => clearInterval(again);
  }, [read, one]);

  if (missing) {
    return (
      <Page title="Not a dive you have" crumb="Dives" onCrumb={onBack}>
        <Empty title="Not a dive you have">It may have been withdrawn, or you were never granted it.</Empty>
      </Page>
    );
  }
  const runs = one?.runs ?? 0;
  const flown = one?.flown ?? 0;
  const flying = one?.flying ?? 0;
  const repeats = found?.repeats ?? one?.repeats ?? 1;
  const ways = found?.scenarios || one?.scenarios || Math.round(runs / Math.max(1, repeats));
  const good = found?.good ?? 0;

  return (
    <Page title={one?.name ?? "A dive"} crumb="Dives" onCrumb={onBack}
          subtitle={one === undefined ? undefined
            : `${ways} conditions${repeats > 1 ? `, each flown ${repeats} times` : ""} · ${flown} of ${runs} flown`}
          actions={one === undefined ? undefined
            : <Status tone={flying > 0 ? "busy" : "good"}>{flying > 0 ? `${flying} flying` : "done"}</Status>}>
      {found === undefined ? <SkeletonLines lines={6} /> : found.flown === 0 ? (
        <Empty title={flying > 0 ? "Nothing has come back yet" : "Nothing flown"}>
          {flying > 0 ? "The results appear here as each condition lands." : "None of its dives flew."}
        </Empty>
      ) : (
        <>
          <RunFacts facts={[
            { label: "did the job", value: `${found.survived} of ${found.flown} conditions` },
            { label: "counts as done", value: `${(good * 100).toFixed(0)}%`,
              note: repeats > 1 ? "a dive counts as done at this score, and a condition when more than half its dives did" : "a dive counts as done at this score" },
            { label: "either way", value: found.marginal ? `${found.marginal} conditions` : "none",
              note: "conditions where some dives did the job and some did not" },
            { label: "energy a dive", value: found.cost && !found.cost.notEnough ? `${(found.cost.energyWh ?? 0).toFixed(1)} Wh` : "—" },
          ]} />

          <section className="run-section">
            <h2>What decides it</h2>
            <p className="decides">{decides(found)}</p>
            {notes(found).map((n) => <p key={n} className="run-note">{n}</p>)}
          </section>

          <section className="run-section">
            <h2>Every condition</h2>
            <Conditions found={found} good={good} />
          </section>

          <section className="run-section">
            <h2>Each setting</h2>
            <Settings found={found} />
          </section>

          <section className="run-section">
            <h2>What it costs</h2>
            <Costs cost={found.cost} cheapest={found.cheapestScenario} />
          </section>
        </>
      )}
    </Page>
  );
}

/** The one line a person reads first. */
function decides(found: Findings): string {
  const failed = found.failsOf ?? [0, 0];
  const rescued = found.rescueOf ?? [0, 0];
  if (found.survived === found.flown) return "Nothing in its conditions breaks it.";
  if (found.nothingDecided) return "Nothing decides it: every difference rests on conditions that could have gone either way. Fly each more times.";
  if (!found.turnsOn) return "No single setting explains the failures.";
  const rescue = found.rescue
    ? ` Setting ${found.rescue} saves ${rescued[0]} of those ${rescued[1]}.`
    : found.noRescue ? " Nothing else rescues it, so at that setting do not go." : "";
  return `It turns on ${found.turnsOn}. At ${found.at} it fails ${failed[0]} of ${failed[1]} times.${rescue}`;
}

/** What qualifies the answer, a short line each. */
function notes(found: Findings): string[] {
  const said: string[] = [];
  if ((found.physics ?? []).length > 1) said.push(`Flown on different physics (${(found.physics ?? []).join(" and ")}), so these are not one table.`);
  if (found.heldBack) said.push(`${found.heldBack} failures were the hull, not the plan. A better plan will not fix those.`);
  return said;
}

/** Every condition against how it went: the grid, on one 0 to 100 scale with done marked. */
function Conditions({ found, good }: { found: Findings; good: number }): React.JSX.Element {
  const rows = (found.scenariosFlown ?? []) as unknown as Flown[];
  const dims = useMemo(() => {
    const seen: string[] = [];
    for (const r of rows) for (const k of Object.keys(chosenOf(r))) if (!seen.includes(k)) seen.push(k);
    return seen;
  }, [rows]);
  const outcome = (r: Flown): { tone: Tone; said: string } =>
    r.marginal ? { tone: "warn", said: "either way" } : r.survived ? { tone: "good", said: "done" } : { tone: "bad", said: "fails" };
  return (
    <Table rows={rows} rowKey={(r) => r.label}
           search={(r) => r.label} searchLabel="Search conditions"
           facets={[...dims.map((d) => ({ key: `d:${d}`, label: d, value: (r: Flown) => chosenOf(r)[d] })),
                    { key: "outcome", label: "Outcome", value: (r: Flown) => outcome(r).said }]}
           initialSort={{ key: "score" }}
           empty="No condition has come back yet."
           columns={[
             ...dims.map((d, i) => ({
               key: `d:${d}`, label: d, grow: i === 0,
               sort: (a: Flown, b: Flown) => (chosenOf(a)[d] ?? "").localeCompare(chosenOf(b)[d] ?? ""),
               render: (r: Flown) => <span className="cell-main">{chosenOf(r)[d] ?? "—"}</span>,
             })),
             { key: "score", label: "Score", width: "220px", sort: (a, b) => a.score - b.score,
               render: (r) => (
                 <span className="score-bar" title={r.runs > 1 ? `median of ${r.runs} dives, ${pct(r.worst)} to ${pct(r.best)}` : r.says}>
                   <span className="score-track">
                     <span style={{ width: pct(r.score) }} />
                     <i className="done-mark" style={{ left: pct(good) }} />
                   </span>
                   <b>{pct(r.score)}</b>
                 </span>
               ) },
             { key: "runs", label: "Dives done", align: "right", priority: 2,
               sort: (a, b) => a.survivedRuns / Math.max(1, a.runs) - b.survivedRuns / Math.max(1, b.runs),
               render: (r) => `${r.survivedRuns} of ${r.runs}` },
             { key: "outcome", label: "Outcome", sort: (a, b) => outcome(a).said.localeCompare(outcome(b).said),
               render: (r) => <Status tone={outcome(r).tone}>{outcome(r).said}</Status> },
           ]} />
  );
}

/** Each setting of each condition: how often it did the job, and what that cost. */
function Settings({ found }: { found: Findings }): React.JSX.Element {
  type Line = { dim: string; value: string; survived?: number; of?: number; wh?: number | null; cheapest: boolean; changes?: number };
  const lines = new Map<string, Line>();
  const at = (dim: string, value: string): Line => {
    const key = `${dim}\u0000${value}`;
    if (!lines.has(key)) lines.set(key, { dim, value, cheapest: false });
    return lines.get(key)!;
  };
  for (const m of found.matters ?? []) {
    for (const r of m.rates ?? []) Object.assign(at(m.name ?? "", r.value ?? ""), { survived: r.survived, of: r.of, changes: m.changes });
  }
  for (const c of found.cheapest ?? []) {
    for (const s of c.settings ?? []) {
      const line = at(c.dimension ?? "", s.value ?? "");
      line.wh = s.meanWh;
      line.cheapest = s.value === c.best;
      if (line.of === undefined) { line.survived = s.survived; line.of = s.of; }
    }
  }
  const rows = [...lines.values()];
  const none = found.madeNoDifference ?? [];
  if (rows.length === 0) {
    return <p className="run-note">{none.length ? `Made no difference to whether it did the job: ${none.join(", ")}.` : "Nothing to compare yet."}</p>;
  }
  let last = "";
  return (
    <>
      <table className="numbers grouped">
        <thead><tr><th>Setting</th><th className="num">Did the job</th><th className="num">Energy a dive</th><th /></tr></thead>
        <tbody>
          {rows.map((r) => {
            const first = r.dim !== last;
            last = r.dim;
            return (
              <tr key={`${r.dim}|${r.value}`} className={first ? "first" : undefined}>
                <td>{first ? <span className="setting-dim">{r.dim}</span> : null}{r.value}</td>
                <td className="num">{r.of ? `${r.survived ?? 0} of ${r.of}` : "—"}</td>
                <td className="num">{typeof r.wh === "number" ? `${r.wh.toFixed(1)} Wh` : r.of ? "failed" : "—"}</td>
                <td>{r.cheapest ? <Status tone="good">cheapest</Status> : null}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {none.length ? <p className="run-note">Made no difference to whether it did the job: {none.join(", ")}.</p> : null}
    </>
  );
}

/** What it takes, as numbers: energy and time, then how many fit in a charge and a day. */
function Costs({ cost, cheapest }: { cost: Cost | undefined; cheapest: Findings["cheapestScenario"] }): React.JSX.Element {
  if (cost === undefined || cost.notEnough) {
    return <p className="run-note">Nothing did the job, so there is nothing to price.</p>;
  }
  const min = (h: number | undefined) => `${((h ?? 0) * 60).toFixed(0)} min`;
  const wh = (w: number | undefined) => `${(w ?? 0).toFixed(1)} Wh`;
  return (
    <>
      <table className="numbers">
        <thead><tr><th /><th className="num">Energy</th><th className="num">Time</th></tr></thead>
        <tbody>
          <tr title={`priced on the ${cost.survived ?? 0} dives that did the job`}>
            <td>The work</td><td className="num">{wh(cost.energyWh)}</td><td className="num">{min(cost.hours)}</td>
          </tr>
          <tr title="descent and both transits included">
            <td>The whole dive</td><td className="num">{wh(cost.diveEnergyWh)}</td><td className="num">{min(cost.diveHours)}</td>
          </tr>
          <tr title="what to size a plan by">
            <td>At the 90th percentile</td><td className="num">{wh(cost.worstEnergyWh)}</td><td className="num">{min(cost.worstHours)}</td>
          </tr>
        </tbody>
      </table>
      <RunFacts facts={[
        { label: "dives on a charge", value: Math.floor(cost.perCharge ?? 0),
          note: `${(cost.usableWh ?? 0).toFixed(0)} usable Wh: ${(cost.capacityWh ?? 0).toFixed(0)} less a ${((cost.reserveFraction ?? 0) * 100).toFixed(0)}% reserve` },
        { label: "dives in a working day", value: Math.floor(cost.perDay ?? 0),
          note: `a ${cost.workingDayHours ?? 8} hour day, held back by ${cost.heldBackBy ?? "time"}` },
        ...(cheapest?.label ? [{ label: "cheapest condition that does the job",
          value: `${cheapest.label.replaceAll(":", ": ")}, ${(cheapest.meanWh ?? 0).toFixed(1)} Wh` }] : []),
      ]} />
    </>
  );
}

function chosenOf(r: Flown): Record<string, string> {
  if (r.chosen && Object.keys(r.chosen).length) return r.chosen;
  // Older rows carry only the label: "current:half a knot · fix:none".
  const out: Record<string, string> = {};
  for (const part of r.label.split(" · ")) {
    const cut = part.indexOf(":");
    if (cut > 0) out[part.slice(0, cut).trim()] = part.slice(cut + 1).trim();
  }
  return out;
}

function pct(v: number | undefined): string {
  return `${Math.round((v ?? 0) * 100)}%`;
}
