// What you may go down in, and what we know the physics of.
//
// The platform's vehicles first: published, granted, flyable. Then the
// catalogue's, whose parameters have a source but which cannot be flown yet,
// each saying why. Every one opens onto a page that explains its physics.

import { CATALOGUE } from "../catalog/vehicles.js";
import type { Held, Packages } from "./Deck.js";
import { VehiclePlan } from "../parts/PlanArt.js";
import { useState } from "react";
import { Card, Empty } from "./parts.js";
import { Page } from "../ui/components.js";

export function Fleet({ held, packages, onOpen }: {
  held: Held;
  packages: Packages;
  onOpen: (of: { id?: string; slug?: string }) => void;
}): React.JSX.Element {
  const published = new Set(held.vehicles.map((v) => v.slug));
  const notYet = CATALOGUE.filter((v) => !published.has(v.slug));
  const [tab, setTab] = useState("flyable");
  return (
    <Page title="Fleet" subtitle="Vehicles, with the parameters they are flown by."
          info="The dynamics are the vehicle: mass, added mass, damping, and where each thruster points. Open one to see what its numbers mean. Catalogued vehicles have parameters with a published source; each says what stands between it and the water."
          tabs={[{ key: "flyable", label: "Flyable", count: held.vehicles.length }, { key: "catalogued", label: "Catalogued", count: notYet.length }]}
          tab={tab} onTab={setTab}>
      {tab === "flyable" ? (
        held.vehicles.length === 0 ? (
          <Empty title="Nothing granted yet">Vehicles appear here once your institution has been granted one.</Empty>
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
        )
      ) : notYet.length === 0 ? (
        <Empty title="Everything catalogued is published">The catalogue and the platform agree.</Empty>
      ) : (
        <div className="cards">
          {notYet.map((one) => (
            <Card key={one.slug} name={one.name} detail={one.summary}
                  art={<VehiclePlan thrusters={thrustersOf(one.dynamics)} size={64} />}
                  specs={[one.manufacturer, `${one.dynamics.massKg} kg`]}
                  later={one.notYet ?? "not published"}
                  onOpen={() => onOpen({ slug: one.slug })} />
          ))}
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
