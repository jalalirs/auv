// What iOcean offers: its places and its vehicles, in one store.
//
// A place or a vehicle iOcean has built is not yours until you take it, and
// what you have taken is in Places or Vehicles. The kinds share one grid with
// a filter, not a tab each: they are all the same act, taking something.

import { useCallback, useEffect, useState } from "react";

import type { Platform, StorePlace } from "@coral-city/api";

import { CATALOGUE } from "../catalog/vehicles.js";
import { ENVIRONMENTS } from "../catalog/environments.js";
import { PlacePlan, VehiclePlan } from "../parts/PlanArt.js";
import { usePlacePicture } from "../parts/Relief.js";
import type { PlacePackage } from "../platform/packages.js";
import type { Held, Packages } from "./Deck.js";
import { Card, Empty } from "./parts.js";
import { Button, Menu, Page, Segmented, SkeletonCards, Status } from "../ui/components.js";

type Kind = "all" | "places" | "vehicles";

export function Store({ platform, held, packages, onOpenPlace, onOpenVehicle, onBuildOn, onChanged }: {
  platform?: Platform;
  held: Held;
  packages: Packages;
  onOpenPlace: (id: string) => void;
  onOpenVehicle: (slug: string) => void;
  /** Compose a new place on a store place's ground. */
  onBuildOn?: (cityId: string) => void;
  onChanged?: () => void | Promise<void>;
}): React.JSX.Element {
  const [kind, setKind] = useState<Kind>("all");
  const [store, setStore] = useState<StorePlace[] | undefined>();
  const [pictures, setPictures] = useState<Record<string, string>>({});
  // The place being taken or let go of, so its card says so while it works.
  const [working, setWorking] = useState<string | undefined>();
  const [trouble, setTrouble] = useState("");
  const institution = held.institution;

  const readStore = useCallback(async () => {
    if (!platform) return;
    setStore(await platform.storePlaces().catch(() => []));
  }, [platform]);
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

  const take = async (one: StorePlace, yes: boolean) => {
    if (!platform || !institution) return;
    setTrouble("");
    setWorking(one.id);
    try {
      if (yes) await platform.adoptStorePlace(institution.id, one.id);
      else await platform.unadoptStorePlace(institution.id, one.id);
      await readStore();
      await onChanged?.();
    } catch (problem) {
      setTrouble(problem instanceof Error ? problem.message : "it could not be changed");
    } finally {
      setWorking(undefined);
    }
  };

  const published = new Set(held.vehicles.map((v) => v.slug));
  const vehicles = CATALOGUE.filter((v) => !published.has(v.slug));
  const showPlaces = kind !== "vehicles";
  const showVehicles = kind !== "places";

  return (
    <Page title="Store" subtitle="Places and vehicles from iOcean. Take one and it is in yours."
          info="iOcean builds places from public data and checks them before publishing them here. Taking a place puts it in your Places; the store's own copy never changes."
          toolbar={<Segmented label="Kind" value={kind} onChange={setKind}
                              options={[{ key: "all", label: "Everything" },
                                        { key: "places", label: "Places", count: store?.length },
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
                           onOpen={() => onOpenPlace(one.id)}
                           actions={working === one.id ? (
                             <Button disabled>{one.adopted ? "Removing…" : "Adding to your places…"}</Button>
                           ) : one.adopted ? (
                             <>
                               <Button onClick={() => onOpenPlace(one.id)}>Open</Button>
                               <Menu label={`More for ${one.name}`} items={[
                                 { label: "Compose a new place on it", onSelect: () => onBuildOn?.(one.id) },
                                 { label: "Remove from your places", danger: true, onSelect: () => void take(one, false) },
                               ]} />
                             </>
                           ) : (
                             <>
                               <Button kind="secondary" disabled={!institution || working !== undefined} onClick={() => void take(one, true)}>Add to your places</Button>
                               <Menu label={`More for ${one.name}`} items={[
                                 { label: "Compose a new place on it", onSelect: () => onBuildOn?.(one.id) },
                               ]} />
                             </>
                           )} />
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
    </Page>
  );
}

/** A place in the store: its own photograph when it ships one, else its relief. */
function StoreCard({ one, photo, pkg, onOpen, actions }: {
  one: StorePlace;
  photo: string | undefined;
  pkg: PlacePackage | null | undefined;
  onOpen: () => void;
  actions: React.ReactNode;
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
          corner={one.adopted ? <Status tone="good">in your places</Status> : undefined}
          onOpen={onOpen} actions={actions} />
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
