// What has been run, and what became of it.

import { useState } from "react";

import type { Platform } from "@coral-city/api";

import type { Held } from "./Deck.js";
import { Empty, PageHead, Pill, ago } from "./parts.js";

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

export function Runs({ platform, held, onChanged, onReplay }: {
  platform: Platform;
  held: Held;
  onChanged: () => void;
  onReplay: (dive: string, run: string) => void;
}): React.JSX.Element {
  const [ending, setEnding] = useState<string | undefined>();
  // A record with a matrix in it is a record somebody has to find one row of.
  const [sift, setSift] = useState("");
  const [showing, setShowing] = useState(60);
  const words = sift.trim().toLowerCase().split(/\s+/).filter(Boolean);
  const shown = words.length === 0 ? held.runs : held.runs.filter(({ name, flownBy }) => {
    const said = `${name} ${flownBy}`.toLowerCase();
    return words.every((word) => said.includes(word));
  });

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

  return (
    <>
      <PageHead title="Dives"
        says="Every run pins its place, its vehicle, its water, its seed and the runtime that produced it — which is what makes running the same thing twice mean something." />

      {outstanding.length > 0 && (
        <section>
          <h2>Holding a machine</h2>
          <div className="ledger runs">
            {outstanding.map(({ dive, name, flownBy, run }) => (
              <div className="row" key={run.id}>
                <div className="who">
                  <strong>{name}</strong>
                  <span className="when">{meta(name, flownBy, run)}</span>
                </div>
                <span className="result" />
                <button className="quiet small" disabled={ending === run.id}
                        onClick={() => void end(dive, run.id)}>
                  {ending === run.id ? "Ending…" : "End it"}
                </button>
                <Pill kind="busy">{run.state}</Pill>
              </div>
            ))}
          </div>
        </section>
      )}

      <section>
        <h2>All of them</h2>
        {held.runs.length > 12 ? (
          <div className="sift">
            <input value={sift} onChange={(e) => setSift(e.target.value)}
                   placeholder={`Search ${held.runs.length} runs — a task, a water, a technology…`} />
            <span>{shown.length === held.runs.length
              ? `${held.runs.length} runs`
              : `${shown.length} of ${held.runs.length}`}</span>
          </div>
        ) : null}
        {held.runs.length === 0 ? (
          <Empty title="Nothing has been run yet">
            Dives appear here as soon as you ask for one.
          </Empty>
        ) : (
          <div className="ledger runs">
            {shown.slice(0, showing).map(({ dive, name, flownBy, run }) => (
              <div className="row" key={run.id}>
                <div className="who">
                  <strong>{name}</strong>
                  <span className="when">{meta(name, flownBy, run)}</span>
                </div>
                <Result outcome={run.outcome} />
                {recorded(run) ? (
                  <button className="quiet small" onClick={() => onReplay(dive, run.id)}>Replay</button>
                ) : <span />}
                <Pill kind={run.state === "succeeded" ? "good"
                  : LIVE.has(run.state) ? "busy"
                  : run.state === "failed" ? "bad" : undefined}>
                  {run.state === "succeeded" && run.outcome?.["surfaced"] === true ? "surfaced" : run.state}
                </Pill>
              </div>
            ))}
            {shown.length > showing ? (
              <button className="quiet more" onClick={() => setShowing(showing + 100)}>
                {shown.length - showing} more
              </button>
            ) : null}
          </div>
        )}
      </section>

      <section>
        <h2>Trials</h2>
        <NotOneTable runs={held.runs} of="dives" />
        <p className="aside">
          One run of one seed is an anecdote. The same dive flown more than once is a
          number with a spread on it, which is the only honest way to say one controller
          is better than another.
        </p>
        <Trials runs={held.runs} />
      </section>

      <section>
        <h2>Side by side</h2>
        <p className="aside">The same dive run more than once, with what each run scored — a change to a controller as a change in a number.</p>
        <Compared runs={held.runs} />
      </section>
    </>
  );
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
        Run the same dive again — from the app, or with <code>coral-city dive --again</code> —
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
