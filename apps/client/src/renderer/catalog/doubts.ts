// What nobody can promise.
//
// The platform takes any doubt at all — a dimension is a name and a list of
// settings, and a setting is whatever it does to the water or to what was
// asked for. That is right: a doubt is whatever somebody could not promise,
// and a platform holding a list of the weather it is allowed to worry about
// would be a platform telling reef programmes what to be uncertain about.
//
// This is the client's palette of the common ones, the way `tasks.ts` is the
// composer's palette of the common objectives. Everything here could be typed
// by hand into the API; nothing here is the limit of what it accepts.
//
// The numbers are the same ones the composer offers for a single dive, so that
// "one knot" means one knot on both screens.

export interface Setting {
  key: string;
  /** What it says on the row. */
  name: string;
  /** What it does — to the water, or (under `objective`) to what was asked. */
  does: Record<string, unknown>;
}

export interface Doubt {
  key: string;
  name: string;
  /** Why somebody would doubt it, in a line. */
  says: string;
  settings: Setting[];
}

export const DOUBTS: Doubt[] = [
  {
    key: "current", name: "The current",
    says: "What the water is doing on the day. The one thing nobody gets to choose and the one that most often decides it.",
    settings: [
      { key: "still", name: "Still", does: { currentMetresPerSecond: 0, currentHeadingDeg: 0 } },
      { key: "gentle", name: "A gentle set", does: { currentMetresPerSecond: 0.15, currentHeadingDeg: 30 } },
      { key: "half knot", name: "Half a knot", does: { currentMetresPerSecond: 0.26, currentHeadingDeg: 30 } },
      { key: "one knot", name: "One knot", does: { currentMetresPerSecond: 0.51, currentHeadingDeg: 30 } },
    ],
  },
  {
    key: "fix", name: "How it knows where it is",
    says: "Whether the array gets laid, whether the ship can hold station over it, or neither.",
    settings: [
      { key: "array", name: "An LBL array", does: { positioning: { kind: "lbl", everyS: 3, accuracyM: 0.5, rangeM: 400 } } },
      { key: "ship", name: "A ship with USBL", does: { positioning: { kind: "usbl", everyS: 2, accuracyPercent: 0.5, rangeM: 500 } } },
      { key: "nothing", name: "Nothing overhead", does: { positioning: { kind: "none" } } },
    ],
  },
  {
    key: "water clarity", name: "How far you can see",
    says: "A week of weather before the window puts the sediment up, and a camera that cannot see the bottom is not surveying it.",
    settings: [
      { key: "clear", name: "Clear", does: {} },
      { key: "murky", name: "Murky — five metres", does: { visibilityM: 5.0 } },
    ],
  },
  {
    key: "trouble", name: "Something gives out",
    says: "A thruster an hour in, or a Doppler log that never comes up. Both happen, and neither is a reason to cancel if the plan survives them.",
    settings: [
      { key: "none", name: "Nothing does", does: {} },
      { key: "thruster", name: "A thruster, an hour in", does: { failures: [{ kind: "thruster", which: 2, atS: 3600 }] } },
      { key: "no log", name: "No Doppler log", does: { fitted: { dvl: false } } },
    ],
  },
  {
    key: "how long", name: "How long the day is",
    says: "The doubt that changes the answer from “do not go” to “allow twice as long”, which is usually the one worth having.",
    settings: [
      { key: "a shift", name: "One shift", does: { objective: { timeLimitS: 2400 } } },
      { key: "two shifts", name: "Two shifts", does: { objective: { timeLimitS: 4800 } } },
    ],
  },
];

/** The document the platform wants, from what somebody ticked. */
export function doubtsFrom(picked: Record<string, string[]>): Record<string, Record<string, Record<string, unknown>>> {
  const out: Record<string, Record<string, Record<string, unknown>>> = {};
  for (const doubt of DOUBTS) {
    const chosen = picked[doubt.key] ?? [];
    if (chosen.length < 2) continue;   // one setting is not a doubt, it is a decision
    const settings: Record<string, Record<string, unknown>> = {};
    for (const one of doubt.settings) {
      if (chosen.includes(one.key)) settings[one.key] = one.does;
    }
    out[doubt.key] = settings;
  }
  return out;
}

/** How many dives that is. */
export function scenariosIn(picked: Record<string, string[]>): number {
  const doubts = doubtsFrom(picked);
  const dimensions = Object.values(doubts).map((d) => Object.keys(d).length);
  return dimensions.length === 0 ? 0 : dimensions.reduce((a, b) => a * b, 1);
}
