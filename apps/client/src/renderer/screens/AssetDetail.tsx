// One asset that is not a reef from a video: a structure (from a 3D model or
// a route) or a seabed survey. What it is, how it was made, what the import
// measured, and the way into a place. A reef has its own page, with its
// pieces and its search for where it fits.

import { useEffect, useState } from "react";
import type { Asset, City, Platform } from "@coral-city/api";
import { Button, Dialog, Menu, Page, Status, SkeletonLines } from "../ui/components.js";
import { ago } from "./parts.js";

/** What an object is, in a word or two. How it was made is on its page. */
export function kindSaid(one: Pick<Asset, "kind" | "type">): string {
  if (one.kind === "reef") return "reef from a video";
  if (one.kind === "bathymetry") return "seabed survey";
  if (one.kind === "cover") return "cover map";
  if (one.kind === "species") return "species list";
  return one.type === "other" || !one.type ? "structure" : one.type.replace("-", " ");
}

const MADE_FROM: Record<string, string> = {
  video: "a dive video", survey: "a survey file", model: "a 3D model", route: "a line drawn on the map",
};

/** A name as people gave it, "SubPipe outfall (Oceanscan-MST, CC BY 4.0)",
 *  as the short name a card shows and the source its page shows. */
export function nameAndSource(full: string): { name: string; source?: string } {
  const found = full.match(/^(.*\S)\s*\(([^()]*)\)\s*$/);
  return found ? { name: found[1]!, source: found[2]! } : { name: full };
}

/** A fact's key as words: shallowestM is "shallowest, m". */
export function factSaid(key: string): string {
  const unit = /M$/.test(key) ? ", m" : "";
  return key.replace(/M$/, "").replace(/([a-z])([A-Z])/g, "$1 $2").toLowerCase().replace(/^bbox$/, "bounds (S, W, N, E)") + unit;
}

function valueSaid(v: unknown): string {
  if (Array.isArray(v)) return v.map((x) => typeof x === "number" ? String(+x.toFixed(5)) : String(x)).join(", ");
  if (typeof v === "number") return String(+v.toFixed(3));
  if (v && typeof v === "object") return JSON.stringify(v);
  return String(v);
}

export function AssetDetail({ platform, id, places, onBack, onCompose, onPlace }: {
  platform: Platform;
  id: string;
  /** Where it could go. Only your own are offered: a store place you have
   *  not taken is in this list but is not yours to put things in. */
  places: City[];
  onBack: () => void;
  /** The New place screen, with this survey as its ground. */
  onCompose: (id: string) => void;
  /** The designer of a place, with this object in hand. */
  onPlace: (id: string, place: string) => void;
}): React.JSX.Element {
  const [one, setOne] = useState<Asset | undefined>();
  const [placing, setPlacing] = useState(false);
  const [trouble, setTrouble] = useState("");
  // Your places, as the side bar counts them (held.yourPlaces).
  const yours: City[] | undefined = places;
  useEffect(() => {
    let live = true;
    const read = () => platform.getAsset(id).then((a) => { if (live) setOne(a); })
      .catch((e: unknown) => { if (live) setTrouble(e instanceof Error ? e.message : "could not read the asset"); });
    void read();
    const again = setInterval(() => { if (one?.state !== "ready" && one?.state !== "failed") void read(); }, 15_000);
    return () => { live = false; clearInterval(again); };
  }, [platform, id]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!one) {
    return <Page title="An object" crumb="Objects" onCrumb={onBack}>{trouble ? <p className="note">{trouble}</p> : <SkeletonLines lines={6} />}</Page>;
  }
  const last = one.steps[one.steps.length - 1];
  const facts = { ...(one.stats ?? {}), ...(one.footprint ?? {}) };
  const { name, source } = nameAndSource(one.name);
  return (
    <Page title={name} crumb="Objects" onCrumb={onBack}
          subtitle={`${kindSaid(one)} · made ${ago(one.createdAt)}`}
          actions={<>
            {one.state === "ready"
              ? one.kind === "bathymetry"
                ? <Button kind="primary" onClick={() => onCompose(one.id)}>Build a place on it</Button>
                : <Button kind="primary" onClick={() => setPlacing(true)}>Place it</Button>
              : null}
            <Menu label={`More for ${name}`} items={[{ label: "Archive", danger: true, onSelect: () => {
              void platform.archiveAsset(one.id).then(onBack, (e: unknown) => setTrouble(e instanceof Error ? e.message : "it could not be archived"));
            } }]} />
          </>}>
        {trouble ? <p className="trouble">{trouble}</p> : null}
      <div className="asset-page">
        <div className="asset-state">
          <Status tone={one.state === "ready" ? "good" : one.state === "failed" ? "bad" : "busy"}>{one.state}</Status>
          {one.state !== "ready" && last ? <span className="note">{last.say}</span> : null}
        </div>
        {one.failure ? <p className="trouble">{one.failure}</p> : null}
        {one.preview && one.state === "ready" ? <img className="asset-preview" src={one.preview} alt={`${one.name}, as the import drew it`} /> : null}
        <dl className="asset-facts">
          <div><dt>made from</dt><dd>{MADE_FROM[one.madeFrom] ?? one.madeFrom}</dd></div>
          {source ? <div><dt>source and licence</dt><dd>{source}</dd></div> : null}
        </dl>
        {Object.keys(facts).length ? (
          <section>
            <h2>What the import measured</h2>
            <dl className="asset-facts">
              {Object.entries(facts).map(([k, v]) => <div key={k}><dt>{factSaid(k)}</dt><dd>{valueSaid(v)}</dd></div>)}
            </dl>
          </section>
        ) : null}
        <section>
          <h2>How it goes into a place</h2>
          <p className="note">{one.kind === "bathymetry"
            ? "A survey is a place's ground: build a place on it, and its depths win where they reach, over the public data."
            : one.meets === "drapes"
            ? "It follows its own route on the seabed, wherever the place's seabed is under it. Nothing to choose."
            : "It stands on the seabed where you say: a latitude, a longitude and a heading, when you put it in a place."}</p>
        </section>
      </div>
      {placing ? (
        <Dialog title={`Place ${name} in`} onClose={() => setPlacing(false)}>
          <div className="place-choice">
            {yours === undefined ? <SkeletonLines lines={3} />
              : yours.length === 0 ? <p className="note">You have no places yet. Make one under Places first.</p> : null}
            {(yours ?? []).map((p) => (
              <button key={p.id} type="button" onClick={() => onPlace(one.id, p.id)}>{p.name}</button>
            ))}
          </div>
        </Dialog>
      ) : null}
    </Page>
  );
}
