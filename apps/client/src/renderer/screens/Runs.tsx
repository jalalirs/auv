// What has been run, and what became of it.
//
// One list for a dive flown once, a dive flown again and again, and a plan
// flown every way the day could go. Repeats of one dive by one controller are
// one row with their average, and a sweep is one row with its conditions,
// because a hundred runs of one question listed one by one bury the rest.

import { useState } from "react";

import type { Platform, Sweep } from "@coral-city/api";

import type { Held } from "./Deck.js";
import { useSweeps } from "./Sweeps.js";
import { ago } from "./parts.js";
import { Button, Page, Status, Table, type Tone } from "../ui/components.js";

const LIVE = new Set(["queued", "preparing", "running"]);

/** What computed a run, as the thing a table may not mix.
 *
 * The digest says exactly what ran and the physics version says whether the
 * answer would have been the same, and it is the second one that decides
 * whether two runs belong in one table. A runtime rebuilt on a new base image
 * has a different digest and the same physics, and refusing to compare those
 * would make this useless by being right too often.
 *
 * A run flown before the runtime declared one answers 0, which groups all of
 * them together as "we do not know" — honestly, and apart from the ones we do.
 */
function physicsOf(one: Held["runs"][number]): number {
  return one.run.physicsVersion ?? 0;
}

/** Runs that are the same question asked again: one dive, one controller,
 *  one physics. What computed it is part of what was tested, so runs either
 *  side of a physics change are never one row. */
export function repeatKey(one: Held["runs"][number]): string {
  return `${one.dive}|${one.flownBy}|${physicsOf(one)}`;
}

/** One row of the list: a run, the same run flown several times (newest
 *  first in times), or a sweep flown under several conditions. */
type Row =
  | { kind: "run"; key: string; name: string; flownBy: string; when: string; state: string; one: Held["runs"][number]; times: Held["runs"] }
  | { kind: "sweep"; key: string; name: string; flownBy: string; when: string; state: string; sweep: Sweep };

function stateOfRun(one: Held["runs"][number]): string {
  return one.run.state === "succeeded" && one.run.outcome?.["surfaced"] === true ? "surfaced" : one.run.state;
}

