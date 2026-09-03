// The panels around the water.
//
// Laid out the way an operator's console is laid out, because that is what this
// is: what the vehicle carries down the left, what it is doing down the right,
// what it has been doing along the bottom, and the water in the middle.
//
// Every number here comes from the vehicle. There is no panel showing something
// the platform does not actually measure — a console that invents a reading is
// worse than one that has fewer of them, because the whole purpose of the thing
// is to be believed about what happened.

import { useEffect, useRef } from "react";

export interface Topic {
  name: string;
  type: string;
  way: "from" | "to";
  messages: number;
  rateHz?: number;
}

/** One thing a hand may move on a controller while it runs. */
export interface Tunable {
  name: string;
  value: number;
  low: number;
  high: number;
  unit: string;
  says: string;
}

export interface ControllerSaid {
  name: string;
  kind: "builtin" | "manual" | "external";
  says: string;
  parameters: Tunable[];
  status: Record<string, unknown>;
}

export interface Helm {
  flying: string;
  preferred?: string | null;
  changes: number;
  controllers: ControllerSaid[];
}

export interface Reading {
  t?: number;
  depthM?: number;
  headingDeg?: number;
  pitchDeg?: number;
  rollDeg?: number;
  view?: string;
  samples?: Record<string, Record<string, number>>;
  flying?: string;
  controller?: Helm;
  speedMs?: number;
  position?: number[];
  velocity?: number[];
  rates?: number[];
  thrust?: number[];
  thrusters?: number;
  netBuoyancyN?: number;
  floorM?: number | null;
  altitudeM?: number | null;
  onTheBottom?: boolean;
  commanded?: boolean;
  byHand?: boolean;
  commandsReceived?: number;
  topics?: Topic[];
}

const KEYS: { key: string; does: string }[] = [
  { key: "W", does: "ahead" },
  { key: "S", does: "astern" },
  { key: "A", does: "port" },
  { key: "D", does: "starboard" },
  { key: "Q", does: "yaw left" },
  { key: "E", does: "yaw right" },
  { key: "SPACE", does: "rise" },
  { key: "C", does: "dive" },
];

