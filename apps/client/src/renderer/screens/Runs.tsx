// What has been run, and what became of it.

import { useState } from "react";

import type { Platform } from "@coral-city/api";

import type { Held } from "./Deck.js";
import { Empty, PageHead, Pill, ago } from "./parts.js";

const LIVE = new Set(["queued", "preparing", "running"]);

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
  if (task === undefined || typeof task.score !== "number") return <span className="result" />;
  return (
    <span className="result" title={task.done ? "the task ran to its end" : "the dive ended before the task did"}>
      {task.name}: <b>{(task.score * 100).toFixed(0)}%</b>
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
    const key = `${one.dive}|${one.flownBy}`;
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
        <span className="runs">{counted.length} runs by {group[0]!.flownBy}</span>
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
          <ul>
            {group.map(({ run, flownBy }) => {
              const task = (run.outcome as Record<string, unknown>)["task"] as { score: number; seconds?: number; thrusterEffort?: number };
              return (
                <li key={run.id}>
                  <span className="score-bar"><span style={{ width: `${Math.round(task.score * 100)}%` }} /></span>
                  <b>{(task.score * 100).toFixed(0)}%</b>
                  <em>{flownBy} · seed {String(run.seed).slice(0, 6)} · effort {task.thrusterEffort?.toFixed(3) ?? "—"} · {ago(run.requestedAt)}</em>
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </div>
  );
}
