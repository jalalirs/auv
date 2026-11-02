// What an object is, as a small line drawing: for a card with no picture yet,
// and for the tiles that choose what to add.

export type ObjectKind = "reef" | "pipeline" | "platform" | "wind-foundation" | "structure" | "survey" | "model" | "video"
  // Where a new place's ground comes from.
  | "store" | "earth" | "flat";

export function ObjectArt({ kind, size = 56 }: { kind: ObjectKind; size?: number }): React.JSX.Element {
  return (
    <svg className="object-art" width={size} height={size} viewBox="0 0 48 48" fill="none" stroke="currentColor"
         strokeWidth={1.6} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {DRAWN[kind]}
    </svg>
  );
}

const SEABED = <path d="M4 40c6-2 10 1 16-1s10-3 14-1 8 2 10 1" opacity={0.5} />;

const DRAWN: Record<ObjectKind, React.ReactNode> = {
  // Branching coral on the bottom.
  reef: <>
    {SEABED}
    <path d="M18 39V27l-5-6M18 30l5-5v-6M23 25l4-3M30 39v-9l4-5v-5M30 33l-4-4" />
    <circle cx="13" cy="20" r="1.2" /><circle cx="23" cy="18" r="1.2" /><circle cx="34" cy="19" r="1.2" />
  </>,
  // A line laid over the seabed, with its joints.
  pipeline: <>
    <path d="M4 36c8-1 12-8 20-8s12-8 20-9" strokeWidth={3} opacity={0.9} />
    <path d="M13 30.5v3M24 26.5v3M35 21.5v3" />
    {SEABED}
  </>,
  // A jacket: legs, braces, a deck above the surface.
  platform: <>
    <path d="M4 14h40" opacity={0.5} strokeDasharray="2 3" />
    <path d="M12 10h24v3H12zM15 13l-3 27M33 13l3 27M14 21h20M13 30h22M14 21l20 9M34 21l-20 9" />
    {SEABED}
  </>,
  // A tower on its foundation, three blades.
  "wind-foundation": <>
    <path d="M24 40V14M21 40h6M24 14l-9-6M24 14l10-4M24 14l-1 11" />
    <circle cx="24" cy="14" r="1.6" />
    <path d="M4 28h40" opacity={0.5} strokeDasharray="2 3" />
    {SEABED}
  </>,
  structure: <>
    <path d="M14 39V21l10-6 10 6v18M14 21l10 6 10-6M24 27v12" />
    {SEABED}
  </>,
  // Depth contours, as a survey draws them.
  survey: <>
    <path d="M6 30c6-8 14-14 22-12s14 8 14 14" />
    <path d="M12 32c4-5 9-9 15-8s10 5 10 9" />
    <path d="M18 34c3-3 6-5 10-4s5 3 5 5" />
    <path d="M6 40h36" opacity={0.5} />
  </>,
  // A cube: a model file.
  model: <path d="M24 8l14 8v16l-14 8-14-8V16zM10 16l14 8 14-8M24 24v16" />,
  // A camera: a dive video.
  video: <>
    <rect x="6" y="16" width="26" height="18" rx="3" />
    <path d="M32 22l10-5v16l-10-5" />
    <circle cx="19" cy="25" r="4" />
  </>,
  // A shop's box with a seabed in it: a place from the Store.
  store: <>
    <path d="M8 18h32v22H8zM8 18l4-8h24l4 8" />
    <path d="M12 34c4-2 7 0 11-1s8-2 13-1" opacity={0.6} />
  </>,
  // The globe: every public source that reaches the spot.
  earth: <>
    <circle cx="24" cy="24" r="16" />
    <path d="M8 24h32M24 8c-6 5-6 27 0 32M24 8c6 5 6 27 0 32" />
  </>,
  // A level seabed under level water: a designed one.
  flat: <>
    <path d="M6 14c3-2 6 2 9 0s6-2 9 0 6 2 9 0 6-2 9 0" opacity={0.6} />
    <path d="M6 36h36M6 40h36" />
    <path d="M24 18v14M20 28l4 4 4-4" opacity={0.6} />
  </>,
};