export function Instruments({ reading, topics, held, history, frames, onLeave, onTune, onHoldHere, onEngage, onPlot, plotted, children }: {
  reading: Reading;
  topics: Topic[];
  held: string[];
  history: { t: number; depth: number; speed: number }[];
  frames: number;
  onLeave: () => void;
  onTune: (controller: string, name: string, value: number) => void;
  onHoldHere: () => void;
  onEngage: (controller: string) => void;
  onPlot: (topic: string) => void;
  plotted: string | undefined;
  children: React.ReactNode;
}): React.JSX.Element {
  const who = reading.controller?.flying ?? (reading.byHand === true ? "manual" : reading.commanded === true ? "stack" : undefined);
  const flying = who === "manual" ? "you" : who === "stack" ? "autonomy" : who === "hold" ? "hold" : "nobody";

  return (
    <div className="console">
      <header className="bar">
        <div className="identity">
          <strong>In the water</strong>
          <span>{elapsed(reading.t)}</span>
        </div>
        <div className="bar-facts">
          <span className={`who-flies ${flying}`}>
            {flying === "you" ? "you have the controls"
              : flying === "autonomy" ? "autonomy is flying"
              : flying === "hold" ? "the hold has it"
              : "nobody is flying"}
          </span>
          <span className="frames">{frames} frames</span>
        </div>
        <button className="quiet" onClick={onLeave}>Surface</button>
      </header>

      <aside className="dock left">
        <Panel name="Topics" note={topics.length === 0 ? "click one to plot it" : `${topics.length} on this vehicle · click to plot`}>
          {topics.length === 0 ? (
            <p className="none">The vehicle has not opened its boundary.</p>
          ) : (
            <ul className="topics">
              {topics.map((topic) => (
                <li key={topic.name} className={topic.name === plotted ? "plotted" : undefined}
                    onClick={() => onPlot(topic.name)} title={`plot ${topic.name}`}>
                  <span className={`way ${topic.way}`}>{topic.way === "from" ? "▲" : "▼"}</span>
                  <div>
                    <strong>{topic.name}</strong>
                    <em>{topic.type}</em>
                  </div>
                  <span className="count">
                    {topic.rateHz !== undefined && topic.rateHz > 0 ? `${topic.rateHz.toFixed(0)} Hz` : ""}
                    <small>{topic.messages.toLocaleString()}</small>
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Panel>

        <Panel name="Controller" note={reading.controller ? `${reading.controller.controllers.length} on this vehicle` : undefined}>
          <ControllerPanel helm={reading.controller} onTune={onTune} onHoldHere={onHoldHere} onEngage={onEngage} />
        </Panel>

        <Panel name="Controls" note="held, not tapped">
          <ul className="keys">
            {KEYS.map(({ key, does }) => (
              <li key={key} className={held.includes(key) ? "down" : undefined}>
                <kbd>{key === "SPACE" ? "space" : key}</kbd>
                <span>{does}</span>
              </li>
            ))}
          </ul>
        </Panel>
      </aside>

      {children}

      <aside className="dock right">
        <Panel name="Vehicle">
          <div className="dials">
            <Dial of="depth" is={reading.depthM} unit="m" />
            <Dial of="altitude" is={reading.altitudeM ?? undefined} unit="m" />
            <Dial of="speed" is={reading.speedMs} unit="m/s" />
          </div>
          <div className="dials">
            <Dial of="heading" is={reading.headingDeg} unit="°" digits={0} />
            <Dial of="pitch" is={reading.pitchDeg} unit="°" digits={1} />
            <Dial of="roll" is={reading.rollDeg} unit="°" digits={1} />
          </div>
          {reading.onTheBottom === true && (
            <p className="resting">Resting on the bottom.</p>
          )}
          <Axes name="velocity" of={reading.velocity} unit="m/s" />
          <Axes name="rates" of={reading.rates} unit="rad/s" />
          {reading.netBuoyancyN === undefined ? null : (
            <p className="aside">
              {reading.netBuoyancyN < 0 ? "Sinks" : "Floats"} at rest —
              {" "}{Math.abs(reading.netBuoyancyN).toFixed(2)} N net buoyancy.
            </p>
          )}
        </Panel>

        <Panel name="Thrusters" note={reading.thrusters ? `${reading.thrusters} fitted` : undefined}>
          <Thrusters of={reading.thrust} />
        </Panel>

        <Panel name="Depth" note="last minute">
          <Plot of={history} pick={(p) => p.depth} invert />
        </Panel>

        <Panel name="Speed" note="last minute">
          <Plot of={history} pick={(p) => p.speed} />
        </Panel>
      </aside>
    </div>
  );
}

/**
 * Who has the vehicle, and what can be moved on them.
 *
 * Every parameter comes from the controller's own declaration, with its range;
 * nothing here knows what a depth gain is. Moving a slider sends the value at
 * once, and the reading that comes back is the controller's, so what the
 * slider shows is what the vehicle is actually flying on.
 */
function ControllerPanel({ helm, onTune, onHoldHere, onEngage }: {
  helm: Helm | undefined;
  onTune: (controller: string, name: string, value: number) => void;
  onHoldHere: () => void;
  onEngage: (controller: string) => void;
}): React.JSX.Element {
  if (helm === undefined) return <p className="none">The vehicle has not said who flies it.</p>;
  return (
    <div className="helm">
      {helm.controllers.map((one) => {
        const flying = one.name === helm.flying;
        const status = one.status ?? {};
        return (
          <details key={one.name} className={`controller${flying ? " flying" : ""}`} open={flying}>
            <summary>
              <span className="dot" />
              <strong>{one.name}</strong>
              <em>{flying ? "flying" : one.kind}</em>
            </summary>
            <p className="says">{one.says}</p>
            {one.name !== "helm" && !flying ? (
              <div className="station">
                <span>{one.name === "stack" ? "the ordinary rule: the stack while it talks" : `keep the ${one.name} on it`}</span>
                <button className="quiet small" onClick={() => onEngage(one.name)}>Give it the vehicle</button>
              </div>
            ) : null}
            {one.name === "hold" ? (
              <div className="station">
                <span>station {fmt(status["targetDepthM"])} m · {fmt(status["targetHeadingDeg"], 0)}° · off by {fmt(status["offStationM"])} m</span>
                <button className="quiet small" onClick={onHoldHere}>Hold here</button>
              </div>
            ) : null}
            {one.parameters.map((p) => (
              <label key={p.name} className="tunable" title={p.says}>
                <span>{p.name}</span>
                <input type="range" min={p.low} max={p.high} step={(p.high - p.low) / 200}
                       value={p.value}
                       onChange={(e) => onTune(one.name, p.name, Number(e.target.value))} />
                <em>{p.value.toFixed(p.high - p.low > 5 ? 1 : 2)} {p.unit}</em>
              </label>
            ))}
          </details>
        );
      })}
    </div>
  );
}

function fmt(value: unknown, digits = 2): string {
  return typeof value === "number" ? value.toFixed(digits) : "—";
}

function Panel({ name, note, children }: {
  name: string;
  note?: string;
  children: React.ReactNode;
}): React.JSX.Element {
  return (
    <section className="panel-box">
      <h3>
        {name}
        {note === undefined ? null : <span>{note}</span>}
      </h3>
      <div className="body">{children}</div>
    </section>
  );
}

function Dial({ of, is, unit, digits = 2 }: {
  of: string; is: number | undefined; unit: string; digits?: number;
}): React.JSX.Element {
  return (
    <div className="dial">
      <span>{of}</span>
      <strong>{is === undefined ? "—" : is.toFixed(digits)}</strong>
      <em>{unit}</em>
    </div>
  );
}

/** Three numbers that are one thing, shown as one thing. */
function Axes({ name, of, unit }: {
  name: string; of: number[] | undefined; unit: string;
}): React.JSX.Element {
  const values = of ?? [0, 0, 0];
  return (
    <div className="axes">
      <span>{name}</span>
      <div>
        {["x", "y", "z"].map((axis, i) => (
          <div key={axis}>
            <em>{axis}</em>
            <strong>{(values[i] ?? 0).toFixed(3)}</strong>
          </div>
        ))}
      </div>
      <small>{unit}</small>
    </div>
  );
}

/**
 * What each thruster is being asked for, as a bar either side of nothing.
 *
 * Either side because a thruster reverses, and a bar that only grows one way
 * shows a vehicle backing up as though it were stopping.
 */
function Thrusters({ of }: { of: number[] | undefined }): React.JSX.Element {
  const commands = of ?? [];
  if (commands.length === 0) return <p className="none">No commands yet.</p>;
  return (
    <div className="thrusters">
      {commands.map((value, i) => (
        <div className="thruster" key={i}>
          <span>{i + 1}</span>
          <div className="track">
            <div className={value < 0 ? "fill back" : "fill"}
                 style={{
                   width: `${Math.min(50, Math.abs(value) * 50)}%`,
                   [value < 0 ? "right" : "left"]: "50%",
                 }} />
          </div>
          <em>{value.toFixed(2)}</em>
        </div>
      ))}
    </div>
  );
}

/**
 * A line of what a number has been doing.
 *
 * Drawn rather than plotted with a library, because it is one line and the
 * library would be larger than the application. Depth is inverted: down is
 * down, which is the only way anybody reads a depth trace.
 */
function Plot({ of, pick, invert }: {
  of: { t: number; depth: number; speed: number }[];
  pick: (point: { t: number; depth: number; speed: number }) => number;
  invert?: boolean;
}): React.JSX.Element {
  const canvas = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const surface = canvas.current;
    if (surface === null) return;
    const width = surface.clientWidth * devicePixelRatio;
    const height = surface.clientHeight * devicePixelRatio;
    if (surface.width !== width) surface.width = width;
    if (surface.height !== height) surface.height = height;

    const ink = surface.getContext("2d");
    if (ink === null) return;
    ink.clearRect(0, 0, width, height);
    if (of.length < 2) return;

    const values = of.map(pick);
    let low = Math.min(...values);
    let high = Math.max(...values);
    if (high - low < 0.05) { const mid = (high + low) / 2; low = mid - 0.05; high = mid + 0.05; }

    const at = (i: number) => {
      const x = (i / (of.length - 1)) * width;
      const share = (values[i]! - low) / (high - low);
      const y = invert === true ? share * height : (1 - share) * height;
      return [x, Math.max(1, Math.min(height - 1, y))] as const;
    };

    ink.strokeStyle = "#1b2f47";
    ink.lineWidth = devicePixelRatio;
    for (const share of [0.25, 0.5, 0.75]) {
      ink.beginPath();
      ink.moveTo(0, height * share);
      ink.lineTo(width, height * share);
      ink.stroke();
    }

    ink.beginPath();
    ink.moveTo(...at(0));
    for (let i = 1; i < of.length; i += 1) ink.lineTo(...at(i));
    ink.strokeStyle = "#40c7f4";
    ink.lineWidth = 1.6 * devicePixelRatio;
    ink.lineJoin = "round";
    ink.stroke();

    const [x, y] = at(of.length - 1);
    ink.beginPath();
    ink.arc(x, y, 2.6 * devicePixelRatio, 0, Math.PI * 2);
    ink.fillStyle = "#40c7f4";
    ink.fill();
  }, [of, pick, invert, of.length]);

  return (
    <div className="plot">
      <canvas ref={canvas} />
      {of.length < 2 ? <span className="none">waiting</span> : null}
    </div>
  );
}

function elapsed(seconds: number | undefined): string {
  if (seconds === undefined) return "—";
  const whole = Math.floor(seconds);
  return `${String(Math.floor(whole / 60)).padStart(2, "0")}:${String(whole % 60).padStart(2, "0")}`;
}
