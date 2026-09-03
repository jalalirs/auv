// Between asking and being in the water.
//
// There is no GPU to pick. You asked for a dive; the platform placed it on a
// host and its cards, or queued it behind others and says where in line it is
// and what it waits for, or refused it with the reason. A queue with nothing
// free is not an error and is not a failure — it is a thing that happens on
// shared hardware, and the honest response is to say it plainly.
//
// While it is placed, the steps are shown as they happen: allocated, the
// place staged, the simulator opening, the controller connected, running.

import { useCallback, useEffect, useRef, useState } from "react";

import type { Hold, Placement, Platform, Run, RunEvent } from "@coral-city/api";

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
  const [placement, setPlacement] = useState<Placement | undefined>();
  const [steps, setSteps] = useState<Step[]>([]);
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

    setPlacement(state?.placement);
    setSteps(progress(state, events));
    // Queued means the platform has the request and no cards yet. Preparing
    // means it has them and is fetching the place, which on a first dive is
    // hundreds of megabytes and takes as long as it takes.
    setSaid(state?.state === "preparing" || state?.state === "running"
      ? "Opening the water…"
      : "Waiting in line…");
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
        {placement === undefined ? null : <Where placement={placement} />}
        {steps.length === 0 ? null : (
          <ol className="steps">
            {steps.map((step) => (
              <li key={step.name} className={step.state}>
                <span className="mark">{step.state === "done" ? "✓" : step.state === "now" ? "…" : ""}</span>
                {step.name}
              </li>
            ))}
          </ol>
        )}
        <p className="quiet">
          {waited < 30
            ? "This takes a moment the first time."
            : "Still waiting. Somebody else may have the machine."}
        </p>
        <button className="quiet" onClick={onGiveUp}>Cancel</button>
      </div>
    </div>
  );
}

/** Where the platform put the dive, or where it stands in line. */
function Where({ placement }: { placement: Placement }): React.JSX.Element {
  if (placement.state === "queued") {
    const ahead = placement.ahead ?? 0;
    return (
      <p className="placement">
        {ahead === 0 ? "Next in line" : `${ordinal(placement.position ?? ahead + 1)} in line, ${ahead} ahead`}
        {placement.waitingFor ? `, waiting for ${placement.waitingFor}.` : "."}
      </p>
    );
  }
  const cards = placement.holds.map(describeHold).join(", ");
  return (
    <p className="placement">
      Placed on <b>{placement.target ?? "a host"}</b>{cards ? `: ${cards}` : ""}.
    </p>
  );
}

function describeHold(hold: Hold): string {
  const gib = hold.gpuMemoryBytes / 2 ** 30;
  const amount = Number.isInteger(gib) ? `${gib} GiB` : `${gib.toFixed(1)} GiB`;
  return `card ${hold.deviceIndex} (${amount}) for the ${hold.part}`;
}

function ordinal(n: number): string {
  const rest = n % 100;
  if (rest >= 11 && rest <= 13) return `${n}th`;
  switch (n % 10) {
    case 1: return `${n}st`;
    case 2: return `${n}nd`;
    case 3: return `${n}rd`;
    default: return `${n}th`;
  }
}

interface Step { name: string; state: "done" | "now" | "later" }

/**
 * The placement progressing, from what the platform recorded. Each step is
 * done once its event has been seen; the first not done is what is happening
 * now. Steps that this dive has no part for — a controller, when nobody
 * brought one — are left out rather than shown as never happening.
 */
function progress(run: Run | undefined, events: RunEvent[]): Step[] {
  if (run === undefined || run.state === "queued") return [];
  const seen = new Set(events.map((e) => e.kind));
  const hasController = run.autonomyDigest !== null && run.autonomyDigest !== undefined;
  const wanted: Array<[string, string[]]> = [
    ["Cards allocated", ["claimed"]],
    ["Place and vehicle staged", ["packages_present"]],
    ["Simulator opening", ["place_open", "vehicle_placed", "spawned"]],
    ...(hasController ? [["Controller started", ["autonomy_started"]] as [string, string[]]] : []),
    ["Stream open", ["stream_open"]],
  ];
  let nowFound = false;
  return wanted.map(([name, kinds]) => {
    const done = kinds.some((k) => seen.has(k));
    if (done) return { name, state: "done" as const };
    if (!nowFound) { nowFound = true; return { name, state: "now" as const }; }
    return { name, state: "later" as const };
  });
}
