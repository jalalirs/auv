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

import { Refused, type Platform } from "@coral-city/api";

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
import { Compose } from "./Compose.js";
import { Reconstructions } from "./Reconstructions.js";
import { ReconstructionPage } from "./Reconstruction.js";
import { VehicleDetail } from "./VehicleDetail.js";
import { ControllerDetail } from "./ControllerDetail.js";
import { AssetDetail } from "./AssetDetail.js";
import { useAddress, type Address } from "../ui/router.js";
import { Skeleton } from "../ui/components.js";

export type { Held, Packages };

/** Where in the application somebody is. Detail pages carry what they are of. */
export type Where =
  // Flying: a plan of work once or under doubts; a single task is "dive".
  | { page: "fly"; mission?: string }
  | { page: "dive" }
  | { page: "places"; tab?: string }
  | { page: "place"; id: string }
  // A new place, built from its data on the platform's machines.
  | { page: "build"; base?: string; with?: string }
  // Reefs rebuilt from dive videos, and one of them; under Places, because
  // what one is for is to be put on a map.
  | { page: "reconstructions" }
  | { page: "reconstruction"; id: string }
  | { page: "asset"; id: string }
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
  | { page: "controller"; slug: string }
  | { page: "runs"; by?: string; view?: string }
  | { page: "replay"; dive: string; run: string }
  | { page: "profile" };

type Rail = Where["page"];

const HOME: Where = { page: "fly" };
const PAGES_KNOWN = new Set<string>(["fly", "dive", "places", "place", "build", "reconstructions", "reconstruction", "asset",
  "layout", "missions", "mission", "sweep", "fleet", "vehicle", "autonomy", "controller", "runs", "replay", "profile"]);
const knownPage = (where: Address): boolean => PAGES_KNOWN.has(where.page);
/** What scrolls on a page: its body, or the main area on a page not yet rebuilt. */
const scroller = (): HTMLElement | null =>
  document.querySelector<HTMLElement>("main .page-body") ?? document.querySelector<HTMLElement>("main");

const PAGES: { key: Rail; name: string; count?: (held: Held) => number | undefined; is: (where: Where) => boolean }[] = [
  { key: "fly", name: "Fly", is: (w) => w.page === "fly" || w.page === "dive" },
  { key: "missions", name: "Missions",
    is: (w) => w.page === "missions" || w.page === "mission" },
  { key: "places", name: "Places", count: (h) => h.yourPlaces.length,
    is: (w) => w.page === "places" || w.page === "place" || w.page === "layout" || w.page === "build"
      || w.page === "reconstructions" || w.page === "reconstruction" || w.page === "asset" },
  { key: "runs", name: "Runs", count: (h) => (h.runsRead ? h.runs.length : undefined),
    is: (w) => w.page === "runs" || w.page === "sweep" || w.page === "replay" },
  { key: "fleet", name: "Fleet", count: (h) => h.vehicles.length, is: (w) => w.page === "fleet" || w.page === "vehicle" },
  { key: "autonomy", name: "Controllers", is: (w) => w.page === "autonomy" || w.page === "controller" },
];

// wants a curated list of currents somebody made once. **Recordings** was a
// list of what dives produced, and a recording belongs to the dive that made
// it, which is where anybody looks. **Sweeps** came off by being built.
const LATER: { key: string; name: string; will: string }[] = [];

