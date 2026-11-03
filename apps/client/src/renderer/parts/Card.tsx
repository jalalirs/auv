// A card for a place, a vehicle, or something that will be one.
//
// The picture is a real render of the thing itself, taken from its own package.
// A card with invented art on it would be a card that lies about which reef you
// are about to dive, so nothing here is ever a stock photograph of something
// similar — but a thing that has no package yet can still be drawn from what is
// actually known about it, its thrusters or its depth, and `art` is that. A
// card with neither still has a picture: a small chart glyph, never a grey box
// saying there is no picture.
//
// A card says one line under its name. Whatever it is given is cut to its
// first sentence and has the platform's own ids taken out ("built from the
// place city_01M2E…"), because a person reads a name, not a key.

import type { City } from "@coral-city/api";

import type { Held, Packages } from "../platform/held.js";
import { usePlacePicture } from "./Relief.js";
import { Skeleton, Status } from "../ui/components.js";

export interface CardProps {
  picture?: string;
  /** Drawn from the thing's own numbers, for one that has no package yet. */
  art?: React.ReactNode;
  name: string;
  detail: string;
  specs?: string[];
  /** Something to say over the picture's corner: today's water, a state. */
  corner?: React.ReactNode;
  chosen?: boolean;
  onChoose?: () => void;
  /** Open the thing's own page, as distinct from choosing it. */
  onOpen?: () => void;
  /** Not built, not granted, not flyable: shown, and unmistakably not usable. */
  later?: string;
  /** The picture is still being read or drawn: a placeholder holds its place. */
  reading?: boolean;
  /** What can be done with it, along the card's foot: buttons, a menu. */
  actions?: React.ReactNode;
}

export function Card({ picture, art, name, detail, specs, corner, chosen, onChoose, onOpen, later, reading, actions }: CardProps): React.JSX.Element {
  const usable = later === undefined;
  const line = cleanLine(detail);
  // A card opens when it is clicked. One that is chosen when clicked, in a
  // picker, still opens from a small mark over its picture's corner.
  const opens = onChoose === undefined ? onOpen : undefined;
  const press = onChoose ?? opens;
  return (
    <div className={`card${chosen ? " chosen" : ""}${usable ? "" : " later"}${opens ? " opens" : ""}`}
         role={press ? "button" : undefined}
         aria-pressed={onChoose ? chosen : undefined}
         tabIndex={press ? 0 : undefined}
         onClick={usable || opens ? press : undefined}
         onKeyDown={(e) => { if ((usable || opens) && press && (e.key === "Enter" || e.key === " ")) press(); }}>
      <div className="picture">
        {reading
          ? <Skeleton className="cover" />
          : picture !== undefined
          ? <img src={picture} alt="" loading="lazy" />
          : art !== undefined
            ? <div className="drawn">{art}{usable ? null : <span>{later}</span>}</div>
            : <div className="drawn"><Glyph seed={name} />{usable ? null : <span>{later}</span>}</div>}
        {corner === undefined ? null : <div className="corner">{corner}</div>}
        {chosen ? <div className="tick" aria-hidden="true">✓</div> : null}
        {onOpen !== undefined && onChoose !== undefined ? (
          <button type="button" className="open-mark" aria-label={`Open ${name}`} title={`Open ${name}`}
                  onClick={(e) => { e.stopPropagation(); onOpen(); }}>
            <svg width="14" height="14" viewBox="0 0 16 16" aria-hidden="true"><path d="M6 3h7v7M13 3 4 12" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" /></svg>
          </button>
        ) : null}
      </div>
      <div className="said">
        <strong>{name}</strong>
        {line ? <span title={line}>{line}</span> : null}
        {specs === undefined || specs.length === 0 ? null : (
          <div className="specs">{specs.map((s) => <span key={s}>{s}</span>)}</div>
        )}
      </div>
      {actions === undefined ? null : (
        <div className="foot" onClick={(e) => e.stopPropagation()}>{actions}</div>
      )}
    </div>
  );
}

/** Platform ids as they leak into summaries: "city_01M2E…", a ULID, a UUID. */
const IDS = /\b[a-z]{2,16}_[0-9A-Za-z]{12,}\b|\b[0-9A-HJKMNP-TV-Z]{26}\b|\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b/g;

