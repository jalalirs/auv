// Aqualink, read into the shapes in bridge.ts.
//
// Pure: given a way to fetch JSON and a way to remember the site list, this
// turns Aqualink's answers into a SeaSite and a SeaRecord. The main process
// gives it a fetch and a file on disk; a page shown in a plain browser while
// the application is being built gives it a fetch and memory. Neither knows
// the other exists, and the numbers come out the same.
//
// Nothing here is ours. The numbers are NOAA Coral Reef Watch satellite products
// and Sofar Spotter buoy readings, kept by Aqualink (aqualink.org); every record
// says which, and the page shows the source beside the number.

import type { LatLon, Reading, SeaDay, SeaNow, SeaRecord, SeaSite, SeaSurvey } from "./bridge.js";

export const AQUALINK_API = "https://ocean-systems.uc.r.appspot.com/api";
const SITE_PAGE = "https://aqualink.org/sites";
const DAY_MS = 24 * 3600 * 1000;

/** The subset of a site the list carries that we keep. */
export interface ListedSite {
  id: number;
  name: string;
  region: string | undefined;
  latitude: number;
  longitude: number;
  depth: number | undefined;
  status: string;
  hasBuoy: boolean;
  timezone: string | undefined;
  maxMonthlyMean: number | undefined;
}

export type FetchJson = <T>(url: string) => Promise<T>;

/** Somewhere to keep the site list between asks: a file, or memory. */
export interface SiteListStore {
  read(): Promise<{ at: number; sites: ListedSite[] } | undefined>;
  write(sites: ListedSite[]): Promise<void>;
}

