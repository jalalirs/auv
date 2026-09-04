// Which way the world is pointing, in the corner of the picture.
//
// The same set of axes every 3D tool puts in the bottom right, and for the
// same reason: a picture of water tells you nothing about which way you are
// facing. It is drawn from the camera's own basis, sent by the dive rather
// than guessed here, so it is right in every view — behind the vehicle,
// through its nose, or straight down.
//
// The convention is stated rather than assumed: x east, y north, z up, which
// is the frame the vehicle's position, heading and depth are all in. A place
// may be authored Y up in centimetres; that is the file's business and not
// the water's.

export interface Basis { right: number[]; up: number[]; forward: number[] }

export function Axes({ basis, upAxis }: { basis: Basis | undefined; upAxis?: string }): React.JSX.Element | null {
  if (basis === undefined) return null;
  const size = 34;
  const middle = size + 10;
  const box = middle * 2;

  // An axis falls on the screen where it lands on the camera's right and up.
  const flat = (axis: number[]): { x: number; y: number; towards: number } => ({
    x: middle + dot(axis, basis.right) * size,
    y: middle - dot(axis, basis.up) * size,
    towards: dot(axis, basis.forward),
  });

  const drawn = [
    { name: "X", axis: [1, 0, 0], ink: "#ff6b6b", ...flat([1, 0, 0]) },
    { name: "Y", axis: [0, 1, 0], ink: "#7bd88f", ...flat([0, 1, 0]) },
    { name: "Z", axis: [0, 0, 1], ink: "#5aa9ff", ...flat([0, 0, 1]) },
  // `towards` is how much an axis runs along the way the camera looks, so a
  // positive one points away from the viewer: drawn first, and dimmed.
  ].sort((a, b) => b.towards - a.towards);

  return (
    <div className="axes" title={`x east, y north, ${upAxis === "Y" ? "y" : "z"} up`}>
      <svg viewBox={`0 0 ${box} ${box}`} width={box} height={box} aria-hidden="true">
        <circle cx={middle} cy={middle} r={size + 6} className="axes-face" />
        {drawn.map((one) => (
          <g key={one.name} opacity={one.towards > 0.55 ? 0.4 : 1}>
            <line x1={middle} y1={middle} x2={one.x} y2={one.y} stroke={one.ink} strokeWidth={2} strokeLinecap="round" />
            <circle cx={one.x} cy={one.y} r={7} fill={one.ink} />
            <text x={one.x} y={one.y + 3.4} textAnchor="middle" className="axes-label">{one.name}</text>
          </g>
        ))}
      </svg>
      <span className="axes-said">{upAxis === "Y" ? "y" : "z"} up</span>
    </div>
  );
}

function dot(a: number[], b: number[]): number {
  return (a[0] ?? 0) * (b[0] ?? 0) + (a[1] ?? 0) * (b[1] ?? 0) + (a[2] ?? 0) * (b[2] ?? 0);
}