export function Runs({ platform, held, onChanged, onReplay, onSweep, onNew, by }: {
  platform: Platform;
  held: Held;
  onChanged: () => void;
  onReplay: (dive: string, run: string) => void;
  onSweep: (sweep: string) => void;
  /** Start a run. */
  onNew?: () => void;
  /** Arrive filtered to one controller's runs. */
  by?: string;
}): React.JSX.Element {
  const [ending, setEnding] = useState<string | undefined>();
  const sweeps = useSweeps(platform, held);
  async function end(dive: string, run: string): Promise<void> {
    setEnding(run);
    try {
      await platform.cancel(dive, run);
      onChanged();
    } finally {
      setEnding(undefined);
    }
  }

  const outstanding = held.runs.filter((r) => LIVE.has(r.run.state));
  // A sweep's dives are its one row; a dive of a sweep not listed is shown on
  // its own, so every dive the side bar counts is somewhere on this page.
  const listed = new Set((sweeps ?? []).map((w) => w.id));
  const ofSweep = new Map<string, number>();
  const repeats = new Map<string, Held["runs"]>();
  for (const one of held.runs) {
    if (one.run.sweepId && listed.has(one.run.sweepId)) {
      ofSweep.set(one.run.sweepId, (ofSweep.get(one.run.sweepId) ?? 0) + 1);
      continue;
    }
    repeats.set(repeatKey(one), [...(repeats.get(repeatKey(one)) ?? []), one]);
  }
  const rows: Row[] = [
    ...[...repeats.values()].map((group): Row => {
      const times = [...group].sort((a, b) => b.run.requestedAt.localeCompare(a.run.requestedAt));
      const one = times[0]!;
      const live = times.find((t) => LIVE.has(t.run.state));
      return { kind: "run", key: one.run.id, name: one.name, flownBy: one.flownBy, when: one.run.requestedAt,
               state: stateOfRun(live ?? one), one, times };
    }),
    ...(sweeps ?? []).map((w): Row => ({
      kind: "sweep", key: w.id, name: w.name.split(" ~ ")[0]!, flownBy: "the plan's own", when: w.createdAt,
      state: w.flying ? "running" : (w.flown ?? 0) >= (w.runs ?? 0) ? "succeeded" : "queued", sweep: w })),
  ];
  // The count is of dives, as the side bar's is, not of rows: a dive flown
  // five times is one row here and five dives there.
  const dives = (some: Row[]) => some.reduce((n, r) => n + (r.kind === "run" ? r.times.length : ofSweep.get(r.sweep.id) ?? 0), 0);
  const open = (r: Row) => {
    if (r.kind === "sweep") onSweep(r.sweep.id);
    else onReplay(r.one.dive, r.one.run.id);
  };

  return (
    <Page title="Dives" subtitle="Every dive, under one condition or many."
          info="A dive flies a mission or a task in a vehicle, under the conditions you chose. Choose one setting for each condition and it is one dive; choose several and it is flown once for each, so you see which condition breaks the plan. Every dive pins its place, vehicle, water, seed and simulator, so flying it again means something. A dive flown again by the same controller is one row, so the rows are fewer than the dives."
>
      {outstanding.length > 0 ? (
        <section className="running-now">
          <h2>Diving now</h2>
          <div className="running-list">
            {outstanding.map((r) => (
              <div key={r.run.id} className="running">
                <Status tone="busy">{r.run.state}</Status>
                <div className="running-what">
                  <span className="cell-main">{r.name}</span>
                  <span className="cell-sub">{r.flownBy} · {ago(r.run.requestedAt)}</span>
                </div>
                <Button kind="ghost" disabled={ending === r.run.id} onClick={() => void end(r.dive, r.run.id)}>{ending === r.run.id ? "Ending…" : "End"}</Button>
              </div>
            ))}
          </div>
        </section>
      ) : null}

      <Table rows={rows} loading={!held.runsRead || sweeps === undefined} rowKey={(r) => r.key} initialPicked={by ? { by: [by] } : undefined}
               lead={onNew ? <Button kind="primary" onClick={onNew}>+ New dive</Button> : undefined}
               onRow={open}
               search={(r) => `${r.name} ${r.flownBy} ${r.kind === "run" ? taskOf(r.one) : ""} ${r.state}`} searchLabel="Search dives"
               tally={{ count: dives, noun: "dives" }}
               facets={[
                 { key: "conditions", label: "Conditions", value: (r) => r.kind === "sweep" ? "several" : r.times.length > 1 ? "one, flown again" : "one" },
                 { key: "by", label: "Flown by", value: (r) => r.flownBy },
                 { key: "state", label: "State", value: (r) => r.state },
                 { key: "when", label: "When", value: (r) => whenOf(r.when) },
               ]}
               initialSort={{ key: "when", down: true }}
               empty={<>Nothing has been flown yet. <a onClick={onNew}>Start a dive</a>.</>}
               columns={[
                 { key: "run", label: "Dive", grow: true, sort: (a, b) => a.name.localeCompare(b.name),
                   render: (r) => <><span className="cell-main">{r.name}{r.kind === "run" && r.times.length > 1 ? <span className="times"> × {r.times.length}</span> : null}</span>
                                  <span className="cell-sub">{r.kind === "sweep" ? sweepSaid(r.sweep) : r.times.length > 1 ? `${r.flownBy} · flown ${r.times.length} times` : r.flownBy}</span></> },
                 { key: "score", label: "Result", align: "right", sort: (a, b) => resultOf(a) - resultOf(b),
                   render: (r) => <ResultCell row={r} /> },
                 { key: "off", label: "Off at the end", align: "right", priority: 3,
                   render: (r) => <span className="cell-meta">{r.kind === "run" ? closingOf(r.one) : ""}</span> },
                 { key: "when", label: "When", priority: 2, sort: (a, b) => a.when.localeCompare(b.when),
                   render: (r) => <span className="cell-meta">{ago(r.when)}</span> },
                 { key: "state", label: "State", render: (r) => <Status tone={toneOf(r.state)}>{r.state === "succeeded" ? "done" : r.state}</Status> },
               ]} />
    </Page>
  );
}

