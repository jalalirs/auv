// What each controller has actually done.
//
// The Autonomy page answered "what have I uploaded". That is the smallest
// question anybody has about a controller. The one they have is **which of
// these should fly my mission**, and the platform already holds the answer:
// every dive this institution defined, which stack flew it, and what became
// of it. Nothing here needs an endpoint that does not exist — it needs the
// runs to be read against the controller that flew them.
//
// A controller that has never flown says so, in those words. It is the most
// useful row on the page: it is the difference between a controller somebody
// deployed and a controller somebody trusts.

import type { Run } from "@coral-city/api";

/** One controller's record, over every dive it flew. */
export interface Record_ {
  dives: number;
  succeeded: number;
  /** Mean of the task score, over the dives that finished with a task. */
  score: number | undefined;
  /** How far its navigation had drifted when it came up, averaged. */
  driftM: number | undefined;
  /** What it spent, averaged over the dives that carried a battery. */
  energyWh: number | undefined;
  /** Things it ran into, summed — a controller that hit three frames on one
   *  dive and nothing on seven did not hit three-eighths of a frame. */
  struck: number;
  /** When it last flew, or nothing if it never has. */
  lastAt: string | undefined;
  /** Dives the platform could not start. Not this controller's failures, so
   *  not counted among its dives — but not hidden either. */
  neverFlew: number;
}

type Flight = { name: string; flownBy: string; run: Run };

// What a failure is about, by what the agent said when it gave up.
//
// The agent writes these sentences in one place — services/worker's diver —
// and both this and `tools/bench` read them. Two matchers on one wire
// format, which is what a wire format is for; what must not happen is two
// different ideas of whose failure it was.
//
// A dive the platform could not start is not somebody's controller flying
// badly, and counting it as one of that controller's dives puts the wrong
// name on a number. Unknown counts as the platform's: attributing a failure
// to a controller on a guess is the one direction that must not be guessed.
const THEIRS = [
  "the controller started and then stopped",
  "defined with a controller and it would not start",
  "defined with a controller and the vehicle never came up",
];

function theirFault(run: Run): boolean {
  const why = String((run as { failureReason?: string }).failureReason ?? "").toLowerCase();
  return THEIRS.some((one) => why.includes(one));
}

function mean(values: number[]): number | undefined {
  return values.length === 0 ? undefined
    : values.reduce((a, b) => a + b, 0) / values.length;
}

/**
 * What one controller has flown, out of every run the institution holds.
 *
 * Matched on the name the dive was flown by, which is what the platform
 * records against a dive that names a stack. A controller renamed between
 * builds is two names and will read as two controllers; that is the record
 * telling the truth rather than this guessing.
 */
export function recordOf(name: string, runs: Flight[]): Record_ {
  const mine = runs
    .filter((one) => one.flownBy === name)
    .filter((one) => one.run.state !== "failed" || theirFault(one.run));
  const done = mine.filter((one) => one.run.state === "succeeded");
  const outcomes = done.map((one) => (one.run.outcome ?? {}) as Record<string, unknown>);
  const tasks = outcomes
    .map((out) => out["task"] as { score?: number; energyWh?: number } | undefined)
    .filter((task): task is { score?: number; energyWh?: number } => task !== undefined);
  const drifts = outcomes
    .map((out) => (out["navigation"] as { driftM?: number } | undefined)?.driftM)
    .filter((v): v is number => typeof v === "number");
  const struck = outcomes
    .map((out) => (out["hit"] as { things?: number } | undefined)?.things ?? 0)
    .reduce((a, b) => a + b, 0);
  const when = mine
    .map((one) => one.run.requestedAt)
    .filter((v): v is string => typeof v === "string")
    .sort();
  return {
    dives: mine.length,
    succeeded: done.length,
    score: mean(tasks.map((t) => t.score).filter((v): v is number => typeof v === "number")),
    driftM: mean(drifts),
    energyWh: mean(tasks.map((t) => t.energyWh).filter((v): v is number => typeof v === "number")),
    struck,
    lastAt: when[when.length - 1],
    neverFlew: runs.filter((one) => one.flownBy === name
      && one.run.state === "failed" && !theirFault(one.run)).length,
  };
}

