// What the application holds about the platform while somebody is in it.
//
// Two layers, read at two speeds. The catalogue — who you are, what you have
// been granted, what is queued — is read at once and kept fresh every ten
// seconds, because a free machine is only useful if it was free recently. The
// packages — what each place and vehicle says about itself — are read once
// each, lazily, because a picture does not change and reading eight packages
// before showing a page is how an application feels slow.

import { useEffect, useRef, useState } from "react";

import type { City, Organisation, Platform, Principal, Queue, Run, Vehicle, AutonomyStack } from "@coral-city/api";

import { placePackage, vehiclePackage, type PlacePackage, type VehiclePackage } from "./packages.js";

export interface Held {
  you: Principal;
  institution: Organisation | undefined;
  places: City[];
  vehicles: Vehicle[];
  queues: Queue[];
  runs: { dive: string; name: string; run: Run }[];
  /** The autonomy this institution has deployed, newest first. */
  stacks: AutonomyStack[];
}

export interface Packages {
  places: Map<string, PlacePackage | null>;     // null: read, and there is no package
  vehicles: Map<string, VehiclePackage | null>;
}

export async function readHeld(platform: Platform): Promise<Held> {
  const [me, places, vehicles, queues] = await Promise.all([
    platform.me(), platform.places(), platform.vehicles(), platform.queues(),
  ]);
  const institution = me.organisations[0];

  // Every dive this institution has defined, and what became of each. The
  // platform keeps runs under the dive that defined them, so gathering them
  // is the client's job and not a missing endpoint.
  let runs: { dive: string; name: string; run: Run }[] = [];
  let stacks: AutonomyStack[] = [];
  if (institution !== undefined) {
    stacks = (await platform.autonomy(institution.id).catch((): AutonomyStack[] => []))
      .sort((a, b) => (a.createdAt < b.createdAt ? 1 : -1));
    const dives = await platform.dives(institution.id);
    const each = await Promise.all(
      dives.slice(0, 12).map(async (dive) => (await platform.runs(dive.id))
        .map((run) => ({ dive: dive.id, name: dive.name, run }))));
    runs = each.flat().sort((a, b) => (a.run.requestedAt < b.run.requestedAt ? 1 : -1));
  }
  return { you: me.principal, institution, places, vehicles, queues, runs, stacks };
}

/**
 * The packages behind what is held, read once each as they are needed.
 *
 * Read once, not on every refresh of the catalogue: the file URLs a package
 * comes with are signed afresh each time, and a picture whose address changes
 * every ten seconds is a picture that flickers. They are read again only when
 * the signatures are about to expire.
 *
 * Returns the packages read so far and re-renders as each arrives, so a page
 * fills in picture by picture rather than waiting for the slowest.
 */
const SIGNED_FOR_MS = 10 * 60 * 1000;

export function usePackages(platform: Platform, held: Held | undefined): Packages {
  const [packages, setPackages] = useState<Packages>({ places: new Map(), vehicles: new Map() });
  const readAt = useRef(new Map<string, number>());

  useEffect(() => {
    if (held === undefined) return;
    const now = Date.now();
    const due = (id: string): boolean => now - (readAt.current.get(id) ?? 0) > SIGNED_FOR_MS;
    for (const place of held.places) {
      if (!due(place.id)) continue;
      readAt.current.set(place.id, now);
      void placePackage(platform, place.id).then(
        (one) => setPackages((was) => ({ ...was, places: new Map(was.places).set(place.id, one ?? null) })),
        // A read that fails keeps what was read before; a picture is not taken
        // down because one refresh timed out.
        () => setPackages((was) => was.places.has(place.id) ? was
          : { ...was, places: new Map(was.places).set(place.id, null) }));
    }
    for (const vehicle of held.vehicles) {
      if (!due(vehicle.id)) continue;
      readAt.current.set(vehicle.id, now);
      void vehiclePackage(platform, vehicle.id).then(
        (one) => setPackages((was) => ({ ...was, vehicles: new Map(was.vehicles).set(vehicle.id, one ?? null) })),
        () => setPackages((was) => was.vehicles.has(vehicle.id) ? was
          : { ...was, vehicles: new Map(was.vehicles).set(vehicle.id, null) }));
    }
  }, [platform, held]);

  return packages;
}
