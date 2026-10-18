// What has been run, and what became of it.
//
// One list for a dive flown once and a plan flown every way the day could go:
// a sweep is a row of its own, its runs folded under it, because a hundred
// runs of one question listed one by one bury the dives somebody flew by hand.

import { useState } from "react";

import type { Platform, Sweep } from "@coral-city/api";

import type { Held } from "./Deck.js";
import { useSweeps } from "./Sweeps.js";
import { Empty, ago } from "./parts.js";
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

/** How many different physics a set of runs was computed by. */
function spans(runs: Held["runs"]): number[] {
  return [...new Set(runs.map(physicsOf))].sort((a, b) => a - b);
}

/** Said wherever runs are put in a table together.
 *
 * The platform pins the place, the vehicle, the water and the seed, and pinned
 * none of that mattered while the simulator itself was moving under it. Two
 * runs from either side of a change to the physics are two answers to two
 * different questions, and a mean taken across them is a number that looks
 * like a measurement and is not one.
 */
function NotOneTable({ runs, of }: { runs: Held["runs"]; of: string }): React.JSX.Element | null {
  const versions = spans(runs);
  if (versions.length < 2) return null;
  const said = versions.map((v) => (v === 0 ? "runs that did not say" : `physics ${v}`));
  return (
    <p className="aside warn">
      These {of} were not all computed by the same simulator — {said.join(" and ")}.
      A change to the physics changes the answer, so they are kept apart rather
      than averaged: two runs either side of one are two answers to two
      different questions.
    </p>
  );
}

