// Where a vehicle's thrusters are and which way they push.
//
// Two views, plan and side, drawn from the catalogue's positions and
// directions and nothing else — so what the page shows is what the allocator
// uses, and a thruster that points the wrong way in the file points the wrong
// way here too, which is the point.

import type { Thruster } from "../physics/dynamics.js";

interface View {
  name: string;
  /** Which body axes map to the drawing's right and up. */
  right: 0 | 1 | 2;
  up: 0 | 1 | 2;
  flipUp?: boolean;
  labels: [string, string, string, string];   // right, left, up, down
}

const VIEWS: View[] = [
  { name: "from above", right: 0, up: 1, flipUp: true, labels: ["bow", "stern", "port", "starboard"] },
  { name: "from starboard", right: 0, up: 2, labels: ["bow", "stern", "up", "down"] },
];

export function ThrusterDiagram({ units, reachM }: {
  units: Thruster[];
  reachM: [number, number, number];
}): React.JSX.Element {
  const size = 220, pad = 34;
  const span = Math.max(reachM[0], reachM[1], reachM[2], 0.3) * 1.25;
  const scale = (size - 2 * pad) / span;
  return (
    <div className="thruster-views">
      {VIEWS.map((view) => {
        const sx = (p: number[]): number => size / 2 + p[view.right]! * scale;
        const sy = (p: number[]): number => size / 2 - (view.flipUp ? -1 : 1) * p[view.up]! * scale;
        return (
          <figure key={view.name} className="thruster-view">
            <svg viewBox={`0 0 ${size} ${size}`} role="img" aria-label={`Thrusters seen ${view.name}`}>
              <defs>
                <marker id="arrow" viewBox="0 0 6 6" refX="5" refY="3" markerWidth="5" markerHeight="5" orient="auto">
                  <path d="M0,0 L6,3 L0,6 Z" className="arrow-head" />
                </marker>
              </defs>
              <line x1={pad} x2={size - pad} y1={size / 2} y2={size / 2} className="axis" />
              <line y1={pad} y2={size - pad} x1={size / 2} x2={size / 2} className="axis" />
              <text x={size - pad + 4} y={size / 2 + 4} className="axis-label">{view.labels[0]}</text>
              <text x={pad - 4} y={size / 2 + 4} className="axis-label end">{view.labels[1]}</text>
              <text x={size / 2} y={pad - 6} className="axis-label mid">{view.labels[2]}</text>
              <text x={size / 2} y={size - pad + 14} className="axis-label mid">{view.labels[3]}</text>
              <ellipse cx={size / 2} cy={size / 2} rx={Math.max(reachM[view.right] / 2, 0.08) * scale * 0.9}
                       ry={Math.max(reachM[view.up] / 2, 0.06) * scale * 0.9} className="hull" />
              {units.map((u) => {
                const x = sx(u.position), y = sy(u.position);
                const len = 0.16 * scale;
                const dx = u.direction[view.right]! * len;
                const dy = -(view.flipUp ? -1 : 1) * u.direction[view.up]! * len;
                const inPlane = Math.hypot(dx, dy) > 1;
                return (
                  <g key={u.name}>
                    {inPlane
                      ? <line x1={x} y1={y} x2={x + dx} y2={y + dy} className="thrust" markerEnd="url(#arrow)" />
                      : <circle cx={x} cy={y} r={5} className="thrust-out" />}
                    <circle cx={x} cy={y} r={4} className="unit" />
                    <text x={x + 7} y={y - 7} className="unit-label">{u.name}</text>
                  </g>
                );
              })}
            </svg>
            <figcaption>{view.name}</figcaption>
          </figure>
        );
      })}
    </div>
  );
}
