// A topic, plotted: every numeric field on it over the last minute, with the
// latest value beside its name. Clicking a topic in the tree opens one of
// these, which is how a console answers "what is the depth sensor saying" —
// by showing it, not by summarising it.

import { useEffect, useRef, useState } from "react";

export interface Sample { t: number; values: Record<string, number> }

/** What the vehicle says about the topic being looked at. */
export interface About { name: string; type: string; way: "from" | "to"; messages: number }

const INKS = ["#40c7f4", "#ff7a5c", "#9be564", "#f4c542", "#c58cff", "#5ce0c8", "#ff9fd6", "#a0aab8"];

export function TopicPlot({ topic, of, about, onLook }: {
  topic: string | undefined;
  of: Sample[];
  /** The topic's own entry in the contract, when there is one. */
  about?: About;
  /** Look through a camera, for a topic that carries pictures. */
  onLook?: (view: string) => void;
}): React.JSX.Element {
  const canvas = useRef<HTMLCanvasElement>(null);
  const [hidden, setHidden] = useState<Set<string>>(new Set());
  const fields = of.length === 0 ? [] : Object.keys(of[of.length - 1]!.values);
  const shown = fields.filter((f) => !hidden.has(f));

  useEffect(() => {
    const surface = canvas.current;
    if (surface === null) return;
    const width = Math.max(1, Math.floor(surface.clientWidth * devicePixelRatio));
    const height = Math.max(1, Math.floor(surface.clientHeight * devicePixelRatio));
    if (surface.width !== width) surface.width = width;
    if (surface.height !== height) surface.height = height;
    const ink = surface.getContext("2d");
    if (ink === null) return;
    ink.fillStyle = "#050a12";
    ink.fillRect(0, 0, width, height);
    if (of.length < 2 || shown.length === 0) return;

    let low = Infinity;
    let high = -Infinity;
    for (const sample of of) {
      for (const field of shown) {
        const v = sample.values[field];
        if (v === undefined) continue;
        if (v < low) low = v;
        if (v > high) high = v;
      }
    }
    if (!Number.isFinite(low)) return;
    if (high - low < 1e-6) { low -= 0.5; high += 0.5; }
    const pad = (high - low) * 0.08;
    low -= pad; high += pad;

    ink.strokeStyle = "#13233a";
    ink.lineWidth = devicePixelRatio;
    for (const share of [0.25, 0.5, 0.75]) {
      ink.beginPath(); ink.moveTo(0, height * share); ink.lineTo(width, height * share); ink.stroke();
    }
    ink.fillStyle = "#4d6485";
    ink.font = `${10 * devicePixelRatio}px system-ui, sans-serif`;
    ink.textBaseline = "top";
    ink.fillText(short(high), 4 * devicePixelRatio, 3 * devicePixelRatio);
    ink.textBaseline = "bottom";
    ink.fillText(short(low), 4 * devicePixelRatio, height - 3 * devicePixelRatio);

    shown.forEach((field, index) => {
      ink.beginPath();
      let started = false;
      for (let i = 0; i < of.length; i += 1) {
        const v = of[i]!.values[field];
        if (v === undefined) continue;
        const x = (i / (of.length - 1)) * width;
        const y = (1 - (v - low) / (high - low)) * height;
        if (!started) { ink.moveTo(x, y); started = true; } else ink.lineTo(x, y);
      }
      ink.strokeStyle = INKS[fields.indexOf(field) % INKS.length]!;
      ink.lineWidth = 1.5 * devicePixelRatio;
      ink.lineJoin = "round";
      ink.stroke();
    });
  }, [of, of.length, shown.join("|")]);

  // Not everything on a vehicle is a number. A topic that carries pictures
  // has nothing to plot and never will, and one nothing publishes has nothing
  // to plot yet — and a blank pane says neither, which reads as broken.
  const pictures = about !== undefined && about.type.endsWith("/Image");
  const said = pictures
    ? (about!.name.startsWith("/camera")
        ? { title: "pictures, not numbers",
            body: "The vehicle's own camera. Look through it in the water pane and it goes out on this topic as it is seen.",
            look: "front" }
        : { title: "pictures, not numbers",
            body: "An imaging sonar the vehicle declares. Nothing renders it yet, so nothing is published on it." })
    : about !== undefined && about.messages === 0 && of.length === 0
      ? { title: "nothing has crossed it yet",
          body: about.way === "to"
            ? "The vehicle listens on this one. It fills in when a controller commands it."
            : "Declared by the vehicle, and silent so far." }
      : undefined;

  if (said !== undefined) {
    return (
      <div className="topic-plot">
        <div className="topic-said">
          <strong>{topic}</strong>
          <em>{said.title}</em>
          <p>{said.body}</p>
          {said.look !== undefined && onLook !== undefined ? (
            <button className="quiet small" onClick={() => onLook(said.look!)}>Look through it</button>
          ) : null}
        </div>
      </div>
    );
  }

  return (
    <div className="topic-plot">
      <canvas ref={canvas} />
      <div className="legend">
        <strong>{topic ?? "no topic chosen"}</strong>
        {fields.map((field, index) => {
          const last = of[of.length - 1]?.values[field];
          return (
            <button key={field} className={hidden.has(field) ? "off" : undefined}
                    style={{ borderColor: INKS[index % INKS.length] }}
                    onClick={() => setHidden((was) => {
                      const next = new Set(was);
                      if (next.has(field)) next.delete(field); else next.add(field);
                      return next;
                    })}>
              <span style={{ background: INKS[index % INKS.length] }} />
              {field}
              <em>{last === undefined ? "—" : short(last)}</em>
            </button>
          );
        })}
        {topic !== undefined && fields.length === 0 ? <em className="none">nothing numeric on it yet</em> : null}
      </div>
    </div>
  );
}

function short(v: number): string {
  const magnitude = Math.abs(v);
  if (magnitude >= 10000) return v.toFixed(0);
  if (magnitude >= 100) return v.toFixed(1);
  if (magnitude >= 1) return v.toFixed(2);
  return v.toFixed(3);
}