export function Runs({ platform, held, onChanged, onReplay, onSweep, by, view }: {
  platform: Platform;
  held: Held;
  onChanged: () => void;
  onReplay: (dive: string, run: string) => void;
  onSweep: (sweep: string) => void;
  /** Arrive filtered to one controller's dives. */
  by?: string;
  /** Arrive on a tab: dives, sweeps or compare. */
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

  const outstanding = held.runs.filter((r) => LIVE.has(r.run.state));
  const [tab, setTab] = useState(view ?? "dives");
  const dives = held.runs.filter(({ run }) => !run.sweepId);

  return (
    <Page title="Runs" subtitle="Every dive and sweep flown, with what each scored."
          info="Every run pins its place, its vehicle, its water, its seed and the runtime that produced it, which is what makes running the same thing twice mean something. A sweep is one plan flown every way the day could go; its runs are under it."
          tabs={[{ key: "dives", label: "Dives", count: dives.length }, { key: "sweeps", label: "Sweeps", count: sweeps.length },
                 { key: "compare", label: "Compare" }]}
          tab={tab} onTab={setTab}>
      {outstanding.length > 0 ? (
        <section className="holding">
          <h2>Holding a machine</h2>
          <Table rows={outstanding} rowKey={(r) => r.run.id} pageSize={10}
                 columns={[
                   { key: "run", label: "Run", render: (r) => <><span className="cell-main">{r.name}</span><span className="cell-sub">{meta(r.name, r.flownBy, r.run)}</span></> },
                   { key: "state", label: "State", render: (r) => <Status tone="busy">{r.run.state}</Status> },
                 ]}
                 actions={(r) => <Button kind="danger" disabled={ending === r.run.id} onClick={() => void end(r.dive, r.run.id)}>{ending === r.run.id ? "Ending…" : "End it"}</Button>} />
        </section>
      ) : null}

      {tab === "dives" ? (
        <Table rows={dives} rowKey={(r) => r.run.id} initialPicked={by ? { by: [by] } : undefined}
               onRow={(r) => { if (recorded(r.run)) onReplay(r.dive, r.run.id); }}
               search={(r) => `${r.name} ${r.flownBy} ${taskOf(r)} ${r.run.state}`} searchLabel="Search dives"
               facets={[
                 { key: "task", label: "Task", value: (r) => taskOf(r) || "no task" },
                 { key: "by", label: "Flown by", value: (r) => r.flownBy },
                 { key: "state", label: "State", value: (r) => r.run.state },
                 { key: "how", label: "How", value: (r) => r.run.mode === "interactive" ? "watched" : "batch" },
                 { key: "when", label: "When", value: (r) => whenOf(r.run.requestedAt) },
               ]}
               initialSort={{ key: "when", down: true }}
               empty={<>Nothing has been run yet. Dives appear here as soon as you ask for one.</>}
               columns={[
                 { key: "run", label: "Dive", sort: (a, b) => a.name.localeCompare(b.name),
                   render: (r) => <><span className="cell-main">{r.name}</span><span className="cell-sub">{meta(r.name, r.flownBy, r.run)}</span></> },
                 { key: "score", label: "Score", align: "right", sort: (a, b) => scoreOf(a) - scoreOf(b),
                   render: (r) => scoreOf(r) >= 0 ? <span title={taskOf(r)}><b>{(scoreOf(r) * 100).toFixed(0)}%</b></span> : <span className="cell-meta">—</span> },
                 { key: "result", label: "How it went", priority: 3, render: (r) => <span className="cell-sub run-detail"><Result outcome={r.run.outcome} /></span> },
                 { key: "when", label: "When", priority: 2, sort: (a, b) => a.run.requestedAt.localeCompare(b.run.requestedAt),
                   render: (r) => <span className="cell-meta">{ago(r.run.requestedAt)}</span> },
                 { key: "state", label: "State", render: (r) => <Status tone={toneOf(r.run.state)}>{r.run.state === "succeeded" && r.run.outcome?.["surfaced"] === true ? "surfaced" : r.run.state}</Status> },
               ]}
               actions={(r) => recorded(r.run) ? <Button onClick={() => onReplay(r.dive, r.run.id)}>Replay</Button> : null} />
      ) : tab === "sweeps" ? (
        <Table rows={sweeps} rowKey={(w) => w.id} onRow={(w) => onSweep(w.id)}
               search={(w) => w.name} searchLabel="Search sweeps"
               facets={[{ key: "state", label: "State", value: (w) => sweepState(w) }, { key: "when", label: "When", value: (w) => whenOf(w.createdAt) }]}
               initialSort={{ key: "when", down: true }}
               empty={<>No sweeps yet. A sweep flies one plan every way the day could go; start one from Fly.</>}
               columns={[
                 { key: "name", label: "Sweep", sort: (a, b) => a.name.localeCompare(b.name), render: (w) => <span className="cell-main">{w.name}</span> },
                 { key: "flown", label: "Flown", align: "right", render: (w) => <span className="cell-meta">{w.flown ?? 0} of {w.runs ?? 0}{w.flying ? ` · ${w.flying} flying` : ""}</span> },
                 { key: "when", label: "When", priority: 2, sort: (a, b) => a.createdAt.localeCompare(b.createdAt), render: (w) => <span className="cell-meta">{ago(w.createdAt)}</span> },
                 { key: "state", label: "State", render: (w) => <Status tone={w.flying ? "busy" : sweepState(w) === "swept" ? "good" : "quiet"}>{sweepState(w)}</Status> },
               ]}
               actions={(w) => <Button onClick={() => onSweep(w.id)}>Read it</Button>} />
      ) : (
        <>
          <section>
            <h2>Trials</h2>
            <NotOneTable runs={held.runs} of="dives" />
            <p className="note">The same dive flown more than once: a number with a spread on it, the only honest way to say one controller is better than another.</p>
            <Trials runs={held.runs} />
          </section>
          <section>
            <h2>Side by side</h2>
            <p className="note">The same dive run more than once, with what each run scored.</p>
            <Compared runs={held.runs} />
          </section>
        </>
      )}
    </Page>
  );
}

function taskOf(one: Held["runs"][number]): string {
  return ((one.run.outcome as Record<string, unknown> | undefined)?.["task"] as { name?: string } | undefined)?.name ?? "";
}

function scoreOf(one: Held["runs"][number]): number {
  const score = ((one.run.outcome as Record<string, unknown> | undefined)?.["task"] as { score?: number } | undefined)?.score;
  return typeof score === "number" ? score : -1;
}

function toneOf(state: string): Tone {
  return state === "succeeded" ? "good" : LIVE.has(state) ? "busy" : state === "failed" ? "bad" : "quiet";
}

function sweepState(w: Sweep): string {
  return w.flying ? "sweeping" : (w.flown ?? 0) >= (w.runs ?? 0) ? "swept" : "waiting";
}

/** When, as the buckets a person filters by. */
function whenOf(iso: string): string {
  const days = (Date.now() - new Date(iso).getTime()) / 86_400_000;
  return days < 1 ? "today" : days < 7 ? "this week" : days < 31 ? "this month" : "older";
}

/** The second line under a run's name: who flew it, unless the name already
 *  says, how, and when. */
function meta(name: string, flownBy: string, run: { mode: string; requestedAt: string }): string {
  const who = name.includes(flownBy) ? "" : `${flownBy} · `;
  return `${who}${run.mode === "interactive" ? "flown" : "batch"} · ${ago(run.requestedAt)}`;
}

/** Whether the run left a recording behind. */
function recorded(run: { artefacts?: number; outcome?: Record<string, unknown> }): boolean {
  if ((run.artefacts ?? 0) > 0) return true;
  const recording = run.outcome?.["recording"] as { files?: number } | undefined;
  return typeof recording?.files === "number" && recording.files > 0;
}

/** What the dive achieved, when it was for something. */
function Result({ outcome }: { outcome: Record<string, unknown> | undefined }): React.JSX.Element {
  const task = outcome?.["task"] as { name?: string; score?: number; seconds?: number; done?: boolean } | undefined;
  // How far out the vehicle was when it came up. The task's score says whether
  // it did the job; this says whether it knew where it was doing it, and the
  // two are different dives going wrong.
  const fix = outcome?.["closingFix"] as
    { errorM?: number; atSurface?: boolean; shareOfDistance?: number | null } | undefined;
  if (task === undefined || typeof task.score !== "number") return <span className="result" />;
  return (
    <span className="result" title={task.done ? "the task ran to its end" : "the dive ended before the task did"}>
      {task.name}: <b>{(task.score * 100).toFixed(0)}%</b>
      {typeof fix?.errorM === "number" ? (
        <span className="quiet" title={fix.atSurface
          ? "where it thought it was against where it was, at the surface — the fix a real dive closes on"
          : "it did not surface, so this is the error at the end rather than a closing fix"}>
          {" · "}{fix.atSurface ? "" : "~"}{fix.errorM.toFixed(1)} m out
          {typeof fix.shareOfDistance === "number"
            ? ` (${(fix.shareOfDistance * 100).toFixed(1)}% of the way run)` : ""}
        </span>
      ) : null}
      <Ride ride={(outcome?.["task"] as { ride?: RideSaid } | undefined)?.ride} />
    </span>
  );
}

/** How the run was flown, as the runtime's ride card says (tasks/ride.py). */
interface RideSaid {
  effort?: { meanShare?: number; peakShare?: number; flatOutShare?: number };
  rollDeg?: { typical?: number; worst?: number };
  pitchDeg?: { typical?: number; worst?: number };
  offLine?: { secondsOff?: number; secondsOnTheLine?: number; worstM?: number; thresholdM?: number };
}

/** Effort, roll and pitch, and time off the line, beside the score: two runs
 *  that both scored 100% can be one flown on a quarter of its thrust, level
 *  and on the line, and one flat out, rolling and wandering. */
function Ride({ ride }: { ride: RideSaid | undefined }): React.JSX.Element | null {
  if (ride === undefined) return null;
  const parts: string[] = [];
  if (typeof ride.effort?.meanShare === "number") {
    parts.push(`${(ride.effort.meanShare * 100).toFixed(0)}% thrust`
      + (ride.effort.flatOutShare ? `, flat out ${(ride.effort.flatOutShare * 100).toFixed(0)}% of the time` : ""));
  }
  const worst = Math.max(ride.rollDeg?.worst ?? 0, ride.pitchDeg?.worst ?? 0);
  if (ride.rollDeg !== undefined) parts.push(`tilted up to ${worst.toFixed(0)}°`);
  if (ride.offLine !== undefined && typeof ride.offLine.secondsOff === "number") {
    parts.push(ride.offLine.secondsOff > 0
      ? `${ride.offLine.secondsOff.toFixed(0)} s off the line, ${(ride.offLine.worstM ?? 0).toFixed(1)} m at worst`
      : "on the line throughout");
  }
  if (parts.length === 0) return null;
  return (
    <span className="quiet" title={"How it was flown, from the simulator's own state: the thrusters' mean command"
      + " as a share of full, the worst roll or pitch, and for a task flown along a line, the time spent more than"
      + ` ${ride.offLine?.thresholdM ?? 1} m off it once it had come onto it`}>
      {" · "}{parts.join(" · ")}
    </span>
  );
}


/** The same dive and controller flown several times: a mean and a spread.
 *
 *  Grouped by what was actually being tested — the dive and who flew it — so
 *  two controllers on one dive are two trials rather than one muddle. A run
 *  that was carried by hand is left out of the arithmetic and said so, because
 *  a vehicle that was picked up did not fly the thing being measured.
 */
function Trials({ runs }: { runs: Held["runs"] }): React.JSX.Element {
  const groups = new Map<string, Held["runs"]>();
  for (const one of runs) {
    const outcome = one.run.outcome as Record<string, unknown> | undefined;
    const task = outcome?.["task"] as { score?: number } | undefined;
    if (typeof task?.score !== "number") continue;
    // What computed it is part of what was being tested. Without this a
    // controller that was "improved" on Tuesday is compared against itself
    // across a physics change, and the improvement is the simulator.
    const key = `${one.dive}|${one.flownBy}|${physicsOf(one)}`;
    groups.set(key, [...(groups.get(key) ?? []), one]);
  }
  const trials = [...groups.values()].filter((g) => g.length > 1)
    .sort((a, b) => b.length - a.length);
  if (trials.length === 0) {
    return (
      <Empty title="Nothing flown twice yet">
        Run the same dive again — from the app, or with <code>iocean dive --again</code> —
        and its runs are gathered here as a mean and a spread.
      </Empty>
    );
  }
  return (
    <div className="trials">
      {trials.map((group) => <Trial key={group[0]!.run.id} group={group} />)}
    </div>
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
function Compared({ runs }: { runs: Held["runs"] }): React.JSX.Element {
  const byDive = new Map<string, Held["runs"]>();
  for (const one of runs) {
    const task = (one.run.outcome as Record<string, unknown> | undefined)?.["task"] as { score?: number } | undefined;
    if (typeof task?.score !== "number") continue;
    byDive.set(one.dive, [...(byDive.get(one.dive) ?? []), one]);
  }
  const groups = [...byDive.values()].filter((g) => g.length > 1);
  if (groups.length === 0) {
    return <Empty title="Nothing to compare yet">Run a dive with a task twice, or with two controllers, and the scores line up here.</Empty>;
  }
  return (
    <div className="compared">
      {groups.map((group) => (
        <div className="group" key={group[0]!.dive}>
          <strong>{group[0]!.name}</strong>
          <NotOneTable runs={group} of="runs" />
          <ul>
            {group.map(({ run, flownBy }) => {
              const task = (run.outcome as Record<string, unknown>)["task"] as { score: number; seconds?: number; thrusterEffort?: number };
              return (
                <li key={run.id}>
                  <span className="score-bar"><span style={{ width: `${Math.round(task.score * 100)}%` }} /></span>
                  <b>{(task.score * 100).toFixed(0)}%</b>
                  <em>{flownBy} · seed {String(run.seed).slice(0, 6)}
                    {run.physicsVersion === undefined ? "" : ` · physics ${run.physicsVersion}`}
                    {" "}· effort {task.thrusterEffort?.toFixed(3) ?? "—"} · {ago(run.requestedAt)}</em>
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </div>
  );
}
