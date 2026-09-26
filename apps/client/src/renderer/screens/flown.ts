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
}

type Flight = { name: string; flownBy: string; run: Run };

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
  const mine = runs.filter((one) => one.flownBy === name);
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
  };
}
