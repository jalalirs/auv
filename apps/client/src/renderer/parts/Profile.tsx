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
    ink.fillStyle = "#050a12";
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

    // Depth lines every metre, or every five when the section is tall.
    const every = deep - shallow > 12 ? 5 : 1;
    ink.strokeStyle = "#13233a";
    ink.fillStyle = "#4d6485";
    ink.font = `${10 * devicePixelRatio}px system-ui, sans-serif`;
    ink.textBaseline = "top";
    ink.lineWidth = devicePixelRatio;
    for (let d = Math.ceil(shallow / every) * every; d <= deep; d += every) {
      ink.beginPath(); ink.moveTo(0, y(d)); ink.lineTo(width, y(d)); ink.stroke();
      // Labels sit to the right of the pane's own name, which lives top left.
      if (y(d) > 22 * devicePixelRatio) ink.fillText(`${d} m`, 4 * devicePixelRatio, y(d) + 2 * devicePixelRatio);
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
      ink.fillStyle = "rgba(120, 88, 52, 0.55)";
      ink.fill();
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
    ink.beginPath(); ink.arc(lastX, lastY, 3 * devicePixelRatio, 0, Math.PI * 2);
    ink.fillStyle = "#40c7f4"; ink.fill();
  }, [of, of.length]);

  return <canvas ref={canvas} className="profile" />;
}
