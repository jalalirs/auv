// The pieces every screen shares.

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
export function Card({ picture, name, detail, chosen, onChoose }: {
  picture: string | undefined;
  name: string;
  detail: string;
  chosen: boolean;
  onChoose: () => void;
}): React.JSX.Element {
  return (
    <button className="card" aria-pressed={chosen} onClick={onChoose}>
      <div className="picture">
        {picture === undefined
          ? "no picture yet"
          : <img src={picture} alt="" />}
      </div>
      <div className="said">
        <strong>{name}</strong>
        <span>{detail}</span>
      </div>
    </button>
  );
}
