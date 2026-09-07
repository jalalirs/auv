// Everything known about the dive, painted onto the dive.
//
// The alternative — a picture in one box and the numbers in six others — asks
// the person watching to do the join themselves: to read "0.42 m off station"
// and work out which way that is, or to see a chart with a circle on it and
// find the same circle in the water. A game does not do this. It draws the
// objective where the objective is, and the state of the world around the
// edges, and the player relates to one thing instead of seven.
//
// So: the task is drawn in the water where it actually is, the transponders
// that are fixing the vehicle are drawn on the seabed where they were laid,
// what the vehicle believes about itself is drawn beside what is true, and the
// instruments live on the edges of the picture. All of it hangs off the camera
// the runtime wrote into each frame — see project.ts, which is the whole trick.

import { Lens, WIDE, TALL, heldInside, inFrame, writtenFrom,
         type Box, type Looking, type OnScreen } from "./project.js";
import type { Geometry } from "./Minimap.js";

/** What was deployed in this water to give fixes, as the record describes it. */
export interface Deployment {
  kind: string;
  at?: number[];
  anchors?: number[][];
  rangeM?: number;
  everyS?: number;
  /** A ship keeping station over the vehicle rather than sitting at a place. */
  overhead?: boolean;
  accuracyM?: number;
  accuracyPercent?: number;
}

export interface Told {
  looking?: Looking | null;
  position: number[];
  /** Where the vehicle believes it is. The gap is the point of the dive. */
  believed?: number[] | null;
  headingDeg: number;
  depthM: number;
  altitudeM?: number | null;
  speedMs?: number | null;
  batteryPercent?: number | null;
  beganAt?: number[] | null;
  geometry?: Geometry | null;
  positioning?: Deployment | null;
  vehicle?: { halfWidthM?: number; halfHeightM?: number;
              /** Where the drawn hull sits relative to the origin, in the
                  vehicle's own frame. The physics works at the centre of
                  gravity and the model was drawn around something else. */
              offsetM?: number[] } | null;
  task?: {
    name?: string;
    kind?: string;
    asks?: string;
    says?: string;
    score?: number;
    done?: boolean;
    failed?: boolean;
  } | null;
  elapsedS?: number;
  ofS?: number;
  /** Hidden, for looking at the picture on its own. */
  showing?: boolean;
}

// One palette, so that a thing means the same colour wherever it is drawn.
const TASK = "#ffd166";        // what is being asked for
const DONE = "#5ad6a0";        // and what has been achieved
const FIX = "#4bb9ff";         // the world telling the vehicle where it is
const BELIEF = "#ff8f6b";      // and what the vehicle made of that
const QUIET = "#c9d8e8";

export function Hud(told: Told): React.JSX.Element | null {
  if (told.showing === false) return null;
  const lens = told.looking?.eye && told.looking.basis ? new Lens(told.looking) : null;
  return (
    // No filter over this. A drop shadow on the whole overlay looked right and
    // was catastrophic: the group's bounding box takes in a range circle a
    // hundred and fifty metres across, whose projection runs to tens of
    // thousands of units, so the filter region became enormous, the layer was
    // rasterised at a fraction of the resolution to fit, and the video behind
    // it came out blurred and three times darker. Text is legible from the
    // stroke behind it in the stylesheet instead, which costs nothing.
    <svg className="world-hud" viewBox={`0 0 ${WIDE} ${TALL}`} preserveAspectRatio="none" aria-hidden="true">
      <g>
        {lens === null ? null : (
          <>
            <Deployed lens={lens} told={told} />
            <InTheWater lens={lens} told={told} />
            <Belief lens={lens} told={told} />
            <Vehicle lens={lens} told={told} />
          </>
        )}
        <Compass headingDeg={told.headingDeg} />
        <Ribbons told={told} />
        <Asked told={told} />
      </g>
    </svg>
  );
}

// ── the task, drawn where the task is ───────────────────────────────────────

