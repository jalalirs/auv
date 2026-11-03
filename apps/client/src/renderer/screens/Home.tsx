// Where you land: what is happening, your worlds, and what has happened.
//
// Not a table. A row of tiles says what is diving now, how many machines are
// free, how this week's dives went and what the platform is building; under
// them your worlds as pictures, and beside them a feed of what happened,
// newest first. Every number is one already held (Held) or one asked of the
// platform here — the things being built, which nothing else on the deck
// reads — so the page never says more than it knows.

import { useEffect, useMemo, useState } from "react";

import type { Asset, BuildRecord, ControllerBuild, Platform } from "@coral-city/api";

import type { Held, Packages } from "./Deck.js";
import { WorldCard } from "../parts/Card.js";
import { nameAndSource } from "./AssetDetail.js";
import { scoreOf } from "./Runs.js";
import { ago, Empty } from "./parts.js";
import { Button, Page, Skeleton, SkeletonCards, type Tone } from "../ui/components.js";

const LIVE = new Set(["preparing", "running"]);
const ENDED = new Set(["succeeded", "failed", "cancelled", "expired"]);
const WEEK = 7 * 86_400_000;
/** How many worlds the page shows before "All worlds"; the feed's length. */
const WORLDS = 6;
const FEED = 30;

/** What the platform is building for you, asked for here. */
interface Building {
  assets: Asset[];
  grounds: { place: string; build: BuildRecord }[];
  controllers: ControllerBuild[];
}

/** One thing that happened, as the feed says it. */
interface Happened {
  key: string;
  at: string;
  tone: Tone;
  word: string;
  what: string;
  open?: () => void;
}

export function Home({ platform, held, packages, free, devices, onOpenWorld, onOpenDive, onNewDive, onWorlds }: {
  platform: Platform;
  held: Held;
  packages: Packages;
  /** Machines of the dive queue no dive is holding, and how many it has. */
  free: number;
  devices: number;
  onOpenWorld: (placeId: string) => void;
  onOpenDive: (diveId: string, runId: string) => void;
  onNewDive: () => void;
  /** Every world, when there are more than the page shows. */
  onWorlds: () => void;
}): React.JSX.Element {
  const building = useBuilding(platform, held);
  const now = Date.now();

  const diving = held.runs.filter((r) => LIVE.has(r.run.state));
  const queued = held.runs.filter((r) => r.run.state === "queued").length;
  const week = held.runs.filter((r) => ENDED.has(r.run.state)
    && now - Date.parse(r.run.endedAt ?? r.run.requestedAt) < WEEK);
  const succeeded = week.filter((r) => r.run.state === "succeeded").length;

  // Building: an object importing, a world's ground being made, a controller
  // being built and tried.
  const busy = building === undefined ? undefined : [
    ...building.assets.filter((a) => a.state !== "ready" && a.state !== "failed").map((a) => nameAndSource(a.name).name),
    ...building.grounds.filter((g) => !g.build.versionId && !g.build.failure)
      .map((g) => held.yourPlaces.find((p) => p.id === g.place)?.name ?? "a world"),
    ...building.controllers.filter((c) => c.state !== "ready" && c.state !== "failed").map((c) => c.slug),
  ];

  const feed = useMemo(() => happenings(held, packages, building, onOpenWorld, onOpenDive),
    [held, packages, building, onOpenWorld, onOpenDive]);

  const worlds = [...held.yourPlaces]
    .sort((a, b) => String(packages.places.get(b.id)?.version.createdAt ?? b.createdAt ?? "")
      .localeCompare(String(packages.places.get(a.id)?.version.createdAt ?? a.createdAt ?? "")));

  return (
    <Page title="Home" wide>
      <div className="home">
        <div className="home-tiles">
          <button type="button" className="home-start" onClick={onNewDive}>
            <span className="new-mark" aria-hidden="true">
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"><path d="M12 5v14M5 12h14" /></svg>
            </span>
            <span><strong>New dive</strong><small>world, mission, vehicle</small></span>
          </button>
          <Tile label="Diving now" value={held.runsRead ? diving.length : undefined}
                said={!held.runsRead ? "" : diving.length ? diving.map((r) => r.name).slice(0, 2).join(", ")
                  : queued ? `${queued} waiting` : "nothing in the water"}
                tone={diving.length ? "busy" : undefined}
                onClick={diving.length === 1 ? () => onOpenDive(diving[0]!.dive, diving[0]!.run.id) : undefined} />
          <Tile label="Machines free" value={free} of={devices}
                said={devices === 0 ? "no machines" : free === 0 ? "all busy" : free === devices ? "all free" : `${devices - free} in use`}
                meter={devices ? free / devices : undefined} />
          <Tile label="This week" value={held.runsRead ? week.length : undefined}
                said={!held.runsRead ? "" : week.length ? `${succeeded} succeeded` : "no dives finished"}
                meter={week.length ? succeeded / week.length : undefined} tone={week.length && succeeded === week.length ? "good" : undefined} />
          <Tile label="Building" value={busy?.length}
                said={busy === undefined ? "" : busy.length ? busy.slice(0, 2).join(", ") : "nothing building"}
                tone={busy?.length ? "busy" : undefined} />
        </div>

        <div className="home-body">
          <section className="home-worlds">
            <div className="home-head">
              <h2>Your worlds</h2>
              {worlds.length > WORLDS ? <Button kind="ghost" onClick={onWorlds}>All {worlds.length}</Button> : null}
            </div>
            {worlds.length === 0 ? (
              <Empty title="No worlds yet">Make one under <a onClick={onWorlds}>Places</a>, or take one from the Store.</Empty>
            ) : (
              <div className="cards">
                {worlds.slice(0, WORLDS).map((one) => (
                  <WorldCard key={one.id} place={one} packages={packages} held={held} onOpen={() => onOpenWorld(one.id)} />
                ))}
              </div>
            )}
          </section>

          <section className="home-feed">
            <div className="home-head"><h2>What happened</h2></div>
            {!held.runsRead && feed.length === 0 ? <SkeletonCards count={1} className="home-feed-list" /> : feed.length === 0 ? (
              <p className="note">Nothing yet. Dives, saved worlds and new objects appear here.</p>
            ) : (
              <ol className="home-feed-list">
                {feed.map((one) => (
                  <li key={one.key}>
                    <button type="button" className={`home-event${one.open ? " opens" : ""}`} disabled={!one.open}
                            onClick={one.open}>
                      <span className={`home-dot tone-${one.tone}`} aria-hidden="true" />
                      <span className="home-what"><b>{one.word}</b> {one.what}</span>
                      <time dateTime={one.at}>{ago(one.at)}</time>
                    </button>
                  </li>
                ))}
              </ol>
            )}
          </section>
        </div>
      </div>
    </Page>
  );
}

