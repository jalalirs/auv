// The plan a dive is flying, as a thing you can read.
//
// A vehicle doing something is not the same as a vehicle that has been asked
// to do something, and until the plan became a document there was no way to
// see the difference: the picture showed where it went, and what it was trying
// to do had to be inferred from that. Now the dive carries the plan it was
// given — worked out by the platform, written by hand, or emitted by a model —
// and this draws it.
//
// Deliberately a list and not a diagram. The chart already draws where the
// manoeuvres are; what this adds is their order, their parameters, and which
// one the vehicle is on, which is the part a picture of the seabed cannot say.

export interface Manoeuvre {
  id: string;
  kind: string;
  at?: { x: number; y: number; depthM?: number; altitudeM?: number };
  points?: { x: number; y: number }[];
  altitudeM?: number;
  arriveM?: number;
  speedMs?: number;
  holdS?: number;
  radiusM?: number;
  next?: string;
}

export interface Flying {
  plan?: string | null;
  by?: string | null;
  manoeuvres: Manoeuvre[];
}

/** What one manoeuvre asks for, in a line. */
function asks(one: Manoeuvre): string {
  if (one.kind === "follow-path") {
    const points = one.points ?? [];
    const ends = points.length > 1 && points[0] && points[points.length - 1]
      ? ` · ${points[0]!.x.toFixed(0)}, ${points[0]!.y.toFixed(0)}`
        + ` to ${points[points.length - 1]!.x.toFixed(0)}, ${points[points.length - 1]!.y.toFixed(0)}`
      : "";
    return `${points.length} points${ends}`
      + (one.altitudeM === undefined ? "" : ` · ${one.altitudeM.toFixed(1)} m up`);
  }
  const at = one.at;
  if (at === undefined) return "";
  const said = [`${at.x.toFixed(0)}, ${at.y.toFixed(0)}`];
  if (at.depthM !== undefined) said.push(`${at.depthM.toFixed(1)} m down`);
  if (at.altitudeM !== undefined) said.push(`${at.altitudeM.toFixed(1)} m up`);
  if (one.arriveM !== undefined) said.push(`within ${one.arriveM.toFixed(1)} m`);
  if (one.speedMs !== undefined) said.push(`${one.speedMs.toFixed(2)} m/s`);
  if (one.holdS !== undefined) said.push(`hold ${one.holdS.toFixed(0)} s`);
  if (one.radiusM !== undefined) said.push(`radius ${one.radiusM.toFixed(1)} m`);
  return said.join(" · ");
}

const CALLED: Record<string, string> = {
  "goto": "go to",
  "follow-path": "follow",
  "station-keeping": "stay",
};

export function Plan({ flying, at }: {
  flying: Flying | undefined;
  /** Which manoeuvre the vehicle is on, when that is known. */
  at?: string;
}): React.JSX.Element | null {
  if (flying === undefined || !flying.manoeuvres?.length) return null;
  return (
    <div className="flight-plan">
      <div className="flight-plan-head">
        <strong>{flying.plan || "the plan"}</strong>
        {flying.by ? <em>{flying.by}</em> : null}
      </div>
      <ol>
        {flying.manoeuvres.map((one) => (
          <li key={one.id} className={one.id === at ? "on" : undefined}>
            <span className="what">{CALLED[one.kind] ?? one.kind}</span>
            <span className="where">{asks(one)}</span>
          </li>
        ))}
      </ol>
    </div>
  );
}
