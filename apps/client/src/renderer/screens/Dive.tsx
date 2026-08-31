// Going in.
//
// One screen, and the only one with a button that takes a machine. Everything
// it needs is chosen already where there was nothing to choose, so the ordinary
// case is: open the application, press Dive.

import { useState } from "react";

import type { AssetVersion, Platform } from "@coral-city/api";

import type { Held } from "./Deck.js";
import { Card, Empty, Fact, Pill, ago } from "./parts.js";

const WHERE = "coral-city.place";
const WHAT = "coral-city.vehicle";

/**
 * What to have chosen already: what you chose last time if it is still there,
 * or the only one if there is only one.
 *
 * Deliberately not "the first of several". Choosing one of many on somebody's
 * behalf and putting a button marked Dive under it is how a person ends up in
 * the wrong water without having chosen to be.
 */
function remembered<T extends { id: string }>(key: string, all: T[]): string | undefined {
  const last = localStorage.getItem(key);
  if (last !== null && all.some((one) => one.id === last)) return last;
  return all.length === 1 ? all[0]!.id : undefined;
}

export function Dive({ platform, held, free, devices, onDiving, onChanged }: {
  platform: Platform;
  held: Held;
  free: number;
  devices: number;
  onDiving: (dive: string, run: string) => void;
  onChanged: () => void;
}): React.JSX.Element {
  const [place, setPlace] = useState(() => remembered(WHERE, held.places));
  const [vehicle, setVehicle] = useState(() => remembered(WHAT, held.vehicles));
  const [asking, setAsking] = useState(false);
  const [refusal, setRefusal] = useState("");

  const chosenPlace = held.places.find((p) => p.id === place);
  const chosenVehicle = held.vehicles.find((v) => v.id === vehicle);
  const ready = chosenPlace !== undefined && chosenVehicle !== undefined;

  async function go(): Promise<void> {
    if (!ready || held.institution === undefined) return;
    setAsking(true);
    setRefusal("");
    try {
      // A dive is defined against the published version of each, because a run
      // pins bytes and not names: the reef you dived is the reef anybody can
      // dive again, even after somebody publishes a newer one.
      const [places, vehicles] = await Promise.all([
        platform.versionsOfPlace(chosenPlace.id),
        platform.versionsOfVehicle(chosenVehicle.id),
      ]);
      const newest = (all: AssetVersion[]): AssetVersion | undefined =>
        all.filter((v) => v.publishedAt).sort((a, b) =>
          (a.publishedAt! < b.publishedAt! ? 1 : -1))[0] ?? all[0];

      const onePlace = newest(places);
      const oneVehicle = newest(vehicles);
      if (onePlace === undefined || oneVehicle === undefined) {
        setRefusal("That place or vehicle has no published package yet.");
        return;
      }

      // Every dive names the water it happened in. Constructed water names no
      // instant on purpose: saying when would claim it was drawn from a
      // measurement of the ocean, and it was not.
      const water = await platform.defineConditions(held.institution.id, {
        kind: "constructed",
        name: "Still water",
        parameters: { currentMetresPerSecond: 0 },
      });

      const defined = await platform.defineDive(held.institution.id, {
        name: `${chosenVehicle.name} in ${chosenPlace.name}`,
        cityVersionId: onePlace.id,
        vehicleVersionId: oneVehicle.id,
        conditionsId: water.id,
      });

      const queue = held.queues[0];
      if (queue === undefined) {
        setRefusal("You have not been granted a queue to run this on.");
        return;
      }
      // The runtime comes from the hosts behind the queue, which say what they
      // can run every time they ask for work. This application cannot know what
      // is installed on a machine in a rack, so it does not guess.
      const runtime = queue.runtimes?.[0];
      if (runtime === undefined) {
        setRefusal("No machine on that queue has said what it can run yet.");
        return;
      }

      const run = await platform.ask(defined.id, {
        queueId: queue.id, mode: "interactive", runtimeVersion: runtime,
      });
      onChanged();
      onDiving(defined.id, run.id);
    } catch (problem) {
      setRefusal(problem instanceof Error ? problem.message : "that did not work");
    } finally {
      setAsking(false);
    }
  }

  const recent = held.runs.slice(0, 4);

  return (
    <>
      <section>
        <div className="hero">
          <div className="said">
            <div className="eyebrow">
              {ready ? "Ready to dive" : "Choose where, and what in"}
            </div>
            <h2>{chosenPlace?.name ?? "A place"}</h2>
            <p>{chosenPlace?.summary ?? "Pick somewhere below to go."}</p>
            <div className="facts">
              <Fact of="vehicle" is={chosenVehicle?.name ?? "—"} />
              <Fact of="water" is="still" />
              <Fact of="machines" is={`${free} free of ${devices}`} />
            </div>
          </div>
          <div className="act">
            <Pill kind={free > 0 ? "good" : "bad"}>
              {free > 0 ? "a machine is free" : "everything is busy"}
            </Pill>
            <button className="big" disabled={asking || !ready} onClick={() => void go()}>
              {asking ? "Asking for water…" : "Dive"}
            </button>
            <span className="refusal">{refusal}</span>
          </div>
        </div>
      </section>

      <section>
        <h2>Where</h2>
        <div className="cards">
          {held.places.map((one) => (
            <Card key={one.id} name={one.name} detail={one.summary || one.verticalDatum}
                  specs={[one.slug, one.verticalDatum]}
                  chosen={one.id === place}
                  onChoose={() => { setPlace(one.id); localStorage.setItem(WHERE, one.id); }} />
          ))}
        </div>
      </section>

      <section>
        <h2>What in</h2>
        <div className="cards">
          {held.vehicles.map((one) => (
            <Card key={one.id} name={one.name} detail={one.summary || "a vehicle"}
                  specs={[one.manufacturer || one.slug]}
                  chosen={one.id === vehicle}
                  onChoose={() => { setVehicle(one.id); localStorage.setItem(WHAT, one.id); }} />
          ))}
        </div>
      </section>

      <section>
        <h2>Lately</h2>
        {recent.length === 0 ? (
          <Empty title="No dives yet">
            What you run appears here, with what it did and how to watch it again.
          </Empty>
        ) : (
          <div className="ledger">
            {recent.map(({ run }) => (
              <div className="row" key={run.id}>
                <strong>{run.mode === "interactive" ? "Flown" : "Batch"}</strong>
                <span className="when">{ago(run.requestedAt)}</span>
                <Pill kind={run.state === "succeeded" ? "good"
                  : run.state === "running" || run.state === "preparing" ? "busy" : undefined}>
                  {run.state}
                </Pill>
              </div>
            ))}
          </div>
        )}
      </section>
    </>
  );
}
