// iocean, once you are in.
//
// A rail down the side and a page beside it. What is on the rail is what this
// platform is made of — places, vehicles, autonomy, dives — so the shape of the
// application says what the thing is before anybody reads a word of it.
//
// Some of it is not built. Those are marked and say what they will be, because
// an empty panel that explains itself is honest and one that shows invented
// content so the screen looks finished is not. The second is more tempting.

import { useCallback, useEffect, useRef, useState } from "react";

import type { Platform } from "@coral-city/api";

import boot from "../../../assets/boot.jpg";
import mark from "../../../assets/iocean.svg";
import { readHeld, usePackages, type Held, type Packages } from "../platform/held.js";
import { Autonomy } from "./Autonomy.js";
import { Dive } from "./Dive.js";
import { Fleet } from "./Fleet.js";
import { LayingOut } from "./Layout.js";
import { Designer } from "./Designer.js";
import { Fly } from "./Fly.js";
import { Missions } from "./Missions.js";
import { Swept } from "./Sweeps.js";
import { PlaceDetail } from "./PlaceDetail.js";
import { Places } from "./Places.js";
import { Profile } from "./Profile.js";
import { Runs } from "./Runs.js";
import { Replay } from "./Replay.js";
import { VehicleDetail } from "./VehicleDetail.js";

export type { Held, Packages };

/** Where in the application somebody is. Detail pages carry what they are of. */
export type Where =
  // Flying: a plan of work once or under doubts; a single task is "dive".
  | { page: "fly"; mission?: string }
  | { page: "dive" }
  | { page: "places" }
  | { page: "place"; id: string }
  // An arrangement of a place, opened from it. Not a tab of its own: a layout
  // detached from the ground it was drawn on means nothing.
  | { page: "layout"; place: string; layout: string }
  // A plan of work. Unlike a layout this is a top-level noun: an arrangement
  // is *of* somewhere and means nothing away from it, while a plan of work is
  // the unit of work itself — the thing somebody comes in to write and comes
  // back to fly.
  | { page: "missions" }
  | { page: "mission"; id: string; place: string }
  // The rehearsal: a plan against everything nobody can promise about it.
  | { page: "sweep"; id: string }
  | { page: "fleet" }
  | { page: "vehicle"; id?: string; slug?: string }
  | { page: "autonomy" }
  | { page: "runs" }
  | { page: "replay"; dive: string; run: string }
  | { page: "profile" };

type Rail = Where["page"];

const PAGES: { key: Rail; name: string; count?: (held: Held) => number; is: (where: Where) => boolean }[] = [
  { key: "fly", name: "Fly", is: (w) => w.page === "fly" || w.page === "dive" },
  { key: "missions", name: "Missions",
    is: (w) => w.page === "missions" || w.page === "mission" },
  { key: "places", name: "Places", count: (h) => h.places.length,
    is: (w) => w.page === "places" || w.page === "place" || w.page === "layout" },
  { key: "runs", name: "Results", count: (h) => h.runs.length,
    is: (w) => w.page === "runs" || w.page === "sweep" || w.page === "replay" },
  { key: "fleet", name: "Fleet", count: (h) => h.vehicles.length, is: (w) => w.page === "fleet" || w.page === "vehicle" },
  { key: "autonomy", name: "Autonomy", is: (w) => w.page === "autonomy" },
];

// wants a curated list of currents somebody made once. **Recordings** was a
// list of what dives produced, and a recording belongs to the dive that made
// it, which is where anybody looks. **Sweeps** came off by being built.
const LATER: { key: string; name: string; will: string }[] = [];

