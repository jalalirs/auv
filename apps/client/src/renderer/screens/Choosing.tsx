// Where, and what in.
//
// Only what you have been granted appears. That is not a filter applied here —
// the platform simply does not list the rest, and an asset nobody granted you
// is indistinguishable from one that does not exist. So this screen shows
// everything it is given and never has to explain an absence.

import { useEffect, useState } from "react";

import type { AssetVersion, City, Platform, Queue, Vehicle } from "@coral-city/api";

import { Badge, Card } from "./parts.js";

const WHERE = "coral-city.place";
const WHAT = "coral-city.vehicle";

/**
 * What to have chosen already: what you chose last time if it is still there,
 * or the only one if there is only one.
 *
 * Deliberately not "the first of several". Picking one of many on somebody's
 * behalf and letting them press a button that says Dive is how a person ends up
 * in the wrong water without having chosen to be.
 */
function remembered<T extends { id: string }>(key: string, all: T[]): string | undefined {
  const last = localStorage.getItem(key);
  if (last !== null && all.some((one) => one.id === last)) return last;
  return all.length === 1 ? all[0]!.id : undefined;
}

interface Loaded {
  places: City[];
  vehicles: Vehicle[];
  queues: Queue[];
}

export function Choosing({ platform, onAsked }: {
  platform: Platform;
  onAsked: (dive: string, run: string) => void;
}): React.JSX.Element {
  const [loaded, setLoaded] = useState<Loaded | undefined>();
  const [place, setPlace] = useState<string | undefined>();
  const [vehicle, setVehicle] = useState<string | undefined>();
  const [asking, setAsking] = useState(false);
  const [refusal, setRefusal] = useState("");

  useEffect(() => {
    void (async () => {
      try {
        const [places, vehicles, queues] = await Promise.all([
          platform.places(), platform.vehicles(), platform.queues(),
        ]);
        setLoaded({ places, vehicles, queues });

        // Already chosen, where there is nothing to choose. One place and one
        // vehicle is not a decision, and presenting it as one makes somebody
        // click twice to say the only thing they could have said. What you
        // picked last time is remembered for when there is more than one.
        setPlace(remembered(WHERE, places));
        setVehicle(remembered(WHAT, vehicles));
      } catch (problem) {
        setRefusal(problem instanceof Error ? problem.message : "could not read the catalogue");
      }
    })();
  }, [platform]);

  async function dive(): Promise<void> {
    if (place === undefined || vehicle === undefined || loaded === undefined) return;
    setAsking(true);
    setRefusal("");
    try {
      // A dive is defined against the published version of each, because a run
      // pins bytes and not names: the reef you dived is the reef anybody can
      // dive again, even after somebody publishes a new one.
      const [placeVersions, vehicleVersions] = await Promise.all([
        platform.versionsOfPlace(place), platform.versionsOfVehicle(vehicle),
      ]);
      const newest = (versions: AssetVersion[]): AssetVersion | undefined =>
        versions.filter((v) => v.publishedAt !== undefined && v.publishedAt !== null)
          .sort((a, b) => (a.publishedAt! < b.publishedAt! ? 1 : -1))[0]
        ?? versions[0];

      const onePlace = newest(placeVersions);
      const oneVehicle = newest(vehicleVersions);
      if (onePlace === undefined || oneVehicle === undefined) {
        setRefusal("That place or vehicle has no published package yet.");
        return;
      }

      const institution = await platform.institution();
      if (institution === undefined) {
        setRefusal("You are not a member of an institution, so there is nowhere to keep a dive.");
        return;
      }
      // Every dive names the water it happened in, and the platform will not
      // accept one that does not. Still water, and constructed — which is a
      // claim about provenance, not a shrug: this water was invented, and
      // saying when it was drawn from would pretend it was measured.
      const water = await platform.defineConditions(institution.id, {
        kind: "constructed",
        name: "Still water",
        parameters: { currentMetresPerSecond: 0 },
      });

      const defined = await platform.defineDive(institution.id, {
        name: `${loaded.places.find((p) => p.id === place)?.name ?? "Dive"}`,
        cityVersionId: onePlace.id,
        vehicleVersionId: oneVehicle.id,
        conditionsId: water.id,
      });
      const queue = loaded.queues[0];
      if (queue === undefined) {
        setRefusal("You have not been granted a queue to run this on.");
        return;
      }

      // The runtime comes from the hosts behind the queue, which report what
      // they can run every time they ask for work. A run records it because a
      // physics fix changes results and comparing across one has to be refused
      // rather than done quietly — and this application cannot know what is
      // installed on a machine in a rack, so it does not guess.
      const runtime = queue.runtimes?.[0];
      if (runtime === undefined) {
        setRefusal("No machine on that queue has said what it can run yet.");
        return;
      }

      const run = await platform.ask(defined.id, {
        queueId: queue.id,
        mode: "interactive",
        runtimeVersion: runtime,
      });
      onAsked(defined.id, run.id);
    } catch (problem) {
      setRefusal(problem instanceof Error ? problem.message : "that did not work");
    } finally {
      setAsking(false);
    }
  }

  if (loaded === undefined) {
    return (
      <div className="middle">
        <Badge />
        <p className="note">{refusal || "Reading what you have been granted…"}</p>
      </div>
    );
  }

  const chosenPlace = loaded.places.find((p) => p.id === place);
  const chosenVehicle = loaded.vehicles.find((v) => v.id === vehicle);

  return (
    <div className="browse">
      <header>
        <Badge under="Choose where, and what to go in" />
      </header>

      <div className="rails">
        <section className="rail">
          <h2>Where</h2>
          <div className="cards">
            {loaded.places.map((one) => (
              <Card key={one.id} picture={undefined} name={one.name}
                    detail={one.summary || one.verticalDatum}
                    chosen={one.id === place}
                    onChoose={() => { setPlace(one.id); localStorage.setItem(WHERE, one.id); }} />
            ))}
          </div>
        </section>

        <section className="rail">
          <h2>What in</h2>
          <div className="cards">
            {loaded.vehicles.map((one) => (
              <Card key={one.id} picture={undefined} name={one.name}
                    detail={one.summary || "a vehicle"}
                    chosen={one.id === vehicle}
                    onChoose={() => { setVehicle(one.id); localStorage.setItem(WHAT, one.id); }} />
            ))}
          </div>
        </section>
      </div>

      <footer>
        <span className="note">
          {chosenPlace === undefined
            ? "Choose a place."
            : chosenVehicle === undefined
              ? `${chosenPlace.name} — now choose a vehicle.`
              : `${chosenVehicle.name} in ${chosenPlace.name}, still water.`}
        </span>
        <span className="refusal">{refusal}</span>
        <span className="spacer" />
        <button disabled={asking || place === undefined || vehicle === undefined}
                onClick={() => void dive()}>
          {asking ? "Asking for water…" : "Dive"}
        </button>
      </footer>
    </div>
  );
}
