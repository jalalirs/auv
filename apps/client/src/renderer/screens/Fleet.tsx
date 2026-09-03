// What you may go down in, and what we know the physics of.
//
// The platform's vehicles first: published, granted, flyable. Then the
// catalogue's, whose parameters have a source but which cannot be flown yet,
// each saying why. Every one opens onto a page that explains its physics.

import { CATALOGUE } from "../catalog/vehicles.js";
import type { Held, Packages } from "./Deck.js";
import { Card, Empty, PageHead } from "./parts.js";

export function Fleet({ held, packages, onOpen }: {
  held: Held;
  packages: Packages;
  onOpen: (of: { id?: string; slug?: string }) => void;
}): React.JSX.Element {
  const published = new Set(held.vehicles.map((v) => v.slug));
  const notYet = CATALOGUE.filter((v) => !published.has(v.slug));
  return (
    <>
      <PageHead title="Fleet"
        says="Vehicles we publish, with the parameters they are flown by. The dynamics are the vehicle: mass, added mass, damping, and where each thruster points. Open one to see what its numbers mean." />
      {held.vehicles.length === 0 ? (
        <Empty title="Nothing granted yet">
          Vehicles appear here once your institution has been granted one.
        </Empty>
      ) : (
        <section>
          <div className="cards">
            {held.vehicles.map((one) => {
              const pkg = packages.vehicles.get(one.id);
              return (
                <Card key={one.id} name={one.name} detail={one.summary || "a vehicle"}
                      picture={pkg?.pictureUrl}
                      specs={[one.manufacturer || "—",
                              pkg?.dynamics ? `${pkg.dynamics.massKg} kg · ${(pkg.dynamics.thrusters as { units?: unknown[] }).units?.length ?? 0} thrusters` : "",
                              pkg?.hull ? "hull" : pkg === null ? "no package" : ""].filter(Boolean)}
                      onOpen={() => onOpen({ id: one.id })} />
              );
            })}
          </div>
        </section>
      )}
      <section>
        <h2>Catalogued, not yet flyable</h2>
        {notYet.length === 0 ? (
          <Empty title="Everything catalogued is published">The catalogue and the platform agree.</Empty>
        ) : (
          <div className="cards">
            {notYet.map((one) => (
              <Card key={one.slug} name={one.name} detail={one.summary}
                    specs={[one.manufacturer, `${one.dynamics.massKg} kg`]}
                    later={one.notYet ?? "not published"}
                    onOpen={() => onOpen({ slug: one.slug })} />
            ))}
          </div>
        )}
        <p className="note">
          Parameters with a published source, so their physics can be read and compared. Each says what stands between it and the water.
        </p>
      </section>
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
