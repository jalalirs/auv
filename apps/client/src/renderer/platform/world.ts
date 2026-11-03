// A place's world: its document of layers, read, made and saved.
//
// Every place has one world (docs/plan/world-document.md). One made before
// worlds existed gets its first version written from what the place already
// says: its package's site record for the water, the terrain's sources, the
// reef and the life, and its newest arrangement for what was put in it. So
// nothing anybody laid out is lost on the way, and from then on the world is
// what is edited and what a dive pins.

import type { AssetVersion, City, LayoutDocument, Mission, Platform, WorldDocument, WorldLayer } from "@coral-city/api";

import type { PlacePackage } from "./packages.js";
import { whereIs } from "./packages.js";

export type { WorldDocument, WorldLayer };

/** The world record of a place, its newest version, and the document in it. */
export interface WorldOf {
  world: Mission | undefined;
  version: AssetVersion | undefined;
  document: WorldDocument;
}

/** What the site record says that a world is made from; read loosely, since
 *  old builds wrote less. */
interface SiteSays {
  from?: { acrossMetres?: number; source?: string; centre?: { latitude: number; longitude: number } };
  enclosed?: boolean;
  water?: { type?: string; from?: string };
  life?: { count?: Record<string, number>; from?: string };
  reef?: { colonies?: number; cover?: { from?: string } };
  perCell?: { sources?: { source: string; kind?: string; citation?: string; licence?: string }[] };
  reconstructions?: { name: string; reconstructionId?: string; video?: { reconstructionId?: string } }[];
  structures?: { name: string; asset?: string; type?: string; route?: { local?: [number, number][] } }[];
}

/** A layer of a world, by kind. */
export function layerOf(document: WorldDocument, kind: WorldLayer["kind"]): WorldLayer | undefined {
  return document.layers.find((l) => l.kind === kind);
}

/** The world a place's package and newest arrangement describe. */
export function worldFromPlace(city: City, pkg: PlacePackage | undefined,
                               arrangement?: LayoutDocument & { objects?: unknown[] }): WorldDocument {
  const site = (pkg?.site ?? {}) as unknown as SiteSays;
  const centre = whereIs(city.extent, pkg?.site);
  const across = site.from?.acrossMetres ?? 1000;
  // A tank, or a place nobody put anywhere real, is a world with no place on
  // Earth: the SubPipe outfall was set down off Thuwal, and its video is from
  // Portugal.
  const virtual = site.enclosed === true || /subpipe/i.test(city.slug);
  const sources = (site.perCell?.sources ?? []).map((s, i) => ({
    asset: "", name: s.source, role: (s.kind === "measured" ? "check" : "depth") as "depth" | "check",
    priority: i, citation: s.citation, origin: s.kind,
  }));
  const things = ((arrangement?.things ?? []) as unknown as { id: string; kind: string }[]).map((t) => ({ ...t }));
  const objects = ((arrangement?.objects ?? []) as { id: string; assetId: string; name: string; meets: string }[]);
  const laidReefs = (site.reconstructions ?? []).map((r, i) => ({
    id: `reef-${i + 1}`, kind: "reef", name: r.name,
    asset: r.reconstructionId ?? r.video?.reconstructionId ?? "", laid: true,
  }));
  const laidStructures = (site.structures ?? []).map((s, i) => ({
    id: `structure-${i + 1}`, kind: "object", name: s.name, meets: s.type === "pipeline" ? "drapes" : "stands",
    asset: (s.asset ?? "").replace(/^asset\//, ""), laid: true,
    ...(s.route?.local ? { route: s.route.local.map(([x, y]) => ({ x, y })), x: 0, y: 0 } : { x: 0, y: 0 }),
  }));
  return {
    iocean: "world/1",
    name: city.name,
    frame: { units: "m", axes: "x east, y north, z up; z = 0 is the sea surface", extentM: [across, across], origin: "middle" },
    georef: virtual || !centre ? null : {
      origin: { lat: centre.latitude, lon: centre.longitude }, north: "true", horizontal: "WGS84", vertical: "MSL",
      setBy: "terrain",
    },
    layers: [
      { id: "water", kind: "water", params: { waterType: site.water?.type ? `Jerlov ${site.water.type}` : "Jerlov IB",
        visibilityM: 12, temperatureC: 28, salinityPsu: 40, from: site.water?.from ?? "chosen" } },
      { id: "terrain", kind: "terrain", stack: sources,
        ...(pkg ? { result: { asset: city.id, version: pkg.version.ordinal, name: `${city.name} as built` } } : {}) },
      { id: "seabed", kind: "seabed", classes: { "1": "sand", "5": "rock", "3": "seagrass" } },
      { id: "reef", kind: "reef", params: { colonies: site.reef?.colonies ?? 0, from: site.reef?.cover?.from ?? "" },
        items: [...laidReefs, ...objects.filter((o) => o.meets === "reef").map((o) => ({ ...o, kind: "reef", asset: o.assetId }))] },
      { id: "structures", kind: "structures",
        items: [...things, ...laidStructures,
                ...objects.filter((o) => o.meets !== "reef").map((o) => ({ ...o, kind: "object", asset: o.assetId }))] },
      { id: "life", kind: "life", params: site.life?.count ? { count: site.life.count, from: site.life.from ?? "" } : {} },
    ],
    ...(pkg ? { bake: { version: pkg.version.id, at: pkg.version.createdAt } } : {}),
    madeFrom: { place: city.id, ...(pkg ? { version: pkg.version.id } : {}) },
  };
}

/** The newest arrangement of a place, which a world is first made from. */
async function newestArrangement(platform: Platform, place: string): Promise<(LayoutDocument & { objects?: unknown[] }) | undefined> {
  const layouts = await platform.layoutsOf(place).catch(() => []);
  const newest = (await Promise.all(layouts.map(async (l) =>
    (await platform.versionsOfLayout(l.id).catch((): AssetVersion[] => []))[0])))
    .filter((v): v is AssetVersion => !!v)
    .sort((a, b) => b.createdAt.localeCompare(a.createdAt))[0];
  return newest?.document as (LayoutDocument & { objects?: unknown[] }) | undefined;
}

/** A place's world: saved, or written from the place when it has none yet. */
export async function readWorld(platform: Platform, city: City, pkg: PlacePackage | undefined): Promise<WorldOf> {
  const world = (await platform.worldsOf(city.id).catch((): Mission[] => []))[0];
  if (world) {
    const version = (await platform.versionsOfWorld(world.id).catch((): AssetVersion[] => []))[0];
    if (version?.document) return { world, version, document: version.document as unknown as WorldDocument };
  }
  return { world, version: undefined, document: worldFromPlace(city, pkg, await newestArrangement(platform, city.id)) };
}

/** Saves a world, making its record first when the place has none. */
export async function saveWorld(platform: Platform, city: City, of: WorldOf, document: WorldDocument,
                                label = ""): Promise<WorldOf> {
  const world = of.world ?? await platform.startWorld(city.id, { slug: "world", name: city.name });
  const version = await platform.saveWorld(world.id, document, label);
  return { world, version, document };
}

/** How a structures item is drawn, from what kind it is. */
export function isObject(item: { kind: string }): boolean {
  return item.kind === "object";
}
