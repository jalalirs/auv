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

/** How the dive's task is going, as the runtime judges it. */
export interface TaskProgress {
  kind: string;
  name: string;
  score: number;
  done: boolean;
  says: string;
  elapsedS: number;
  detail: Record<string, unknown>;
}

export interface Reading {
  /** How much of the hull is under the surface, from one to nothing. */
  submerged?: number;
  surfaced?: boolean;
  /** Up against ground it cannot ride over. */
  againstTheGround?: boolean;
  /** Where the camera is looking, for the axes drawn in the corner. */
  camera?: { basis?: { right: number[]; up: number[]; forward: number[] }; upAxis?: string; view?: string };
  t?: number;
  depthM?: number;
  headingDeg?: number;
  pitchDeg?: number;
  rollDeg?: number;
  view?: string;
  samples?: Record<string, Record<string, number>>;
  task?: TaskProgress | null;
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
  { key: "Z", does: "roll left" },
  { key: "X", does: "roll right" },
  { key: "R", does: "pitch up" },
  { key: "F", does: "pitch down" },
];

export function Instruments({ reading, topics, held, history, frames, onLeave, onTune, onHoldHere, onEngage, onPlot, plotted, pad, water, children }: {
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
  pad?: string;
  /** What the water is doing, from the dive's greeting. */
  water?: { currentMetresPerSecond: number; currentHeadingDeg: number; visibilityM?: number | null };
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

        <Panel name="Controls" note={pad ? `gamepad: ${pad.split("(")[0].trim()}` : "held, not tapped · roll and pitch only where the hull can"}>
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
        {reading.task ? (
          <Panel name="Task" note={reading.task.done ? "over" : `${reading.task.elapsedS.toFixed(0)} s in`}>
            <div className="task">
              <div className="task-head">
                <strong>{reading.task.name}</strong>
                <em>{(reading.task.score * 100).toFixed(0)}%</em>
              </div>
              <div className="score"><div style={{ width: `${Math.round(reading.task.score * 100)}%` }} /></div>
              <p className="says">{reading.task.says}</p>
            </div>
          </Panel>
        ) : null}
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
          {reading.againstTheGround === true && (
            <p className="resting surfaced">Up against the ground — it cannot go that way.</p>
          )}
          {typeof reading.submerged === "number" && reading.submerged < 1 && (
            <p className="resting surfaced">
              {reading.submerged <= 0
                ? "Out of the water — no buoyancy, no thrust."
                : `Breaking the surface — ${(reading.submerged * 100).toFixed(0)}% of the hull is in the water.`}
            </p>
          )}
          <Axes name="velocity" of={reading.velocity} unit="m/s" />
          <Axes name="rates" of={reading.rates} unit="rad/s" />
          {reading.netBuoyancyN === undefined ? null : (
            <p className="aside">
              {reading.netBuoyancyN < 0 ? "Sinks" : "Floats"} at rest —
              {" "}{Math.abs(reading.netBuoyancyN).toFixed(2)} N net buoyancy.
            </p>
          )}
          {water === undefined ? null : (
            <p className="aside">
              {water.currentMetresPerSecond > 0.01
                ? `Current ${(water.currentMetresPerSecond / 0.5144).toFixed(1)} kn towards ${water.currentHeadingDeg.toFixed(0).padStart(3, "0")}°`
                : "Still water"}
              {water.visibilityM ? ` · ${water.visibilityM.toFixed(0)} m visibility` : ""}.
            </p>
          )}
        </Panel>

        <Panel name="Thrusters" note={reading.thrusters ? `${reading.thrusters} fitted` : undefined}>
          <Thrusters of={reading.thrust} />
        </Panel>

        <Panel name="Depth" note="last minute">
          <Plot of={history} pick={(p) => p.depth} unit="m" invert />
        </Panel>

        <Panel name="Speed" note="last minute">
          <Plot of={history} pick={(p) => p.speed} unit="m/s" />
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
  // Nothing here changes shape with who is flying. Every controller is shown
  // the same way all the time — its rows, its sliders — and a hand-over moves
  // only the dot and the word beside it, which have a fixed width. Folding
  // and unfolding on the hand-over, or rows that came and went with it,
  // resized the panel while a key was held and moved everything under it.
  return (
    <div className="helm">
      {helm.controllers.map((one) => {
        const flying = one.name === helm.flying;
        const status = one.status ?? {};
        return (
          <section key={one.name} className={`controller${flying ? " flying" : ""}`}>
            <header>
              <span className="dot" />
              <strong>{one.name}</strong>
              <em>{flying ? "flying" : one.kind}</em>
            </header>
            <p className="says">{one.says}</p>
            {one.name !== "helm" ? (
              <div className="station">
                <span>{flying ? "has the vehicle"
                  : one.name === "stack" ? "flies while it talks"
                  : "standing by"}</span>
                <button className="quiet small engage" disabled={flying} onClick={() => onEngage(one.name)}
                        title={flying ? "It has the vehicle" : "Give it the vehicle, and keep it on it"}>
                  {flying ? "Flying" : "Engage"}
                </button>
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
          </section>
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
          <em>{(Object.is(value, -0) || Math.abs(value) < 0.005 ? 0 : value).toFixed(2)}</em>
        </div>
      ))}
      <p className="unit">share of full thrust, −1 astern to 1 ahead</p>
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
function Plot({ of, pick, unit, invert }: {
  of: { t: number; depth: number; speed: number }[];
  pick: (point: { t: number; depth: number; speed: number }) => number;
  /** What the numbers are in. A trace without one is a shape, not a reading. */
  unit: string;
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

    // What it is worth, and between what. A trace with no numbers on it says
    // only that something went up and came down again.
    ink.font = `${10 * devicePixelRatio}px system-ui, sans-serif`;
    ink.fillStyle = "#4d6485";
    ink.textAlign = "right";
    ink.textBaseline = "top";
    ink.fillText(`${(invert === true ? low : high).toFixed(2)} ${unit}`,
                 width - 5 * devicePixelRatio, 3 * devicePixelRatio);
    ink.textBaseline = "bottom";
    ink.fillText(`${(invert === true ? high : low).toFixed(2)} ${unit}`,
                 width - 5 * devicePixelRatio, height - 3 * devicePixelRatio);
    ink.textAlign = "left";
    ink.textBaseline = "top";
    ink.fillStyle = "#c9d6e6";
    ink.font = `600 ${12 * devicePixelRatio}px system-ui, sans-serif`;
    ink.fillText(`${values[values.length - 1]!.toFixed(2)} ${unit}`,
                 5 * devicePixelRatio, 3 * devicePixelRatio);
  }, [of, pick, invert, unit, of.length]);

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