export function Deck({ platform, onDiving }: {
  platform: Platform;
  onDiving: (dive: string, run: string) => void;
}): React.JSX.Element {
  const [where, setWhere] = useState<Where>({ page: "fly" });
  const [held, setHeld] = useState<Held | undefined>();
  const [trouble, setTrouble] = useState("");
  const packages = usePackages(platform, held);

  const held_ = useRef<Held | undefined>(undefined);
  held_.current = held;

  /** Everything, dives included. Asked for when something has changed. */
  const read = useCallback(async () => {
    try {
      setHeld(await readHeld(platform));
    } catch (problem) {
      setTrouble(problem instanceof Error ? problem.message : "could not read the platform");
    }
  }, [platform]);

  useEffect(() => { void read(); }, [read]);

  // Kept fresh while somebody is looking at it. A queue that says one GPU is
  // free is only useful if it was true recently — but the dives are not that,
  // and re-reading hundreds of them every ten seconds is a thing to do to a
  // platform rather than ask of it.
  useEffect(() => {
    const again = setInterval(() => {
      void (async () => {
        try {
          setHeld(await readHeld(platform, held_.current));
        } catch {
          // A tick that fails keeps what it had; the next one will do.
        }
      })();
    }, 10_000);
    return () => clearInterval(again);
  }, [platform]);

  if (held === undefined) {
    return (
      <div className="middle boot">
        {/* Shown whole rather than cropped to fill: the picture has its own
            wordmark down the left, and anything that crops to the window eats
            it on the first narrow screen. The blur behind fills what is left
            over, so there are no bars and nothing is lost. */}
        <img className="boot-art" src={boot} alt="" />
        <div className="badge-big">
          <img src={mark} alt="" />
          <strong>iocean</strong>
        </div>
        <div className="tide" />
        <p className="note">{trouble || "Reading the platform…"}</p>
      </div>
    );
  }

  // The queue a dive will run on is the first; its machines are the ones
  // that matter here. Summing every queue counted test hardware alongside.
  const free = held.queues[0]?.free ?? 0;
  const devices = held.queues[0]?.devices ?? 0;
  const initials = (held.you.displayName || held.you.email || "?")
    .split(/[\s@.]+/).filter(Boolean).slice(0, 2).map((w) => w[0]!.toUpperCase()).join("");

  return (
    <div className="deck">
      <nav>
        <div className="here">
          <img src={mark} alt="" />
          <strong>iocean</strong>
        </div>

        {PAGES.map((one) => (
          <a key={one.key} aria-current={one.is(where) ? "page" : undefined}
             onClick={() => setWhere({ page: one.key } as Where)}>
            {one.name}
            {one.count === undefined ? null : <small>{one.count(held)}</small>}
          </a>
        ))}

        {LATER.length === 0 ? null : <h2>Not yet</h2>}
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
        {where.page === "fly" ? (
          <Fly platform={platform} held={held} packages={packages} mission={where.mission}
               onDiving={onDiving} onChanged={read}
               onSwept={(id) => setWhere({ page: "sweep", id })}
               onSingleTask={() => setWhere({ page: "dive" })}
               onDesign={(id, place) => setWhere({ page: "mission", id, place })} />
        ) : where.page === "dive" ? (
          <Dive platform={platform} held={held} packages={packages} free={free} devices={devices}
                onDiving={onDiving} onChanged={read} onOpen={setWhere} />
        ) : where.page === "places" ? (
          <Places held={held} packages={packages} onOpen={(id) => setWhere({ page: "place", id })} />
        ) : where.page === "place" ? (
          <PlaceDetail held={held} packages={packages} id={where.id}
                       platform={platform}
                       onLayOut={(layout) => setWhere({ page: "layout", place: where.id, layout })}
                       onBack={() => setWhere({ page: "places" })} />
        ) : where.page === "layout" ? (
          <LayingOut platform={platform} packages={packages}
                     place={where.place} layout={where.layout}
                     onBack={() => setWhere({ page: "place", id: where.place })} />
        ) : where.page === "missions" ? (
          <Missions platform={platform} held={held}
                    onOpen={(id, place) => setWhere({ page: "mission", id, place })}
                    onFly={(id) => setWhere({ page: "fly", mission: id })} />
        ) : where.page === "mission" ? (
          <Designer platform={platform} held={held} packages={packages} mission={where.id} place={where.place}
                    onBack={() => setWhere({ page: "missions" })}
                    onFly={(id) => setWhere({ page: "fly", mission: id })} />
        ) : where.page === "sweep" ? (
          <Swept platform={platform} sweep={where.id} onBack={() => setWhere({ page: "runs" })} />
        ) : where.page === "fleet" ? (
          <Fleet held={held} packages={packages}
                 onOpen={(of) => setWhere({ page: "vehicle", ...of })} />
        ) : where.page === "vehicle" ? (
          <VehicleDetail held={held} packages={packages} id={where.id} slug={where.slug}
                         onBack={() => setWhere({ page: "fleet" })} />
        ) : where.page === "autonomy" ? (
          <Autonomy held={held} />
        ) : where.page === "runs" ? (
          <Runs platform={platform} held={held} onChanged={read}
                onReplay={(dive, run) => setWhere({ page: "replay", dive, run })}
                onSweep={(id) => setWhere({ page: "sweep", id })} />
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
