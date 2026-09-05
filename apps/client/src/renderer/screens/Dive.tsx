// Going in.
//
// One screen, and the only one with a button that takes a machine. Everything
// a dive is — where, what in, what for — is chosen on one composer with the
// picture of the place behind it, so pressing Dive is a decision about
// something you can see, and nothing is chosen by scrolling past it. What
// needs no choosing is chosen already: what you chose last time if it is still
// there, or the only one if there is only one. Nothing else is on this page;
// what became of earlier dives is the Dives page's business.

import { useState } from "react";

import type { Platform } from "@coral-city/api";

import { PILOTED, TASKS, type Task, WATERS, type Water } from "../catalog/tasks.js";
import { alertKind, leadTemperature, useSea } from "../ocean/sea.js";
import { Line } from "../parts/Line.js";
import { ControllerArt } from "../parts/ControllerArt.js";
import { TaskArt } from "../parts/TaskArt.js";
import { WaterArt } from "../parts/WaterArt.js";
import type { Choice } from "../parts/Picker.js";
import { newestOf, whereIs } from "../platform/packages.js";
import type { Held, Packages, Where } from "./Deck.js";
import { Card, Credit, Fact, Pill, SeaPill, useLoadedPicture } from "./parts.js";

const WHERE = "coral-city.place";
const WHAT = "coral-city.vehicle";
const WHY = "coral-city.task";
const WHO = "coral-city.controller";
const HOW = "coral-city.water";

/** The controller a person is: keys, with the hold beneath them. */
const MANUAL = "manual";

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

