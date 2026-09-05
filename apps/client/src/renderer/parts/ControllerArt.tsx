// A picture for whoever is flying: keys, or a fingerprint of the image.
//
// A controller has no face. What it has is a digest — the exact bytes the
// dive will pin — so that is what is drawn: a small symmetrical figure read
// out of the digest itself, in a colour taken from it. Two builds of the same
// controller look different, which is the truth about them, and the same build
// looks the same on every screen for ever, which is the other truth.
//
// A person at the keys is drawn as the keys.

/** The eight numbers a figure needs, from the front of a digest. */
function readOff(digest: string): number[] {
  const hex = digest.replace(/^sha256:/, "").replace(/[^0-9a-f]/gi, "");
  const numbers: number[] = [];
  for (let i = 0; i < 16; i += 1) {
    numbers.push(parseInt(hex.slice(i * 2, i * 2 + 2) || "0", 16) || 0);
  }
  return numbers;
}

export function ControllerArt({ digest, manual, size = 34 }: {
  /** The image digest the controller is pinned by. */
  digest?: string;
  /** A person at the keys rather than a program. */
  manual?: boolean;
  size?: number;
}): React.JSX.Element {
  if (manual || !digest) {
    return (
      <svg className="task-art" width={size} height={size} viewBox="0 0 40 40" aria-hidden="true">
        <rect x="0" y="0" width="40" height="40" rx="8" className="task-art-ground" />
        <rect x="7" y="13" width="26" height="15" rx="3" fill="none" stroke="#40c7f4" strokeWidth="1.5" />
        <rect x="11" y="17" width="5" height="5" rx="1" fill="#40c7f4" />
        <rect x="18" y="17" width="5" height="5" rx="1" fill="#40c7f4" opacity="0.45" />
        <rect x="25" y="17" width="5" height="5" rx="1" fill="#40c7f4" opacity="0.45" />
        <rect x="14" y="24" width="12" height="2.5" rx="1.2" fill="#40c7f4" opacity="0.6" />
      </svg>
    );
  }

  const numbers = readOff(digest);
  const hue = (numbers[0]! * 360) / 256;
  const ink = `hsl(${hue.toFixed(0)}, 62%, 62%)`;
  const faint = `hsl(${((hue + 40) % 360).toFixed(0)}, 55%, 46%)`;
  // Five rows of three, mirrored: the left half is read off the digest and the
  // right half is its reflection, which is what makes it a figure rather than
  // a rash of squares.
  const cells: React.JSX.Element[] = [];
  for (let row = 0; row < 5; row += 1) {
    for (let column = 0; column < 3; column += 1) {
      const value = numbers[row * 3 + column]!;
      if (value % 5 < 2) continue;
      const x = 6 + column * 7;
      const y = 6 + row * 6;
      const colour = value % 7 < 3 ? faint : ink;
      cells.push(<rect key={`${row}-${column}`} x={x} y={y} width="6" height="5" rx="1.4" fill={colour} />);
      if (column < 2) {
        cells.push(<rect key={`${row}-${column}-m`} x={34 - x - 6 + 6} y={y} width="6" height="5" rx="1.4"
                         fill={colour} />);
      }
    }
  }
  return (
    <svg className="task-art" width={size} height={size} viewBox="0 0 40 40" aria-hidden="true">
      <rect x="0" y="0" width="40" height="40" rx="8" className="task-art-ground" />
      {cells}
    </svg>
  );
}
