// The pieces every page shares.

import mark from "../../../assets/coral-city.svg";

export function Badge({ under }: { under?: string }): React.JSX.Element {
  return (
    <div className="badge">
      <img src={mark} alt="" />
      <div>
        <h1>Coral City</h1>
        {under === undefined ? null : <p>{under}</p>}
      </div>
    </div>
  );
}

/**
 * A card for a place or a vehicle.
 *
 * The picture is a real render of the thing itself, taken from its own package,
 * or nothing at all. A card with invented art on it would be a card that lies
 * about which reef you are about to dive.
 */
export function Card({ picture, name, detail, specs, chosen, onChoose }: {
  picture?: string;
  name: string;
  detail: string;
  specs?: string[];
  chosen?: boolean;
  onChoose?: () => void;
}): React.JSX.Element {
  return (
    <button className="card" aria-pressed={chosen} onClick={onChoose}
            disabled={onChoose === undefined}>
      <div className="picture">
        {picture === undefined ? "no picture yet" : <img src={picture} alt="" />}
      </div>
      <div className="said">
        <strong>{name}</strong>
        <span>{detail}</span>
        {specs === undefined ? null : (
          <div className="specs">{specs.map((s) => <span key={s}>{s}</span>)}</div>
        )}
      </div>
    </button>
  );
}

export function Fact({ of, is }: { of: string; is: string }): React.JSX.Element {
  return (
    <div className="fact">
      <span>{of}</span>
      <strong>{is}</strong>
    </div>
  );
}

export function Pill({ kind, children }: {
  kind?: "good" | "busy" | "bad";
  children: React.ReactNode;
}): React.JSX.Element {
  return <span className={kind ? `pill ${kind}` : "pill"}>{children}</span>;
}

/**
 * A place where something will be and is not.
 *
 * Said plainly, with what it will be and why it is not here yet. An empty panel
 * that explains itself is honest; one that shows invented content so the screen
 * looks finished is not, and it is the more tempting of the two.
 */
export function Empty({ title, children, soon }: {
  title: string;
  children: React.ReactNode;
  soon?: string;
}): React.JSX.Element {
  return (
    <div className="empty">
      <strong>{title}</strong>
      <p>{children}</p>
      {soon === undefined ? null : <span className="soon">{soon}</span>}
    </div>
  );
}

export function PageHead({ title, says }: {
  title: string;
  says: string;
}): React.JSX.Element {
  return (
    <div className="page-head">
      <h1>{title}</h1>
      <p>{says}</p>
    </div>
  );
}

/** How long ago, in words somebody would use. */
export function ago(when: string | undefined): string {
  if (when === undefined) return "";
  const seconds = Math.max(0, (Date.now() - Date.parse(when)) / 1000);
  if (seconds < 60) return "just now";
  if (seconds < 3600) return `${Math.round(seconds / 60)} min ago`;
  if (seconds < 86400) return `${Math.round(seconds / 3600)} h ago`;
  return `${Math.round(seconds / 86400)} d ago`;
}
