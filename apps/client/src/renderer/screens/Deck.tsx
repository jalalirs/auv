// Coral City, once you are in.
//
// A rail down the side and a page beside it. What is on the rail is what this
// platform is made of — places, vehicles, autonomy, dives — so the shape of the
// application says what the thing is before anybody reads a word of it.
//
// Some of it is not built. Those are marked and say what they will be, because
// an empty panel that explains itself is honest and one that shows invented
// content so the screen looks finished is not. The second is more tempting.

import { useCallback, useEffect, useState } from "react";

import type { City, Organisation, Platform, Principal, Queue, Run, Vehicle }
  from "@coral-city/api";

import mark from "../../../assets/coral-city.svg";
import { Autonomy } from "./Autonomy.js";
import { Dive } from "./Dive.js";
import { Fleet } from "./Fleet.js";
import { Places } from "./Places.js";
import { Profile } from "./Profile.js";
import { Runs } from "./Runs.js";

export interface Held {
  you: Principal;
  institution: Organisation | undefined;
  places: City[];
  vehicles: Vehicle[];
  queues: Queue[];
  runs: { dive: string; run: Run }[];
}

type Page = "dive" | "places" | "fleet" | "autonomy" | "runs" | "profile";

const PAGES: { key: Page; name: string; count?: (held: Held) => number }[] = [
  { key: "dive", name: "Dive" },
  { key: "places", name: "Places", count: (h) => h.places.length },
  { key: "fleet", name: "Fleet", count: (h) => h.vehicles.length },
  { key: "autonomy", name: "Autonomy" },
  { key: "runs", name: "Dives", count: (h) => h.runs.length },
];

// Named here rather than left out, so the shape of the platform is visible
// before the whole of it is built. Each says what it will be on its own page.
const LATER: { key: string; name: string }[] = [
  { key: "conditions", name: "Conditions" },
  { key: "sweeps", name: "Sweeps" },
  { key: "recordings", name: "Recordings" },
];

export function Deck({ platform, onDiving }: {
  platform: Platform;
  onDiving: (dive: string, run: string) => void;
}): React.JSX.Element {
  const [page, setPage] = useState<Page>("dive");
  const [held, setHeld] = useState<Held | undefined>();
  const [trouble, setTrouble] = useState("");

  const read = useCallback(async () => {
    try {
      const [me, places, vehicles, queues] = await Promise.all([
        platform.me(), platform.places(), platform.vehicles(), platform.queues(),
      ]);
      const institution = me.organisations[0];

      // Every dive this institution has defined, and what became of each. The
      // platform keeps runs under the dive that defined them, so gathering them
      // is the client's job and not a missing endpoint.
      let runs: { dive: string; run: Run }[] = [];
      if (institution !== undefined) {
        const dives = await platform.dives(institution.id);
        const each = await Promise.all(
          dives.slice(0, 12).map(async (dive) => (await platform.runs(dive.id))
            .map((run) => ({ dive: dive.id, run }))));
        runs = each.flat().sort((a, b) =>
          a.run.requestedAt < b.run.requestedAt ? 1 : -1);
      }
      setHeld({ you: me.principal, institution, places, vehicles, queues, runs });
    } catch (problem) {
      setTrouble(problem instanceof Error ? problem.message : "could not read the platform");
    }
  }, [platform]);

  useEffect(() => { void read(); }, [read]);

  // Kept fresh while somebody is looking at it. A queue that says one GPU is
  // free is only useful if it was true recently.
  useEffect(() => {
    const again = setInterval(() => { void read(); }, 10_000);
    return () => clearInterval(again);
  }, [read]);

  if (held === undefined) {
    return (
      <div className="middle">
        <p className="note">{trouble || "Reading the platform…"}</p>
      </div>
    );
  }

  const free = held.queues.reduce((n, q) => n + q.free, 0);
  const devices = held.queues.reduce((n, q) => n + q.devices, 0);
  const initials = (held.you.displayName || held.you.email || "?")
    .split(/[\s@.]+/).filter(Boolean).slice(0, 2).map((w) => w[0]!.toUpperCase()).join("");

  return (
    <div className="deck">
      <nav>
        <div className="here">
          <img src={mark} alt="" />
          <strong>Coral City</strong>
        </div>

        {PAGES.map((one) => (
          <a key={one.key} aria-current={page === one.key ? "page" : undefined}
             onClick={() => setPage(one.key)}>
            {one.name}
            {one.count === undefined ? null : <small>{one.count(held)}</small>}
          </a>
        ))}

        <h2>Not yet</h2>
        {LATER.map((one) => (
          <a key={one.key} className="later" title="Not built yet">{one.name}</a>
        ))}

        <div className="who" onClick={() => setPage("profile")}
             style={{ cursor: "pointer" }}>
          <div className="initials">{initials}</div>
          <div>
            <strong>{held.you.displayName || "You"}</strong>
            <span>{held.institution?.name ?? "no institution"}</span>
          </div>
        </div>
      </nav>

      <main>
        {page === "dive" ? (
          <Dive platform={platform} held={held} free={free} devices={devices}
                onDiving={onDiving} onChanged={read} />
        ) : page === "places" ? (
          <Places held={held} />
        ) : page === "fleet" ? (
          <Fleet held={held} />
        ) : page === "autonomy" ? (
          <Autonomy />
        ) : page === "runs" ? (
          <Runs platform={platform} held={held} onChanged={read} />
        ) : (
          <Profile platform={platform} held={held} free={free} devices={devices} />
        )}
      </main>
    </div>
  );
}
