// What a package says about itself.
//
// The platform records packages and does not read them: a place is a set of
// files with digests, and the platform knows their names and nothing else.
// Everything a card or a page shows beyond a name — where a place is, what it
// looks like, how deep it goes, how a vehicle moves — is read here out of the
// package's own files, through the short-lived URLs the platform hands out.
//
// So a picture is a real render of the thing itself, or there is no picture.
// Nothing here invents one.

import type { AssetVersion, PackageFile, Platform, VehicleDynamics } from "@coral-city/api";

/** The newest published version, or the newest draft if nothing is published. */
export function newestOf(versions: AssetVersion[]): AssetVersion | undefined {
  const published = versions.filter((v) => v.publishedAt);
  const sorted = (published.length > 0 ? published : versions)
    .slice()
    .sort((a, b) => ((a.publishedAt ?? a.createdAt ?? "") < (b.publishedAt ?? b.createdAt ?? "") ? 1 : -1));
  return sorted[0];
}

/** What tools/make-site writes beside a place's terrain. Only what is read here. */
export interface SiteRecord {
  name: string;
  from?: {
    surveyed?: boolean;
    centre?: { latitude: number; longitude: number };
    acrossMetres?: number;
    sampleMetres?: number;
    surveys?: { name: string }[];
    source?: string;
  };
  datum?: string;
  deepestM?: number;
  shallowestM?: number;
  beginAt?: number[];
  beginBecause?: string;
  reef?: { colonies?: number; source?: string; kinds?: Record<string, number> };
  layers?: Record<string, string>;
  picture?: string;
}

/**
 * Who a picture is by, when it is not a render of the thing itself.
 *
 * A package may carry a photograph of the real place or vehicle beside its
 * own files, under a licence that asks to be named. picture.json says so, and
 * the page says it beside the picture.
 */
export interface PictureCredit {
  title?: string;
  author?: string;
  licence?: string;
  source?: string;
  /** "photograph" of the real thing, or "render" from the package's own model. */
  kind?: "photograph" | "render";
}

export interface PlacePackage {
  version: AssetVersion;
  files: PackageFile[];
  pictureUrl: string | undefined;
  credit: PictureCredit | undefined;
  site: SiteRecord | undefined;
}

export interface VehiclePackage {
  version: AssetVersion;
  files: PackageFile[];
  pictureUrl: string | undefined;
  credit: PictureCredit | undefined;
  dynamics: VehicleDynamics | undefined;
  /** The hull's USD, if the package carries one; without it the vehicle cannot be drawn. */
  hull: PackageFile | undefined;
}

const PICTURES = ["picture.jpg", "picture.png", "picture.jpeg"];

function pictureIn(files: PackageFile[]): string | undefined {
  return files.find((f) => PICTURES.includes(f.path.toLowerCase()))?.url;
}

async function readJson<T>(files: PackageFile[], name: string): Promise<T | undefined> {
  const file = files.find((f) => f.path === name);
  if (file === undefined) return undefined;
  try {
    const response = await fetch(file.url);
    if (!response.ok) return undefined;
    return (await response.json()) as T;
  } catch {
    return undefined;
  }
}

export async function placePackage(platform: Platform, placeId: string): Promise<PlacePackage | undefined> {
  const version = newestOf(await platform.versionsOfPlace(placeId));
  if (version === undefined) return undefined;
  const files = await platform.files(version.id);
  const [site, credit] = await Promise.all([
    readJson<SiteRecord>(files, "site.json"), readJson<PictureCredit>(files, "picture.json")]);
  return { version, files, pictureUrl: pictureIn(files), credit, site };
}

export async function vehiclePackage(platform: Platform, vehicleId: string): Promise<VehiclePackage | undefined> {
  const version = newestOf(await platform.versionsOfVehicle(vehicleId));
  if (version === undefined) return undefined;
  const files = await platform.files(version.id);
  const [dynamics, credit] = await Promise.all([
    readJson<VehicleDynamics>(files, "dynamics.json"), readJson<PictureCredit>(files, "picture.json")]);
  return {
    version, files, pictureUrl: pictureIn(files), credit, dynamics,
    hull: files.find((f) => /\.usd[ac]?$|\.usdz$/i.test(f.path)),
  };
}

/**
 * The centre of a place, if its package says where it is.
 *
 * The platform's own extent is used when it is set; a place founded without
 * one falls back to what its site record says. A place that says neither is
 * nowhere, and a page must say so rather than put it at zero-zero in the Gulf
 * of Guinea.
 */
export function whereIs(extent: { west: number; south: number; east: number; north: number } | undefined,
                        site: SiteRecord | undefined): { latitude: number; longitude: number } | undefined {
  if (extent && (extent.west !== 0 || extent.east !== 0 || extent.north !== 0 || extent.south !== 0)) {
    return { latitude: (extent.north + extent.south) / 2, longitude: (extent.east + extent.west) / 2 };
  }
  return site?.from?.centre;
}