export function Deck({ platform, onDiving, onSignOut }: {
  platform: Platform;
  /** Forgets the session and goes back to signing in. */
  onSignOut: () => void;
  onDiving: (dive: string, run: string) => void;
}): React.JSX.Element {
  // Every page has an address and a history entry: Back works everywhere.
  const { where, go: setWhere, back } = useAddress<Where>(HOME, knownPage, scroller);
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

  // Opens on the catalogue, which is a few requests; the runs, one request per
  // dive, follow behind placeholders.
  useEffect(() => {
    let stale = false;
    void (async () => {
      try {
        const quick = await readHeld(platform, undefined, { runs: false });
        if (!stale) setHeld((was) => was ?? quick);
      } catch (problem) {
        // A session that ran out while the application was open.
        if (problem instanceof Refused && problem.status === 401) { onSignOut(); return; }
        if (!stale) setTrouble(problem instanceof Error ? problem.message : "could not read the platform");
        return;
      }
      if (!stale) await read();
    })();
    return () => { stale = true; };
  }, [platform, read, onSignOut]);

  // Kept fresh while somebody is looking at it. A queue that says one GPU is
  // free is only useful if it was true recently — but the dives are not that,
  // and re-reading hundreds of them every ten seconds is a thing to do to a
  // platform rather than ask of it.
  useEffect(() => {
    const again = setInterval(() => {
      void (async () => {
        try {
          const next = await readHeld(platform, held_.current);
          // A tick that began before the runs arrived must not take them away.
          setHeld((was) => next.runsRead || !was?.runsRead ? next : { ...next, runs: was.runs, runsRead: true });
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
        {/* Fills the window, cropped from the right, because the picture has
            its own wordmark down the left. A window narrower than 3:2 shows it
            whole instead, with the blur behind filling what is left over. */}
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
            {one.count === undefined ? null : one.count(held) === undefined
              ? <Skeleton width={18} height={10} className="count" /> : <small>{one.count(held)}</small>}
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
               onSingleTask={() => setWhere({ page: "dive" }, { replace: true })}
               onDesign={(id, place) => setWhere({ page: "mission", id, place })} />
        ) : where.page === "dive" ? (
          <Dive platform={platform} held={held} packages={packages} free={free} devices={devices}
                onDiving={onDiving} onChanged={read} onOpen={setWhere}
                onPlan={() => setWhere({ page: "fly" }, { replace: true })} />
        ) : where.page === "places" ? (
          <Places platform={platform} held={held} packages={packages} tab={where.tab ?? "places"}
                  onTab={(tab) => setWhere({ page: "places", tab: tab === "places" ? undefined : tab }, { replace: true })}
                  onOpen={(id) => setWhere({ page: "place", id })}
                  onBuild={() => setWhere({ page: "build" })}
                  onBuildOn={(id) => setWhere({ page: "build", base: id })}
                  onChanged={read}
                  onFromVideo={() => setWhere({ page: "reconstructions" }, { replace: true })} />
        ) : where.page === "reconstructions" ? (
          <Reconstructions platform={platform} held={held} onBack={() => setWhere({ page: "places" }, { replace: true })}
                           onTab={(tab) => setWhere({ page: "places", tab: tab === "places" ? undefined : tab }, { replace: true })}
                           onOpen={(id) => setWhere({ page: "reconstruction", id })}
                           onOpenAsset={(id) => setWhere({ page: "asset", id })} />
        ) : where.page === "asset" ? (
          <AssetDetail platform={platform} id={where.id} onBack={() => back({ page: "reconstructions" })}
                       onCompose={(id) => setWhere({ page: "build", with: id })} />
        ) : where.page === "reconstruction" ? (
          <ReconstructionPage platform={platform} held={held} packages={packages} id={where.id}
                              onBack={() => back({ page: "reconstructions" })}
                              onOpenPlace={(id) => { void read(); setWhere({ page: "place", id }); }} />
        ) : where.page === "build" ? (
          <Compose platform={platform} held={held} base={where.base} chosen={where.with} onBack={() => back({ page: "places" })}
                   onOpen={(id) => { void read(); setWhere({ page: "place", id }); }} />
        ) : where.page === "place" ? (
          <PlaceDetail held={held} packages={packages} id={where.id}
                       platform={platform}
                       onLayOut={(layout) => setWhere({ page: "layout", place: where.id, layout })}
                       onBack={() => back({ page: "places" })} />
        ) : where.page === "layout" ? (
          <LayingOut platform={platform} packages={packages}
                     place={where.place} layout={where.layout}
                     onBack={() => back({ page: "place", id: where.place })} />
        ) : where.page === "missions" ? (
          <Missions platform={platform} held={held}
                    onOpen={(id, place) => setWhere({ page: "mission", id, place })}
                    onFly={(id) => setWhere({ page: "fly", mission: id })} />
        ) : where.page === "mission" ? (
          <Designer platform={platform} held={held} packages={packages} mission={where.id} place={where.place}
                    onBack={() => back({ page: "missions" })}
                    onFly={(id) => setWhere({ page: "fly", mission: id })} />
        ) : where.page === "sweep" ? (
          <Swept platform={platform} sweep={where.id} onBack={() => back({ page: "runs" })} />
        ) : where.page === "fleet" ? (
          <Fleet held={held} packages={packages}
                 onOpen={(of) => setWhere({ page: "vehicle", ...of })} />
        ) : where.page === "vehicle" ? (
          <VehicleDetail held={held} packages={packages} id={where.id} slug={where.slug}
                         onBack={() => back({ page: "fleet" })} />
        ) : where.page === "autonomy" ? (
          <Autonomy platform={platform} held={held} onChanged={read}
                    onFly={(stack) => { try { localStorage.setItem("coral-city.controller", stack); } catch { /* remembered or not */ } setWhere({ page: "dive" }); }}
                    onRuns={(by) => setWhere({ page: "runs", by })}
                    onOpen={(slug) => setWhere({ page: "controller", slug })}
                    onCompare={() => setWhere({ page: "runs", view: "compare" })} />
        ) : where.page === "controller" ? (
          <ControllerDetail platform={platform} held={held} slug={where.slug}
                            onBack={() => back({ page: "autonomy" })}
                            onFly={(stack) => { try { localStorage.setItem("coral-city.controller", stack); } catch { /* remembered or not */ } setWhere({ page: "dive" }); }}
                            onReplay={(dive, run) => setWhere({ page: "replay", dive, run })}
                            onPulled={read} />
        ) : where.page === "runs" ? (
          <Runs key={`${where.by ?? ""}|${where.view ?? ""}`} platform={platform} held={held} onChanged={read}
                by={where.by} view={where.view}
                onReplay={(dive, run) => setWhere({ page: "replay", dive, run })}
                onSweep={(id) => setWhere({ page: "sweep", id })} />
        ) : where.page === "replay" ? (
          <Replay platform={platform} dive={where.dive} run={where.run}
                  onBack={() => back({ page: "runs" })} />
        ) : (
          <Profile platform={platform} held={held} free={free} devices={devices} onSignOut={onSignOut}
                   onSwitch={() => { setHeld(undefined); void read(); }} />
        )}
      </main>
    </div>
  );
}
