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

import type { Platform } from "@coral-city/api";

import mark from "../../../assets/coral-city.svg";
import { readHeld, usePackages, type Held, type Packages } from "../platform/held.js";
import { Autonomy } from "./Autonomy.js";
import { Dive } from "./Dive.js";
import { Fleet } from "./Fleet.js";
import { PlaceDetail } from "./PlaceDetail.js";
import { Places } from "./Places.js";
import { Profile } from "./Profile.js";
import { Runs } from "./Runs.js";
import { Replay } from "./Replay.js";
import { VehicleDetail } from "./VehicleDetail.js";

export type { Held, Packages };

/** Where in the application somebody is. Detail pages carry what they are of. */
export type Where =
  | { page: "dive" }
  | { page: "places" }
  | { page: "place"; id: string }
  | { page: "fleet" }
  | { page: "vehicle"; id?: string; slug?: string }
  | { page: "autonomy" }
  | { page: "runs" }
  | { page: "replay"; dive: string; run: string }
  | { page: "profile" };

type Rail = Where["page"];

const PAGES: { key: Rail; name: string; count?: (held: Held) => number; is: (where: Where) => boolean }[] = [
  { key: "dive", name: "Dive", is: (w) => w.page === "dive" },
  { key: "places", name: "Places", count: (h) => h.places.length, is: (w) => w.page === "places" || w.page === "place" },
  { key: "fleet", name: "Fleet", count: (h) => h.vehicles.length, is: (w) => w.page === "fleet" || w.page === "vehicle" },
  { key: "autonomy", name: "Autonomy", is: (w) => w.page === "autonomy" },
  { key: "runs", name: "Dives", count: (h) => h.runs.length, is: (w) => w.page === "runs" },
];

// Named here rather than left out, so the shape of the platform is visible
// before the whole of it is built. Each says what it will be on its own page.
const LATER: { key: string; name: string; will: string }[] = [
  { key: "conditions", name: "Conditions", will: "Currents, turbidity and light, observed or constructed, named on every dive." },
  { key: "sweeps", name: "Sweeps", will: "The same dive across many conditions, with nobody watching, scored." },
  { key: "recordings", name: "Recordings", will: "What a survey recorded, listed, fetched and replayed." },
];

export function Deck({ platform, onDiving }: {
  platform: Platform;
  onDiving: (dive: string, run: string) => void;
}): React.JSX.Element {
  const [where, setWhere] = useState<Where>({ page: "dive" });
  const [held, setHeld] = useState<Held | undefined>();
  const [trouble, setTrouble] = useState("");
  const packages = usePackages(platform, held);

  const read = useCallback(async () => {
    try {
      setHeld(await readHeld(platform));
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
      <div className="middle boot">
        <div className="badge-big">
          <img src={mark} alt="" />
          <strong>Coral City</strong>
        </div>
        <div className="tide" />
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
          <a key={one.key} aria-current={one.is(where) ? "page" : undefined}
             onClick={() => setWhere({ page: one.key } as Where)}>
            {one.name}
            {one.count === undefined ? null : <small>{one.count(held)}</small>}
          </a>
        ))}

        <h2>Not yet</h2>
        {LATER.map((one) => (
          <a key={one.key} className="later" title={one.will}>{one.name}</a>
        ))}

        <div className="who" onClick={() => setWhere({ page: "profile" })}
             style={{ cursor: "pointer" }}>
          <div className="initials">{initials}</div>
          <div>
            <strong>{held.you.displayName || "You"}</strong>
            <span>{held.institution?.name ?? "no institution"}</span>
          </div>
        </div>
      </nav>

      <main>
        {where.page === "dive" ? (
          <Dive platform={platform} held={held} packages={packages} free={free} devices={devices}
                onDiving={onDiving} onChanged={read} onOpen={setWhere} />
        ) : where.page === "places" ? (
          <Places held={held} packages={packages} onOpen={(id) => setWhere({ page: "place", id })} />
        ) : where.page === "place" ? (
          <PlaceDetail held={held} packages={packages} id={where.id}
                       onBack={() => setWhere({ page: "places" })} />
        ) : where.page === "fleet" ? (
          <Fleet held={held} packages={packages}
                 onOpen={(of) => setWhere({ page: "vehicle", ...of })} />
        ) : where.page === "vehicle" ? (
          <VehicleDetail held={held} packages={packages} id={where.id} slug={where.slug}
                         onBack={() => setWhere({ page: "fleet" })} />
        ) : where.page === "autonomy" ? (
          <Autonomy />
        ) : where.page === "runs" ? (
          <Runs platform={platform} held={held} onChanged={read}
                onReplay={(dive, run) => setWhere({ page: "replay", dive, run })} />
        ) : where.page === "replay" ? (
          <Replay platform={platform} dive={where.dive} run={where.run}
                  onBack={() => setWhere({ page: "runs" })} />
        ) : (
          <Profile platform={platform} held={held} free={free} devices={devices} />
        )}
      </main>
    </div>
  );
}
