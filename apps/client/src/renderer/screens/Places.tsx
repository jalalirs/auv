// Where you may dive.
//
// Only what you have been granted appears — not filtered here, but simply not
// listed by the platform. An asset nobody granted you is indistinguishable from
// one that does not exist, which is deliberate, and it means this page never
// has to explain an absence.

import type { Held } from "./Deck.js";
import { Card, Empty, PageHead } from "./parts.js";

export function Places({ held }: { held: Held }): React.JSX.Element {
  return (
    <>
      <PageHead title="Places"
        says="Water we keep, versioned and granted. A dive pins the version it ran in, so the reef you dived is the reef anybody can dive again." />
      {held.places.length === 0 ? (
        <Empty title="Nothing granted yet">
          Places appear here once somebody grants your institution access to them.
        </Empty>
      ) : (
        <section>
          <div className="cards">
            {held.places.map((one) => (
              <Card key={one.id} name={one.name} detail={one.summary || "a place"}
                    specs={[one.slug, `datum: ${one.verticalDatum}`,
                            one.discoverable ? "listed" : "unlisted"]} />
            ))}
          </div>
        </section>
      )}
      <section>
        <h2>Coming</h2>
        <Empty title="Real reefs" soon="not built yet">
          Bathymetry and photogrammetry, so a place is somewhere that exists rather
          than a tank we had a scene for. The platform is built so this is a content
          pipeline and not a rewrite.
        </Empty>
      </section>
    </>
  );
}