/** A card's one line: the first sentence, with no ids in it and nothing an id left dangling. */
export function cleanLine(said: string | undefined): string {
  if (!said) return "";
  let line = said
    // "built from the place city_01M…" says nothing once the id is gone.
    .replace(/\b(?:built|made|copied|taken|derived)?\s*(?:from|of|on)\s+(?:the\s+)?(?:place|asset|object|version|city|world)\s+(?:\b[a-z]{2,16}_[0-9A-Za-z]{12,}\b|\b[0-9A-HJKMNP-TV-Z]{26}\b|\b[0-9a-f-]{36}\b)/gi, "")
    .replace(IDS, "");
  const cut = line.search(/[.;:](\s|$)/);
  if (cut > 0) line = line.slice(0, cut);
  return line.replace(/\(\s*\)/g, "").replace(/\s+([,·])/g, "$1").replace(/([,·])(?:\s*[,·])+/g, "$1")
    .replace(/^[\s,·–-]+|[\s,·–-]+$/g, "").replace(/\s{2,}/g, " ");
}

/** A picture for a card that has none: depth contours round a seabed, its
 *  shape turned by the name so two cards side by side are not one image. */
export function Glyph({ seed, size = 108 }: { seed: string; size?: number }): React.JSX.Element {
  let h = 2166136261;
  for (let i = 0; i < seed.length; i++) h = Math.imul(h ^ seed.charCodeAt(i), 16777619);
  const turn = (h >>> 0) % 360;
  const lean = 0.72 + ((h >>> 9) % 20) / 100;
  const rings = [30, 22, 14, 7];
  return (
    <svg className="task-art glyph" width={size} height={size} viewBox="0 0 80 80" aria-hidden="true">
      <rect x="0" y="0" width="80" height="80" rx="12" fill="#d6ebf3" />
      <g transform={`rotate(${turn} 40 40)`}>
        {rings.map((r, i) => (
          <ellipse key={r} cx={40 + i * 2} cy={40 - i} rx={r} ry={r * lean}
                   fill={["#a9d3e8", "#6fa9d0", "#3a74ad", "#1c4680"][i]} stroke="#10305c" strokeOpacity="0.35" strokeWidth="0.8" />
        ))}
      </g>
    </svg>
  );
}

/** How deep a place goes, as its package's site says: "2–18 m", "to 18 m". */
export function depthSaid(site: { shallowestM?: number; deepestM?: number } | undefined): string {
  if (site?.deepestM === undefined) return "";
  const deep = site.deepestM.toFixed(0);
  return site.shallowestM !== undefined && site.shallowestM > 0.05 && site.shallowestM < site.deepestM
    ? `${site.shallowestM.toFixed(0)}–${deep} m` : `to ${deep} m`;
}

/** What the ground of a place is: measured, derived from imagery, or made up. */
export function standingOf(place: City, site: { from?: { surveyed?: boolean } } | undefined): string {
  // A composed place has no extent: zero on every side means nobody could say where it is.
  const somewhere = place.extent !== undefined
    && (place.extent.west !== 0 || place.extent.east !== 0 || place.extent.north !== 0 || place.extent.south !== 0);
  return site?.from?.surveyed === true ? "surveyed"
    : site?.from?.surveyed === false ? (somewhere ? "derived depths" : "composed") : "";
}

/** One of your worlds as a card: its picture (photograph or charted seabed),
 *  its name, and one line of depth and state. */
export function WorldCard({ place, packages, held, onOpen, actions }: {
  place: City;
  packages: Packages;
  /** To say when a dive is flying in it now. */
  held?: Held;
  onOpen?: () => void;
  actions?: React.ReactNode;
}): React.JSX.Element {
  const pkg = packages.places.get(place.id);
  const picture = usePlacePicture(pkg);
  const site = pkg?.site;
  const diving = held !== undefined && pkg?.version !== undefined
    && held.runs.some((r) => r.placeVersion === pkg.version.id && (r.run.state === "running" || r.run.state === "preparing"));
  const line = [depthSaid(site), standingOf(place, site) || (pkg === null ? "not published" : "")].filter(Boolean).join(" · ");
  return (
    <Card name={place.name} detail={line || "a world"} picture={picture ?? undefined}
          reading={picture === undefined && pkg !== null}
          corner={diving ? <Status tone="busy">diving now</Status> : undefined}
          onOpen={onOpen} actions={actions} />
  );
}
