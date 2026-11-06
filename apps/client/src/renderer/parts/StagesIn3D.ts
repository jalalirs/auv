// A mission's work drawn in the world, in three dimensions: the launch at the
// surface, the transit between stages dashed, each stage as what it is — a
// route at its depth, a transect and a survey's lanes draped over the ground
// at their altitude, a point and its ring — the chosen one in the vehicle's
// colour, each numbered where it ends. The same stages the chart drew, at the
// heights they are flown, so a lane that would run into a bommie is seen to.
//
// Marks are sprites, a constant size on the screen however far the camera is:
// a tank two metres across and a reef two kilometres across read the same.

import * as THREE from "three";
import { Line2 } from "three/examples/jsm/lines/Line2.js";
import { LineGeometry } from "three/examples/jsm/lines/LineGeometry.js";
import { LineMaterial } from "three/examples/jsm/lines/LineMaterial.js";

import { geometryOf, handlesOf, heightOf, type Drawn, type Leg, type P, type Stage } from "../catalog/stages.js";

/** What of a mission the view draws. */
export interface PlanIn3D {
  stages: Stage[];
  legs: Leg[];
  drawn: Drawn[];
  chosen?: number;
  launch: P;
  /** The points of a drawing not finished yet. */
  drawing?: P[];
  /** The chosen stage's points can be taken hold of and moved. */
  editing?: boolean;
}

/** How the view stands: the ground's height in the scene, the depth stretch,
 *  how big the world is and the size of the screen, which fat lines need. */
export interface Scale {
  floor: (x: number, y: number) => number;
  lift: number;
  acrossM: number;
  resolution: THREE.Vector2;
}

const CHOSEN = 0xf0a84f, DRAWN = 0x7fd3ff, LAUNCH = 0x4fd48a, DRAWING = 0xffe066;

export function stagesInto(group: THREE.Group, plan: PlanIn3D, scale: Scale): void {
  const { floor, lift, acrossM } = scale;
  const step = acrossM / 150;
  // A point at a stage's height, in the scene; never above the surface.
  const at = (p: P, height: ReturnType<typeof heightOf>, over = 0) => {
    const y = "depthM" in height ? -height.depthM * lift : floor(p.x, p.y) + height.altitudeM * lift;
    return new THREE.Vector3(p.x, Math.min(0, y) + over, -p.y);
  };
  // A path between points, following the ground when it is flown over it.
  const along = (points: P[], height: ReturnType<typeof heightOf>, close = false) => {
    const out: THREE.Vector3[] = [];
    const list = close && points.length > 2 ? [...points, points[0]!] : points;
    list.forEach((p, i) => {
      if (i > 0 && "altitudeM" in height) {
        const a = list[i - 1]!;
        const n = Math.min(200, Math.max(1, Math.ceil(Math.hypot(p.x - a.x, p.y - a.y) / step)));
        for (let k = 1; k < n; k++) out.push(at({ x: a.x + ((p.x - a.x) * k) / n, y: a.y + ((p.y - a.y) * k) / n }, height));
      }
      out.push(at(p, height));
    });
    return out;
  };
  const line = (points: THREE.Vector3[], colour: number, width: number, how: { dashed?: boolean; opacity?: number; stage?: number } = {}) => {
    if (points.length < 2) return;
    const geometry = new LineGeometry();
    geometry.setPositions(points.flatMap((p) => [p.x, p.y, p.z]));
    const material = new LineMaterial({
      color: colour, linewidth: width, worldUnits: false, transparent: true, opacity: how.opacity ?? 1,
      depthTest: false, dashed: how.dashed ?? false, dashSize: step * 1.2, gapSize: step * 1.2,
    });
    material.resolution.copy(scale.resolution);
    const drawnLine = new Line2(geometry, material);
    drawnLine.computeLineDistances();
    drawnLine.renderOrder = 10;
    if (how.stage !== undefined) drawnLine.userData.stage = how.stage;
    group.add(drawnLine);
  };
  // A stage's own line, over a dark edge so it reads on the pale shallows and
  // the navy deep alike.
  const edged = (points: THREE.Vector3[], colour: number, width: number, how: { opacity?: number; stage?: number }) => {
    line(points, 0x04080f, width + 3, { opacity: 0.55 * (how.opacity ?? 1) });
    line(points, colour, width, how);
  };
  const mark = (where: THREE.Vector3, look: string, size: number, data: Record<string, number> = {}) => {
    const sprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: textureOf(look), depthTest: false, sizeAttenuation: false }));
    sprite.position.copy(where);
    sprite.scale.set(size, size, 1);
    sprite.renderOrder = 12;
    Object.assign(sprite.userData, data);
    group.add(sprite);
  };

  // The launch, at the surface.
  mark(new THREE.Vector3(plan.launch.x, 0, -plan.launch.y), "launch", 0.032);

  let was = new THREE.Vector3(plan.launch.x, 0, -plan.launch.y);
  plan.stages.forEach((stage, i) => {
    const leg = plan.legs[i];
    if (!leg) return;
    const geo = geometryOf(stage, plan.drawn, leg.from);
    const height = heightOf(stage);
    const on = i === plan.chosen;
    const colour = on ? CHOSEN : DRAWN;
    const opacity = on || geo.drawn ? 1 : 0.55;
    const width = on ? 3.5 : 2.5;

    // How it gets there, from where the stage before it left the vehicle.
    const first = geo.route?.[0] ?? geo.line?.[0] ?? geo.area?.[0] ?? geo.point;
    if (first) {
      const there = at(first, height);
      if (there.distanceTo(was) > step / 4) line([was, there], colour, 2, { dashed: true, opacity: 0.85, stage: i });
    }
    if (geo.route?.length) {
      edged(along(geo.route, height), colour, width, { opacity, stage: i });
      if (!(on && plan.editing)) for (const p of geo.route) mark(at(p, height), on ? "dot-on" : "dot", 0.014, { stage: i });
    }
    if (geo.line) {
      edged(along(geo.line, height), colour, width, { opacity, stage: i });
      mark(at(geo.line[1], height), on ? "end-on" : "end", 0.02, { stage: i });
    }
    if (geo.area) {
      const [sw, , ne] = [geo.area[0]!, geo.area[1]!, geo.area[2]!];
      edged(along(geo.area, height, true), colour, width, { opacity, stage: i });
      group.add(sheet(sw, ne, at, height, colour, on ? 0.22 : 0.12, i));
      // The lanes it will fly, faintly.
      const swath = Math.max(0.05, Number(stage["swathM"] ?? 3));
      const lanes = Math.min(80, Math.floor((ne.y - sw.y) / swath));
      for (let k = 0; k < lanes; k++) {
        const y = sw.y + swath / 2 + k * swath;
        line(along([{ x: sw.x, y }, { x: ne.x, y }], height), colour, 1, { opacity: 0.5, stage: i });
      }
    }
    if (geo.point) {
      mark(at(geo.point, height), on ? "dot-on" : "dot", 0.02, { stage: i });
      if (geo.ring) {
        const ring: P[] = [];
        for (let k = 0; k < 48; k++) {
          const a = (k / 48) * Math.PI * 2;
          ring.push({ x: geo.point.x + Math.cos(a) * geo.ring, y: geo.point.y + Math.sin(a) * geo.ring });
        }
        line(along(ring, height, true), colour, 1.5, { dashed: true, opacity, stage: i });
      }
    }
    // What can be taken hold of on the chosen stage.
    if (on && plan.editing) handlesOf(stage).forEach((p, k) => mark(at(p, height), "handle", 0.022, { stage: i, handle: k }));

    // Its number, where it ends.
    const end = at(leg.to, height);
    mark(end.clone().add(new THREE.Vector3(0, step * 1.5, 0)), on ? `n-on:${i + 1}` : `n:${i + 1}`, 0.03, { stage: i });
    was = end;
  });

  // What is being drawn, before it is finished: on the ground.
  if (plan.drawing?.length) {
    const ground = { altitudeM: 0.05 };
    line(along(plan.drawing, ground), DRAWING, 2, { dashed: true });
    for (const p of plan.drawing) mark(at(p, ground), "drawing", 0.016);
  }
}

