// How the vehicle knows where it is.
//
// There is no GPS underwater, so this is a real choice with real consequences
// and it belongs on the composer beside the water. A dive is a place, a
// vehicle, a fit of technology, a body of water, a controller and a task —
// six things chosen separately, and the interesting results come from crossing
// them: the same survey on dead reckoning and inside an LBL array is two
// different problems, and the difference is the point.
//
// Two halves, kept apart because they belong to different people. What the
// vehicle carries is stated by whoever published the vehicle, and `fitted`
// only ever takes things away from it — the same hull with the Doppler log
// unshipped. What is deployed in the water is stated here, because a ship
// overhead or an array on the seabed is a fact about the situation and not
// about the vehicle.

export interface Positioning {
  key: string;
  name: string;
  says: string;
  /** What the errors are, in the words a person would use. */
  expect: string;
  parameters: {
    positioning?: Record<string, unknown>;
    fitted?: Record<string, unknown>;
  };
}

export const POSITIONING: Positioning[] = [
  {
    key: "dead-reckoning",
    name: "Dead reckoning",
    says: "The Doppler log, the compass and the pressure sensor. Nothing deployed, nothing overhead.",
    expect: "A metre or two out over a hundred metres, and it never comes back on its own.",
    parameters: { positioning: { kind: "none" } },
  },
  {
    key: "usbl",
    name: "A ship overhead, with USBL",
    says: "One transceiver at the surface, ranging and bearing to the vehicle every couple of seconds.",
    expect: "Half a per cent of slant range: tens of centimetres shallow, metres deep.",
    parameters: {
      positioning: { kind: "usbl", everyS: 2, accuracyPercent: 0.5, rangeM: 500, at: [0, 0, 0] },
    },
  },
  {
    key: "lbl",
    name: "Inside an LBL array",
    says: "Transponders laid on the seabed and surveyed in. A fix every few seconds — inside the array only.",
    expect: "Half a metre while you are in it, and dead reckoning the moment you leave.",
    parameters: {
      positioning: { kind: "lbl", everyS: 3, accuracyM: 0.5, rangeM: 150, at: [0, 0, -10] },
    },
  },
  {
    key: "beacon",
    name: "A beacon on the station",
    says: "One transponder on the dock, ranging and bearing to it — nothing about the world, everything about the dock.",
    expect: "Centimetres alongside it, useless from far away. This is what docking needs and dead reckoning cannot give.",
    parameters: {
      positioning: { kind: "beacon", everyS: 1, accuracyM: 0.3, rangeM: 60, at: [0, 0, -6] },
    },
  },
  {
    key: "no-dvl",
    name: "No Doppler log",
    says: "The log is unshipped: a compass, a clock and whatever the vehicle believes about its own speed.",
    expect: "Tens of metres over a few hundred. This is what navigation was before the DVL.",
    parameters: { positioning: { kind: "none" }, fitted: { dvl: false } },
  },
  {
    key: "poor-compass",
    name: "A compass in a steel frame",
    says: "The log is fitted and the heading is five degrees out, which is what a magnetometer beside six motors does.",
    expect: "Eight metres of cross-track over a hundred, all of it sideways.",
    parameters: { positioning: { kind: "none" }, fitted: { headingAccuracyDeg: 5.0 } },
  },
];
