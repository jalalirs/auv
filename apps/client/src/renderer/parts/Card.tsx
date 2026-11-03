// A card for a place, a vehicle, or something that will be one.
//
// The picture is a real render of the thing itself, taken from its own package.
// A card with invented art on it would be a card that lies about which reef you
// are about to dive, so nothing here is ever a stock photograph of something
// similar — but a thing that has no package yet can still be drawn from what is
// actually known about it, its thrusters or its depth, and `art` is that.

import { Skeleton } from "../ui/components.js";

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
            : <span>{usable ? "no picture yet" : later}</span>}
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
        <span>{detail}</span>
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