// ---------------------------------------------------------------------------
// Which of two controllers is better, which is not what an average can say.
//
// Every row above averages one controller over the dives it happened to fly.
// Those are not the same dives: a controller that flew three station holds and
// a controller that flew three transects have two numbers that cannot be put
// beside each other, and the page was putting them beside each other. Worse,
// the higher number belonged to whoever had flown the easier set — so the one
// thing the page invited you to do was the one thing it could not support.
//
// A comparison is a comparison when the dive is the same dive. The bench
// already guarantees that and says so in the name it gives each row:
//
//     bench · <suite> · <controller>[ on <hull>][ over <reef>] · <task>
//
// so two rows describe the same trial when the suite, the task, the hull and
// the reef all match and only the controller differs. The seed follows from the
// suite and the task, which is what makes the trial repeatable in the first
// place. Nothing outside the bench is compared: a dive somebody set up by hand
// has no counterpart and is not pretended to have one.

/** One trial, as a bench row names it. */
interface Trial {
  suite: string;
  task: string;
  /** The hull and the reef, as the row states them — "" when both are the usual. */
  over: string;
}

const PARTS = " · ";

/**
 * The trial a bench row describes, or nothing if the row is not a bench row.
 *
 * The controller's own field carries the hull, the reef, and whether there was
 * anything in the water when those are not the usual ones — "pursue on
 * remus-100 over al-fahal through things" — so what is left of that field after
 * the controller's name is part of the trial and not part of who flew it.
 *
 * All three matter and "through" most of all: a dive flown through things and a
 * dive flown through open water are not the same dive, and reading them as one
 * trial would compare a controller that had obstacles against one that did not
 * and call the difference skill.
 */
export function trialOf(name: string): Trial | undefined {
  const parts = name.split(PARTS);
  if (parts.length !== 4 || parts[0] !== "bench") return undefined;
  const [, suite, whose, task] = parts as [string, string, string, string];
  const said = / (on|over|through) /.exec(whose);
  return { suite, task, over: said === null ? "" : whose.slice(said.index + 1) };
}

const sameTrial = (a: Trial, b: Trial) =>
  a.suite === b.suite && a.task === b.task && a.over === b.over;

/** How one controller did against another, over the trials they both flew. */
export interface HeadToHead {
  /** The other controller, by the name the record holds. */
  against: string;
  /** Trials both of them flew and both of them scored. */
  shared: number;
  /** Of those, the ones this controller scored higher on. */
  better: number;
  /** And the ones neither won, to the third decimal — a tie is a finding. */
  same: number;
}

type Scored = { trial: Trial; score: number };

function scoredTrials(name: string, runs: Flight[]): Scored[] {
  const out: Scored[] = [];
  for (const one of runs) {
    if (one.flownBy !== name || one.run.state !== "succeeded") continue;
    const trial = trialOf(one.name);
    if (trial === undefined) continue;
    const score = ((one.run.outcome ?? {}) as { task?: { score?: number } }).task?.score;
    if (typeof score !== "number") continue;
    out.push({ trial, score });
  }
  return out;
}

/**
 * This controller against each of the others, over the trials they share.
 *
 * Sorted by how much there is to go on — a controller compared over eight
 * trials says more than one compared over one — and controllers with nothing in
 * common are left out rather than reported as a nil-all draw.
 */
export function headToHead(name: string, others: string[], runs: Flight[]): HeadToHead[] {
  const mine = scoredTrials(name, runs);
  const out: HeadToHead[] = [];
  for (const against of others) {
    if (against === name) continue;
    const theirs = scoredTrials(against, runs);
    let shared = 0, better = 0, same = 0;
    for (const one of mine) {
      const match = theirs.find((two) => sameTrial(one.trial, two.trial));
      if (match === undefined) continue;
      shared += 1;
      // To the third decimal, because two controllers that differ only in
      // floating-point noise did the same thing and saying otherwise would
      // make a bench reward rounding.
      const gap = Math.round((one.score - match.score) * 1000);
      if (gap > 0) better += 1;
      else if (gap === 0) same += 1;
    }
    if (shared > 0) out.push({ against, shared, better, same });
  }
  return out.sort((a, b) => b.shared - a.shared);
}

/** The head-to-head as the page says it, or nothing when there is nothing to say. */
export function saidAs(one: HeadToHead): string {
  if (one.same === one.shared) {
    return `the same as ${one.against} on all ${one.shared} shared ${
      one.shared === 1 ? "task" : "tasks"}`;
  }
  return `better than ${one.against} on ${one.better} of ${one.shared}${
    one.same > 0 ? `, level on ${one.same}` : ""}`;
}
