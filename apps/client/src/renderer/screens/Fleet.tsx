// What you may go down in, and what we know the physics of.
//
// The platform's vehicles first: published, granted, flyable. Then the
// catalogue's, whose parameters have a source but which cannot be flown yet,
// each saying why. Every one opens onto a page that explains its physics.

import type { Held, Packages } from "./Deck.js";
import { VehiclePlan } from "../parts/PlanArt.js";
import { Card, Empty } from "./parts.js";
import { Page } from "../ui/components.js";

export function Fleet({ held, packages, onOpen, onStore }: {
  held: Held;
  packages: Packages;
  onOpen: (of: { id?: string; slug?: string }) => void;
  onStore?: () => void;
}): React.JSX.Element {
  return (
    <Page title="Vehicles" subtitle="Your fleet, with the parameters each is flown by."
          info="The dynamics are the vehicle: mass, added mass, damping, and where each thruster points. Open one to see what its numbers mean. Vehicles iOcean is still adding are in the Store.">
      {held.vehicles.length === 0 ? (
          <Empty title="No vehicles yet">Vehicles appear here once your organisation has one. <a onClick={onStore}>See the Store</a>.</Empty>
        ) : (
          <div className="cards">
            {held.vehicles.map((one) => {
              const pkg = packages.vehicles.get(one.id);
              return (
                <Card key={one.id} name={one.name} detail={one.summary || "a vehicle"}
                      picture={pkg?.pictureUrl}
                      art={<VehiclePlan thrusters={thrustersOf(pkg?.dynamics)} size={72} />}
                      specs={[one.manufacturer || "—",
                              pkg?.dynamics ? `${pkg.dynamics.massKg} kg · ${(pkg.dynamics.thrusters as { units?: unknown[] }).units?.length ?? 0} thrusters` : "",
                              pkg?.hull ? "hull" : pkg === null ? "no package" : ""].filter(Boolean)}
                      onOpen={() => onOpen({ id: one.id })} />
              );
            })}
          </div>
        )}
    </Page>
  );
}


/**
 * Where a catalogued vehicle's thrusters are, whichever way its package says
 * it. The platform's own dynamics carry a list; a package copied out of a
 * paper wraps them in `units` beside the note that describes the layout.
 */
function thrustersOf(dynamics: unknown): { position?: number[]; direction?: number[] }[] {
  const said = (dynamics ?? {}) as { thrusters?: unknown };
  const thrusters = said.thrusters as { units?: unknown[] } | unknown[] | undefined;
  if (Array.isArray(thrusters)) return thrusters as { position?: number[] }[];
  if (thrusters && Array.isArray(thrusters.units)) return thrusters.units as { position?: number[] }[];
  return [];
}
