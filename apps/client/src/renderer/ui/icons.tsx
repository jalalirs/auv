// The editor's icons: one line drawing per tool and per kind of thing, on a
// 24-unit square, stroked in the text colour so they follow the theme.
//
// Drawn here rather than taken from an icon set, since most of what is in a
// world (a transponder, a nursery frame, a table coral) is in no icon set.

import React from "react";

const P = (d: string) => <path d={d} />;

const ICONS = {
  // Tools
  select: <>{P("M5 3l13 7.5-6 1.5-2.5 6z")}</>,
  move: <>{P("M12 3v18M3 12h18")}{P("M9 6l3-3 3 3M9 18l3 3 3-3M6 9l-3 3 3 3M18 9l3 3-3 3")}</>,
  rotate: <>{P("M20 12a8 8 0 1 1-2.6-5.9")}{P("M20 3v4.5h-4.5")}</>,
  scale: <>{P("M4 14v6h6")}{P("M4 20l7-7")}<rect x="12" y="4" width="8" height="8" rx="1" /></>,
  scatter: <><circle cx="7" cy="8" r="1.4" /><circle cx="13" cy="5" r="1.4" /><circle cx="17" cy="10" r="1.4" /><circle cx="10" cy="13" r="1.4" /><circle cx="16" cy="16" r="1.4" /><circle cx="6" cy="17" r="1.4" /><circle cx="12" cy="12" r="9" strokeDasharray="2 2.5" /></>,
  measure: <>{P("M3 17L17 3l4 4L7 21z")}{P("M7 13l2 2M10 10l2 2M13 7l2 2")}</>,
  undo: <>{P("M9 14L4 9l5-5")}{P("M4 9h10a6 6 0 0 1 0 12h-3")}</>,
  redo: <>{P("M15 14l5-5-5-5")}{P("M20 9H10a6 6 0 0 0 0 12h3")}</>,
  duplicate: <><rect x="8" y="8" width="12" height="12" rx="2" />{P("M16 8V5a1 1 0 0 0-1-1H5a1 1 0 0 0-1 1v10a1 1 0 0 0 1 1h3")}</>,
  delete: <>{P("M4 7h16M10 11v6M14 11v6")}{P("M6 7l1 13h10l1-13M9 7V4h6v3")}</>,
  frame: <>{P("M4 9V4h5M15 4h5v5M20 15v5h-5M9 20H4v-5")}<circle cx="12" cy="12" r="2.5" /></>,
  grid: <>{P("M4 4h16v16H4zM4 9.3h16M4 14.7h16M9.3 4v16M14.7 4v16")}</>,
  snap: <>{P("M6 4v8a6 6 0 0 0 12 0V4")}{P("M6 4h4v8a2 2 0 0 0 4 0V4h4")}{P("M6 8h4M14 8h4")}</>,
  viewTop: <>{P("M12 3l8 4.5v9L12 21l-8-4.5v-9z")}<path d="M12 3l8 4.5-8 4.5-8-4.5z" fill="currentColor" fillOpacity=".45" /></>,
  viewFront: <>{P("M12 3l8 4.5v9L12 21l-8-4.5v-9z")}<path d="M4 7.5l8 4.5v9l-8-4.5z" fill="currentColor" fillOpacity=".45" /></>,
  viewRight: <>{P("M12 3l8 4.5v9L12 21l-8-4.5v-9z")}<path d="M20 7.5L12 12v9l8-4.5z" fill="currentColor" fillOpacity=".45" /></>,
  viewPersp: <>{P("M12 3l8 4.5v9L12 21l-8-4.5v-9zM12 12v9M12 12l8-4.5M12 12L4 7.5")}</>,
  assets: <>{P("M3 7l9-4 9 4-9 4zM3 7v10l9 4 9-4V7M12 11v10")}</>,
  panelLeft: <><rect x="3" y="4" width="18" height="16" rx="2" />{P("M9 4v16")}</>,
  panelRight: <><rect x="3" y="4" width="18" height="16" rx="2" />{P("M15 4v16")}</>,
  panelBottom: <><rect x="3" y="4" width="18" height="16" rx="2" />{P("M3 15h18")}</>,
  search: <><circle cx="10.5" cy="10.5" r="6" />{P("M15 15l5 5")}</>,
  plus: <>{P("M12 5v14M5 12h14")}</>,
  chevron: <>{P("M9 6l6 6-6 6")}</>,
  eye: <>{P("M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12z")}<circle cx="12" cy="12" r="3" /></>,
  eyeOff: <>{P("M3 3l18 18M10.6 5.1A10 10 0 0 1 12 5c6.4 0 10 7 10 7a17 17 0 0 1-3 3.9M6.6 6.6A17 17 0 0 0 2 12s3.6 7 10 7a9.7 9.7 0 0 0 5.4-1.6")}{P("M9.9 9.9a3 3 0 0 0 4.2 4.2")}</>,
  lock: <><rect x="5" y="11" width="14" height="10" rx="2" />{P("M8 11V7a4 4 0 0 1 8 0v4")}</>,
  unlock: <><rect x="5" y="11" width="14" height="10" rx="2" />{P("M8 11V7a4 4 0 0 1 7.7-1.5")}</>,
  dive: <>{P("M6 4l13 8-13 8z")}</>,
  save: <>{P("M5 3h11l4 4v13a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1z")}{P("M8 3v5h7V3M7 21v-7h10v7")}</>,
  rename: <>{P("M4 20h4L19 9l-4-4L4 16z")}{P("M13.5 6.5l4 4")}</>,
  folder: <>{P("M3 6a1 1 0 0 1 1-1h5l2 2h9a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1z")}</>,

  // The world and its layers
  world: <><circle cx="12" cy="12" r="9" />{P("M3 12h18M12 3c3 3 3 15 0 18M12 3c-3 3-3 15 0 18")}</>,
  water: <>{P("M2 8c2.5-2 4.5-2 7 0s4.5 2 7 0 4.5-2 6 0M2 13c2.5-2 4.5-2 7 0s4.5 2 7 0 4.5-2 6 0M2 18c2.5-2 4.5-2 7 0s4.5 2 7 0 4.5-2 6 0")}</>,
  terrain: <>{P("M2 20l6-10 4 6 3-4 7 8z")}{P("M6.3 13l1.7 1.5 1.6-1.4")}</>,
  source: <>{P("M4 17l4-5 4 3 4-7 4 4")}{P("M4 21h16")}</>,
  seabed: <>{P("M2 16c3-2 6-2 10 0s7 2 10 0")}<circle cx="6" cy="20" r=".8" /><circle cx="11" cy="20.5" r=".8" /><circle cx="16" cy="20" r=".8" /><circle cx="20" cy="21" r=".8" /><circle cx="8" cy="11" r="1.3" /><circle cx="15" cy="10" r="2" /></>,
  swatch: <><rect x="5" y="5" width="14" height="14" rx="3" /></>,
  glass: <><ellipse cx="12" cy="5" rx="7" ry="2.5" />{P("M5 5v14c0 1.4 3.1 2.5 7 2.5s7-1.1 7-2.5V5")}{P("M8 9v8")}</>,
  hall: <>{P("M3 20h18M5 20V9l7-5 7 5v11")}{P("M9 20v-6h6v6")}</>,
  reef: <>{P("M12 21v-8M12 13L8 8M12 13l4-6M8 8L6 4M8 8l3-3M16 7l-1-4M16 7l3-2")}{P("M6 21h12")}</>,
  structures: <>{P("M4 21V10l8-6 8 6v11z")}{P("M9 21v-6h6v6")}</>,
  life: <>{P("M2 12c3-4 7-5 11-5 3 0 5 2 7 5-2 3-4 5-7 5-4 0-8-1-11-5z")}{P("M20 12l2-3v6z")}<circle cx="8" cy="11" r="1" /></>,
  fish: <>{P("M3 12c3-3.5 6.5-4.5 10-4.5 2.5 0 4.6 1.8 6 4.5-1.4 2.7-3.5 4.5-6 4.5-3.5 0-7-1-10-4.5z")}{P("M19 12l3-3v6z")}</>,
  shark: <>{P("M2 14c4-2 9-3 14-2l3-4v5l3 1-3 1v1c-6 1-12 0-17-2z")}{P("M10 12l2-5 2 5")}</>,
  missions: <>{P("M5 21V4M5 4h11l-2 3.5 2 3.5H5")}</>,
  mission: <><circle cx="5" cy="18" r="2" />{P("M7 17c4-2 2-8 6-9s5 4 6 0")}<circle cx="19" cy="6" r="2" /></>,
  colonies: <><circle cx="7" cy="16" r="3" /><circle cx="15" cy="15" r="4" /><circle cx="11" cy="8" r="3" /></>,

  // Coral, by form
  "coral-table": <>{P("M3 9c3-2 15-2 18 0-3 1.5-15 1.5-18 0z")}{P("M12 10.5V20M9 20h6")}</>,
  "coral-massive": <>{P("M3 20c0-6.5 4-11 9-11s9 4.5 9 11z")}{P("M8 15h1M13 13h1M15 17h1M10 18h1")}</>,
  "coral-brain": <>{P("M3 20c0-6.5 4-11 9-11s9 4.5 9 11z")}{P("M6 18c1-3 3-1 4-4s3-1 3-3M10 20c1-2 3-1 4-3s2-2 4-1")}</>,
  "coral-branching": <>{P("M12 21V12M12 12L7 6M12 12l5-7M9.5 9L6 9M15 8l3 1M12 16l-4-2M12 15l4-1")}</>,
  "coral-finger": <>{P("M6 20V10a1.5 1.5 0 0 1 3 0v10M10.5 20V7a1.5 1.5 0 0 1 3 0v13M15 20v-8a1.5 1.5 0 0 1 3 0v8")}{P("M4 20h16")}</>,
  "coral-plume": <>{P("M12 21C12 14 10 9 12 3c2 6 0 11 0 18z")}{P("M12 8l-3-2M12 12l-4-2M12 16l-3-1M12 9l3-2M12 13l4-2")}</>,
  "coral-fan": <>{P("M12 21V14M12 14C6 14 3 9 4 4c4 0 12 0 16 0 1 5-2 10-8 10z")}{P("M12 14V5M12 14L7 5M12 14l5-9")}</>,
  "coral-sponge": <>{P("M7 5h10l-1.5 15h-7z")}<ellipse cx="12" cy="5" rx="5" ry="1.5" /></>,
  "coral-encrusting": <>{P("M2 19c1-3 3-4 5-3 1-3 4-4 6-2 2-2 6-1 6 2 2 0 3 2 3 3z")}</>,
  coral: <>{P("M12 21V12M12 12L7 6M12 12l5-7M9.5 9L6 9M15 8l3 1")}</>,

  // Equipment
  transponder: <><rect x="9" y="11" width="6" height="10" rx="1" />{P("M12 11V6")}{P("M8 5a5.5 5.5 0 0 1 8 0M5.5 2.5a9 9 0 0 1 13 0")}</>,
  "mooring-block": <><rect x="4" y="12" width="16" height="9" rx="1" /><circle cx="12" cy="8.5" r="2.5" /></>,
  "nursery-frame": <>{P("M3 21L8 5h8l5 16M5.5 13h13M8 5v16M16 5v16")}</>,
  "marker-post": <>{P("M8 21V3")}{P("M8 4h10l-3 3 3 3H8")}{P("M5 21h6")}</>,
  ship: <>{P("M2 15h20l-3 5H5z")}{P("M6 15V10h9v5M9 10V6h4v4")}</>,
  buoy: <><circle cx="12" cy="15" r="5" />{P("M12 10V3M12 3l4 2-4 2M2 20c3-1.5 5-1.5 7 0s5 1.5 7 0 4-1.5 6 0")}</>,
  dredger: <>{P("M2 16h20l-3 5H5z")}{P("M5 16V11h8v5M13 12l7-7M20 5l1 6")}</>,
  "mooring-line": <>{P("M7 3c0 6 10 8 10 15")}<circle cx="7" cy="3" r="1.2" />{P("M14 20h6M17 18v4")}</>,
  pipeline: <>{P("M2 9h14a3 3 0 0 1 3 3v9M2 15h11a0 0 0 0 1 0 0v6")}{P("M5 9v6M9 9v6")}</>,
  "restoration-cell": <><rect x="4" y="4" width="16" height="16" strokeDasharray="3 2.4" /><circle cx="12" cy="12" r="2" /></>,
  object: <>{P("M12 3l8 4.5v9L12 21l-8-4.5v-9zM12 12v9M12 12l8-4.5M12 12L4 7.5")}</>,
  "video-reef": <><rect x="2" y="7" width="13" height="10" rx="2" />{P("M15 10l6-3v10l-6-3")}</>,
} as const;

export type IconName = keyof typeof ICONS;

export function hasIcon(name: string): name is IconName {
  return name in ICONS;
}

export function Icon({ name, size = 16, title }: { name: IconName | string; size?: number; title?: string }): React.JSX.Element {
  const drawn = hasIcon(name) ? ICONS[name] : ICONS.object;
  return (
    <svg className="icon" viewBox="0 0 24 24" width={size} height={size} fill="none" stroke="currentColor"
         strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden={title ? undefined : true}>
      {title ? <title>{title}</title> : null}
      {drawn}
    </svg>
  );
}
