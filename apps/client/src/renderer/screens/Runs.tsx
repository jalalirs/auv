// What has been run, and what became of it.

import { useState } from "react";

import type { Platform } from "@coral-city/api";

import type { Held } from "./Deck.js";
import { Empty, PageHead, Pill, ago } from "./parts.js";

const LIVE = new Set(["queued", "preparing", "running"]);

export function Runs({ platform, held, onChanged }: {
  platform: Platform;
  held: Held;
  onChanged: () => void;
}): React.JSX.Element {
  const [ending, setEnding] = useState<string | undefined>();

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
          <div className="ledger">
            {outstanding.map(({ dive, run }) => (
              <div className="row" key={run.id}>
                <strong>{run.mode === "interactive" ? "Flown" : "Batch"}</strong>
                <Pill kind="busy">{run.state}</Pill>
                <button className="quiet" disabled={ending === run.id}
                        onClick={() => void end(dive, run.id)}>
                  {ending === run.id ? "Ending…" : "End it"}
                </button>
              </div>
            ))}
          </div>
        </section>
      )}

      <section>
        <h2>All of them</h2>
        {held.runs.length === 0 ? (
          <Empty title="Nothing has been run yet">
            Dives appear here as soon as you ask for one.
          </Empty>
        ) : (
          <div className="ledger">
            {held.runs.slice(0, 40).map(({ run }) => (
              <div className="row" key={run.id}>
                <strong>{run.mode === "interactive" ? "Flown" : "Batch"}</strong>
                <span className="when">{ago(run.requestedAt)}</span>
                <Pill kind={run.state === "succeeded" ? "good"
                  : LIVE.has(run.state) ? "busy"
                  : run.state === "failed" ? "bad" : undefined}>
                  {run.state}
                </Pill>
              </div>
            ))}
          </div>
        )}
      </section>

      <section>
        <h2>Coming</h2>
        <Empty title="Replay, and scoring" soon="not built yet">
          A run pins everything it needed, so it can be run again and produce the
          same trajectory. What is missing is watching it back, and a score against
          what the dive was trying to do.
        </Empty>
      </section>
    </>
  );
}
