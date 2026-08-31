// What you may go down in.

import type { Held } from "./Deck.js";
import { Card, Empty, PageHead } from "./parts.js";

export function Fleet({ held }: { held: Held }): React.JSX.Element {
  return (
    <>
      <PageHead title="Fleet"
        says="Vehicles we publish, with the parameters they are flown by. The dynamics are the vehicle: mass, added mass, damping, and where each thruster points." />
      {held.vehicles.length === 0 ? (
        <Empty title="Nothing granted yet">
          Vehicles appear here once your institution has been granted one.
        </Empty>
      ) : (
        <section>
          <div className="cards">
            {held.vehicles.map((one) => (
              <Card key={one.id} name={one.name} detail={one.summary || "a vehicle"}
                    specs={[one.manufacturer || "—", one.slug]} />
            ))}
          </div>
        </section>
      )}
      <section>
        <h2>Coming</h2>
        <Empty title="Your own vehicle" soon="not built yet">
          Bring a hull and a set of parameters and fly it here. Today the vehicles
          are ours and the autonomy is yours; there is no reason the vehicle cannot
          be yours too, beyond the work of letting you publish one.
        </Empty>
      </section>
    </>
  );
}