function InTheWater({ lens, told }: { lens: Lens; told: Told }): React.JSX.Element | null {
  const g = told.geometry;
  if (!g) return null;
  const floor = (told.beganAt ?? told.position)[2] ?? told.position[2]!;
  const done = told.task?.done === true;
  const ink = done ? DONE : TASK;
  return (
    <g>
      {g.circle ? (
        <>
          {/* The station: a ring where it is, and a mast so it is findable
              when the vehicle has drifted off and is looking elsewhere. */}
          <path d={lens.ring([g.circle.x, g.circle.y, floor], g.circle.radiusM)}
                fill="none" stroke={ink} strokeWidth="2.5" opacity="0.95" />
          <path d={lens.ring([g.circle.x, g.circle.y, floor], g.circle.radiusM * 2.4)}
                fill="none" stroke={ink} strokeWidth="1" strokeDasharray="6 8" opacity="0.4" />
          <path d={lens.path([[g.circle.x, g.circle.y, floor], [g.circle.x, g.circle.y, floor + 0.85]])}
                fill="none" stroke={ink} strokeWidth="1.2" opacity="0.55" />
          <Label lens={lens} at={[g.circle.x, g.circle.y, floor + 1.05]} ink={ink} text="station" />
        </>
      ) : null}

      {g.line ? (
        <path d={lens.path(g.line.map((p) => [p.x, p.y, floor]))} fill="none" stroke={ink}
              strokeWidth="1.6" strokeDasharray="10 7" opacity="0.7" />
      ) : null}

      {g.rectangle ? (
        <path d={lens.path(g.rectangle.map((p) => [p.x, p.y, floor]), true)} fill="none"
              stroke={ink} strokeWidth="2" opacity="0.8" />
      ) : null}

      {/* Waypoints as gates standing in the water: reached ones go quiet, the
          one being flown to is named and ranged. */}
      {(g.points ?? []).map((p, i) => {
        const reached = i < (g.reached ?? 0);
        const next = i === (g.reached ?? 0);
        return (
          <Gate key={i} lens={lens} at={[p.x, p.y, -p.depthM]} from={told.position}
                ink={reached ? DONE : next ? TASK : QUIET} number={i + 1}
                dim={!next && !reached} ranged={next} />
        );
      })}

      {(g.marks ?? []).map((m, i) => (
        <Gate key={`m${i}`} lens={lens} at={[m.x, m.y, floor]} from={told.position}
              ink={m.done ? DONE : TASK} number={null} dim={m.done === true} ranged={false} />
      ))}
    </g>
  );
}

function Gate({ lens, at, from, ink, number, dim, ranged }: {
  lens: Lens; at: number[]; from: number[]; ink: string;
  number: number | null; dim: boolean; ranged: boolean;
}): React.JSX.Element | null {
  const on = lens.at(at);
  if (on === null) return null;
  const shown = inFrame(on, 0);
  const held = shown ? on : heldInside(on);
  // A gate held to the edge is a sign saying which way, not a gate: drawn at
  // the size it would be, it hangs half off the picture.
  const size = shown ? Math.max(7, Math.min(46, lens.metresAcross(on.awayM) * 0.8)) : 13;
  const away = Math.hypot(at[0]! - from[0]!, at[1]! - from[1]!);
  return (
    <g opacity={dim ? 0.45 : 1}>
      <path d={`M${held.x} ${held.y - size} L${held.x + size} ${held.y} L${held.x} ${held.y + size} L${held.x - size} ${held.y} Z`}
            fill="none" stroke={ink} strokeWidth={ranged ? 2.6 : 1.6} />
      {number === null ? null : (
        <text x={held.x} y={held.y + 5} textAnchor="middle" fontSize="15" fill={ink} fontWeight="600">{number}</text>
      )}
      {ranged ? (
        <text x={held.x} y={held.y - size - 8} textAnchor="middle" fontSize="15" fill={ink}>
          {away.toFixed(1)} m
        </text>
      ) : null}
    </g>
  );
}

// ── what is fixing the vehicle, drawn where it was laid ─────────────────────