export function Dive({ platform, held, packages, free, devices, onDiving, onChanged, onOpen }: {
  platform: Platform;
  held: Held;
  packages: Packages;
  free: number;
  devices: number;
  onDiving: (dive: string, run: string) => void;
  onChanged: () => void;
  onOpen: (where: Where) => void;
}): React.JSX.Element {
  const [place, setPlace] = useState(() => remembered(WHERE, held.places));
  const [vehicle, setVehicle] = useState(() => remembered(WHAT, held.vehicles));
  const [task, setTask] = useState<Task>(() =>
    TASKS.find((t) => t.key === localStorage.getItem(WHY)) ?? PILOTED);
  // Who flies it: you, or a stack the institution deployed. A stack that has
  // since gone falls back to you rather than to the wrong stack.
  const [flownBy, setFlownBy] = useState<string>(() => {
    const last = localStorage.getItem(WHO);
    return last !== null && held.stacks.some((s) => s.id === last) ? last : MANUAL;
  });
  const chosenStack = held.stacks.find((s) => s.id === flownBy);
  const [water, setWater] = useState<Water>(() =>
    WATERS.find((w) => w.key === localStorage.getItem(HOW)) ?? WATERS[0]!);
  const [asking, setAsking] = useState(false);
  const [refusal, setRefusal] = useState("");

  const chosenPlace = held.places.find((p) => p.id === place);
  const chosenVehicle = held.vehicles.find((v) => v.id === vehicle);
  const placePackage = chosenPlace === undefined ? undefined : packages.places.get(chosenPlace.id);
  const vehiclePackage = chosenVehicle === undefined ? undefined : packages.vehicles.get(chosenVehicle.id);
  const sea = useSea(chosenPlace === undefined ? undefined : whereIs(chosenPlace.extent, placePackage?.site));
  const ready = chosenPlace !== undefined && chosenVehicle !== undefined
    && placePackage !== null && vehiclePackage !== null;

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
      const onePlace = newestOf(places);
      const oneVehicle = newestOf(vehicles);
      if (onePlace === undefined || oneVehicle === undefined) {
        setRefusal("That place or vehicle has no published package yet.");
        return;
      }

      // Every dive names the water it happened in. Constructed water names no
      // instant on purpose: saying when would claim it was drawn from a
      // measurement of the ocean, and it was not.
      const conditions = await platform.defineConditions(held.institution.id, {
        kind: "constructed",
        name: water.name,
        parameters: water.parameters,
      });

      // What the dive is for goes with it, and the runtime judges it as the
      // dive runs; the name says so too, for anyone reading the record.
      const defined = await platform.defineDive(held.institution.id, {
        name: `${task.key === "piloted" ? "" : task.name + ": "}${chosenVehicle.name} in ${chosenPlace.name}`,
        cityVersionId: onePlace.id,
        vehicleVersionId: oneVehicle.id,
        conditionsId: conditions.id,
        objective: task.objective,
        autonomyStackId: chosenStack?.id,
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

  // ── what there is to choose from ─────────────────────────────────────────
  const places: Choice[] = held.places.map((one) => {
    const pkg = packages.places.get(one.id);
    const site = pkg?.site;
    return {
      key: one.id, name: one.name, picture: pkg?.pictureUrl,
      says: site?.deepestM !== undefined ? `${site.shallowestM?.toFixed(0) ?? "?"}–${site.deepestM.toFixed(0)} m`
        : one.summary?.split(".")[0],
      mark: <PlaceMark place={one} packages={packages} />,
      later: pkg === null ? "no package yet" : undefined,
    };
  });
  const vehicles: Choice[] = held.vehicles.map((one) => {
    const pkg = packages.vehicles.get(one.id);
    return {
      key: one.id, name: one.name, picture: pkg?.pictureUrl,
      says: [one.manufacturer, pkg?.dynamics ? `${pkg.dynamics.massKg} kg` : undefined].filter(Boolean).join(" · "),
      later: pkg === null ? "no package yet" : pkg !== undefined && pkg.hull === undefined ? "no hull yet" : undefined,
    };
  });
  const tasks: Choice[] = [PILOTED, ...TASKS].map((one) => ({
    key: one.key, name: one.name, later: one.unavailable,
    says: one.judgedOn.length > 0 ? `${one.asks} · judged on ${one.judgedOn.join(", ")}` : one.asks,
    // The shape of the thing it asks for, drawn: a task has a pattern, not a face.
    art: <TaskArt kind={(one.objective?.["kind"] as string) ?? one.key} />,
  }));
  const waters: Choice[] = WATERS.map((one) => ({
    key: one.key, name: one.name, says: one.says,
    // The water's own two numbers, drawn: where it runs and how far you see.
    art: <WaterArt speedMs={one.parameters.currentMetresPerSecond}
                   headingDeg={one.parameters.currentHeadingDeg}
                   visibilityM={one.parameters.visibilityM} />,
  }));
  // One row per controller, its newest build chosen; earlier builds stay on
  // the dives that pinned them and in the count.
  const controllers: Choice[] = [
    { key: MANUAL, name: "You, at the keys",
      says: "W A S D, Q E, space and C, or a gamepad; the hold has it whenever your hands are off",
      art: <ControllerArt manual /> },
    ...held.controllers.map(({ slug, name, newest, builds }) => {
      const needs = (newest.needs ?? {}) as { gpu?: boolean; gpuMemoryBytes?: number; cpu?: number; memoryBytes?: number };
      const gpu = needs.gpu || newest.wantsGpu
        ? `${needs.gpuMemoryBytes ? (needs.gpuMemoryBytes / 2 ** 30).toFixed(0) + " GiB of a card" : "a card"}`
        : "no card";
      return {
        key: newest.id, name, group: `deployed to ${held.institution?.name ?? "you"}`,
        says: `${slug} · ${newest.imageDigest.slice(7, 19)} · ${gpu}${builds.length > 1 ? ` · ${builds.length} builds, newest chosen` : ""}`,
        // A controller has no face; it has a digest. That is what is drawn.
        art: <ControllerArt digest={newest.imageDigest} />,
      };
    }),
  ];

  // ── what the chosen place says about itself ──────────────────────────────
  const site = placePackage?.site;
  const picture = useLoadedPicture(placePackage?.pictureUrl);
  const lead = sea.at === "known" ? leadTemperature(sea.record) : undefined;
  const alert = sea.at === "known" ? sea.record.now.alertLevel?.value : undefined;

  return (
    <>
      <section>
        <div className={`composer${picture ? " pictured" : ""}`}
             style={picture ? { backgroundImage: `url("${picture}")` } : undefined}>
          <div className="composer-top">
            <div className="said">
              <div className="eyebrow">
                {ready ? "Ready to dive" : chosenPlace === undefined ? "Choose where" : chosenVehicle === undefined ? "Choose what in" : "Not yet"}
              </div>
              <h2>{chosenPlace?.name ?? "Somewhere"}</h2>
              <p>{chosenPlace?.summary ?? "Choose a place below; its picture and its sea appear here."}</p>
              <div className="facts">
                {lead === undefined ? null : (
                  <Fact of={`water, ${lead.where}`} is={`${lead.value.toFixed(1)} °C`}
                        note={`by ${lead.source}, from ${sea.at === "known" ? sea.record.site.name : ""} on Aqualink`} />
                )}
                {alert === undefined ? null : (
                  <div className="fact"><span>heat stress</span>
                    <strong><Pill kind={alertKind(alert)}>{["none", "watch", "warning", "alert 1", "alert 2"][Math.max(0, Math.min(4, Math.round(alert)))]}</Pill></strong>
                  </div>
                )}
                {site?.deepestM === undefined ? null : (
                  <Fact of="depth" is={`${site.shallowestM?.toFixed(0) ?? "?"}–${site.deepestM.toFixed(0)} m`} />
                )}
                {site?.beginAt === undefined ? null : (
                  <Fact of="begins" is={`${(-site.beginAt[2]!).toFixed(1)} m down`} note={site.beginBecause} />
                )}
                {site?.reef?.colonies ? <Fact of="reef" is={`${site.reef.colonies.toLocaleString()} colonies`} note={site.reef.source} /> : null}
                <Fact of="machines" is={`${free} free of ${devices}`} />
              </div>
            </div>
            <div className="act">
              <Pill kind={free > 0 ? "good" : "bad"}>
                {free > 0 ? "a machine is free" : "everything is busy"}
              </Pill>
              <button className="big" disabled={asking || !ready || task.unavailable !== undefined} onClick={() => void go()}>
                {asking ? "Asking for water…" : "Dive"}
              </button>
              <span className="refusal">{refusal}</span>
            </div>
          </div>
          {placePackage?.credit && placePackage.credit.kind !== "render"
            ? <div className="composer-credit"><Credit of={placePackage.credit} /></div> : null}
        </div>

        <div className="plan">
          <Line label="Where" choices={places} chosen={place}
                onChoose={(key) => { setPlace(key); localStorage.setItem(WHERE, key); }}
                onOpen={(key) => onOpen({ page: "place", id: key })} />
          <Line label="In" choices={vehicles} chosen={vehicle}
                onChoose={(key) => { setVehicle(key); localStorage.setItem(WHAT, key); }}
                onOpen={(key) => onOpen({ page: "vehicle", id: key })} />
          <Line label="Flown by" choices={controllers} chosen={flownBy}
                onChoose={(key) => { setFlownBy(key); localStorage.setItem(WHO, key); }}
                onOpen={chosenStack === undefined ? undefined : () => onOpen({ page: "autonomy" })}
                hint={chosenStack === undefined ? undefined
                  : <>Your stack flies from the start; the keys still win while they are held.</>} />
          <Line label="Water" choices={waters} chosen={water.key}
                onChoose={(key) => { setWater(WATERS.find((w) => w.key === key)!); localStorage.setItem(HOW, key); }} />
          <Line label="For" choices={tasks} chosen={task.key}
                onChoose={(key) => { const t = [PILOTED, ...TASKS].find((x) => x.key === key)!; setTask(t); localStorage.setItem(WHY, key); }}
                hint={task.judgedOn.length > 0 ? <>The score is on the dive when it ends.</> : undefined} />
        </div>
      </section>
    </>
  );
}

/** The sea at a place, as the small mark on its row. */
function PlaceMark({ place, packages }: { place: Held["places"][number]; packages: Packages }): React.JSX.Element | null {
  const pkg = packages.places.get(place.id);
  const sea = useSea(whereIs(place.extent, pkg?.site));
  if (sea.at !== "known") return null;
  return <SeaPill sea={sea} />;
}

/** A place's card, with today's sea in its corner — for the places page. */
export function PlaceCard({ place, packages, chosen, onChoose, onOpen }: {
  place: Held["places"][number];
  packages: Packages;
  chosen?: boolean;
  onChoose?: () => void;
  onOpen?: () => void;
}): React.JSX.Element {
  const pkg = packages.places.get(place.id);
  const sea = useSea(whereIs(place.extent, pkg?.site));
  const site = pkg?.site;
  const specs = [
    site?.from?.surveyed === true ? "surveyed" : site?.from?.surveyed === false ? "constructed" : place.slug,
    site?.deepestM === undefined ? `datum: ${place.verticalDatum}` : `to ${site.deepestM.toFixed(0)} m`,
    site?.reef?.colonies ? `${site.reef.colonies.toLocaleString()} colonies` : "",
  ].filter(Boolean);
  return (
    <Card name={place.name} detail={place.summary || "a place"} picture={pkg?.pictureUrl}
          specs={specs} corner={<SeaPill sea={sea} />}
          chosen={chosen} onChoose={onChoose} onOpen={onOpen}
          later={pkg === null ? "no package yet" : undefined} />
  );
}
