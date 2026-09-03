// Choosing one of a few.
//
// A column with a label and a short list, one row chosen. Every row is whole:
// no truncation, no sideways scrolling, nothing hidden. A row carries its name,
// one line under it, a small picture when the thing has one, and whatever mark
// belongs beside it — today's water, a reason it cannot be chosen. Three of
// these side by side under the banner are the whole of choosing a dive.

export interface Choice {
  key: string;
  name: string;
  /** A line under the name: a depth range, a manufacturer, what a task asks. */
  says?: string;
  picture?: string;
  /** Something small at the row's end: a pill. */
  mark?: React.ReactNode;
  /** Shown, and not choosable, with the reason. */
  later?: string;
}

export function Picker({ label, choices, chosen, onChoose, onOpen, foot }: {
  label: string;
  choices: Choice[];
  chosen: string | undefined;
  onChoose: (key: string) => void;
  /** Open the chosen thing's own page. */
  onOpen?: (key: string) => void;
  /** A line under the list, about what is chosen. */
  foot?: React.ReactNode;
}): React.JSX.Element {
  return (
    <div className="picker" role="radiogroup" aria-label={label}>
      <h3>{label}</h3>
      <div className="options">
        {choices.map((one) => {
          const is = one.key === chosen;
          return (
            <button key={one.key} type="button" role="radio" aria-checked={is}
                    className={`option${is ? " chosen" : ""}${one.later ? " later" : ""}`}
                    disabled={one.later !== undefined}
                    onClick={() => onChoose(one.key)}>
              <span className="radio" aria-hidden="true" />
              {one.picture ? <img className="thumb" src={one.picture} alt="" loading="lazy" /> : null}
              <span className="option-said">
                <strong>{one.name}</strong>
                {one.later ? <em>{one.later}</em> : one.says ? <span>{one.says}</span> : null}
              </span>
              {one.mark}
              {is && onOpen ? (
                <a className="option-open" title="Open its page"
                   onClick={(e) => { e.stopPropagation(); onOpen(one.key); }}>›</a>
              ) : null}
            </button>
          );
        })}
      </div>
      {foot === undefined ? null : <div className="picker-foot">{foot}</div>}
    </div>
  );
}


/**
 * The same choice as a row: a label, a line of chips, and one line under it
 * about what is chosen. Five of these stacked read as a sentence — in this
 * place, with this vehicle, flown by this, in this water, for this — which is
 * what choosing a dive is, and it fits any number of choices without turning
 * the page into five columns of cards. Chips that cannot be chosen yet are
 * folded away behind a count, so the row stays about what can be.
 */
export function Row({ label, choices, chosen, onChoose, onOpen, foot }: {
  label: string;
  choices: Choice[];
  chosen: string | undefined;
  onChoose: (key: string) => void;
  onOpen?: (key: string) => void;
  foot?: React.ReactNode;
}): React.JSX.Element {
  const ready = choices.filter((c) => c.later === undefined);
  const later = choices.filter((c) => c.later !== undefined);
  const picked = choices.find((c) => c.key === chosen);
  return (
    <div className="row-choice" role="radiogroup" aria-label={label}>
      <h3>{label}</h3>
      <div className="chips">
        {ready.map((one) => {
          const is = one.key === chosen;
          return (
            <button key={one.key} type="button" role="radio" aria-checked={is}
                    className={`chip${is ? " chosen" : ""}`} onClick={() => onChoose(one.key)}>
              {one.picture ? <img src={one.picture} alt="" loading="lazy" /> : null}
              <span>{one.name}</span>
              {one.mark}
            </button>
          );
        })}
        {later.length > 0 ? (
          <span className="chip later" title={later.map((c) => `${c.name}: ${c.later}`).join("\n")}>
            {later.length} not ready
          </span>
        ) : null}
      </div>
      <div className="row-said">
        {picked ? (
          <>
            <span>{picked.says}</span>
            {onOpen ? <a className="option-open" onClick={() => onOpen(picked.key)}>open ›</a> : null}
          </>
        ) : <span className="none">nothing chosen</span>}
        {foot === undefined ? null : <div className="picker-foot">{foot}</div>}
      </div>
    </div>
  );
}