function Deployed({ lens, told }: { lens: Lens; told: Told }): React.JSX.Element | null {
  const d = told.positioning;
  if (!d || d.kind === "none") return null;
  // A ship keeping station overhead is above the vehicle, wherever that is.
  if (d.overhead === true) {
    return <Anchor lens={lens} at={[told.position[0]!, told.position[1]!, 0]}
                   from={told.position} named="ship" heard reach={d.rangeM} />;
  }
  if (!d.at) return null;
  const seabed = (told.beganAt ?? told.position)[2] ?? -10;
  const anchors: number[][] = d.anchors?.length
    ? d.anchors.map((a) => [a[0]!, a[1]!, a[2] ?? d.at![2] ?? seabed])
    // A ship or a buoy is at the surface, wherever the record says it sits;
    // a dock beacon is on the bottom. Both are one thing rather than three.
    : [[d.at[0]!, d.at[1]!, d.kind === "usbl" ? 0 : (d.at[2] ?? seabed)]];
  const named = d.kind === "lbl" ? "transponder" : d.kind === "usbl" ? "ship" : "beacon";
  // What a pinned marker has to keep off: the task card, and the button that
  // puts the overlay away. Both live in corners, and a transponder behind the
  // vehicle is pinned to a corner every frame of every dive.
  const keepOut: Box[] = [{ x: WIDE - 190, y: 8, wide: 190, tall: 44 }];
  if (told.task?.name) keepOut.push({ x: 18, y: 14, wide: 442, tall: told.task.asks ? 140 : 108 });
  return (
    <g>
      {anchors.map((a, i) => {
        const away = Math.hypot(a[0]! - told.position[0]!, a[1]! - told.position[1]!);
        return (
          <Anchor key={i} lens={lens} at={a} from={told.position} named={named}
                  heard={d.rangeM === undefined || away <= d.rangeM} reach={d.rangeM} keepOut={keepOut} />
        );
      })}
      {/* Where the array stops working, on the bottom. Leaving it is the
          moment a dive goes back to dead reckoning, and it should be visible
          before it happens rather than inferred afterwards. */}
      {d.kind === "lbl" && d.rangeM ? (
        <path d={lens.ring([d.at[0]!, d.at[1]!, d.at[2] ?? seabed], d.rangeM, 96)} fill="none"
              stroke={FIX} strokeWidth="1" strokeDasharray="14 10" opacity="0.3" />
      ) : null}
    </g>
  );
}

function Anchor({ lens, at, from, named, heard, keepOut }: {
  lens: Lens; at: number[]; from: number[]; named: string; heard: boolean; reach?: number;
  keepOut?: Box[];
}): React.JSX.Element | null {
  const on = lens.at(at);
  if (on === null) return null;
  const held = inFrame(on, 0) ? on : heldInside(on, 26, keepOut);
  const written = writtenFrom(held);
  const away = Math.hypot(at[0]! - from[0]!, at[1]! - from[1]!, at[2]! - from[2]!);
  return (
    <g opacity={heard ? 0.9 : 0.35}>
      {/* The line a fix comes down. Dashed, because it is a range and not a
          rope, and drawn only while the vehicle is in range of it. */}
      {heard ? (
        <path d={lens.path([from, at])} fill="none" stroke={FIX} strokeWidth="1"
              strokeDasharray="3 9" opacity="0.5" />
      ) : null}
      <circle cx={held.x} cy={held.y} r="7" fill="none" stroke={FIX} strokeWidth="2" />
      <circle cx={held.x} cy={held.y} r="2" fill={FIX} />
      <text x={held.x + written.dx} y={held.y + 4} fontSize="14" fill={FIX} textAnchor={written.anchor}>
        {named} · {away.toFixed(0)} m
      </text>
    </g>
  );
}

// ── the two positions ───────────────────────────────────────────────────────

function Belief({ lens, told }: { lens: Lens; told: Told }): React.JSX.Element | null {
  const believed = told.believed;
  if (!believed) return null;
  const drift = Math.hypot(believed[0]! - told.position[0]!, believed[1]! - told.position[1]!);
  // Below this the two are the same thing to look at, and a box drawn over
  // the hull every frame says less than the number under the picture does.
  if (drift < 0.4) return null;
  const on = lens.at(believed);
  if (on === null) return null;
  const held = inFrame(on, 0) ? on : heldInside(on);
  const size = Math.max(9, Math.min(60, lens.metresAcross(on.awayM) * 0.5));
  return (
    <g>
      <path d={lens.path([drawnAt(told), believed])} fill="none" stroke={BELIEF} strokeWidth="1.4"
            strokeDasharray="5 5" opacity="0.75" />
      <rect x={held.x - size} y={held.y - size * 0.5} width={size * 2} height={size}
            fill="none" stroke={BELIEF} strokeWidth="1.6" strokeDasharray="6 4" opacity="0.9" />
      <text x={held.x} y={held.y - size * 0.5 - 8} textAnchor="middle" fontSize="14" fill={BELIEF}>
        thinks it is here · {drift.toFixed(1)} m out
      </text>
    </g>
  );
}

