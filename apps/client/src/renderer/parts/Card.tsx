// A card for a place, a vehicle, or something that will be one.
//
// The picture is a real render of the thing itself, taken from its own package.
// A card with invented art on it would be a card that lies about which reef you
// are about to dive, so nothing here is ever a stock photograph of something
// similar — but a thing that has no package yet can still be drawn from what is
// actually known about it, its thrusters or its depth, and `art` is that.

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
}

export function Card({ picture, art, name, detail, specs, corner, chosen, onChoose, onOpen, later }: CardProps): React.JSX.Element {
  const usable = later === undefined;
  return (
    <div className={`card${chosen ? " chosen" : ""}${usable ? "" : " later"}`}
         role={onChoose ? "button" : undefined}
         aria-pressed={onChoose ? chosen : undefined}
         tabIndex={onChoose ? 0 : undefined}
         onClick={usable ? onChoose : undefined}
         onKeyDown={(e) => { if (usable && onChoose && (e.key === "Enter" || e.key === " ")) onChoose(); }}>
      <div className="picture">
        {picture !== undefined
          ? <img src={picture} alt="" loading="lazy" />
          : art !== undefined
            ? <div className="drawn">{art}{usable ? null : <span>{later}</span>}</div>
            : <span>{usable ? "no picture yet" : later}</span>}
        {corner === undefined ? null : <div className="corner">{corner}</div>}
        {chosen ? <div className="tick" aria-hidden="true">✓</div> : null}
      </div>
      <div className="said">
        <div className="title-row">
          <strong>{name}</strong>
          {onOpen === undefined ? null : (
            <a className="open" onClick={(e) => { e.stopPropagation(); onOpen(); }}>open ›</a>
          )}
        </div>
        <span>{detail}</span>
        {specs === undefined || specs.length === 0 ? null : (
          <div className="specs">{specs.map((s) => <span key={s}>{s}</span>)}</div>
        )}
      </div>
    </div>
  );
}
