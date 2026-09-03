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