function Vehicle({ lens, told }: { lens: Lens; told: Told }): React.JSX.Element | null {
  const on = lens.at(drawnAt(told));
  if (on === null || !inFrame(on, 120)) return null;
  const half = Math.max(10, lens.metresAcross(on.awayM) * (told.vehicle?.halfWidthM ?? 0.3) * 1.25);
  const arm = half * 0.45;
  // Corners rather than a box: a box hides the thing it is drawn around.
  const corner = (dx: number, dy: number) =>
    `M${on.x + dx * half} ${on.y + dy * half - dy * arm} L${on.x + dx * half} ${on.y + dy * half} `
    + `L${on.x + dx * half - dx * arm} ${on.y + dy * half}`;
  return (
    <g opacity="0.85">
      <path d={[corner(-1, -1), corner(1, -1), corner(-1, 1), corner(1, 1)].join(" ")}
            fill="none" stroke="#eaf4ff" strokeWidth="1.6" />
    </g>
  );
}

/**
 * Where the hull appears, as against where the vehicle is.
 *
 * The offset is in the vehicle's own frame, so it turns with the vehicle:
 * something drawn a fifth of a metre above the origin stays above it through
 * a yaw and leans with a roll, which is what you see in the picture.
 */
export function drawnAt(told: Told): number[] {
  const offset = told.vehicle?.offsetM;
  if (offset === undefined || offset.every((v) => v === 0)) return told.position;
  const heading = (told.headingDeg * Math.PI) / 180;
  const cos = Math.cos(heading);
  const sin = Math.sin(heading);
  return [
    told.position[0]! + offset[0]! * cos - offset[1]! * sin,
    told.position[1]! + offset[0]! * sin + offset[1]! * cos,
    told.position[2]! + (offset[2] ?? 0),
  ];
}

function Label({ lens, at, ink, text }: { lens: Lens; at: number[]; ink: string; text: string }):
React.JSX.Element | null {
  const on = lens.at(at);
  if (!inFrame(on, 0)) return null;
  return <text x={(on as OnScreen).x} y={(on as OnScreen).y} textAnchor="middle" fontSize="14" fill={ink}>{text}</text>;
}

// ── the instruments, around the edges ───────────────────────────────────────

function Compass({ headingDeg }: { headingDeg: number }): React.JSX.Element {
  // A strip of the horizon: the ticks slide, the vehicle's own mark does not,
  // which is the whole reason a heading tape beats a number.
  const across = 520;         // pixels of tape shown
  const perDeg = across / 90; // ninety degrees of it
  const marks: React.JSX.Element[] = [];
  const from = Math.round(headingDeg - 46);
  for (let d = from; d <= headingDeg + 46; d += 1) {
    const at = WIDE / 2 + (d - headingDeg) * perDeg;
    const whole = ((d % 360) + 360) % 360;
    if (whole % 10 !== 0) continue;
    const cardinal = whole % 90 === 0;
    marks.push(
      <g key={d}>
        <path d={`M${at} 24 L${at} ${cardinal ? 40 : 33}`} stroke={QUIET} strokeWidth={cardinal ? 2 : 1}
              opacity={cardinal ? 0.95 : 0.6} />
        {whole % 30 === 0 ? (
          <text x={at} y={56} textAnchor="middle" fontSize="14" fill={QUIET}
                opacity={cardinal ? 1 : 0.7} fontWeight={cardinal ? "600" : "400"}>
            {whole === 0 ? "N" : whole === 90 ? "E" : whole === 180 ? "S" : whole === 270 ? "W" : whole}
          </text>
        ) : null}
      </g>,
    );
  }
  return (
    <g>
      <path d={`M${WIDE / 2 - across / 2} 24 H${WIDE / 2 + across / 2}`} stroke={QUIET} strokeWidth="1" opacity="0.25" />
      {marks}
      <path d={`M${WIDE / 2} 18 L${WIDE / 2 - 7} 6 L${WIDE / 2 + 7} 6 Z`} fill="#eaf4ff" />
      <text x={WIDE / 2} y={74} textAnchor="middle" fontSize="15" fill="#eaf4ff" fontWeight="600">
        {(((headingDeg % 360) + 360) % 360).toFixed(0).padStart(3, "0")}°
      </text>
    </g>
  );
}