/** A sweep's second line: how many conditions, and how far it has got. */
function sweepSaid(w: Sweep): string {
  const runs = w.runs ?? 0;
  const ways = w.scenarios || Math.round(runs / Math.max(1, w.repeats ?? 1));
  const flown = w.flown ?? 0;
  return `${ways} ${ways === 1 ? "condition" : "conditions"}${(w.repeats ?? 1) > 1 ? ` × ${w.repeats}` : ""}`
    + (flown < runs ? ` · ${flown} of ${runs} flown` : ` · ${runs} dives`);
}

/** What a row sorts by in the Result column. */
/** A row's score: its run's, or the average of the times it was flown. */
export function averageOf(times: Held["runs"]): number {
  const scores = times.map(scoreOf).filter((v) => v >= 0);
  return scores.length ? scores.reduce((a, b) => a + b, 0) / scores.length : -1;
}

function resultOf(r: Row): number {
  if (r.kind === "run") return averageOf(r.times);
  const runs = r.sweep.runs ?? 0;
  return runs ? (r.sweep.flown ?? 0) / runs - 2 : -3;
}

/** A score as a number and a short bar; a sweep as how much of it has flown. */
function ResultCell({ row }: { row: Row }): React.JSX.Element {
  if (row.kind === "sweep") {
    const runs = row.sweep.runs ?? 0;
    const flown = row.sweep.flown ?? 0;
    return flown >= runs ? <span className="cell-meta">{runs} flown</span> : <span className="cell-meta">{flown} of {runs}</span>;
  }
  const score = averageOf(row.times);
  if (score < 0) return <span className="cell-meta">—</span>;
  const many = row.times.filter((t) => scoreOf(t) >= 0).length > 1;
  return (
    <span className="score-bar" title={many ? `average of ${row.times.length} dives` : taskOf(row.one)}>
      <span className="score-track"><span style={{ width: `${(score * 100).toFixed(0)}%` }} /></span>
      <b>{(score * 100).toFixed(0)}%</b>
    </span>
  );
}

/** How far out it was when it came up, the one number beside the score. */
export function closingOf(one: Held["runs"][number]): string {
  const fix = one.run.outcome?.["closingFix"] as { errorM?: number } | undefined;
  return typeof fix?.errorM === "number" ? `${fix.errorM.toFixed(1)} m` : "";
}

export function taskOf(one: Held["runs"][number]): string {
  return ((one.run.outcome as Record<string, unknown> | undefined)?.["task"] as { name?: string } | undefined)?.name ?? "";
}

export function scoreOf(one: Held["runs"][number]): number {
  const score = ((one.run.outcome as Record<string, unknown> | undefined)?.["task"] as { score?: number } | undefined)?.score;
  return typeof score === "number" ? score : -1;
}

export function toneOf(state: string): Tone {
  return state === "succeeded" ? "good" : LIVE.has(state) ? "busy" : state === "failed" ? "bad" : "quiet";
}

/** When, as the buckets a person filters by. */
function whenOf(iso: string): string {
  const days = (Date.now() - new Date(iso).getTime()) / 86_400_000;
  return days < 1 ? "today" : days < 7 ? "this week" : days < 31 ? "this month" : "older";
}

/** Whether the run left a recording behind. */
export function recorded(run: { artefacts?: number; outcome?: Record<string, unknown> }): boolean {
  if ((run.artefacts ?? 0) > 0) return true;
  const recording = run.outcome?.["recording"] as { files?: number } | undefined;
  return typeof recording?.files === "number" && recording.files > 0;
}
