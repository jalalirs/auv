// A big reef drawn whole: every colony a point, sized as the colony is and
// coloured as its form, so a reef of a million reads as the reef from afar;
// near where the camera looks, the colonies as their shapes, a few tens of
// thousands at most, drawn again as the view moves.
//
// The rows somebody edited are the world's items and drawn as such; here
// they are left out.

import * as THREE from "three";

import type { Near, Population } from "../platform/colonies.js";
import { CORAL_SHAPES, coralGeometry } from "./World3D.js";

const POINTS_VERTEX = `
  attribute float size;
  attribute vec3 colour;
  uniform float scale;
  varying vec3 vColour;
  varying float vPixels;
  void main() {
    vColour = colour;
    vec4 mv = modelViewMatrix * vec4(position, 1.0);
    vPixels = size <= 0.0 ? 0.0 : clamp(size * scale / -mv.z, 2.0, 28.0);
    gl_PointSize = vPixels;
    gl_Position = projectionMatrix * mv;
  }`;
const POINTS_FRAGMENT = `
  varying vec3 vColour;
  varying float vPixels;
  void main() {
    // Round when it is big enough to be seen round; a pixel or two is a square.
    vec2 d = gl_PointCoord - 0.5;
    if (vPixels > 4.0 && dot(d, d) > 0.25) discard;
    gl_FragColor = vec4(vColour, 1.0);
    #include <colorspace_fragment>
  }`;

/** Every colony of the population as a point on the ground. */
export function populationPoints(p: Population, floor: (x: number, y: number) => number): THREE.Points {
  const position = new Float32Array(p.count * 3), colour = new Float32Array(p.count * 3), size = new Float32Array(p.count);
  const c = new THREE.Color();
  const palette = p.forms.map((form) => new THREE.Color(CORAL_SHAPES[form]?.colour ?? CORAL_SHAPES.massive!.colour));
  for (let i = 0; i < p.count; i++) {
    const x = p.x[i]!, y = p.y[i]!;
    position.set([x, floor(x, y) + 0.05, -y], i * 3);
    c.copy(palette[p.form[i]!] ?? palette[0] ?? c);
    colour.set([c.r, c.g, c.b], i * 3);
    // A plate spreads twice its listed size.
    size[i] = Math.max(0.15, p.sizeM[i]!) * (p.forms[p.form[i]!] === "table" ? 2 : 1);
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.BufferAttribute(position, 3));
  geometry.setAttribute("colour", new THREE.BufferAttribute(colour, 3));
  geometry.setAttribute("size", new THREE.BufferAttribute(size, 1));
  geometry.userData.sizes = size.slice();
  const points = new THREE.Points(geometry, new THREE.ShaderMaterial({
    uniforms: { scale: { value: 800 } }, vertexShader: POINTS_VERTEX, fragmentShader: POINTS_FRAGMENT,
  }));
  points.frustumCulled = false;
  return points;
}

/** The rows that are drawn as items instead, left out of the points. */
export function leaveOut(points: THREE.Points, rows: Set<number>): void {
  const size = points.geometry.getAttribute("size") as THREE.BufferAttribute;
  const was = points.geometry.userData.sizes as Float32Array;
  const array = size.array as Float32Array;
  array.set(was);
  for (const row of rows) array[row] = 0;
  size.needsUpdate = true;
}

/** The colonies near a point as their shapes, instanced by form. */
export function nearbyInto(group: THREE.Group, p: Population, near: Near, at: { x: number; y: number }, radiusM: number,
                           floor: (x: number, y: number) => number, rows: Set<number>, most = 30000): void {
  for (const old of [...group.children]) {
    group.remove(old);
    (old as THREE.InstancedMesh).geometry?.dispose();
    ((old as THREE.InstancedMesh).material as THREE.Material | undefined)?.dispose();
  }
  const byForm = new Map<number, number[]>();
  for (const row of near.within(at.x, at.y, radiusM, most)) {
    if (rows.has(row)) continue;
    const list = byForm.get(p.form[row]!);
    if (list) list.push(row); else byForm.set(p.form[row]!, [row]);
  }
  const m = new THREE.Matrix4(), q = new THREE.Quaternion(), up = new THREE.Vector3(0, 1, 0), s = new THREE.Vector3(), v = new THREE.Vector3();
  for (const [k, list] of byForm) {
    const form = p.forms[k] ?? "massive";
    const mesh = new THREE.InstancedMesh(coralGeometry(form),
      new THREE.MeshStandardMaterial({ color: CORAL_SHAPES[form]?.colour ?? CORAL_SHAPES.massive!.colour, roughness: 0.75, side: THREE.DoubleSide }),
      list.length);
    list.forEach((row, i) => {
      const x = p.x[row]!, y = p.y[row]!, size = Math.max(0.15, p.sizeM[row]!);
      q.setFromAxisAngle(up, -(p.builtDeg[row]! * Math.PI) / 180);
      m.compose(v.set(x, floor(x, y) - 0.02, -y), q, s.set(size, size, size));
      mesh.setMatrixAt(i, m);
    });
    mesh.userData.rows = list;
    mesh.computeBoundingSphere();
    group.add(mesh);
  }
}
