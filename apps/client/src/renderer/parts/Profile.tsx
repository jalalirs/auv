// The last minute in section: the vehicle's depth over time, with the bottom
// under it. What a depth plot alone cannot show is whether two metres down is
// mid-water or a hand's breadth off the coral; this does.

import { useEffect, useRef } from "react";

export interface Moment { t: number; depth: number; speed: number; floor?: number }

export function Profile({ of }: { of: Moment[] }): React.JSX.Element {
  const canvas = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const surface = canvas.current;
    if (surface === null) return;
    const width = Math.max(1, Math.floor(surface.clientWidth * devicePixelRatio));
    const height = Math.max(1, Math.floor(surface.clientHeight * devicePixelRatio));
    if (surface.width !== width) surface.width = width;
    if (surface.height !== height) surface.height = height;
    const ink = surface.getContext("2d");
    if (ink === null) return;
    // The water column: paler where the light still reaches, darker below.
    const column = ink.createLinearGradient(0, 0, 0, height);
    column.addColorStop(0, "#0b2036");
    column.addColorStop(1, "#04070d");
    ink.fillStyle = column;
    ink.fillRect(0, 0, width, height);
    if (of.length < 2) return;

    const depths = of.map((m) => m.depth);
    const floors = of.map((m) => (m.floor === undefined ? undefined : -m.floor));
    let shallow = Math.min(...depths, ...floors.filter((f): f is number => f !== undefined));
    let deep = Math.max(...depths, ...floors.filter((f): f is number => f !== undefined));
    if (deep - shallow < 1) { const mid = (deep + shallow) / 2; shallow = mid - 0.5; deep = mid + 0.5; }
    const pad = (deep - shallow) * 0.08;
    shallow -= pad; deep += pad;
    const pixelsPerMetre = height / (deep - shallow);
    const y = (depth: number) => (depth - shallow) * pixelsPerMetre;
    const x = (i: number) => (i / (of.length - 1)) * width;

    // Depth lines every metre, or every five when the section is tall, with
    // their depth on the left. A section without a scale is a squiggle.
    const every = deep - shallow > 12 ? 5 : 1;
    ink.font = `${10 * devicePixelRatio}px system-ui, sans-serif`;
    ink.textBaseline = "middle";
    ink.lineWidth = devicePixelRatio;
    for (let d = Math.ceil(shallow / every) * every; d <= deep; d += every) {
      ink.strokeStyle = "rgba(90, 140, 200, 0.14)";
      ink.beginPath(); ink.moveTo(34 * devicePixelRatio, y(d)); ink.lineTo(width, y(d)); ink.stroke();
      ink.fillStyle = "#4d6485";
      ink.fillText(`${d} m`, 5 * devicePixelRatio, y(d));
    }

    // The bottom.
    if (floors.some((f) => f !== undefined)) {
      ink.beginPath();
      let started = false;
      for (let i = 0; i < of.length; i += 1) {
        const f = floors[i];
        if (f === undefined) continue;
        if (!started) { ink.moveTo(x(i), y(f)); started = true; } else ink.lineTo(x(i), y(f));
      }
      ink.lineTo(width, height); ink.lineTo(0, height); ink.closePath();
      const ground = ink.createLinearGradient(0, 0, 0, height);
      ground.addColorStop(0, "rgba(146, 110, 68, 0.75)");
      ground.addColorStop(1, "rgba(58, 44, 28, 0.85)");
      ink.fillStyle = ground;
      ink.fill();
      // The bottom itself, drawn over the fill, so the seabed has an edge.
      ink.beginPath();
      started = false;
      for (let i = 0; i < of.length; i += 1) {
        const f = floors[i];
        if (f === undefined) continue;
        if (!started) { ink.moveTo(x(i), y(f)); started = true; } else ink.lineTo(x(i), y(f));
      }
      ink.strokeStyle = "rgba(214, 176, 118, 0.85)";
      ink.lineWidth = 1.2 * devicePixelRatio;
      ink.stroke();
    }

    // The vehicle.
    ink.beginPath();
    ink.moveTo(x(0), y(depths[0]!));
    for (let i = 1; i < of.length; i += 1) ink.lineTo(x(i), y(depths[i]!));
    ink.strokeStyle = "#40c7f4";
    ink.lineWidth = 1.6 * devicePixelRatio;
    ink.lineJoin = "round";
    ink.stroke();
    const lastX = x(of.length - 1);
    const lastY = y(depths[depths.length - 1]!);
    ink.beginPath(); ink.arc(lastX, lastY, 5.5 * devicePixelRatio, 0, Math.PI * 2);
    ink.fillStyle = "rgba(64, 199, 244, 0.2)"; ink.fill();
    ink.beginPath(); ink.arc(lastX, lastY, 3 * devicePixelRatio, 0, Math.PI * 2);
    ink.fillStyle = "#40c7f4"; ink.fill();

    // Where it is now, and how much water is under it — the two numbers this
    // pane exists to answer.
    const last = of[of.length - 1]!;
    const under = last.floor === undefined ? undefined : last.depth - -last.floor;
    ink.font = `600 ${11 * devicePixelRatio}px system-ui, sans-serif`;
    ink.fillStyle = "#c9d6e6";
    ink.textAlign = "right";
    ink.textBaseline = "top";
    ink.fillText(`${last.depth.toFixed(2)} m down`, width - 8 * devicePixelRatio, 6 * devicePixelRatio);
    if (under !== undefined) {
      ink.font = `${10 * devicePixelRatio}px system-ui, sans-serif`;
      ink.fillStyle = "#9fb3cc";
      ink.fillText(`${Math.abs(under).toFixed(2)} m off the bottom`,
                   width - 8 * devicePixelRatio, 21 * devicePixelRatio);
    }
    ink.textAlign = "left";
    ink.fillStyle = "#4d6485";
    ink.font = `${9.5 * devicePixelRatio}px system-ui, sans-serif`;
    ink.textBaseline = "bottom";
    ink.fillText("a minute ago", 5 * devicePixelRatio, height - 4 * devicePixelRatio);
    ink.textAlign = "right";
    ink.fillText("now", width - 6 * devicePixelRatio, height - 4 * devicePixelRatio);
    ink.textAlign = "left";
  }, [of, of.length]);

  return <canvas ref={canvas} className="profile" />;
}
