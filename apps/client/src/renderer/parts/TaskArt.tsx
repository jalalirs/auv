// A picture of each task: the shape of the thing it asks for.
//
// Not an icon of a boat or a magnifying glass. A task is a pattern flown over
// the ground, so the picture is that pattern — the square of the waypoints,
// the passes of a survey, the ring an inspection goes round, the cradle a dock
// is approached along. Somebody who has flown one recognises it, and somebody
// who has not learns something from looking at it, which is more than a
// pictogram does.
//
// Drawn rather than fetched: they are twenty lines of geometry each, they are
// crisp at any size, they take the console's own colours, and there is nothing
// to ship, sign or lose.

const INK = "#40c7f4";        // the vehicle's track
const MARK = "#f4c542";       // what the task asks for

export function TaskArt({ kind, size = 34 }: { kind: string; size?: number }): React.JSX.Element {
  return (
    <svg className="task-art" width={size} height={size} viewBox="0 0 40 40" aria-hidden="true">
      <rect x="0" y="0" width="40" height="40" rx="8" className="task-art-ground" />
      {shape(kind)}
    </svg>
  );
}

function shape(kind: string): React.JSX.Element {
  switch (kind) {
    // Staying put: a station, and the vehicle on it.
    case "hold-station":
    case "hold":
      return (
        <>
          <circle cx="20" cy="20" r="9" fill="none" stroke={MARK} strokeWidth="1.4" strokeDasharray="3 2.5" />
          <circle cx="20" cy="20" r="3" fill={INK} />
        </>
      );

    // Four points in order, and the track round them.
    case "waypoints":
      return (
        <>
          <path d="M11 27 L11 13 L27 13 L27 27 Z" fill="none" stroke={INK} strokeWidth="1.6"
                strokeLinejoin="round" />
          {[[11, 27], [11, 13], [27, 13], [27, 27]].map(([x, y], i) => (
            <circle key={i} cx={x} cy={y} r="2.6" fill={i === 0 ? INK : "none"} stroke={MARK} strokeWidth="1.3" />
          ))}
        </>
      );

    // A straight line held over the bottom.
    case "transect":
      return (
        <>
          <path d="M4 30 Q 14 26 20 29 T 36 27" fill="none" stroke={MARK} strokeWidth="1.6" opacity="0.7" />
          <path d="M6 17 L34 17" stroke={INK} strokeWidth="1.8" strokeLinecap="round" />
          <path d="M6 17 L6 30 M34 17 L34 27" stroke={MARK} strokeWidth="1" strokeDasharray="2 2" opacity="0.8" />
        </>
      );

    // Passes a swath apart, over a rectangle.
    case "survey":
      return (
        <>
          <rect x="7" y="8" width="26" height="24" rx="2" fill="none" stroke={MARK} strokeWidth="1.2"
                strokeDasharray="3 2" />
          <path d="M10 12 H30 V18 H10 V24 H30 V30" fill="none" stroke={INK} strokeWidth="1.6"
                strokeLinejoin="round" strokeLinecap="round" />
        </>
      );

    // From here to there, by the short way.
    case "reach":
      return (
        <>
          <circle cx="9" cy="29" r="2.6" fill={INK} />
          <path d="M9 29 L28 13" stroke={INK} strokeWidth="1.8" strokeLinecap="round" />
          <path d="M23 13 L29 12 L28 18" fill="none" stroke={INK} strokeWidth="1.6"
                strokeLinejoin="round" strokeLinecap="round" />
          <circle cx="30" cy="11" r="4.5" fill="none" stroke={MARK} strokeWidth="1.4" />
          <circle cx="30" cy="11" r="1.4" fill={MARK} />
        </>
      );

    // A pattern flown until the thing is in front of you.
    case "search":
      return (
        <>
          <rect x="6" y="8" width="28" height="24" rx="2" fill="none" stroke={MARK} strokeWidth="1.1"
                strokeDasharray="3 2" opacity="0.8" />
          <path d="M9 12 H31 V19 H9 V26 H31" fill="none" stroke={INK} strokeWidth="1.5"
                strokeLinejoin="round" strokeLinecap="round" opacity="0.85" />
          <circle cx="26" cy="26" r="3.4" fill={MARK} />
          <circle cx="26" cy="26" r="6.4" fill="none" stroke={MARK} strokeWidth="1" opacity="0.55" />
        </>
      );

    // Every colony in a patch, passed over low.
    case "treat":
      return (
        <>
          <circle cx="20" cy="20" r="14" fill="none" stroke={MARK} strokeWidth="1.1" strokeDasharray="3 2" />
          {[[13, 14], [21, 12], [27, 17], [12, 22], [19, 20], [26, 25], [15, 28], [23, 29]].map(([x, y], i) => (
            <circle key={i} cx={x} cy={y} r="1.9" fill={i < 5 ? MARK : "none"} stroke={MARK} strokeWidth="1" />
          ))}
          <path d="M8 16 H32 M8 24 H32" stroke={INK} strokeWidth="1.4" strokeLinecap="round" opacity="0.85" />
        </>
      );

    // Round a thing, facing it.
    case "inspect":
      return (
        <>
          <circle cx="20" cy="20" r="12" fill="none" stroke={INK} strokeWidth="1.6" strokeDasharray="5 3" />
          <rect x="16" y="16" width="8" height="8" rx="1.5" fill={MARK} />
          {[0, 90, 180, 270].map((angle) => {
            const a = (angle * Math.PI) / 180;
            return (
              <path key={angle}
                    d={`M${20 + 12 * Math.cos(a)} ${20 + 12 * Math.sin(a)} L${20 + 7 * Math.cos(a)} ${20 + 7 * Math.sin(a)}`}
                    stroke={INK} strokeWidth="1.1" opacity="0.75" />
            );
          })}
        </>
      );

    // Marks visited and held at.
    case "revisit":
      return (
        <>
          <path d="M8 30 L16 14 L30 22" fill="none" stroke={INK} strokeWidth="1.6"
                strokeLinejoin="round" strokeLinecap="round" />
          {[[8, 30], [16, 14], [30, 22]].map(([x, y], i) => (
            <g key={i}>
              <circle cx={x} cy={y} r="4.6" fill="none" stroke={MARK} strokeWidth="1.1"
                      strokeDasharray={i === 2 ? "2 2" : undefined} />
              <circle cx={x} cy={y} r="2" fill={MARK} />
            </g>
          ))}
        </>
      );

    // The cradle, and the line you come in on.
    case "dock":
      return (
        <>
          <path d="M6 20 H24" stroke={INK} strokeWidth="1.6" strokeLinecap="round" strokeDasharray="4 2.5" />
          <path d="M19 16 L24 20 L19 24" fill="none" stroke={INK} strokeWidth="1.6"
                strokeLinejoin="round" strokeLinecap="round" />
          <path d="M28 10 L34 10 L34 30 L28 30" fill="none" stroke={MARK} strokeWidth="1.8"
                strokeLinejoin="round" />
          <path d="M28 15 L31 15 M28 25 L31 25" stroke={MARK} strokeWidth="1.4" strokeLinecap="round" />
        </>
      );

    // Time passing on the station.
    case "wait":
      return (
        <>
          <circle cx="20" cy="20" r="11" fill="none" stroke={MARK} strokeWidth="1.5" />
          <path d="M20 13 V20 L25 23" fill="none" stroke={INK} strokeWidth="1.8"
                strokeLinecap="round" strokeLinejoin="round" />
        </>
      );

    // Several things, in order.
    case "mission":
      return (
        <>
          <path d="M8 20 H32" stroke={MARK} strokeWidth="1.2" strokeDasharray="3 2" opacity="0.7" />
          {[9, 17, 25, 33].map((x, i) => (
            <rect key={x} x={x - 3.4} y={i === 1 ? 12 : 16} width="6.8" height={i === 1 ? 16 : 8} rx="1.6"
                  fill={i < 2 ? INK : "none"} stroke={INK} strokeWidth="1.3" opacity={i < 2 ? 1 : 0.75} />
          ))}
        </>
      );

    // Home, and up.
    case "return":
      return (
        <>
          <path d="M6 8 H34" stroke={MARK} strokeWidth="1.4" strokeDasharray="3 2" />
          <path d="M28 30 Q 16 30 14 16" fill="none" stroke={INK} strokeWidth="1.7"
                strokeLinecap="round" />
          <path d="M10 20 L14 14 L18 20" fill="none" stroke={INK} strokeWidth="1.7"
                strokeLinejoin="round" strokeLinecap="round" />
          <circle cx="28" cy="30" r="2.6" fill={INK} />
        </>
      );

    // Nobody is judging: a hand on the keys.
    case "piloted":
    default:
      return (
        <>
          <rect x="7" y="14" width="26" height="14" rx="3" fill="none" stroke={INK} strokeWidth="1.5" />
          <rect x="11" y="18" width="5" height="5" rx="1" fill={INK} opacity="0.85" />
          <rect x="18" y="18" width="5" height="5" rx="1" fill={INK} opacity="0.5" />
          <rect x="25" y="18" width="5" height="5" rx="1" fill={INK} opacity="0.5" />
        </>
      );
  }
}