/** A number and what it means, with a bar when it is a share. */
function Tile({ label, value, of, said, meter, tone, onClick }: {
  label: string;
  /** Undefined while it is still being read. */
  value: number | undefined;
  /** Out of how many, said small after it. */
  of?: number;
  said: string;
  /** A share, 0 to 1, drawn as a thin bar. */
  meter?: number;
  tone?: Tone;
  onClick?: () => void;
}): React.JSX.Element {
  return (
    <div className={`home-tile${tone ? ` tone-${tone}` : ""}${onClick ? " opens" : ""}`}
         role={onClick ? "button" : undefined} tabIndex={onClick ? 0 : undefined} onClick={onClick}
         onKeyDown={(e) => { if (onClick && (e.key === "Enter" || e.key === " ")) onClick(); }}>
      <span className="home-label">{label}</span>
      {value === undefined ? <Skeleton width={48} height={28} />
        : <strong>{value.toLocaleString()}{of !== undefined ? <small> of {of}</small> : null}</strong>}
      <span className="home-said" title={said}>{said || " "}</span>
      {meter === undefined ? null : (
        <span className="home-meter" aria-hidden="true"><span style={{ width: `${Math.round(meter * 100)}%` }} /></span>
      )}
    </div>
  );
}

/** What is being built for the organisation, read now and every half minute. */
function useBuilding(platform: Platform, held: Held): Building | undefined {
  const [building, setBuilding] = useState<Building | undefined>();
  const org = held.institution?.id;
  // The worlds as a key: the list is re-read every ten seconds as a new array.
  const places = held.yourPlaces.map((p) => p.id).join(" ");
  useEffect(() => {
    if (!org) { setBuilding({ assets: [], grounds: [], controllers: [] }); return; }
    let stale = false;
    const read = async () => {
      const [assets, controllers, grounds] = await Promise.all([
        platform.listAssets(org).catch((): Asset[] => []),
        platform.controllerBuildsOf(org).catch((): ControllerBuild[] => []),
        Promise.all(places.split(" ").filter(Boolean).map(async (place) =>
          (await platform.buildsOf(place).catch((): BuildRecord[] => [])).map((build) => ({ place, build })))),
      ]);
      if (!stale) setBuilding({ assets, controllers, grounds: grounds.flat() });
    };
    void read();
    const again = setInterval(() => void read(), 30_000);
    return () => { stale = true; clearInterval(again); };
  }, [platform, org, places]);
  return building;
}

