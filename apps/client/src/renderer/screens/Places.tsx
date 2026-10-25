// Where you may dive, and where you will be able to.
//
// Only what you have been granted appears — not filtered here, but simply not
// listed by the platform. An asset nobody granted you is indistinguishable from
// one that does not exist, which is deliberate, and it means this page never
// has to explain an absence.
//
// Under them, the places the platform is for and has not built. Shown as what
// they are — intentions, with what building each takes — so the shape of the
// product is visible before the whole of it exists.

import { ENVIRONMENTS } from "../catalog/environments.js";
import type { Held, Packages } from "./Deck.js";
import { PlaceCard } from "./Dive.js";
import { PlacePlan } from "../parts/PlanArt.js";
import { Card, Empty } from "./parts.js";
import { useCallback, useEffect, useState } from "react";
import type { City, Platform, StorePlace } from "@coral-city/api";
import { Button, Dialog, Menu, Page, Status } from "../ui/components.js";
import { PLACES_TABS } from "./placesTabs.js";

export function Places({ platform, held, packages, tab = "places", onTab, onOpen, onBuild, onFromVideo, onBuildOn, onChanged }: {
  platform?: Platform;
  held: Held;
  packages: Packages;
  /** places or store; assets is its own page (Reconstructions). */
  tab?: string;
  onTab?: (tab: string) => void;
  onOpen: (id: string) => void;
  onBuild?: () => void;
  onFromVideo?: () => void;
  /** Compose a new place on a store place's ground. */
  onBuildOn?: (cityId: string) => void;
  /** Read the places again, after one is retired. */
  onChanged?: () => void | Promise<void>;
}): React.JSX.Element {
  const [store, setStore] = useState<StorePlace[] | undefined>();
  const [pictures, setPictures] = useState<Record<string, string>>({});
  const [trouble, setTrouble] = useState("");
  const [retiring, setRetiring] = useState<City | undefined>();
  const [busy, setBusy] = useState(false);
  const institution = held.institution;

  const readStore = useCallback(() => {
    if (!platform) return;
    platform.storePlaces().then(setStore).catch(() => setStore([]));
  }, [platform]);
  useEffect(readStore, [readStore]);
  // Each store place's picture, from its newest published version.
  useEffect(() => {
    if (!platform || tab !== "store") return;
    for (const one of store ?? []) {
      if (!one.versionId || !one.picture || pictures[one.id]) continue;
      void platform.files(one.versionId).then((files) => {
        const url = files.find((f) => f.path === "picture.jpg")?.url;
        if (url) setPictures((was) => ({ ...was, [one.id]: url }));
      }).catch(() => undefined);
    }
  }, [platform, store, tab, pictures]);

  // Yours: what the organisation owns or holds; a store place only once it
  // has been taken (Use it).
  const storeIds = new Set((store ?? []).map((s) => s.id));
  const adopted = new Set((store ?? []).filter((s) => s.adopted).map((s) => s.id));
  const yours = held.places.filter((p) => !storeIds.has(p.id) || adopted.has(p.id));
  const slugs = new Set(held.places.map((p) => p.slug));

  const adopt = async (one: StorePlace, take: boolean) => {
    if (!platform || !institution) return;
    setTrouble("");
    try {
      if (take) await platform.adoptStorePlace(institution.id, one.id);
      else await platform.unadoptStorePlace(institution.id, one.id);
      readStore();
    } catch (problem) {
      setTrouble(problem instanceof Error ? problem.message : "it could not be changed");
    }
  };

  // Retiring hides a place and refuses new dives in it; its versions, runs
  // and files stay, and the platform can bring it back.
  const retire = async (one: City) => {
    if (!platform) return;
    setBusy(true);
    setTrouble("");
    try {
      await platform.retirePlace(one.id);
      setRetiring(undefined);
      await onChanged?.();
    } catch (problem) {
      setTrouble(problem instanceof Error ? problem.message : "it could not be retired");
      setRetiring(undefined);
    } finally {
      setBusy(false);
    }
  };
  // Only the organisation that owns a place manages it; a place taken from
  // the store is let go of there instead.
  const mayRetire = (one: City) => platform !== undefined && institution !== undefined
    && one.ownedByOrg === institution.id;

  return (
    <Page title="Places" subtitle="Places composed from ground and assets; a dive pins the version it ran in."
          info="A place is composed from its ground (a place from the iOcean map store, every public source for a square, a flat seabed, or your own survey) and the assets put into it, such as reefs rebuilt from dive videos. A dive pins the version it ran in, so the reef you dived is the reef anybody can dive again."
          tabs={[{ ...PLACES_TABS[0]!, count: yours.length }, PLACES_TABS[1]!, { ...PLACES_TABS[2]!, count: store?.length }]}
          tab={tab} onTab={(key) => { if (key === "assets") onFromVideo?.(); else onTab?.(key); }}
          actions={onBuild ? <Button kind="primary" onClick={onBuild}>New place</Button> : undefined}>
      {trouble ? <p className="trouble">{trouble}</p> : null}
      {tab === "store" ? (
        <>
          {store === undefined ? <p className="note">Reading the store…</p> : store.length === 0 ? (
            <Empty title="The store is empty">iOcean publishes the places it builds from public data here, open to everybody.</Empty>
          ) : (
            <div className="cards">
              {store.map((one) => (
                <div key={one.id} className="store-card">
                  <Card name={one.name} detail={one.summary || "an iOcean place"}
                        picture={pictures[one.id]}
                        art={<PlacePlan standing={one.surveyed ? "surveyed" : "derived"} deepestM={one.deepestM} size={64} />}
                        specs={[
                          one.deepestM !== undefined ? `to ${one.deepestM.toFixed(0)} m` : "",
                          one.surveyedFraction !== undefined ? `${Math.round(one.surveyedFraction * 100)}% measured` : one.surveyed ? "surveyed" : "derived depths",
                          one.colonies ? `${one.colonies.toLocaleString()} colonies` : "",
                        ].filter(Boolean)}
                        corner={one.adopted ? <Status tone="good">yours</Status> : undefined}
                        onOpen={() => onOpen(one.id)} />
                  <div className="store-actions">
                    {one.adopted
                      ? <Button kind="ghost" onClick={() => void adopt(one, false)}>Remove from yours</Button>
                      : <Button onClick={() => void adopt(one, true)} disabled={!institution}>Use it</Button>}
                    <Button kind="secondary" onClick={() => onBuildOn?.(one.id)}>Build on it</Button>
                  </div>
                </div>
              ))}
            </div>
          )}
          <section className="store-coming">
            <h2>Coming to the store</h2>
            <div className="cards">
              {ENVIRONMENTS.map((one) => (
                <Card key={one.key} name={one.name} detail={`${one.where} · ${one.purpose}`}
                      art={<PlacePlan standing={one.standing} deepestM={depthOf(one)} size={64} />}
                      specs={[one.standing, ...one.sources.slice(0, 1)]}
                      later={one.becomes !== undefined && slugs.has(one.becomes) ? "grows from a place you have" : "not built yet"} />
              ))}
            </div>
          </section>
        </>
      ) : yours.length === 0 ? (
        <Empty title="No places yet">Compose one with New place, or take one from the Map store.</Empty>
      ) : (
        <div className="cards">
          {yours.map((one) => (
            <div key={one.id} className="store-card">
              <PlaceCard place={one} packages={packages} onOpen={() => onOpen(one.id)} />
              {mayRetire(one) ? (
                <div className="store-actions">
                  <Menu label={`More for ${one.name}`}
                        items={[{ label: "Retire", danger: true, onSelect: () => setRetiring(one) }]} />
                </div>
              ) : null}
            </div>
          ))}
        </div>
      )}
      {retiring ? (
        <Dialog title={`Retire ${retiring.name}?`} onClose={() => { if (!busy) setRetiring(undefined); }}
                actions={<>
                  <Button kind="ghost" disabled={busy} onClick={() => setRetiring(undefined)}>Cancel</Button>
                  <Button kind="danger" disabled={busy} onClick={() => void retire(retiring)}>{busy ? "Retiring…" : "Retire"}</Button>
                </>}>
          <p>It leaves your places and no new dives can be made in it.</p>
          <p className="note">Its history is kept: every version, run and file stays, and dives already flown in it still replay.</p>
        </Dialog>
      ) : null}
    </Page>
  );
}


/** How deep a planned place goes, read out of what it says about itself. */
function depthOf(one: { purpose?: string; takes?: string; summary?: string }): number | undefined {
  const said = `${one.purpose ?? ""} ${one.takes ?? ""} ${one.summary ?? ""}`;
  const found = said.match(/(\d{1,3})\s*(?:m\b|metres)/);
  return found ? Number(found[1]) : undefined;
}
