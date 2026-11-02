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
import { Button, Dialog, Page, Status, Table, type Tone } from "../ui/components.js";

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
          tabs={[{ key: "dives", label: "Dives", count: held.runsRead ? dives.length : undefined }, { key: "sweeps", label: "Sweeps", count: sweeps?.length },
                 { key: "compare", label: "Compare" }]}
          tab={tab} onTab={setTab}>
      {tab === "dives" && outstanding.length > 0 ? (
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
        <Table rows={dives} loading={!held.runsRead} rowKey={(r) => r.run.id} initialPicked={by ? { by: [by] } : undefined}
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
        <Table rows={sweeps ?? []} loading={sweeps === undefined} rowKey={(w) => w.id} onRow={(w) => onSweep(w.id)}
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
        <Trials runs={held.runs} loading={!held.runsRead} onReplay={onReplay} />
      )}
    </Page>
  );
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
export function recorded(run: { artefacts?: number; outcome?: Record<string, unknown> }): boolean {
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