function Ribbons({ told }: { told: Told }): React.JSX.Element {
  const speed = told.speedMs ?? null;
  const battery = told.batteryPercent ?? null;
  return (
    <g>
      <Readout x={54} y={TALL / 2 - 26} name="depth" value={told.depthM.toFixed(2)} unit="m" />
      {told.altitudeM === null || told.altitudeM === undefined ? null : (
        <Readout x={54} y={TALL / 2 + 34} name="altitude" value={told.altitudeM.toFixed(2)} unit="m"
                 warn={told.altitudeM < 0.8} />
      )}
      {speed === null ? null : (
        <Readout x={WIDE - 54} y={TALL / 2 - 26} name="speed" value={speed.toFixed(2)} unit="m/s" right />
      )}
      {battery === null ? null : (
        <Readout x={WIDE - 54} y={TALL / 2 + 34} name="battery" value={battery.toFixed(0)} unit="%"
                 right warn={battery < 25} />
      )}
    </g>
  );
}

function Readout({ x, y, name, value, unit, right, warn }: {
  x: number; y: number; name: string; value: string; unit: string; right?: boolean; warn?: boolean;
}): React.JSX.Element {
  const anchor = right ? "end" : "start";
  return (
    <g>
      <text x={x} y={y} textAnchor={anchor} fontSize="13" fill={QUIET} opacity="0.75"
            letterSpacing="1.5">{name.toUpperCase()}</text>
      <text x={x} y={y + 26} textAnchor={anchor} fontSize="27" fill={warn ? BELIEF : "#eaf4ff"}
            fontWeight="600">
        {value}<tspan fontSize="14" fill={QUIET} fontWeight="400"> {unit}</tspan>
      </text>
    </g>
  );
}

/** What the dive is for, and how it is going, in the corner of its own picture. */
function Asked({ told }: { told: Told }): React.JSX.Element | null {
  const task = told.task;
  if (!task?.name) return null;
  const score = Math.max(0, Math.min(1, task.score ?? 0));
  const wide = 430;
  return (
    <g>
      <rect x="24" y="20" width={wide} height={task.asks ? 128 : 96} rx="10"
            fill="#04121e" opacity="0.55" />
      <text x="44" y="48" fontSize="19" fill="#eaf4ff" fontWeight="600">{task.name}</text>
      <text x={wide - 4} y={48} textAnchor="end" fontSize="21" fill={task.done ? DONE : TASK}
            fontWeight="600">{(score * 100).toFixed(0)}%</text>
      {task.asks ? <Wrapped x={44} y={74} wide={wide - 44} size={13} fill={QUIET} text={task.asks} /> : null}
      <text x={44} y={task.asks ? 120 : 78} fontSize="13" fill={QUIET}>{task.says ?? ""}</text>
      {/* The clock lives at the end of the line the task is talking on, which
          is the one place on the card nothing else wants. */}
      {told.elapsedS === undefined ? null : (
        <text x={wide - 4} y={task.asks ? 120 : 78} textAnchor="end" fontSize="13" fill={QUIET}>
          {told.elapsedS.toFixed(0)} s{told.ofS ? ` of ${told.ofS.toFixed(0)}` : ""}
        </text>
      )}
      <rect x="44" y={task.asks ? 132 : 88} width={wide - 44} height="5" rx="2.5" fill="#0e2233" />
      <rect x="44" y={task.asks ? 132 : 88} width={(wide - 44) * score} height="5" rx="2.5"
            fill={task.done ? DONE : TASK} />
      {task.done || task.failed ? (
        <text x={WIDE / 2} y={TALL - 54} textAnchor="middle" fontSize="30"
              fill={task.failed ? BELIEF : DONE} fontWeight="600" letterSpacing="3">
          {task.failed ? "FAILED" : "ACHIEVED"}
        </text>
      ) : null}
    </g>
  );
}

/** Text that will not run off the card it is written on. */
function Wrapped({ x, y, wide, size, fill, text }: {
  x: number; y: number; wide: number; size: number; fill: string; text: string;
}): React.JSX.Element {
  const per = Math.max(8, Math.floor(wide / (size * 0.54)));
  const lines: string[] = [];
  let line = "";
  for (const word of text.split(" ")) {
    if ((line + " " + word).trim().length > per) { lines.push(line.trim()); line = word; }
    else line = `${line} ${word}`;
  }
  if (line.trim()) lines.push(line.trim());
  return (
    <>
      {lines.slice(0, 2).map((one, i) => (
        <text key={i} x={x} y={y + i * (size + 4)} fontSize={size} fill={fill}>{one}</text>
      ))}
    </>
  );
}
