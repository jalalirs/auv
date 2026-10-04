// The work drawn over a place's chart: the launch, the transit between stages
// dashed, each stage as what it is — a route, a line, a rectangle and its
// lanes, a point and its ring — the chosen one in the vehicle's colour, each
// numbered where it ends. One drawing for the designer and for Fly, so the
// plan somebody flies looks like the plan somebody drew.

import { geometryOf, type Drawn, type Leg, type P, type Stage } from "../catalog/stages.js";
import type { Frame } from "./SiteChart.js";

export function drawStages(g: CanvasRenderingContext2D, frame: Frame, stages: Stage[], legs: Leg[],
                           drawn: Drawn[], chosen: number | undefined, launch: P): void {
  const { toX, toY, perM } = frame;
    const ink = (on: boolean, drawnOne: boolean) => (on ? "#f0a84f" : drawnOne ? "#1b6e93" : "rgba(27,110,147,.55)");
    // The launch.
    g.fillStyle = "#4fd48a"; g.strokeStyle = "#0b2a1c"; g.lineWidth = 2;
    g.beginPath(); g.moveTo(toX(launch.x), toY(launch.y) - 9); g.lineTo(toX(launch.x) + 8, toY(launch.y) + 6);
    g.lineTo(toX(launch.x) - 8, toY(launch.y) + 6); g.closePath(); g.fill(); g.stroke();

    stages.forEach((stage, i) => {
      const leg = legs[i];
      if (!leg) return;
      const geo = geometryOf(stage, drawn, leg.from);
      const on = i === chosen;
      g.strokeStyle = ink(on, geo.drawn); g.fillStyle = ink(on, geo.drawn);
      g.lineWidth = on ? 3 : 2;
      // How it gets there.
      const first = geo.route?.[0] ?? geo.line?.[0] ?? geo.area?.[0] ?? geo.point;
      if (first && (first.x !== leg.from.x || first.y !== leg.from.y)) {
        g.save(); g.setLineDash([4, 5]); g.lineWidth = 1.4; g.globalAlpha = 0.7;
        g.beginPath(); g.moveTo(toX(leg.from.x), toY(leg.from.y)); g.lineTo(toX(first.x), toY(first.y)); g.stroke();
        g.restore();
      }
      if (geo.route?.length) {
        g.beginPath();
        geo.route.forEach((p, k) => (k === 0 ? g.moveTo(toX(p.x), toY(p.y)) : g.lineTo(toX(p.x), toY(p.y))));
        g.stroke();
        geo.route.forEach((p) => { g.beginPath(); g.arc(toX(p.x), toY(p.y), on ? 4.5 : 3.5, 0, Math.PI * 2); g.fill(); });
      }
      if (geo.line) {
        const [a, b] = geo.line;
        g.beginPath(); g.moveTo(toX(a.x), toY(a.y)); g.lineTo(toX(b.x), toY(b.y)); g.stroke();
        const ang = Math.atan2(toY(b.y) - toY(a.y), toX(b.x) - toX(a.x));
        g.beginPath(); g.moveTo(toX(b.x), toY(b.y));
        g.lineTo(toX(b.x) - 10 * Math.cos(ang - 0.4), toY(b.y) - 10 * Math.sin(ang - 0.4));
        g.lineTo(toX(b.x) - 10 * Math.cos(ang + 0.4), toY(b.y) - 10 * Math.sin(ang + 0.4));
        g.closePath(); g.fill();
      }
      if (geo.area) {
        const [w, , n] = [geo.area[0]!, geo.area[1]!, geo.area[2]!];
        const left = toX(w.x), right = toX(geo.area[1]!.x), top = toY(n.y), bottom = toY(w.y);
        g.save(); g.globalAlpha = on ? 0.22 : 0.14; g.fillRect(left, top, right - left, bottom - top); g.restore();
        g.strokeRect(left, top, right - left, bottom - top);
        // The lanes it will fly, faintly.
        const swath = Math.max(0.05, Number(stage["swathM"] ?? 3)) * perM;
        g.save(); g.globalAlpha = 0.35; g.lineWidth = 1;
        for (let y = top + swath / 2; y < bottom; y += Math.max(swath, 3)) {
          g.beginPath(); g.moveTo(left + 2, y); g.lineTo(right - 2, y); g.stroke();
        }
        g.restore();
      }
      if (geo.point) {
        g.beginPath(); g.arc(toX(geo.point.x), toY(geo.point.y), on ? 6 : 5, 0, Math.PI * 2); g.fill();
        if (geo.ring) {
          g.save(); g.setLineDash([3, 3]);
          g.beginPath(); g.arc(toX(geo.point.x), toY(geo.point.y), geo.ring * perM, 0, Math.PI * 2); g.stroke();
          g.restore();
        }
      }
      // Its number, where it ends.
      g.font = "600 11px system-ui"; g.textAlign = "center"; g.textBaseline = "middle";
      g.fillStyle = "#04080f";
      g.beginPath(); g.arc(toX(leg.to.x) + 11, toY(leg.to.y) - 11, 8, 0, Math.PI * 2); g.fill();
      g.fillStyle = on ? "#f0a84f" : "#dbe3ec";
      g.fillText(String(i + 1), toX(leg.to.x) + 11, toY(leg.to.y) - 11);
    });

}
