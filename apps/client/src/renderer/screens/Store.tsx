// What iOcean offers: its places, objects and vehicles, in one store.
//
// Taking a place or an object copies it into yours: a place of your own to
// change as you like, while the store's never changes, and taking it again
// makes another copy. The kinds share one grid with a filter, not a tab each:
// they are all the same act, taking something.

import { useCallback, useEffect, useState } from "react";

import type { Asset, Platform, StorePlace } from "@coral-city/api";

import { CATALOGUE } from "../catalog/vehicles.js";
import { ENVIRONMENTS } from "../catalog/environments.js";
import { ObjectArt } from "../parts/ObjectArt.js";
import { PlacePlan, VehiclePlan } from "../parts/PlanArt.js";
import { usePlacePicture } from "../parts/Relief.js";
import type { PlacePackage } from "../platform/packages.js";
import { kindSaid, nameAndSource } from "./AssetDetail.js";
import type { Held, Packages } from "./Deck.js";
import { artOf } from "./Reconstructions.js";
import { Card, Empty } from "./parts.js";
import { Button, Dialog, Page, Segmented, SkeletonCards, Status } from "../ui/components.js";

type Kind = "all" | "places" | "objects" | "vehicles";

export function Store({ platform, held, packages, onOpenPlace, onOpenVehicle, onOpenObject, onBuildOn, onChanged }: {
  platform?: Platform;
  held: Held;
  packages: Packages;
  onOpenPlace: (id: string) => void;
  onOpenVehicle: (slug: string) => void;
  /** One of your objects, just copied from the store. */
  onOpenObject?: (id: string) => void;
  /** Compose a new place on a store place's ground. */
  onBuildOn?: (cityId: string) => void;
  onChanged?: () => void | Promise<void>;
}): React.JSX.Element {
  const [kind, setKind] = useState<Kind>("all");
  const [store, setStore] = useState<StorePlace[] | undefined>();
  const [objects, setObjects] = useState<Asset[] | undefined>();
  // Your own finished objects: those not in the store yet are offered here to
  // put in it, so the store holds everything you have.
  const [ours, setOurs] = useState<Asset[]>([]);
  // What was just copied, so its card can say where it went.
  const [copied, setCopied] = useState<Record<string, string>>({});
  const [pictures, setPictures] = useState<Record<string, string>>({});
  // The place being taken or let go of, so its card says so while it works.
  const [working, setWorking] = useState<string | undefined>();
  const [trouble, setTrouble] = useState("");
  // The card opened: what it is, and what can be done with it, in one place.
  const [looking, setLooking] = useState<{ place: StorePlace } | { object: Asset } | undefined>();
  const institution = held.institution;

  const readStore = useCallback(async () => {
    if (!platform) return;
    setStore(await platform.storePlaces().catch(() => []));
    setObjects(await platform.storeObjects().catch(() => []));
    if (held.institution) setOurs(await platform.listAssets(held.institution.id).catch(() => []));
  }, [platform, held.institution]);
  useEffect(() => { void readStore(); }, [readStore]);
  useEffect(() => {
    if (!platform) return;
    for (const one of store ?? []) {
      if (!one.versionId || !one.picture || pictures[one.id]) continue;
      void platform.files(one.versionId).then((files) => {
        const url = files.find((f) => f.path === "picture.jpg")?.url;
        if (url) setPictures((was) => ({ ...was, [one.id]: url }));
      }).catch(() => undefined);
    }
  }, [platform, store, pictures]);

  const busy = async (id: string, work: () => Promise<void>) => {
    if (!platform || !institution) return;
    setTrouble("");
    setWorking(id);
    try {
      await work();
      await readStore();
      await onChanged?.();
    } catch (problem) {
      setTrouble(problem instanceof Error ? problem.message : "it could not be done");
    } finally {
      setWorking(undefined);
    }
  };
  const copyPlace = (one: StorePlace) => busy(one.id, async () => {
    const made = await platform!.copyStorePlace(institution!.id, one.id);
    setCopied((was) => ({ ...was, [one.id]: made.id }));
  });
  const offer = (one: Asset, on: boolean) => busy(one.id, async () => { await platform!.offerAsset(one.id, on); });
  const offerAll = (list: Asset[]) => busy("all", async () => {
    for (const one of list) await platform!.offerAsset(one.id, true);
  });
  const letGo = (one: StorePlace) => busy(one.id, () => platform!.unadoptStorePlace(institution!.id, one.id));
  const copyObject = (one: Asset) => busy(one.id, async () => {
    const made = await platform!.copyStoreObject(institution!.id, one.id);
    setCopied((was) => ({ ...was, [one.id]: made.id }));
  });

  const offered = new Set((objects ?? []).map((o) => o.id));
  const notYet = ours.filter((o) => o.state === "ready" && !offered.has(o.id));
  const yours = (one: Asset) => institution !== undefined && one.orgId === institution.id;
  const published = new Set(held.vehicles.map((v) => v.slug));
  const vehicles = CATALOGUE.filter((v) => !published.has(v.slug));
  const showPlaces = kind === "all" || kind === "places";
  const showObjects = kind === "all" || kind === "objects";
  const showVehicles = kind === "all" || kind === "vehicles";

  return (
    <Page title="Store" subtitle="Places, objects and vehicles on iOcean, yours among them. Copy one and it is yours."
          info="iOcean builds places from public data and checks them before publishing them here. Copying a place makes a place of your own to change; the store's never changes, and you can copy it as many times as you like."
          toolbar={<Segmented label="Kind" value={kind} onChange={setKind}
                              options={[{ key: "all", label: "Everything" },
                                        { key: "places", label: "Places", count: store?.length },
                                        { key: "objects", label: "Objects", count: objects ? objects.length + notYet.length : undefined },
                                        { key: "vehicles", label: "Vehicles", count: vehicles.length }]} />}>
      {trouble ? <p className="trouble">{trouble}</p> : null}
      {showPlaces ? (
        <section className="store-kind">
          {kind === "all" ? <h2>Places</h2> : null}
          {store === undefined ? <SkeletonCards count={3} /> : store.length === 0 ? (
            <Empty title="No places in the store yet">iOcean publishes the places it builds from public data here.</Empty>
          ) : (
            <div className="cards">
              {store.map((one) => (
                <StoreCard key={one.id} one={one} photo={pictures[one.id]} pkg={packages.places.get(one.id)}
                           working={working === one.id} onOpen={() => setLooking({ place: one })} />
              ))}
              {kind === "places" ? ENVIRONMENTS.map((one) => (
                <Card key={one.key} name={one.name} detail={one.where}
                      art={<PlacePlan standing={one.standing} deepestM={depthOf(one)} size={64} />}
                      specs={[one.standing]} later="coming" />
              )) : null}
            </div>
          )}
        </section>
      ) : null}
      {showObjects ? (
        <section className="store-kind">
          {kind === "all" ? <h2>Objects</h2> : null}
          {objects === undefined ? <SkeletonCards count={3} /> : objects.length + notYet.length === 0 ? (
            <Empty title="No objects in the store yet">Reefs, structures and models iOcean offers will appear here.</Empty>
          ) : (
            <div className="cards">
              {objects.map((one) => {
                const { name, source } = nameAndSource(one.name);
                return (
                  <Card key={one.id} name={name} detail={source ? `${kindSaid(one)} · ${source}` : kindSaid(one)}
                        picture={one.preview || undefined} art={<ObjectArt kind={artOf(one)} />}
                        corner={working === one.id ? <Status tone="busy">{yours(one) ? "working" : "copying"}</Status>
                          : copied[one.id] ? <Status tone="good">in your objects</Status>
                          : yours(one) ? <Status tone="good">yours</Status> : undefined}
                        onOpen={() => setLooking({ object: one })} />
                );
              })}
            </div>
          )}
          {notYet.length ? (
            <>
              <div className="store-yours">
                <h3>Yours, not in the store yet</h3>
                <Button disabled={working !== undefined} onClick={() => void offerAll(notYet)}>
                  {working === "all" ? "Putting them in…" : `Put all ${notYet.length} in the store`}
                </Button>
              </div>
              <div className="cards">
                {notYet.map((one) => {
                  const { name, source } = nameAndSource(one.name);
                  return (
                    <Card key={one.id} name={name} detail={source ? `${kindSaid(one)} · ${source}` : kindSaid(one)}
                          picture={one.preview || undefined} art={<ObjectArt kind={artOf(one)} />}
                          corner={working === one.id ? <Status tone="busy">working</Status> : <Status>only yours</Status>}
                          onOpen={() => setLooking({ object: one })} />
                  );
                })}
              </div>
            </>
          ) : null}
        </section>
      ) : null}
      {showVehicles ? (
        <section className="store-kind">
          {kind === "all" ? <h2>Vehicles</h2> : null}
          {vehicles.length === 0 ? (
            <Empty title="Every vehicle iOcean has is in your fleet">New vehicles appear here as iOcean adds them.</Empty>
          ) : (
            <div className="cards">
              {vehicles.map((one) => (
                <Card key={one.slug} name={one.name} detail={one.manufacturer}
                      art={<VehiclePlan thrusters={thrustersOf(one.dynamics)} size={64} />}
                      specs={[`${one.dynamics.massKg} kg`]}
                      later={one.notYet ? "coming" : "not yet flyable"}
                      onOpen={() => onOpenVehicle(one.slug)} />
              ))}
            </div>
          )}
        </section>
      ) : null}
      {looking ? (() => {
        const place = "place" in looking ? looking.place : undefined;
        const object = "object" in looking ? looking.object : undefined;
        const id = place?.id ?? object!.id;
        const mine = copied[id];
        const own = object !== undefined && yours(object);
        const inStore = object !== undefined && offered.has(object.id);
        const close = () => setLooking(undefined);
        const name = place?.name ?? nameAndSource(object!.name).name;
        return (
          <Dialog title={name} onClose={close} wide
                  actions={<>
                    {place?.adopted ? <Button kind="danger" disabled={working !== undefined} onClick={() => void letGo(place)}>Stop sharing the store's own</Button> : null}
                    {place ? <Button kind="ghost" onClick={() => { close(); onBuildOn?.(place.id); }}>Build a new place on its ground</Button> : null}
                    {place ? <Button onClick={() => { close(); onOpenPlace(place.id); }}>Look inside</Button> : null}
                    {mine ? <Button onClick={() => { close(); if (place) onOpenPlace(mine); else onOpenObject?.(mine); }}>Open your copy</Button> : null}
                    {own ? <Button onClick={() => { close(); onOpenObject?.(object.id); }}>Open it</Button> : null}
                    {own ? (
                      <Button kind={inStore ? "danger" : "primary"} disabled={working !== undefined}
                              onClick={() => void offer(object, !inStore).then(close)}>
                        {working === id ? "Working…" : inStore ? "Take it out of the store" : "Put it in the store"}
                      </Button>
                    ) : (
                      <Button kind="primary" disabled={!institution || working !== undefined}
                              onClick={() => void (place ? copyPlace(place) : copyObject(object!))}>
                        {working === id ? "Copying…" : mine ? "Copy it again" : place ? "Copy to your places" : "Copy to your objects"}
                      </Button>
                    )}
                  </>}>
            <div className="store-look">
              {place ? <StoreCard one={place} photo={pictures[place.id]} pkg={packages.places.get(place.id)} working={false} />
                : <Card name={name} detail={kindSaid(object!)} picture={object!.preview || undefined} art={<ObjectArt kind={artOf(object!)} />} />}
              <div className="store-said">
                <p>{place?.summary ?? nameAndSource(object!.name).source ?? kindSaid(object!)}</p>
                {place?.copies ? <p className="note">{place.copies === 1 ? "One copy is in your places." : `${place.copies} copies are in your places.`}</p> : null}
                <p className="note">{own
                  ? inStore ? "Anybody on iOcean can copy it into their own objects. Taking it out stops new copies; copies made stay." : "Only your organisation has it. In the store, anybody on iOcean can copy it."
                  : "The store's own never changes; a copy is yours to change, and taking it again makes another."}</p>
              </div>
            </div>
          </Dialog>
        );
      })() : null}
    </Page>
  );
}

/** A place in the store: its own photograph when it ships one, else its relief. */
function StoreCard({ one, photo, pkg, onOpen, working }: {
  one: StorePlace;
  photo: string | undefined;
  pkg: PlacePackage | null | undefined;
  onOpen?: () => void;
  working: boolean;
}): React.JSX.Element {
  const drawn = usePlacePicture(photo !== undefined ? null : pkg);
  const picture = photo ?? drawn ?? undefined;
  return (
    <Card name={one.name} detail={firstSentence(one.summary) || "an iOcean place"}
          picture={picture} reading={photo === undefined && drawn === undefined}
          art={<PlacePlan standing={one.surveyed ? "surveyed" : "derived"} deepestM={one.deepestM} size={64} />}
          specs={[
            one.deepestM !== undefined ? `to ${one.deepestM.toFixed(0)} m` : "",
            one.surveyedFraction !== undefined ? `${Math.round(one.surveyedFraction * 100)}% measured` : one.surveyed ? "surveyed" : "derived depths",
            one.colonies ? `${one.colonies.toLocaleString()} colonies` : "",
          ].filter(Boolean)}
          corner={working ? <Status tone="busy">copying</Status> : one.copies ? <Status tone="good">{one.copies === 1 ? "1 copy in your places" : `${one.copies} copies in your places`}</Status>
            : one.adopted ? <Status tone="good">in your places</Status> : undefined}
          onOpen={onOpen} />
  );
}

/** A card says one sentence; the place's page says the rest. */
export function firstSentence(said: string | undefined): string {
  if (!said) return "";
  const cut = said.search(/[.;:](\s|$)/);
  return cut > 0 ? said.slice(0, cut) : said;
}

function depthOf(one: { purpose?: string; takes?: string; summary?: string }): number | undefined {
  const said = `${one.purpose ?? ""} ${one.takes ?? ""} ${one.summary ?? ""}`;
  const found = said.match(/(\d{1,3})\s*(?:m\b|metres)/);
  return found ? Number(found[1]) : undefined;
}

export function thrustersOf(dynamics: unknown): { position?: number[]; direction?: number[] }[] {
  const said = (dynamics ?? {}) as { thrusters?: unknown };
  const thrusters = said.thrusters as { units?: unknown[] } | unknown[] | undefined;
  if (Array.isArray(thrusters)) return thrusters as { position?: number[] }[];
  if (thrusters && Array.isArray(thrusters.units)) return thrusters.units as { position?: number[] }[];
  return [];
}