/** Everything that happened that is held, newest first. */
function happenings(held: Held, packages: Packages, building: Building | undefined,
                    onOpenWorld: (id: string) => void, onOpenDive: (dive: string, run: string) => void): Happened[] {
  const out: Happened[] = [];
  for (const r of held.runs) {
    const open = () => onOpenDive(r.dive, r.run.id);
    const { state, startedAt, endedAt, requestedAt } = r.run;
    if (ENDED.has(state)) {
      const score = scoreOf(r);
      out.push({
        key: `${r.run.id}:end`, at: endedAt ?? startedAt ?? requestedAt, open,
        tone: state === "succeeded" ? "good" : state === "failed" ? "bad" : "quiet",
        word: state === "succeeded" ? "Finished" : state === "failed" ? "Failed" : state === "cancelled" ? "Ended" : "Expired",
        what: `${r.name}${state === "succeeded" && score >= 0 ? ` · ${(score * 100).toFixed(0)}%` : ""}`
          + (state === "failed" && r.run.failureReason ? ` · ${r.run.failureReason}` : ""),
      });
    }
    if (startedAt) out.push({ key: `${r.run.id}:start`, at: startedAt, open, tone: "busy", word: "Started", what: r.name });
    else if (state === "queued") out.push({ key: `${r.run.id}:queued`, at: requestedAt, open, tone: "quiet", word: "Waiting", what: r.name });
  }
  // A world's newest version is when it was last saved.
  for (const place of held.yourPlaces) {
    const version = packages.places.get(place.id)?.version;
    if (version) {
      out.push({ key: `${place.id}:v${version.ordinal}`, at: version.createdAt, tone: "quiet", word: "Saved",
                 what: `${place.name}, version ${version.ordinal}`, open: () => onOpenWorld(place.id) });
    }
  }
  for (const a of building?.assets ?? []) {
    const at = a.steps[a.steps.length - 1]?.at ?? a.createdAt;
    const name = nameAndSource(a.name).name;
    if (a.state === "ready") out.push({ key: `${a.id}:ready`, at, tone: "good", word: "Ready", what: name });
    else if (a.state === "failed") out.push({ key: `${a.id}:failed`, at, tone: "bad", word: "Failed", what: name });
  }
  for (const { place, build } of building?.grounds ?? []) {
    const name = held.yourPlaces.find((p) => p.id === place)?.name ?? "a world";
    if (build.versionId) {
      out.push({ key: `${build.id}:built`, at: build.recordedAt ?? build.createdAt, tone: "good", word: "Built",
                 what: `the ground of ${name}`, open: () => onOpenWorld(place) });
    } else if (build.failure) {
      out.push({ key: `${build.id}:failed`, at: build.recordedAt ?? build.createdAt, tone: "bad", word: "Failed",
                 what: `the ground of ${name}`, open: () => onOpenWorld(place) });
    }
  }
  for (const c of building?.controllers ?? []) {
    const at = c.recordedAt ?? c.createdAt;
    if (c.state === "ready") out.push({ key: `${c.id}:ready`, at, tone: "good", word: "Deployed", what: c.slug });
    else if (c.state === "failed") out.push({ key: `${c.id}:failed`, at, tone: "bad", word: "Failed", what: `building ${c.slug}` });
  }
  // Something with no time to it (an old record) is left out rather than sorted.
  return out.filter((h) => typeof h.at === "string").sort((a, b) => b.at.localeCompare(a.at)).slice(0, FEED);
}
