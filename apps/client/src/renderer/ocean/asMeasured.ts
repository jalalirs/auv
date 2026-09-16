// What the sea is doing, as conditions a dive can be flown in.
//
// The platform has always known the difference between water somebody composed
// and water somebody measured: `constructed` conditions are refused if they
// name an instant, and `observed` conditions are refused if they do not,
// because an instant is a claim about provenance. That distinction is built,
// enforced and tested — and nothing had ever created an observed condition.
// The slot was cut and empty.
//
// Meanwhile the application already reads real measurements for every place:
// NOAA Coral Reef Watch satellite products and Sofar Spotter buoys, through
// Aqualink, shown as a pill on the place card. This turns what is already in
// hand into water a dive can be flown in, with the instant it was taken and
// who took it.
//
// What it cannot give is the current, and that is the one thing a dive most
// wants. A satellite does not measure it and a wave buoy does not either, so
// the current stays whatever was chosen and this says so rather than inventing
// a number to fill the field.

import type { Reading, SeaNow, SeaRecord } from "../../shared/bridge.js";

/** Conditions as the platform takes them. */
export interface Measured {
  kind: "observed";
  name: string;
  observedAt: string;
  sources: Record<string, unknown>[];
  parameters: Record<string, unknown>;
}

/** What each instrument is, in the words a person would use. */
const INSTRUMENTS: Record<string, string> = {
  noaa: "NOAA Coral Reef Watch, by satellite",
  spotter: "a Sofar Spotter buoy in the water",
  hobo: "a HOBO logger in the water",
};

function newest(...readings: (Reading | undefined)[]): Reading | undefined {
  const had = readings.filter((one): one is Reading => one !== undefined);
  if (had.length === 0) return undefined;
  return had.reduce((a, b) => (Date.parse(b.at) > Date.parse(a.at) ? b : a));
}

/**
 * The sea as it was measured, or nothing if nobody measured it.
 *
 * Nothing rather than a default: water with an instant on it is a claim that
 * somebody took a reading, and a claim like that must fail rather than fall
 * back.
 */
export function asMeasured(record: SeaRecord | undefined): Measured | undefined {
  if (record === undefined) return undefined;
  const now: SeaNow = record.now;

  // The temperature the vehicle is actually in, preferring an instrument in
  // the water over a satellite reading the skin of it.
  const temperature = newest(now.bottomTemperatureC, now.topTemperatureC)
    ?? now.satelliteTemperatureC;
  if (temperature === undefined) return undefined;

  const parameters: Record<string, unknown> = { temperatureC: temperature.value };
  const sources: Record<string, unknown>[] = [];
  const cite = (what: string, reading: Reading | undefined): void => {
    if (reading === undefined) return;
    sources.push({
      what,
      at: reading.at,
      from: INSTRUMENTS[reading.source] ?? reading.source,
      through: "aqualink.org",
    });
  };
  cite("temperature", temperature);

  // Sea state, which is measured where there is a buoy and is what a surface
  // vehicle and a launch both live with.
  if (now.significantWaveHeightM !== undefined) {
    parameters["significantWaveHeightM"] = now.significantWaveHeightM.value;
    cite("wave height", now.significantWaveHeightM);
  }
  if (now.waveMeanPeriodS !== undefined) {
    parameters["waveMeanPeriodS"] = now.waveMeanPeriodS.value;
    cite("wave period", now.waveMeanPeriodS);
  }
  if (now.waveMeanDirectionDeg !== undefined) {
    parameters["waveHeadingDeg"] = now.waveMeanDirectionDeg.value;
  }
  if (now.windSpeedMs !== undefined) {
    parameters["windSpeedMs"] = now.windSpeedMs.value;
    cite("wind", now.windSpeedMs);
  }
  if (now.windDirectionDeg !== undefined) {
    parameters["windHeadingDeg"] = now.windDirectionDeg.value;
  }

  // Said out loud, because a field that is absent reads as a field nobody
  // thought about. Nothing here measures the current.
  parameters["currentNotMeasured"] = true;

  return {
    kind: "observed",
    name: `${record.site.name}, as measured`,
    observedAt: temperature.at,
    sources,
    parameters,
  };
}
