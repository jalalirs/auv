// One vehicle, and what its numbers mean.
//
// The parameters are the vehicle. This page reads them the way the runner
// does and says what follows: whether it floats, how fast it can go on each
// axis before drag matches thrust, how much it can turn, where every thruster
// is and which way it pushes. Three of the numbers can be changed on the page
// to see what a heavier battery or a bigger thruster does; nothing typed here
// is saved — a change to a vehicle is a version, and publishing one is not
// this page's job yet.

import { useMemo, useState } from "react";

import type { VehicleDynamics } from "@coral-city/api";

import { catalogued } from "../catalog/vehicles.js";
import type { PictureCredit } from "../platform/packages.js";
import { AXES, derive, thrustersOf, withNumber, withThrust } from "../physics/dynamics.js";
import type { Held, Packages } from "./Deck.js";
import { Credit, Empty, PageHead, Pill, Row, ThrusterDiagram, fixed, useLoadedPicture } from "./parts.js";

const UNITS: Record<(typeof AXES)[number], string> = {
  surge: "m/s", sway: "m/s", heave: "m/s", roll: "rad/s", pitch: "rad/s", yaw: "rad/s",
};

export function VehicleDetail({ held, packages, id, slug, onBack }: {
  held: Held;
  packages: Packages;
  id?: string;
  slug?: string;
  onBack: () => void;
}): React.JSX.Element {
  const vehicle = id === undefined ? undefined : held.vehicles.find((v) => v.id === id);
  const pkg = vehicle === undefined ? undefined : packages.vehicles.get(vehicle.id);
  const listed = catalogued(slug ?? vehicle?.slug ?? "");
  const name = vehicle?.name ?? listed?.name ?? "A vehicle";
  const summary = vehicle?.summary ?? listed?.summary ?? "";
  const dynamics: VehicleDynamics | undefined = pkg?.dynamics ?? listed?.dynamics;

  if (dynamics === undefined) {
    return (
      <>
        <PageHead title={name} says={summary} back="Fleet" onBack={onBack} />
        {pkg === undefined && vehicle !== undefined
          ? <p className="note">Reading the package…</p>
          : <Empty title="No dynamics">This vehicle's package states no dynamics, so it cannot be flown and there is nothing to explain.</Empty>}
      </>
    );
  }
  return <Explained name={name} summary={summary} dynamics={dynamics}
                    picture={pkg?.pictureUrl} credit={pkg?.credit} source={listed?.source}
                    flyable={vehicle !== undefined && pkg?.hull !== undefined}
                    notYet={vehicle === undefined ? (listed?.notYet ?? "not published") : pkg?.hull === undefined ? "no hull in the package" : undefined}
                    version={pkg?.version.ordinal} onBack={onBack} />;
}

function Explained({ name, summary, dynamics, picture, credit, source, flyable, notYet, version, onBack }: {
  name: string;
  summary: string;
  dynamics: VehicleDynamics;
  picture: string | undefined;
  credit: PictureCredit | undefined;
  source: string | undefined;
  flyable: boolean;
  notYet: string | undefined;
  version: number | undefined;
  onBack: () => void;
}): React.JSX.Element {
  const base = thrustersOf(dynamics);
  const shown = useLoadedPicture(picture);
  const [massKg, setMass] = useState(dynamics.massKg);
  const [volume, setVolume] = useState(dynamics.displacedVolumeM3);
  const [forwardN, setForward] = useState(base.maxForwardN);
  const [reverseN, setReverse] = useState(base.maxReverseN);
  const changed = massKg !== dynamics.massKg || volume !== dynamics.displacedVolumeM3
    || forwardN !== base.maxForwardN || reverseN !== base.maxReverseN;

  const tried = useMemo(() =>
    withThrust(withNumber(withNumber(dynamics, "massKg", massKg), "displacedVolumeM3", volume), forwardN, reverseN),
    [dynamics, massKg, volume, forwardN, reverseN]);
  const now = useMemo(() => derive(tried), [tried]);
  const was = useMemo(() => derive(dynamics), [dynamics]);
  // The contract carries these blocks as opaque objects on purpose: their
  // shape belongs to the runtime that reads them. Read here as the catalogue writes them.
  const sensors = (dynamics.sensors as unknown as Array<{ kind: string; name: string }>) ?? [];
  const contract = dynamics.topicContract as unknown as { publishes?: { topic: string; type: string }[]; subscribes?: { topic: string; type: string }[] };

  return (
    <>
      <PageHead title={name} says={summary} back="Fleet" onBack={onBack}
                aside={<Pill kind={flyable ? "good" : undefined}>{flyable ? "flyable" : notYet}</Pill>} />

      <div className="two">
        <section>
          <div className={`hero tall${shown ? " pictured" : ""}`}
               style={shown ? { backgroundImage: `url("${shown}")` } : undefined}>
            <div className="said">{shown ? null : <div className="eyebrow">no picture yet</div>}</div>
          </div>
          <Credit of={credit} />
          <h2 style={{ marginTop: 22 }}>Thrusters</h2>
          <ThrusterDiagram units={now.thrusters.units} reachM={now.reachM} />
          <p className="note">
            {now.thrusters.units.length} × {now.thrusters.model ?? "thruster"}, {fixed(forwardN, 0, " N")} ahead and {fixed(reverseN, 0, " N")} astern each
            {now.thrusters.timeConstantS ? `, spooling in ${now.thrusters.timeConstantS} s` : ""}.
          </p>
        </section>

        <section>
          <h2>How it sits</h2>
          <div className="kvs">
            <Row of="mass" is={<Try value={massKg} unit="kg" step={0.1} onChange={setMass} />} />
            <Row of="displaces" is={<Try value={volume} unit="m³" step={0.0001} digits={4} onChange={setVolume} />} />
            <Row of="weighs" is={fixed(now.buoyancy.weightN, 1, " N")} />
            <Row of="buoyancy" is={fixed(now.buoyancy.buoyancyN, 1, " N")} note="Seawater at 1025 kg/m³" />
            <Row of="so it" is={
              <span className={now.buoyancy.sits === "sinks" ? "warn" : ""}>
                {now.buoyancy.sits} by {fixed(Math.abs(now.buoyancy.netN), 1, " N")} ({fixed(Math.abs(now.buoyancy.netKg) * 1000, 0, " g")})
              </span>}
              note="A survey ROV is trimmed slightly buoyant, so that a dead vehicle comes up" />
            <Row of="righting arm" is={fixed(now.buoyancy.rightingArmM * 100, 1, " cm")}
                 note="The centre of buoyancy above the centre of gravity. Zero would mean no restoring moment at all." />
            <Row of="thrust each" is={
              <span>
                <Try value={forwardN} unit="N ahead" step={0.5} onChange={setForward} />{" "}
                <Try value={reverseN} unit="N astern" step={0.5} onChange={setReverse} />
              </span>} />
          </div>
          {changed ? (
            <p className="note">
              You are looking at what these numbers would do. Nothing is saved; a change to a vehicle is a new version.{" "}
              <a onClick={() => { setMass(dynamics.massKg); setVolume(dynamics.displacedVolumeM3); setForward(base.maxForwardN); setReverse(base.maxReverseN); }}>Put them back.</a>
            </p>
          ) : null}

          <h2 style={{ marginTop: 22 }}>On each axis</h2>
          <table className="axes">
            <thead>
              <tr><th>axis</th><th>authority</th><th>effective mass</th><th>drag</th><th>top speed</th></tr>
            </thead>
            <tbody>
              {AXES.map((axis, k) => {
                const a = now.authority[k]!, s = now.speeds[k]!, before = was.speeds[k]!;
                const unitN = k < 3 ? "N" : "N·m";
                const massUnit = k < 3 ? "kg" : "kg·m²";
                return (
                  <tr key={axis}>
                    <th>{axis}</th>
                    <td>{a.contributors === 0 ? <em>none</em> : `${fixed(a.positive, 0)} / ${fixed(a.negative, 0)} ${unitN}`}</td>
                    <td>{fixed(s.effectiveMass, k < 3 ? 1 : 2, ` ${massUnit}`)}</td>
                    <td title="linear, quadratic">{fixed(Math.abs(s.linear), 1)}, {fixed(Math.abs(s.quadratic), 1)}</td>
                    <td>
                      {a.contributors === 0 ? "—"
                        : `${fixed(s.positive, 2)} ${UNITS[axis]}`}
                      {a.contributors > 0 && Math.abs(s.positive - before.positive) > 1e-3
                        ? <em className="delta"> was {fixed(before.positive, 2)}</em> : null}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <p className="note">
            Authority is every thruster pushing the same way; top speed is where drag equals it. Effective mass is the vehicle's plus the water it drags along. An axis with no authority is one this vehicle cannot command.
          </p>

          <h2 style={{ marginTop: 22 }}>Senses</h2>
          <div className="kvs">
            {sensors.map((s) => <Row key={s.name} of={s.kind.replace(/_/g, " ")} is={s.name} />)}
            {contract.publishes ? <Row of="publishes" is={contract.publishes.map((p) => p.topic).join(", ")} /> : null}
            {contract.subscribes ? <Row of="acts on" is={contract.subscribes.map((p) => p.topic).join(", ")} /> : null}
          </div>

          <h2 style={{ marginTop: 22 }}>Where the numbers come from</h2>
          <p className="note">
            {source ?? "The published package's dynamics.json."}
            {version !== undefined ? ` Package version ${version}.` : ""}
          </p>
          <button className="quiet" disabled title="Publishing a version from here is not built yet">Publish as a version</button>
        </section>
      </div>
    </>
  );
}

/** A number that can be tried, in place. */
function Try({ value, unit, step, digits, onChange }: {
  value: number;
  unit: string;
  step: number;
  digits?: number;
  onChange: (value: number) => void;
}): React.JSX.Element {
  return (
    <label className="try">
      <input type="number" value={digits === undefined ? value : Number(value.toFixed(digits))} step={step} min={0}
             onChange={(e) => { const n = Number(e.target.value); if (Number.isFinite(n) && n >= 0) onChange(n); }} />
      <span>{unit}</span>
    </label>
  );
}
