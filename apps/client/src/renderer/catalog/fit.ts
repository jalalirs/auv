// What a vehicle carries on a dive, and what carrying it costs.
//
// A vehicle package says what the hull has. A dive says what of it is fitted,
// and the two are not the same question: the same hull without its Doppler log
// is a different problem and should not need a second vehicle in the
// catalogue. That distinction has been in the platform for a while — the
// runtime reads `fitted` and always has — and there has never been anywhere to
// say it except by hand.
//
// It is not a label. Every instrument draws, the computer draws, and the
// hotel load used to be one number standing for all of them together, so
// unfitting something changed the endurance by exactly nothing. Each states
// its own draw now, so this screen is a choice about how long the dive lasts.

/** One thing the hull carries, as its package declares it. */
export interface Carried {
  kind: string;
  name?: string;
  watts?: number;
  wattsNote?: string;
}

/** What a vehicle thinks with. */
export interface Machine {
  kind?: string;
  watts?: number;
  tops?: number;
  ramGb?: number;
  note?: string;
}

/** In the words somebody would use, rather than the package's keys. */
export const INSTRUMENTS: Record<string, { name: string; why: string }> = {
  underwater_camera: { name: "Camera", why: "What it sees, and what a survey brings home." },
  imaging_sonar: { name: "Sonar", why: "What it can see that nobody told it about. The largest single draw on a small hull." },
  dvl: { name: "Doppler log", why: "Speed over the ground. Without it the navigation is dead reckoning on a compass, and it drifts fast." },
  imu: { name: "IMU", why: "Which way it is pointing. Nothing flies without one." },
  barometer: { name: "Depth", why: "Pressure is depth. It costs nothing." },
  ctd: { name: "CTD", why: "The water it is flying in: temperature, salinity, density. This is what a section brings home." },
};

/** What the vehicle draws, before it has moved. */
export function drawOf(carried: Carried[], machine: Machine | undefined,
                       base: number, off: Set<string>): number {
  let watts = base;
  for (const one of carried) {
    if (off.has(one.kind)) continue;
    watts += one.watts ?? 0;
  }
  if (!off.has("computer")) watts += machine?.watts ?? 0;
  return watts;
}

/**
 * Roughly how long the battery lasts at rest, in hours.
 *
 * At rest, which is not a dive — a vehicle that is working is mostly spending
 * on thrust. It is the right number for this screen even so, because it is the
 * part the fit changes and the part a person can do something about.
 */
export function hoursAtRest(usableWh: number, watts: number): number {
  return watts <= 0 ? 0 : usableWh / watts;
}

/** Whether what is flying it could run on what it carries. */
export function beyondTheHull(machine: Machine | undefined,
                              needs: { tops?: number; ramGb?: number } | undefined): string | undefined {
  if (machine === undefined || needs === undefined) return undefined;
  if ((needs.tops ?? 0) > (machine.tops ?? 0)) {
    return `This controller wants ${needs.tops} TOPS and the hull carries `
      + `${machine.tops ?? 0}. It would not run at sea.`;
  }
  if ((needs.ramGb ?? 0) > (machine.ramGb ?? 0)) {
    return `This controller wants ${needs.ramGb} GB and the hull carries `
      + `${machine.ramGb ?? 0} GB.`;
  }
  return undefined;
}
