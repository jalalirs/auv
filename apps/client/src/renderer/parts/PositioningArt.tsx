// A picture of how the vehicle knows where it is.
//
// The vehicle, and whatever is telling it: a ship overhead with a cone of
// sound, transponders on the seabed, or nothing at all but its own log
// pinging the bottom. The picture is the arrangement, because that is what
// the choice actually is.

const INK = "#40c7f4";
const MARK = "#f4c542";
const FAINT = "#9fb3cc";

export function PositioningArt({ kind, size = 34 }: { kind: string; size?: number }): React.JSX.Element {
  return (
    <svg className="task-art" width={size} height={size} viewBox="0 0 40 40" aria-hidden="true">
      <rect x="0" y="0" width="40" height="40" rx="8" className="task-art-ground" />
      {/* The surface, and the bottom: every one of these is drawn between them. */}
      <path d="M4 8 H36" stroke="#7fd3ff" strokeWidth="1.2" opacity="0.8" />
      <path d="M4 33 H36" stroke={MARK} strokeWidth="1.2" opacity="0.55" />
      {shape(kind)}
    </svg>
  );
}

function shape(kind: string): React.JSX.Element {
  const vehicle = <rect x="17" y="19" width="7" height="4.5" rx="1.4" fill={INK} />;
  switch (kind) {
    // A ship, and a cone of sound down to the vehicle.
    case "usbl":
      return (
        <>
          <path d="M14 8 L26 8 L23 5 L17 5 Z" fill={FAINT} />
          <path d="M20 8 L15 21 M20 8 L26 21" stroke={FAINT} strokeWidth="1" opacity="0.7"
                strokeDasharray="2 2" />
          <path d="M20 8 L20 19" stroke={FAINT} strokeWidth="1.2" opacity="0.5" />
          {vehicle}
        </>
      );

    // Transponders on the seabed, ranging in.
    case "lbl":
      return (
        <>
          {[8, 20, 32].map((x) => (
            <g key={x}>
              <path d={`M${x} 33 L${x} 29`} stroke={MARK} strokeWidth="1.4" />
              <circle cx={x} cy="28" r="2" fill={MARK} />
              <path d={`M${x} 28 L20.5 22`} stroke={MARK} strokeWidth="0.9" opacity="0.6"
                    strokeDasharray="2 2" />
            </g>
          ))}
          {vehicle}
        </>
      );

    // One transponder, and the vehicle homing on it.
    case "beacon":
      return (
        <>
          <path d="M30 33 L30 27" stroke={MARK} strokeWidth="1.6" />
          <circle cx="30" cy="25.5" r="2.4" fill={MARK} />
          {[6, 10, 14].map((r) => (
            <path key={r} d={`M${30 - r} 25.5 A ${r} ${r} 0 0 1 ${30} ${25.5 - r}`}
                  fill="none" stroke={MARK} strokeWidth="1" opacity={0.55 - r * 0.02} />
          ))}
          <rect x="9" y="19" width="7" height="4.5" rx="1.4" fill={INK} />
          <path d="M17 21 L24 23" stroke={INK} strokeWidth="1.2" strokeDasharray="2 2" />
        </>
      );

    // The log, pinging the bottom, and nothing else.
    case "no-dvl":
      return (
        <>
          {vehicle}
          <path d="M20 24 L20 31" stroke="#ff7a5c" strokeWidth="1.3" strokeDasharray="2 2" opacity="0.85" />
          <path d="M17 28 L23 33 M23 28 L17 33" stroke="#ff7a5c" strokeWidth="1.5" strokeLinecap="round" />
        </>
      );

    // A compass, wrong.
    case "poor-compass":
      return (
        <>
          {vehicle}
          <circle cx="20" cy="28.5" r="4.5" fill="none" stroke={FAINT} strokeWidth="1.1" />
          <path d="M20 28.5 L23.4 25.6" stroke="#ff7a5c" strokeWidth="1.5" strokeLinecap="round" />
          <path d="M20 28.5 L20 24" stroke={FAINT} strokeWidth="1" opacity="0.55" strokeDasharray="1.5 1.5" />
        </>
      );

    // Dead reckoning: the log has the bottom, and the track is its own.
    default:
      return (
        <>
          {vehicle}
          <path d="M20 24 L20 32" stroke={INK} strokeWidth="1.2" opacity="0.8" strokeDasharray="2 2" />
          <path d="M17.5 30 L20 33 L22.5 30" fill="none" stroke={INK} strokeWidth="1.2"
                strokeLinejoin="round" opacity="0.8" />
          <path d="M6 26 Q 11 24 14 21" fill="none" stroke={INK} strokeWidth="1.3" opacity="0.6" />
        </>
      );
  }
}
