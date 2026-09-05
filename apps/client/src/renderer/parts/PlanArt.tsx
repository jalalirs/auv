// Pictures for the things that have no photograph yet.
//
// A vehicle that has been catalogued but not published has no hull to render
// and no picture to show — but it does have numbers, and the numbers are a
// drawing: its thrusters, where they sit and which way they point, seen from
// above. That is more use than a grey square and more honest than a stock
// photograph of something else.
//
// A place that is planned rather than built has a shape too: how deep it goes,
// and whether the ground is surveyed, mixed or made up. Drawn as a section.

const INK = "#40c7f4";
const MARK = "#f4c542";
const HULL = "#9fb3cc";

export function VehiclePlan({ thrusters, size = 34 }: {
  /** Where each thruster sits and which way it pushes, in metres, body frame. */
  thrusters?: { position?: number[]; direction?: number[] }[];
  size?: number;
}): React.JSX.Element {
  const units = (thrusters ?? []).filter((t) => Array.isArray(t.position));
  // The frame, to the scale of the widest thruster offset, seen from above:
  // body x forward is up the picture, y to starboard is right.
  const reach = Math.max(0.12, ...units.map((t) => Math.max(Math.abs(t.position![0] ?? 0),
                                                            Math.abs(t.position![1] ?? 0))));
  const scale = 12 / reach;
  return (
    <svg className="task-art" width={size} height={size} viewBox="0 0 40 40" aria-hidden="true">
      <rect x="0" y="0" width="40" height="40" rx="8" className="task-art-ground" />
      <rect x="13" y="10" width="14" height="20" rx="3.5" fill="none" stroke={HULL} strokeWidth="1.3" />
      <path d="M20 10 L20 6" stroke={HULL} strokeWidth="1.3" strokeLinecap="round" />
      {units.map((one, i) => {
        const [ahead = 0, starboard = 0, up = 0] = one.position!;
        const x = 20 + starboard * scale;
        const y = 20 - ahead * scale;
        const vertical = Math.abs((one.direction ?? [0, 0, 1])[2] ?? 0) > 0.7;
        return vertical
          ? <rect key={i} x={x - 2.6} y={y - 2.6} width="5.2" height="5.2" rx="1.2"
                  fill={MARK} opacity={up >= 0 ? 0.95 : 0.6} />
          : <circle key={i} cx={x} cy={y} r="2.7" fill={INK} />;
      })}
      {units.length === 0 ? (
        <text x="20" y="24" textAnchor="middle" fill={HULL} fontSize="9" opacity="0.7">?</text>
      ) : null}
    </svg>
  );
}

export function PlacePlan({ deepestM, standing, size = 34 }: {
  /** How deep it goes, when the catalogue says. */
  deepestM?: number;
  /** Whether the ground is surveyed, part surveyed, or made up. */
  standing?: string;
  size?: number;
}): React.JSX.Element {
  // A section: the surface, and a bottom whose profile is drawn from how deep
  // the place goes. Dashed where the ground is not a survey.
  const deep = Math.max(0, Math.min(1, (deepestM ?? 20) / 40));
  const floor = 12 + deep * 18;
  const dashed = standing !== undefined && standing !== "surveyed";
  return (
    <svg className="task-art" width={size} height={size} viewBox="0 0 40 40" aria-hidden="true">
      <rect x="0" y="0" width="40" height="40" rx="8" className="task-art-ground" />
      <path d="M4 9 H36" stroke="#7fd3ff" strokeWidth="1.3" strokeLinecap="round" opacity="0.85" />
      <path d={`M4 ${floor} Q 11 ${floor - 5} 16 ${floor - 1} T 27 ${floor - 3} T 36 ${floor + 1}`}
            fill="none" stroke={MARK} strokeWidth="1.6" strokeLinecap="round"
            strokeDasharray={dashed ? "3 2.5" : undefined} />
      <path d={`M4 ${floor} Q 11 ${floor - 5} 16 ${floor - 1} T 27 ${floor - 3} T 36 ${floor + 1} L36 36 L4 36 Z`}
            fill={MARK} opacity="0.14" />
      {deepestM === undefined ? null : (
        <text x="20" y={Math.min(34, floor + 6)} textAnchor="middle" fill={HULL} fontSize="7.5" opacity="0.85">
          {`${deepestM.toFixed(0)} m`}
        </text>
      )}
    </svg>
  );
}
