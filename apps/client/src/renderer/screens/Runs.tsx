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
            {held.runs.slice(0, 40).map(({ dive, name, run }) => (
              <div className="row" key={run.id}>
                <strong>{name}</strong>
                <span className="when">{run.mode === "interactive" ? "flown" : "batch"} · {ago(run.requestedAt)}</span>
                <Result outcome={run.outcome} />
                {recorded(run) ? (
                  <button className="quiet small" onClick={() => onReplay(dive, run.id)}>Replay</button>
                ) : null}
                <Pill kind={run.state === "succeeded" ? "good"
                  : LIVE.has(run.state) ? "busy"
                  : run.state === "failed" ? "bad" : undefined}>
                  {run.state === "succeeded" && run.outcome?.["surfaced"] === true ? "surfaced" : run.state}
                </Pill>
              </div>
            ))}
          </div>
        )}
      </section>

      <section>
        <h2>Coming</h2>
        <Empty title="Running it again" soon="not built yet">
          A run pins everything it needed, so it can be run again and produce the
          same trajectory. Playing a recording back is here; asking for the same
          run again is not yet.
        </Empty>
      </section>
    </>
  );
}

/** Whether the run left a recording behind. */
function recorded(run: { artefacts?: number; outcome?: Record<string, unknown> }): boolean {
  if ((run.artefacts ?? 0) > 0) return true;
  const recording = run.outcome?.["recording"] as { files?: number } | undefined;
  return typeof recording?.files === "number" && recording.files > 0;
}

/** What the dive achieved, when it was for something. */
function Result({ outcome }: { outcome: Record<string, unknown> | undefined }): React.JSX.Element | null {
  const task = outcome?.["task"] as { name?: string; score?: number; seconds?: number; done?: boolean } | undefined;
  if (task === undefined || typeof task.score !== "number") return null;
  return (
    <span className="result" title={task.done ? "the task ran to its end" : "the dive ended before the task did"}>
      {task.name}: <b>{(task.score * 100).toFixed(0)}%</b>
    </span>
  );
}
