// What has been run, and what became of it.
//
// One list for a dive flown once and a plan flown every way the day could go:
// a sweep is a row of its own, its runs folded under it, because a hundred
// runs of one question listed one by one bury the dives somebody flew by hand.

import { useState } from "react";

import type { Platform, Sweep } from "@coral-city/api";

import type { Held } from "./Deck.js";
import { useSweeps } from "./Sweeps.js";
import { ago } from "./parts.js";
import { Button, Dialog, Page, Segmented, Status, Table, type Tone } from "../ui/components.js";

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

/** How many different physics a set of runs was computed by. */
function spans(runs: Held["runs"]): number[] {
  return [...new Set(runs.map(physicsOf))].sort((a, b) => a - b);
}


/** One row of the list: a run flown once, or a sweep flown under several conditions. */
type Row =
  | { kind: "run"; key: string; name: string; flownBy: string; when: string; state: string; one: Held["runs"][number] }
  | { kind: "sweep"; key: string; name: string; flownBy: string; when: string; state: string; sweep: Sweep };

export function Runs({ platform, held, onChanged, onReplay, onSweep, onNew, by, view }: {
  platform: Platform;
  held: Held;
  onChanged: () => void;
  onReplay: (dive: string, run: string) => void;
  onSweep: (sweep: string) => void;
  /** Start a run. */
  onNew?: () => void;
  /** Arrive filtered to one controller's runs. */
  by?: string;
  /** Arrive on the repeats view. */
  view?: string;
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

  const [showing, setShowing] = useState<"all" | "repeats">(view === "compare" ? "repeats" : "all");
  const outstanding = held.runs.filter((r) => LIVE.has(r.run.state));
  const rows: Row[] = [
    ...held.runs.filter(({ run }) => !run.sweepId).map((one): Row => ({
      kind: "run", key: one.run.id, name: one.name, flownBy: one.flownBy, when: one.run.requestedAt,
      state: one.run.state === "succeeded" && one.run.outcome?.["surfaced"] === true ? "surfaced" : one.run.state, one })),
    ...(sweeps ?? []).map((w): Row => ({
      kind: "sweep", key: w.id, name: w.name.split(" ~ ")[0]!, flownBy: "the plan's own", when: w.createdAt,
      state: w.flying ? "running" : (w.flown ?? 0) >= (w.runs ?? 0) ? "succeeded" : "queued", sweep: w })),
  ];
  const open = (r: Row) => {
    if (r.kind === "sweep") onSweep(r.sweep.id);
    else onReplay(r.one.dive, r.one.run.id);
  };

  return (
    <Page title="Runs" subtitle="Every run, under one condition or many."
          info="A run flies a mission or a task in a vehicle, under the conditions you chose. Choose one setting for each condition and it is one run; choose several and it is flown once for each, so you see which condition breaks the plan. Every run pins its place, vehicle, water, seed and simulator, so running it again means something."
          actions={onNew ? <Button kind="primary" onClick={onNew}>New run</Button> : undefined}
          toolbar={<Segmented label="View" value={showing} onChange={setShowing}
                              options={[{ key: "all", label: "Every run" }, { key: "repeats", label: "Repeated runs" }]} />}>
      {outstanding.length > 0 ? (
        <section className="running-now">
          <h2>Running now</h2>
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

      {showing === "all" ? (
        <Table rows={rows} loading={!held.runsRead || sweeps === undefined} rowKey={(r) => r.key} initialPicked={by ? { by: [by] } : undefined}
               onRow={open}
               search={(r) => `${r.name} ${r.flownBy} ${r.kind === "run" ? taskOf(r.one) : ""} ${r.state}`} searchLabel="Search runs"
               facets={[
                 { key: "conditions", label: "Conditions", value: (r) => r.kind === "sweep" ? "several" : "one" },
                 { key: "by", label: "Flown by", value: (r) => r.flownBy },
                 { key: "state", label: "State", value: (r) => r.state },
                 { key: "when", label: "When", value: (r) => whenOf(r.when) },
               ]}
               initialSort={{ key: "when", down: true }}
               empty={<>Nothing has been run yet. <a onClick={onNew}>Start a run</a>.</>}
               columns={[
                 { key: "run", label: "Run", grow: true, sort: (a, b) => a.name.localeCompare(b.name),
                   render: (r) => <><span className="cell-main">{r.name}</span><span className="cell-sub">{r.kind === "sweep" ? sweepSaid(r.sweep) : r.flownBy}</span></> },
                 { key: "score", label: "Result", align: "right", sort: (a, b) => resultOf(a) - resultOf(b),
                   render: (r) => <ResultCell row={r} /> },
                 { key: "off", label: "Off at the end", align: "right", priority: 3,
                   render: (r) => <span className="cell-meta">{r.kind === "run" ? closingOf(r.one) : ""}</span> },
                 { key: "when", label: "When", priority: 2, sort: (a, b) => a.when.localeCompare(b.when),
                   render: (r) => <span className="cell-meta">{ago(r.when)}</span> },
                 { key: "state", label: "State", render: (r) => <Status tone={toneOf(r.state)}>{r.state === "succeeded" ? "done" : r.state}</Status> },
               ]}
               actions={(r) => r.kind === "sweep" ? <Button kind="ghost" onClick={() => onSweep(r.sweep.id)}>Open</Button>
                 : <Button kind="ghost" onClick={() => onReplay(r.one.dive, r.one.run.id)}>Open</Button>} />
      ) : (
        <Trials runs={held.runs} loading={!held.runsRead} onReplay={onReplay} />
      )}
    </Page>
  );
}

/** A sweep's second line: how many conditions, and how far it has got. */
function sweepSaid(w: Sweep): string {
  const runs = w.runs ?? 0;
  const ways = w.scenarios || Math.round(runs / Math.max(1, w.repeats ?? 1));
  const flown = w.flown ?? 0;
  return `${ways} ${ways === 1 ? "condition" : "conditions"}${(w.repeats ?? 1) > 1 ? ` × ${w.repeats}` : ""}`
    + (flown < runs ? ` · ${flown} of ${runs} flown` : ` · ${runs} runs`);
}

/** What a row sorts by in the Result column. */
function resultOf(r: Row): number {
  if (r.kind === "run") return scoreOf(r.one);
  const runs = r.sweep.runs ?? 0;
  return runs ? (r.sweep.flown ?? 0) / runs - 2 : -3;
}

/** A score as a number and a short bar; a sweep as how much of it has flown. */
function ResultCell({ row }: { row: Row }): React.JSX.Element {
  if (row.kind === "sweep") {
    const runs = row.sweep.runs ?? 0;
    const flown = row.sweep.flown ?? 0;
    return flown >= runs ? <span className="cell-meta">open to read</span> : <span className="cell-meta">{flown} of {runs}</span>;
  }
  const score = scoreOf(row.one);
  if (score < 0) return <span className="cell-meta">—</span>;
  return (
    <span className="score-bar" title={taskOf(row.one)}>
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

/** The same dive and controller flown several times: a mean and a spread.
 *
 *  Grouped by what was actually being tested — the dive and who flew it — so
 *  two controllers on one dive are two trials rather than one muddle. A run
 *  that was carried by hand is left out of the arithmetic and said so, because
 *  a vehicle that was picked up did not fly the thing being measured.
 */
type Trial = {
  key: string; dive: string; conditions: string; flownBy: string; physics: number;
  runs: Held["runs"]; scores: number[]; mean: number; spread: number; worst: number; best: number; energyWh?: number;
};

/** The same dive flown more than once by one controller on one physics: a
 *  mean and a spread. What computed it is part of what was tested, so runs
 *  either side of a physics change are never one row. */
function trialsOf(runs: Held["runs"]): Trial[] {
  const groups = new Map<string, Held["runs"]>();
  for (const one of runs) {
    if (scoreOf(one) < 0) continue;
    const key = `${one.dive}|${one.flownBy}|${physicsOf(one)}`;
    groups.set(key, [...(groups.get(key) ?? []), one]);
  }
  return [...groups.entries()].filter(([, g]) => g.length > 1).map(([key, g]) => {
    const scores = g.map(scoreOf);
    const mean = scores.reduce((a, b) => a + b, 0) / scores.length;
    const spread = Math.sqrt(scores.reduce((a, b) => a + (b - mean) ** 2, 0) / scores.length);
    const energies = g.map((one) => ((one.run.outcome as Record<string, unknown> | undefined)?.["task"] as { energyWh?: number } | undefined)?.energyWh)
      .filter((e): e is number => typeof e === "number");
    const [dive, ...rest] = g[0]!.name.split(" ~ ");
    return { key, dive: dive!.trim(), conditions: rest.join(" · ").replace(/:/g, ": "), flownBy: g[0]!.flownBy,
             physics: physicsOf(g[0]!), runs: g, scores, mean, spread, worst: Math.min(...scores), best: Math.max(...scores),
             energyWh: energies.length ? energies.reduce((a, b) => a + b, 0) / energies.length : undefined };
  });
}

/** Worst to best on a 0 to 100% scale, the mean as a dot, each run a tick. */
function ScoreRange({ trial }: { trial: Trial }): React.JSX.Element {
  const at = (v: number) => `${(v * 100).toFixed(1)}%`;
  return (
    <span className="score-range" title={`worst ${at(trial.worst)} · mean ${at(trial.mean)} · best ${at(trial.best)}`}>
      <span className="track">
        <span className="span" style={{ left: at(trial.worst), width: at(Math.max(trial.best - trial.worst, 0.004)) }} />
        {trial.scores.map((v, i) => <span key={i} className="tick" style={{ left: at(v) }} />)}
        <span className="mean" style={{ left: at(trial.mean) }} />
      </span>
    </span>
  );
}

function Trials({ runs, loading, onReplay }: { runs: Held["runs"]; loading: boolean; onReplay: (dive: string, run: string) => void }): React.JSX.Element {
  const trials = trialsOf(runs);
  const [open, setOpen] = useState<Trial | undefined>();
  const physics = spans(runs);
  return (
    <>
      <p className="note">The same dive flown more than once by the same controller. Each row is a mean with its spread; the bar runs from the worst run to the best on 0 to 100%, the dot is the mean, and each tick is one run.{physics.length > 1 ? " Runs from different simulator versions are never put in one row." : ""}</p>
      <Table rows={trials} loading={loading} rowKey={(t) => t.key} onRow={setOpen}
             search={(t) => `${t.dive} ${t.conditions} ${t.flownBy}`} searchLabel="Search trials"
             facets={[{ key: "dive", label: "Dive", value: (t) => t.dive }, { key: "by", label: "Flown by", value: (t) => t.flownBy },
                      ...(physics.length > 1 ? [{ key: "physics", label: "Simulator", value: (t: Trial) => t.physics ? `physics ${t.physics}` : "not said" }] : [])]}
             initialSort={{ key: "runs", down: true }}
             empty={<>Nothing flown twice yet. Run the same dive again and its runs are gathered here as a mean and a spread.</>}
             columns={[
               { key: "dive", label: "Dive", sort: (a, b) => a.dive.localeCompare(b.dive),
                 render: (t) => <><span className="cell-main">{t.dive}</span>{t.conditions ? <span className="cell-sub">{t.conditions}</span> : null}</> },
               { key: "by", label: "Flown by", priority: 2, render: (t) => <span className="cell-meta">{t.flownBy}</span> },
               { key: "runs", label: "Runs", align: "right", sort: (a, b) => a.runs.length - b.runs.length, render: (t) => t.runs.length },
               { key: "score", label: "Score", align: "right", sort: (a, b) => a.mean - b.mean,
                 render: (t) => <span className="score-cell"><b>{(t.mean * 100).toFixed(0)}%</b><span className="cell-meta"> ± {(t.spread * 100).toFixed(0)}</span></span> },
               { key: "range", label: "Worst to best", priority: 2, render: (t) => <ScoreRange trial={t} /> },
               { key: "energy", label: "Energy a run", align: "right", priority: 3,
                 render: (t) => <span className="cell-meta">{t.energyWh === undefined ? "—" : `${t.energyWh.toFixed(1)} Wh`}</span> },
             ]} />
      {open ? (
        <Dialog title={open.dive} onClose={() => setOpen(undefined)}
                actions={<Button kind="primary" onClick={() => setOpen(undefined)}>Close</Button>}>
          <p className="note">{open.conditions || "as the plan has it"} · flown by {open.flownBy}{open.physics ? ` · physics ${open.physics}` : ""}</p>
          <table className="dialog-table">
            <thead><tr><th>Run</th><th className="right">Score</th><th>When</th><th /></tr></thead>
            <tbody>
              {open.runs.map((one, i) => (
                <tr key={one.run.id}>
                  <td>{i + 1} · seed {String(one.run.seed).slice(0, 6)}</td>
                  <td className="right"><b>{(scoreOf(one) * 100).toFixed(0)}%</b></td>
                  <td className="cell-meta">{ago(one.run.requestedAt)}</td>
                  <td className="right">{recorded(one.run) ? <Button onClick={() => onReplay(one.dive, one.run.id)}>Replay</Button> : null}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Dialog>
      ) : null}
    </>
  );
}

function Trial({ group }: { group: Held["runs"] }): React.JSX.Element {
  const scored = group.map((one) => {
    const outcome = one.run.outcome as Record<string, unknown>;
    const task = outcome["task"] as { score: number; thrusterEffort?: number; energyWh?: number };
    return { one, score: task.score, energy: task.energyWh,
             carried: typeof outcome["carried"] === "number" ? (outcome["carried"] as number) : 0 };
  });
  const clean = scored.filter((s) => s.carried === 0);
  const counted = clean.length > 1 ? clean : scored;
  const scores = counted.map((s) => s.score);
  const mean = scores.reduce((a, b) => a + b, 0) / scores.length;
  const spread = Math.sqrt(scores.reduce((a, b) => a + (b - mean) ** 2, 0) / scores.length);
  const worst = Math.min(...scores);
  const best = Math.max(...scores);
  const energies = counted.map((s) => s.energy).filter((e): e is number => typeof e === "number");
  const energy = energies.length ? energies.reduce((a, b) => a + b, 0) / energies.length : undefined;
  const carried = scored.length - clean.length;
  return (
    <div className="trial">
      <div className="trial-head">
        <strong>{group[0]!.name}</strong>
        <span className="mean">{(mean * 100).toFixed(0)}%</span>
        <span className="spread">± {(spread * 100).toFixed(0)} · worst {(worst * 100).toFixed(0)}% · best {(best * 100).toFixed(0)}%</span>
        <span className="runs">
          {counted.length} runs by {group[0]!.flownBy}
          {physicsOf(group[0]!) === 0 ? "" : ` · physics ${physicsOf(group[0]!)}`}
        </span>
      </div>
      <div className="spread-bar" title="the band is one standard deviation either side of the mean">
        <span className="band" style={{ left: `${Math.max(0, (mean - spread) * 100)}%`,
                                        width: `${Math.min(100, spread * 200)}%` }} />
        {scores.map((score, i) => (
          <span key={i} className={`tick${score === worst ? " worst" : ""}`}
                style={{ left: `calc(${(score * 100).toFixed(1)}% - 1px)` }} />
        ))}
      </div>
      <p className="aside">
        {energy === undefined ? "" : `${energy.toFixed(1)} Wh a run on average. `}
        {carried > 0 ? `${carried} run${carried > 1 ? "s were" : " was"} carried by hand and left out.` : ""}
      </p>
    </div>
  );
}

/** Dives with more than one scored run, each run's score beside the others'. */
