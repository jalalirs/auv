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
  runs: { dive: string; name: string; flownBy: string; run: Run }[];
  /** The autonomy this institution has deployed, newest first, every build. */
  stacks: AutonomyStack[];
  /** The same as controllers: one per slug, its newest build first. */
  controllers: Controller[];
}

/** A controller somebody deployed, across its builds. */
export interface Controller {
  slug: string;
  name: string;
  newest: AutonomyStack;
  builds: AutonomyStack[];
}

/** Builds grouped by slug, newest build first within each, newest controller first. */
export function controllersOf(stacks: AutonomyStack[]): Controller[] {
  const by = new Map<string, AutonomyStack[]>();
  for (const one of stacks) by.set(one.slug, [...(by.get(one.slug) ?? []), one]);
  return [...by.entries()].map(([slug, builds]) => {
    const sorted = [...builds].sort((a, b) => (a.createdAt < b.createdAt ? 1 : -1));
    return { slug, name: sorted[0]!.name, newest: sorted[0]!, builds: sorted };
  }).sort((a, b) => (a.newest.createdAt < b.newest.createdAt ? 1 : -1));
}

export interface Packages {
  places: Map<string, PlacePackage | null>;     // null: read, and there is no package
  vehicles: Map<string, VehiclePackage | null>;
}

/**
 * What a refresh is for.
 *
 * The catalogue is cheap and wants to be current: a queue that says a machine
 * is free is only useful if it was true seconds ago. The dives are neither —
 * with a matrix in the record that is hundreds of requests, and nothing about
 * them changes between one ten-second tick and the next unless somebody is
 * flying. So a tick reads the catalogue and keeps the dives it already had,
 * and the dives are read afresh only when the application asks for them.
 */
export async function readHeld(platform: Platform, keep?: Held): Promise<Held> {
  const [me, places, vehicles, queues] = await Promise.all([
    platform.me(), platform.places(), platform.vehicles(), platform.queues(),
  ]);
  const institution = me.organisations[0];

  // Every dive this institution has defined, and what became of each. The
  // platform keeps runs under the dive that defined them, so gathering them
  // is the client's job and not a missing endpoint.
  let runs: { dive: string; name: string; flownBy: string; run: Run }[] = [];
  let stacks: AutonomyStack[] = [];
  if (institution !== undefined) {
    stacks = (await platform.autonomy(institution.id).catch((): AutonomyStack[] => []))
      .sort((a, b) => (a.createdAt < b.createdAt ? 1 : -1));
    // Every dive the institution has, not the last dozen. Twelve was fine
    // when twelve was all there were; a matrix of two hundred and seventy-five
    // is a record with two hundred and seventy-five things to look at, and a
    // Dives page that quietly shows the newest few of them is a page that
    // lies about what was run.
    //
    // The platform keeps runs under their dive, so this is one request each.
    // In batches, because two hundred and seventy-five at once is a thing to
    // do to a machine rather than ask of it.
    if (keep !== undefined) {
      return { ...keep, you: me.principal, institution, places, vehicles, queues };
    }
    const dives = await platform.dives(institution.id);
    const named = (dive: { id: string; name: string; autonomyStackId?: string | null }) =>
      dive.autonomyStackId
        ? (stacks.find((s) => s.id === dive.autonomyStackId)?.name ?? "a stack since gone")
        : "by hand";
    const gathered: { dive: string; name: string; flownBy: string; run: Run }[] = [];
    for (let at = 0; at < dives.length; at += 24) {
      const batch = await Promise.all(dives.slice(at, at + 24).map(async (dive) =>
        (await platform.runs(dive.id).catch((): Run[] => []))
          .map((run) => ({ dive: dive.id, name: dive.name, run, flownBy: named(dive) }))));
      gathered.push(...batch.flat());
    }
    runs = gathered.sort((a, b) => (a.run.requestedAt < b.run.requestedAt ? 1 : -1));
  }
  return { you: me.principal, institution, places, vehicles, queues, runs, stacks, controllers: controllersOf(stacks) };
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
