// Between asking and being in the water.
//
// There is no GPU to pick. You asked for a dive; either a device is free and
// the platform starts it, or none is and it says so. A queue with nothing free
// is not an error and is not a failure — it is a thing that happens on shared
// hardware, and the honest response is to say it plainly and offer to try
// again.

import { useCallback, useEffect, useRef, useState } from "react";

import type { Platform, RunEvent } from "@coral-city/api";

import type { Stream } from "../App.js";
import { Badge } from "./parts.js";

/** How often the platform is asked what happened to the run. */
const ASK_EVERY = 2000;

export function Waiting({ platform, dive, run, onRunning, onGiveUp }: {
  platform: Platform;
  dive: string;
  run: string;
  onRunning: (stream: Stream) => void;
  onGiveUp: () => void;
}): React.JSX.Element {
  const [said, setSaid] = useState("Finding you a machine…");
  const [stuck, setStuck] = useState<string | undefined>();
  const [waited, setWaited] = useState(0);
  const done = useRef(false);

  const look = useCallback(async () => {
    if (done.current) return;
    const [state, events] = await Promise.all([
      platform.runs(dive).then((runs) => runs.find((r) => r.id === run)),
      platform.events(dive, run).catch((): RunEvent[] => []),
    ]);

    const open = events.find((e) => e.kind === "stream_open");
    if (open !== undefined) {
      done.current = true;
      const detail = open.detail as Record<string, unknown>;
      onRunning({
        host: String(detail.host),
        signalPort: Number(detail.signalPort),
        diveId: dive,
        runId: run,
      });
      return;
    }

    // Every way a run can be over, not only the one that says failed. A run
    // that expired while it waited is finished and will never start, and
    // watching it for a stream is watching forever — which is exactly what
    // this did: it sat on "waiting for a free GPU" with two free GPUs.
    const over: Record<string, string> = {
      failed: "The dive could not be started.",
      expired: "That request waited too long and the platform let it go.",
      cancelled: "The dive was cancelled.",
      succeeded: "The dive finished before it could be watched.",
    };
    if (state !== undefined && state.state in over) {
      done.current = true;
      setStuck(state.failureReason || over[state.state]!);
      return;
    }

    // Queued means the platform has the request and no device yet. Preparing
    // means it has one and is fetching the place, which on a first dive is
    // hundreds of megabytes and takes as long as it takes.
    setSaid(state?.state === "preparing"
      ? "Syncing the place onto the machine…"
      : "Waiting for a free GPU…");
  }, [platform, dive, run, onRunning]);

  useEffect(() => {
    const tick = setInterval(() => {
      setWaited((w) => w + ASK_EVERY / 1000);
      void look();
    }, ASK_EVERY);
    void look();
    return () => clearInterval(tick);
  }, [look]);

  if (stuck !== undefined) {
    return (
      <div className="middle">
        <Badge />
        <div className="waiting">
          <h2>No water right now</h2>
          <p>{stuck}</p>
          <button onClick={onGiveUp}>Try again</button>
        </div>
      </div>
    );
  }

  return (
    <div className="middle">
      <Badge />
      <div className="waiting">
        <h2>{said}</h2>
        <p>
          {waited < 30
            ? "This takes a moment the first time."
            : "Still waiting. Somebody else may have the machine."}
        </p>
        <button className="quiet" onClick={onGiveUp}>Cancel</button>
      </div>
    </div>
  );
}