/** An area's sheet, draped over the ground at its altitude. */
function sheet(sw: P, ne: P, at: (p: P, h: ReturnType<typeof heightOf>) => THREE.Vector3,
               height: ReturnType<typeof heightOf>, colour: number, opacity: number, stage: number): THREE.Mesh {
  const n = 24;
  const geometry = new THREE.PlaneGeometry(1, 1, n, n);
  const position = geometry.attributes.position as THREE.BufferAttribute;
  for (let k = 0; k < position.count; k++) {
    const x = sw.x + (position.getX(k) + 0.5) * (ne.x - sw.x), y = sw.y + (position.getY(k) + 0.5) * (ne.y - sw.y);
    const p = at({ x, y }, height);
    position.setXYZ(k, p.x, p.y, p.z);
  }
  const mesh = new THREE.Mesh(geometry, new THREE.MeshBasicMaterial({
    color: colour, transparent: true, opacity, depthTest: false, depthWrite: false, side: THREE.DoubleSide,
  }));
  mesh.renderOrder = 9;
  mesh.userData.stage = stage;
  return mesh;
}

// Each look drawn once, then shared.
const looks = new Map<string, THREE.CanvasTexture>();
function textureOf(look: string): THREE.CanvasTexture {
  const known = looks.get(look);
  if (known) return known;
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = 64;
  const g = canvas.getContext("2d")!;
  const hex = (c: number) => `#${c.toString(16).padStart(6, "0")}`;
  const disc = (r: number, fill: string, stroke?: string, width = 6) => {
    g.beginPath(); g.arc(32, 32, r, 0, Math.PI * 2);
    g.fillStyle = fill; g.fill();
    if (stroke) { g.lineWidth = width; g.strokeStyle = stroke; g.stroke(); }
  };
  if (look === "launch") {
    g.beginPath(); g.moveTo(32, 58); g.lineTo(8, 12); g.lineTo(56, 12); g.closePath();
    g.fillStyle = hex(LAUNCH); g.fill(); g.lineWidth = 5; g.strokeStyle = "#0b2a1c"; g.stroke();
  } else if (look.startsWith("n")) {
    const [kind, text] = look.split(":");
    disc(26, "#04080f", kind === "n-on" ? hex(CHOSEN) : "#dbe3ec", 4);
    g.font = "700 30px system-ui"; g.textAlign = "center"; g.textBaseline = "middle";
    g.fillStyle = kind === "n-on" ? hex(CHOSEN) : "#dbe3ec";
    g.fillText(text ?? "", 32, 34);
  } else if (look === "handle") {
    disc(24, "#ffffff", hex(CHOSEN), 9);
  } else if (look === "drawing") {
    disc(24, hex(DRAWING), "#04080f", 5);
  } else {
    const on = look.endsWith("-on");
    disc(look.startsWith("end") ? 20 : 24, hex(on ? CHOSEN : DRAWN), "#04080f", 5);
  }
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  looks.set(look, texture);
  return texture;
}
