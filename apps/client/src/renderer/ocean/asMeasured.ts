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

/**
 * The sea as it was on a stated day, or nothing if nobody recorded that day.
 *
 * "Fly it as it was last Tuesday" is a different question from "fly it as it
 * is", and it is the one an operator asks: a dive is planned against a day
 * that already happened, because that is the day there is evidence for.
 *
 * What the record holds for a past day is the satellite temperature and the
 * heat it had been under, and **that is all** — the daily series carries no
 * wave and no wind, because the buoy's are readings and not a history. So
 * this returns a day's temperature with that day's instant on it, and says
 * nothing about the rest. A dive flown from it reads, claim by claim:
 * temperature measured, sea state nobody said, current nobody said. Which is
 * the truth about what anybody knows about last Tuesday, and is worth more
 * than a plausible number with no instant behind it.
 */
export function asItWasOn(record: SeaRecord | undefined, date: string): Measured | undefined {
  if (record === undefined) return undefined;
  const day = record.days.find((one) => one.date === date);
  if (day === undefined || day.satelliteTemperatureC === undefined) return undefined;
  // Noon UTC: a daily satellite product is a day and not a moment, and
  // pretending it was taken at midnight would be a sharper claim than the
  // product makes.
  const at = `${day.date}T12:00:00Z`;
  const parameters: Record<string, unknown> = {
    temperatureC: day.satelliteTemperatureC,
    // Said out loud, as above: a field that is absent reads as a field
    // nobody thought about.
    currentNotMeasured: true,
  };
  const sources = [{
    what: "temperature", parameter: "temperatureC", at,
    from: `${INSTRUMENTS["noaa"]}, as a daily mean`, through: "aqualink.org",
  }];
  if (day.degreeHeatingWeeks !== undefined) {
    parameters["degreeHeatingWeeks"] = day.degreeHeatingWeeks;
    sources.push({
      what: "heat stress", parameter: "degreeHeatingWeeks", at,
      from: INSTRUMENTS["noaa"]!, through: "aqualink.org",
    });
  }
  return {
    kind: "observed",
    name: `${record.site.name}, as it was on ${day.date}`,
    observedAt: at,
    sources,
    parameters,
  };
}

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
  // `parameter` is the field this reading became, so that a run can put the
  // instrument beside the number rather than beside a word for it. `what` is
  // still there because it is what a person reads.
  const cite = (what: string, parameter: string, reading: Reading | undefined): void => {
    if (reading === undefined) return;
    sources.push({
      what,
      parameter,
      at: reading.at,
      from: INSTRUMENTS[reading.source] ?? reading.source,
      through: "aqualink.org",
    });
  };
  cite("temperature", "temperatureC", temperature);

  // Sea state, which is measured where there is a buoy and is what a surface
  // vehicle and a launch both live with.
  if (now.significantWaveHeightM !== undefined) {
    parameters["significantWaveHeightM"] = now.significantWaveHeightM.value;
    cite("wave height", "significantWaveHeightM", now.significantWaveHeightM);
  }
  if (now.waveMeanPeriodS !== undefined) {
    parameters["waveMeanPeriodS"] = now.waveMeanPeriodS.value;
    cite("wave period", "waveMeanPeriodS", now.waveMeanPeriodS);
  }
  if (now.waveMeanDirectionDeg !== undefined) {
    parameters["waveHeadingDeg"] = now.waveMeanDirectionDeg.value;
  }
  if (now.windSpeedMs !== undefined) {
    parameters["windSpeedMs"] = now.windSpeedMs.value;
    cite("wind", "windSpeedMs", now.windSpeedMs);
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
