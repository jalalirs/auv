// A picture of the water: how hard it is running, and how far you can see.
//
// Drawn from the same two numbers the dive is defined with, so the picture is
// the condition rather than a decoration of it. The arrows point where the
// current flows towards and lengthen with its speed; the haze over them is the
// visibility. Still, murky water and a two-knot set look as different here as
// they feel down there.

export function WaterArt({ speedMs = 0, headingDeg = 0, visibilityM, size = 34 }: {
  /** Metres a second. */
  speedMs?: number;
  /** Where it flows towards, from north, clockwise — as a chart writes it. */
  headingDeg?: number;
  /** How far you can see, when the water says. */
  visibilityM?: number | null;
  size?: number;
}): React.JSX.Element {
  const strength = Math.max(0, Math.min(1, speedMs / 1.1));
  // Screen y runs down, and a heading of zero is north, which is up.
  const turn = headingDeg;
  const murk = visibilityM == null ? 0 : Math.max(0, Math.min(0.75, 1 - visibilityM / 17));
  const rows = [12, 20, 28];
  const length = 7 + strength * 11;

  return (
    <svg className="task-art" width={size} height={size} viewBox="0 0 40 40" aria-hidden="true">
      <rect x="0" y="0" width="40" height="40" rx="8" className="task-art-ground" />
      <g transform={`rotate(${turn} 20 20)`}>
        {rows.map((y, i) => {
          const from = 20 - length / 2;
          const to = 20 + length / 2;
          const x = 20 + (i - 1) * 8;
          return (
            <g key={y} opacity={strength < 0.02 ? 0.5 : 1}>
              <line x1={x} y1={to} x2={x} y2={from} stroke="#7fd3ff"
                    strokeWidth={1.2 + strength * 1.1} strokeLinecap="round" />
              {strength > 0.02 ? (
                <path d={`M${x - 2.6} ${from + 3.4} L${x} ${from} L${x + 2.6} ${from + 3.4}`}
                      fill="none" stroke="#7fd3ff" strokeWidth={1.2 + strength * 1.1}
                      strokeLinecap="round" strokeLinejoin="round" />
              ) : null}
            </g>
          );
        })}
      </g>
      {murk > 0.02 ? (
        <>
          <rect x="0" y="0" width="40" height="40" rx="8" fill="#9fb3cc" opacity={murk * 0.55} />
          <circle cx="12" cy="14" r="5" fill="#c9d6e6" opacity={murk * 0.22} />
          <circle cx="27" cy="26" r="7" fill="#c9d6e6" opacity={murk * 0.18} />
        </>
      ) : null}
    </svg>
  );
}
