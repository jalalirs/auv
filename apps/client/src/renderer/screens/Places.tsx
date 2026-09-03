// Where you may dive, and where you will be able to.
//
// Only what you have been granted appears — not filtered here, but simply not
// listed by the platform. An asset nobody granted you is indistinguishable from
// one that does not exist, which is deliberate, and it means this page never
// has to explain an absence.
//
// Under them, the places the platform is for and has not built. Shown as what
// they are — intentions, with what building each takes — so the shape of the
// product is visible before the whole of it exists.

import { ENVIRONMENTS } from "../catalog/environments.js";
import type { Held, Packages } from "./Deck.js";
import { PlaceCard } from "./Dive.js";
import { Card, Empty, PageHead } from "./parts.js";

export function Places({ held, packages, onOpen }: {
  held: Held;
  packages: Packages;
  onOpen: (id: string) => void;
}): React.JSX.Element {
  const slugs = new Set(held.places.map((p) => p.slug));
  return (
    <>
      <PageHead title="Places"
        says="Water we keep, versioned and granted. A dive pins the version it ran in, so the reef you dived is the reef anybody can dive again. Each place says what its sea is doing today, from the nearest monitoring site." />
      {held.places.length === 0 ? (
        <Empty title="Nothing granted yet">
          Places appear here once somebody grants your institution access to them.
        </Empty>
      ) : (
        <section>
          <div className="cards">
            {held.places.map((one) => (
              <PlaceCard key={one.id} place={one} packages={packages} onOpen={() => onOpen(one.id)} />
            ))}
          </div>
        </section>
      )}
      <section>
        <h2>The places this is for</h2>
        <div className="cards">
          {ENVIRONMENTS.map((one) => (
            <Card key={one.key} name={one.name} detail={`${one.where} · ${one.purpose}`}
                  specs={[one.standing, ...one.sources.slice(0, 1)]}
                  later={one.becomes !== undefined && slugs.has(one.becomes)
                    ? "grows from a place you have" : "not built yet"} />
          ))}
        </div>
        <p className="note">
          Each of these is real data first: a survey, a chart, a habitat map. What each takes is on its card; none is a scene somebody had lying around.
        </p>
      </section>
    </>
  );
}
