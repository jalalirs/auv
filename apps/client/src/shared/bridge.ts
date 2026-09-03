// What crosses between the window and the process that owns it.
//
// The renderer gets no Node. Everything it may ask the main process for is
// named here, one call at a time, typed once and shared by both sides — so the
// preload that exposes it and the page that calls it cannot disagree about a
// shape without the compiler saying so.

/** A place on the globe, in WGS 84 degrees. */
export interface LatLon {
  latitude: number;
  longitude: number;
}

/**
 * An Aqualink monitoring site: somewhere somebody keeps a record of the sea.
 *
 * Aqualink (aqualink.org) is a philanthropic ocean monitoring platform. Every
 * site carries NOAA Coral Reef Watch satellite products — temperature, heat
 * stress, alert level — and the sites with a buoy carry live water temperature,
 * wind and waves as well. Looe Key Reef has one, three hundred metres from the
 * centre of our site.
 */
export interface SeaSite {
  id: number;
  name: string;
  region: string | undefined;
  at: LatLon;
  /** Metres from the point that was asked about. */
  distanceM: number;
  depthM: number | undefined;
  /** "deployed" means a buoy is in the water and reporting. */
  status: string;
  hasBuoy: boolean;
  timezone: string | undefined;
  /** The highest monthly mean temperature this site has seen; bleaching stress is counted above it. */
  maxMonthlyMeanC: number | undefined;
  url: string;
}

/** One reading, with when it was taken and what took it. */
export interface Reading {
  value: number;
  at: string;
  /** "noaa" for a satellite product, "spotter" or "hobo" for an instrument in the water. */
  source: string;
}

/** What the sea is doing at a site now, or as recently as anybody measured. */
export interface SeaNow {
  satelliteTemperatureC?: Reading;
  sstAnomalyC?: Reading;
  /** Degree heating weeks: accumulated heat stress over twelve weeks. Bleaching likely above 4, severe above 8. */
  degreeHeatingWeeks?: Reading;
  /** NOAA Coral Reef Watch alert level, 0 to 4. */
  alertLevel?: Reading;
  bottomTemperatureC?: Reading;
  topTemperatureC?: Reading;
  windSpeedMs?: Reading;
  windDirectionDeg?: Reading;
  significantWaveHeightM?: Reading;
  waveMeanPeriodS?: Reading;
  waveMeanDirectionDeg?: Reading;
  barometricPressureHpa?: Reading;
}

/** One day of the satellite record. */
export interface SeaDay {
  date: string;
  satelliteTemperatureC: number | undefined;
  degreeHeatingWeeks: number | undefined;
  alertLevel: number | undefined;
}

/** A dive somebody logged at the site, with what they saw. */
export interface SeaSurvey {
  id: number;
  on: string;
  by: string | undefined;
  comments: string | undefined;
  weather: string | undefined;
  temperatureC: number | undefined;
  pictureUrl: string | undefined;
  observations: string | undefined;
}

export interface SeaRecord {
  site: SeaSite;
  now: SeaNow;
  days: SeaDay[];
  surveys: SeaSurvey[];
  /** When this was fetched, so a page can say how fresh it is. */
  fetchedAt: string;
}

/** What the window may ask the main process. */
export interface Bridge {
  ocean: {
    /** The nearest monitoring site to a point, within a radius, or nothing. */
    nearestSite(at: LatLon, withinKm: number): Promise<SeaSite | undefined>;
    /** Everything known about a site, fetched fresh or from a short cache. */
    record(siteId: number, at: LatLon): Promise<SeaRecord>;
  };
  app: {
    /** The application's version, from its own package. */
    version(): Promise<string>;
  };
}

/** The channel names, one per call, so both sides spell them the same way. */
export const CHANNELS = {
  nearestSite: "ocean:nearest-site",
  record: "ocean:record",
  version: "app:version",
} as const;

declare global {
  interface Window {
    coralCity: Bridge;
  }
}