export class InMemoryStore implements SiteListStore {
  #kept: { at: number; sites: ListedSite[] } | undefined;
  async read(): Promise<{ at: number; sites: ListedSite[] } | undefined> { return this.#kept; }
  async write(sites: ListedSite[]): Promise<void> { this.#kept = { at: Date.now(), sites }; }
}

export class AqualinkReader {
  #fetch: FetchJson;
  #store: SiteListStore;
  #sites: ListedSite[] | undefined;
  #records = new Map<number, { at: number; record: SeaRecord }>();

  constructor(fetchJson: FetchJson, store: SiteListStore) {
    this.#fetch = fetchJson;
    this.#store = store;
  }

  // ── the site list ─────────────────────────────────────────────────────────

  async #siteList(): Promise<ListedSite[]> {
    if (this.#sites !== undefined) return this.#sites;
    const kept = await this.#store.read();
    if (kept !== undefined && Date.now() - kept.at < DAY_MS) {
      this.#sites = kept.sites;
      return kept.sites;
    }
    const raw = await this.#fetch<Array<Record<string, unknown>>>(`${AQUALINK_API}/sites`);
    const sites = raw.map(listed).filter((s): s is ListedSite => s !== undefined);
    await this.#store.write(sites);
    this.#sites = sites;
    return sites;
  }

  /**
   * The nearest site to a point, within a radius.
   *
   * Preferring a site that reports over one that merely exists: a buoy fifteen
   * hundred metres away says more about the water than a satellite pixel three
   * hundred metres away, so a deployed site within the radius wins over a
   * nearer one that is only a pin on a map.
   */
  async nearestSite(at: LatLon, withinKm: number): Promise<SeaSite | undefined> {
    const sites = await this.#siteList();
    const scored = sites
      .map((site) => ({ site, distanceM: metresBetween(at, site) }))
      .filter((one) => one.distanceM <= withinKm * 1000)
      .sort((a, b) => a.distanceM - b.distanceM);
    if (scored.length === 0) return undefined;
    const best = scored.find((one) => one.site.hasBuoy && one.site.status === "deployed")
      ?? scored.find((one) => one.site.status === "deployed" || one.site.status === "approved")
      ?? scored[0]!;
    return describe(best.site, best.distanceM);
  }

  // ── one site's record ─────────────────────────────────────────────────────

  async record(siteId: number, at: LatLon): Promise<SeaRecord> {
    const kept = this.#records.get(siteId);
    if (kept !== undefined && Date.now() - kept.at < 10 * 60 * 1000) return kept.record;

    const since = new Date(Date.now() - 56 * DAY_MS).toISOString().slice(0, 10);
    const until = new Date().toISOString().slice(0, 10);
    const [detail, latest, daily, surveys] = await Promise.all([
      this.#fetch<Record<string, unknown>>(`${AQUALINK_API}/sites/${siteId}`),
      this.#fetch<{ latestData: Array<{ metric: string; value: number; timestamp: string; source: string }> }>(
        `${AQUALINK_API}/sites/${siteId}/latest_data`),
      this.#fetch<Array<Record<string, unknown>>>(`${AQUALINK_API}/sites/${siteId}/daily_data?start=${since}&end=${until}`),
      this.#fetch<Array<Record<string, unknown>>>(`${AQUALINK_API}/sites/${siteId}/surveys`).catch(() => []),
    ]);

    const site = describe(listed(detail) ?? {
      id: siteId, name: "", region: undefined, latitude: at.latitude, longitude: at.longitude,
      depth: undefined, status: "", hasBuoy: false, timezone: undefined, maxMonthlyMean: undefined,
    }, 0);
    site.distanceM = Math.round(metresBetween(at, site.at));

    const take = (metric: string): Reading | undefined => {
      const one = latest.latestData.find((r) => r.metric === metric);
      return one === undefined ? undefined : { value: one.value, at: one.timestamp, source: one.source };
    };
    const now: SeaNow = {
      satelliteTemperatureC: take("satellite_temperature"),
      sstAnomalyC: take("sst_anomaly"),
      degreeHeatingWeeks: take("dhw"),
      alertLevel: take("temp_alert"),
      bottomTemperatureC: take("bottom_temperature"),
      topTemperatureC: take("top_temperature"),
      windSpeedMs: take("wind_speed"),
      windDirectionDeg: take("wind_direction"),
      significantWaveHeightM: take("significant_wave_height"),
      waveMeanPeriodS: take("wave_mean_period"),
      waveMeanDirectionDeg: take("wave_mean_direction"),
      barometricPressureHpa: take("barometric_pressure_top"),
    };

    const days: SeaDay[] = daily
      .map((d) => {
        const heatingDays = numberOr(d["degreeHeatingDays"]);
        return {
          date: String(d["date"]).slice(0, 10),
          satelliteTemperatureC: numberOr(d["satelliteTemperature"]),
          // Aqualink keeps degree heating *days*; weeks is the unit everybody reads.
          degreeHeatingWeeks: heatingDays === undefined ? undefined : heatingDays / 7,
          alertLevel: numberOr(d["dailyAlertLevel"]),
        };
      })
      .sort((a, b) => (a.date < b.date ? -1 : 1));

    const logged: SeaSurvey[] = surveys.map((s) => {
      const user = s["user"] as { fullName?: string } | null;
      const media = s["featuredSurveyMedia"] as { url?: string; thumbnailUrl?: string; observations?: string } | null;
      return {
        id: s["id"] as number,
        on: String(s["diveDate"] ?? "").slice(0, 10),
        by: user?.fullName,
        comments: typeof s["comments"] === "string" ? (s["comments"] as string) : undefined,
        weather: typeof s["weatherConditions"] === "string" ? (s["weatherConditions"] as string) : undefined,
        temperatureC: numberOr(s["temperature"]) ?? numberOr(s["satelliteTemperature"]),
        pictureUrl: media?.thumbnailUrl ?? media?.url,
        observations: media?.observations,
      };
    }).sort((a, b) => (a.on < b.on ? 1 : -1));

    const record: SeaRecord = { site, now, days, surveys: logged, fetchedAt: new Date().toISOString() };
    this.#records.set(siteId, { at: Date.now(), record });
    return record;
  }
}

/** One site as Aqualink lists it, reduced to what is kept, or nothing if it has no position. */
export function listed(one: Record<string, unknown>): ListedSite | undefined {
  const polygon = one["polygon"] as { type?: string; coordinates?: number[] } | null;
  if (!polygon || polygon.type !== "Point" || !polygon.coordinates) return undefined;
  const [longitude, latitude] = polygon.coordinates;
  if (typeof latitude !== "number" || typeof longitude !== "number") return undefined;
  const region = one["region"] as { name?: string } | null;
  return {
    id: one["id"] as number,
    name: String(one["name"] ?? "").trim(),
    region: region?.name,
    latitude, longitude,
    depth: numberOr(one["depth"]),
    status: String(one["status"] ?? ""),
    hasBuoy: one["sensorId"] !== null && one["sensorId"] !== undefined,
    timezone: typeof one["timezone"] === "string" ? (one["timezone"] as string) : undefined,
    maxMonthlyMean: numberOr(one["maxMonthlyMean"]),
  };
}

function describe(site: ListedSite, distanceM: number): SeaSite {
  return {
    id: site.id, name: site.name, region: site.region,
    at: { latitude: site.latitude, longitude: site.longitude },
    distanceM: Math.round(distanceM),
    depthM: site.depth, status: site.status, hasBuoy: site.hasBuoy,
    timezone: site.timezone, maxMonthlyMeanC: site.maxMonthlyMean,
    url: `${SITE_PAGE}/${site.id}`,
  };
}

function numberOr(value: unknown): number | undefined {
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

/** Great-circle distance, good to a fraction of a percent at these scales. */
export function metresBetween(a: LatLon, b: LatLon): number {
  const rad = Math.PI / 180;
  const dLat = (b.latitude - a.latitude) * rad;
  const dLon = (b.longitude - a.longitude) * rad;
  const h = Math.sin(dLat / 2) ** 2
    + Math.cos(a.latitude * rad) * Math.cos(b.latitude * rad) * Math.sin(dLon / 2) ** 2;
  return 2 * 6_371_000 * Math.asin(Math.sqrt(h));
}
