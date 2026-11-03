// Your worlds, as pictures: the first thing iOcean shows after Home. Choosing
// one goes into it. A new world starts from a terrain: a copy from the Store,
// your survey, public data, or a designed flat.

import type { Held, Packages } from "./Deck.js";
import { Page } from "../ui/components.js";
import { Empty } from "./parts.js";
import { WorldCard } from "../parts/Card.js";

export function Worlds({ held, packages, onOpen, onNew }: {
  held: Held;
  packages: Packages;
  onOpen: (place: string) => void;
  onNew: () => void;
}): React.JSX.Element {
  const worlds = held.yourPlaces;
  return (
    <Page title="Worlds" actions={<button className="primary" onClick={onNew}>New world</button>}>
      {worlds.length === 0 ? (
        <Empty title="No worlds yet">Make one from a terrain: a Store copy, your survey, public data or a designed flat.</Empty>
      ) : (
        <div className="cards">
          {worlds.map((city) => (
            <WorldCard key={city.id} place={city} packages={packages} held={held} onOpen={() => onOpen(city.id)} />
          ))}
        </div>
      )}
    </Page>
  );
}
