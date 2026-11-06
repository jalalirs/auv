// A world in three dimensions, as a modelling tool's viewport: its terrain,
// the water over it and everything in it, to orbit, choose in (one, several,
// a box of them), and move, turn and grow with a gizmo or by dragging.
//
// Drawn here, in the application, and not by the simulator: it is instant,
// works offline and costs the shared machines nothing. What a camera on a
// vehicle would really see is the simulator's, and a dive.
//
// The world's frame is x east, y north, z up in metres, origin at the middle.
// three.js is y up, so a world point (x, y, z) is drawn at (x, z * lift, -y),
// where lift stretches the depths: a reef three kilometres across and forty
// metres deep is a flat plate at its true shape.

import { useEffect, useImperativeHandle, useRef } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { TransformControls } from "three/examples/jsm/controls/TransformControls.js";
import { ViewHelper } from "three/examples/jsm/helpers/ViewHelper.js";
import { Line2 } from "three/examples/jsm/lines/Line2.js";
import type { LineMaterial } from "three/examples/jsm/lines/LineMaterial.js";

import { groundAt, type Ground } from "./SiteChart.js";
import { stagesInto, type PlanIn3D } from "./StagesIn3D.js";

/** Something drawn in the world: an item of its reef or its structures. */
export interface Shown {
  id: string;
  /** A piece of equipment's kind, "coral", "object" for a model, "reef" for a reef. */
  kind: string;
  x: number;
  y: number;
  /** Metres up, when it is not on the ground or the surface. */
  z?: number;
  headingDeg?: number;
  /** A built colony's turn in the build, which its headingDeg turns from. */
  builtDeg?: number;
  /** A coral's size, or across, along and up for a model or a reef. */
  sizeM?: number | [number, number, number];
  form?: string;
  route?: { x: number; y: number }[];
  ends?: { x: number; y: number; z?: number }[];
  corners?: { x: number; y: number }[];
  radiusM?: number;
  heightM?: number;
  name?: string;
  locked?: boolean;
}

export interface Showing { terrain: boolean; water: boolean; structures: boolean; reef: boolean }

/** What a press in the view does. */
export type Mode = "select" | "move" | "rotate" | "scale" | "place" | "scatter" | "measure";

/** How far the selection has gone since the gizmo or a drag took hold of it. */
export interface Delta { dx: number; dy: number; turnDeg: number; scale: number }

export type ViewName = "top" | "front" | "right" | "persp";

/** What the editor can ask of the view. */
export interface View3D {
  view: (which: ViewName) => void;
  /** Frame these items, or the whole world when none. */
  frame: (ids: string[]) => void;
  /** Frame these points of the world, from the ground under them to the surface. */
  frameOn: (points: { x: number; y: number }[]) => void;
}

/** A tank's inside, as its site record says: the water is kept within glass,
 *  round or a box. Metres, z up, z = 0 at the surface. */
export interface Glass {
  min: [number, number, number];
  max: [number, number, number];
  round?: { centre: [number, number]; radiusM: number };
}

/** One blue ramp, light in the shallows to navy in the deep, like a chart. */
export function chartColour(depthM: number, deepestM: number): [number, number, number] {
  if (depthM <= 0) return [222, 214, 190];
  const t = Math.min(1, Math.sqrt(depthM / Math.max(deepestM, 1)));
  const stops: [number, [number, number, number]][] = [
    [0, [205, 233, 240]], [0.25, [146, 201, 222]], [0.5, [84, 155, 196]], [0.75, [40, 102, 158]], [1, [18, 50, 96]],
  ];
  for (let i = 1; i < stops.length; i++) {
    const [t1, c1] = stops[i]!, [t0, c0] = stops[i - 1]!;
    if (t <= t1) {
      const f = (t - t0) / (t1 - t0);
      return [c0[0] + (c1[0] - c0[0]) * f, c0[1] + (c1[1] - c0[1]) * f, c0[2] + (c1[2] - c0[2]) * f];
    }
  }
  return stops[stops.length - 1]![1];
}

/** A contour interval that draws five to fifteen lines over this range. */
export function contourStep(deepestM: number): number {
  for (const step of [0.5, 1, 2, 5, 10, 20, 50, 100]) if (deepestM / step <= 15) return step;
  return 200;
}

/** The chart drawn on the terrain: the ramp, hillshade from the north-west, thin contours. */
function chartTexture(ground: Ground, size = 1024): THREE.CanvasTexture {
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = size;
  const g = canvas.getContext("2d")!;
  const image = g.createImageData(size, size);
  const { acrossM } = ground;
  const deepest = deepestOf(ground);
  const step = contourStep(deepest);
  const cell = acrossM / size;
  const at = (i: number, j: number) => groundAt(ground, (i / size - 0.5) * acrossM, (0.5 - j / size) * acrossM);
  const row: number[] = new Array(size + 1);
  let above: number[] = Array.from({ length: size + 1 }, (_, i) => at(i, 0));
  for (let j = 0; j < size; j++) {
    for (let i = 0; i <= size; i++) row[i] = at(i, j + 1);
    for (let i = 0; i < size; i++) {
      const d = above[i]!;
      const dx = (above[i + 1]! - d) / cell, dy = (row[i]! - d) / cell;
      // Light from the north-west, forty-five degrees up; depth is down.
      const shade = Math.max(0.55, Math.min(1.25, 1 + (dx - dy) * 0.6));
      let [r, gr, b] = chartColour(d, deepest);
      const band = (v: number) => Math.floor(v / step);
      if (d > 0 && (band(d) !== band(above[i + 1]!) || band(d) !== band(row[i]!))) {
        r *= 0.72; gr *= 0.76; b *= 0.82;
      }
      const k = (j * size + i) * 4;
      image.data[k] = Math.min(255, r * shade);
      image.data[k + 1] = Math.min(255, gr * shade);
      image.data[k + 2] = Math.min(255, b * shade);
      image.data[k + 3] = 255;
    }
    above = row.slice();
  }
  g.putImageData(image, 0, 0);
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.anisotropy = 4;
  return texture;
}

/** How much the depths are stretched so the shape of the ground can be seen. */
/** The deepest the ground goes, at least 1 m. A loop, since a whole ground
 *  spread into Math.max overflows the stack. */
function deepestOf(ground: Ground): number {
  let deepest = 1;
  for (const d of ground.depth) if (Number.isFinite(d) && d > deepest) deepest = d;
  return deepest;
}

export function liftOf(ground: Ground): number {
  const deepest = deepestOf(ground);
  return Math.min(12, Math.max(1, ground.acrossM / (deepest * 25)));
}

const COLOURS: Record<string, number> = {
  transponder: 0xf2c230, "mooring-block": 0x8a8f94, "nursery-frame": 0xd9822b, "marker-post": 0xe94f37,
  ship: 0xeeeeee, buoy: 0xf26b1d, dredger: 0xb5651d, pipeline: 0x3b5f8a, "mooring-line": 0x222222,
  "restoration-cell": 0x2e9e6e, object: 0x5d7fa8, reef: 0xe0735c,
};
const CHOSEN = 0xff8a3d;
const SURFACE = new Set(["ship", "buoy", "dredger"]);

export function World3D({ ground, glass, items, showing, selected, mode, snap, grid, ghost, brush, measure, plan, api,
                          onPick, onSelect, onTransformStart, onTransform, onTransformEnd, onHover, onDrop, onHandle }: {
  ground: Ground;
  /** A tank: drawn as its glass and the water in it, the ground cut to it. */
  glass?: Glass;
  items: Shown[];
  showing: Showing;
  selected: string[];
  mode: Mode;
  /** Moves by whole metres, turns by fifteen degrees, grows by tenths. */
  snap: boolean;
  grid: boolean;
  /** What is in hand, drawn faintly where it would go. */
  ghost?: Shown;
  /** The scatter brush, a ring on the ground. */
  brush?: { x: number; y: number; radiusM: number };
  /** A tape between two points on the ground. */
  measure?: { x: number; y: number }[];
  /** A mission's work, drawn at the heights it is flown. */
  plan?: PlanIn3D;
  api?: React.Ref<View3D>;
  /** A click on the ground with something in hand, a brush or a tape; and
   *  which of a plan's stages was clicked, if one was. */
  onPick: (at: { x: number; y: number }, how: { shift: boolean; stage?: number }) => void;
  onSelect: (ids: string[], how: "replace" | "add" | "toggle") => void;
  onTransformStart: () => void;
  onTransform: (delta: Delta) => void;
  onTransformEnd: () => void;
  onHover?: (at: { x: number; y: number } | undefined) => void;
  /** Something dragged in from the asset browser and let go over the ground. */
  onDrop?: (key: string, at: { x: number; y: number }) => void;
  /** A point of the chosen stage taken hold of, dragged over the ground and let go. */
  onHandle?: (k: number, at: { x: number; y: number }, phase: "start" | "move" | "end") => void;
}): React.JSX.Element {
  const host = useRef<HTMLDivElement>(null);
  const scene = useRef<{
    renderer: THREE.WebGLRenderer; scene: THREE.Scene; camera: THREE.PerspectiveCamera;
    controls: OrbitControls; gizmo: TransformControls; proxy: THREE.Object3D;
    terrain: THREE.Mesh; water: THREE.Object3D; things: THREE.Group; corals: THREE.Group; marks: THREE.Group;
    overlay: THREE.Group; plan: THREE.Group; grid: THREE.Object3D; lift: number;
    /** The drawing's size in pixels, which fat lines are drawn to. */
    resolution: THREE.Vector2;
    /** Where each item is in the scene, and how big, for framing and boxes. */
    where: Map<string, { at: THREE.Vector3; r: number }>;
    dragging: boolean;
  } | undefined>(undefined);
  const said = useRef({ onPick, onSelect, onTransformStart, onTransform, onTransformEnd, onHover, onDrop, onHandle, selected, mode, items, plan });
  said.current = { onPick, onSelect, onTransformStart, onTransform, onTransformEnd, onHover, onDrop, onHandle, selected, mode, items, plan };

  useImperativeHandle(api, () => ({
    view: (which) => {
      const s = scene.current;
      if (!s) return;
      const r = s.camera.position.distanceTo(s.controls.target);
      const t = s.controls.target;
      const dir = which === "top" ? new THREE.Vector3(0, 1, 0.002)
        : which === "front" ? new THREE.Vector3(0, 0.03, 1)
        : which === "right" ? new THREE.Vector3(1, 0.03, 0)
        : new THREE.Vector3(0.45, 0.55, 0.75);
      s.camera.position.copy(t).addScaledVector(dir.normalize(), r);
      s.controls.update();
    },
    frame: (ids) => {
      const s = scene.current;
      if (!s) return;
      const box = new THREE.Box3();
      for (const id of ids) {
        const w = s.where.get(id);
        if (w) box.expandByPoint(w.at.clone().addScalar(w.r)).expandByPoint(w.at.clone().addScalar(-w.r));
      }
      if (box.isEmpty()) box.setFromObject(s.terrain);
      aim(s, box);
    },
    frameOn: (points) => {
      const s = scene.current;
      if (!s || !points.length) return;
      const box = new THREE.Box3();
      for (const p of points) {
        box.expandByPoint(new THREE.Vector3(p.x, floor(ground, p.x, p.y, s.lift), -p.y));
        box.expandByPoint(new THREE.Vector3(p.x, 0, -p.y));
      }
      aim(s, box);
    },
  }), [ground]);

  /** The camera on a box, from the side it looks from now. */
  const aim = (s: NonNullable<typeof scene.current>, box: THREE.Box3) => {
    const centre = box.getCenter(new THREE.Vector3());
    const size = Math.max(box.getSize(new THREE.Vector3()).length() / 2, ground.acrossM / 400);
    const far = size / Math.sin((s.camera.fov * Math.PI) / 360) * 2;
    const dir = s.camera.position.clone().sub(s.controls.target).normalize();
    s.controls.target.copy(centre);
    s.camera.position.copy(centre).addScaledVector(dir, far);
    s.controls.update();
  };

  // The scene, once per ground.
  useEffect(() => {
    const el = host.current;
    if (!el) return;
    const lift = glass ? 1 : liftOf(ground);
    const across = ground.acrossM;
    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.autoClear = false;
    el.appendChild(renderer.domElement);
    const world = new THREE.Scene();
    world.background = new THREE.Color(0x0d2236);
    world.fog = new THREE.Fog(0x0d2236, across * 1.2, across * 4);
    const camera = new THREE.PerspectiveCamera(45, 1, across / 2000, across * 20);
    camera.position.set(across * 0.45, across * 0.55, across * 0.75);
    const controls = new OrbitControls(camera, renderer.domElement);
    // Look at the middle of the seabed, wherever it is: 10 m down off a reef,
    // half a metre in a tank.
    let total = 0, n = 0;
    for (const d of ground.depth) if (Number.isFinite(d)) { total += Math.max(0, d); n++; }
    const middle = n ? total / n : 0;
    controls.target.set(0, -middle * lift, 0);
    controls.maxPolarAngle = Math.PI * 0.495;
    controls.enableDamping = true;
    controls.dampingFactor = 0.12;
    controls.update();

    world.add(new THREE.HemisphereLight(0xdfefff, 0x1b2a38, 1.1));
    const sun = new THREE.DirectionalLight(0xffffff, 1.6);
    sun.position.set(-across, across * 1.5, -across * 0.6);
    world.add(sun);
    let gridAt = -middle * lift, gridSize = across, gridStep = niceStep(across / 20);
    if (glass) {
      // A tank stands in a hall: look at the whole of it, from a little above.
      const tall = glass.max[2] - glass.min[2];
      const wide = Math.max(glass.max[0] - glass.min[0], glass.max[1] - glass.min[1]);
      const reach = Math.max(tall, wide) * 1.7;
      world.background = new THREE.Color(0x101c28);
      world.fog = null;
      camera.near = reach / 500;
      camera.far = reach * 40;
      camera.position.set(reach * 0.55, glass.min[2] + tall * 0.85, reach * 0.95);
      controls.target.set(0, glass.min[2] + tall * 0.45, 0);
      controls.maxPolarAngle = Math.PI * 0.62;
      controls.update();
      gridAt = glass.min[2] - 1 + 0.01;
      gridSize = Math.ceil(wide * 3.2);
      gridStep = 1;
    }

    // A tank's column is walls: finer, or its faces zig-zag into streaks.
    const segments = Math.min(glass ? 400 : 255, ground.columns - 1);
    const plane = new THREE.PlaneGeometry(across, across, segments, segments);
    plane.rotateX(-Math.PI / 2);
    const position = plane.attributes.position as THREE.BufferAttribute;
    for (let k = 0; k < position.count; k++) {
      const x = position.getX(k), y = -position.getZ(k);
      position.setY(k, -groundAt(ground, x, y) * lift);
    }
    if (glass) inTheTank(plane, glass);
    plane.computeVertexNormals();
    const terrain = new THREE.Mesh(plane, glass
      ? new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.92 })
      : new THREE.MeshStandardMaterial({ map: chartTexture(ground), roughness: 0.95 }));
    terrain.name = "terrain";
    world.add(terrain);

    const water = glass ? tank(world, glass) : new THREE.Mesh(
      new THREE.PlaneGeometry(across * 1.02, across * 1.02).rotateX(-Math.PI / 2),
      new THREE.MeshStandardMaterial({ color: 0x3f8fc4, transparent: true, opacity: 0.18, depthWrite: false, side: THREE.DoubleSide }));
    world.add(water);

    const lines = Math.max(2, Math.round(gridSize / gridStep));
    const gridLines = new THREE.GridHelper(lines * gridStep, lines, 0x7fa6c4, 0x4a6a84);
    (gridLines.material as THREE.Material).transparent = true;
    (gridLines.material as THREE.Material).opacity = 0.35;
    (gridLines.material as THREE.Material).depthWrite = false;
    gridLines.position.y = gridAt;
    world.add(gridLines);

    const things = new THREE.Group();
    const corals = new THREE.Group();
    const marks = new THREE.Group();
    const overlay = new THREE.Group();
    const planned = new THREE.Group();
    world.add(things, corals, marks, overlay, planned);

    // The gizmo holds a stand-in at the middle of the selection; what it does
    // to the stand-in is said to the editor as a change from where it began.
    const proxy = new THREE.Object3D();
    world.add(proxy);
    const gizmo = new TransformControls(camera, renderer.domElement);
    gizmo.setSize(0.85);
    gizmo.setSpace("world");
    world.add(gizmo.getHelper());
    const began = new THREE.Vector3();
    const turnOf = (q: THREE.Quaternion) => -2 * Math.atan2(q.y, q.w) * 180 / Math.PI;
    const growthOf = (v: THREE.Vector3) => [v.x, v.y, v.z].reduce((best, s) => Math.abs(s - 1) > Math.abs(best - 1) ? s : best, 1);
    gizmo.addEventListener("dragging-changed", (e) => { controls.enabled = !(e as unknown as { value: boolean }).value; });
    gizmo.addEventListener("mouseDown", () => {
      if (scene.current) scene.current.dragging = true;
      began.copy(proxy.position);
      said.current.onTransformStart();
    });
    gizmo.addEventListener("objectChange", () => {
      if (!scene.current?.dragging) return;
      const dx = proxy.position.x - began.x, dy = -(proxy.position.z - began.z);
      said.current.onTransform({ dx, dy, turnDeg: turnOf(proxy.quaternion), scale: growthOf(proxy.scale) });
    });
    gizmo.addEventListener("mouseUp", () => {
      if (scene.current) scene.current.dragging = false;
      proxy.quaternion.identity();
      proxy.scale.set(1, 1, 1);
      said.current.onTransformEnd();
    });

    const helper = new ViewHelper(camera, renderer.domElement);
    helper.setLabels("E", "Up", "S");
    helper.center = controls.target;

    const resolution = new THREE.Vector2(1, 1);
    scene.current = { renderer, scene: world, camera, controls, gizmo, proxy, terrain, water, things, corals, marks, overlay,
                      plan: planned, grid: gridLines, lift, resolution, where: new Map(), dragging: false };

    const fit = () => {
      const w = el.clientWidth || 1, h = el.clientHeight || 1;
      renderer.setSize(w, h);
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      resolution.set(w, h);
      planned.traverse((o) => { if (o instanceof Line2) (o.material as LineMaterial).resolution.set(w, h); });
    };
    fit();
    const watching = new ResizeObserver(fit);
    watching.observe(el);

    // Choosing, boxing, dragging and putting down.
    const ray = new THREE.Raycaster();
    const pointer = new THREE.Vector2();
    const cast = (event: { clientX: number; clientY: number }) => {
      const box = renderer.domElement.getBoundingClientRect();
      pointer.set(((event.clientX - box.left) / box.width) * 2 - 1, -((event.clientY - box.top) / box.height) * 2 + 1);
      ray.setFromCamera(pointer, camera);
    };
    const onGround = (): { x: number; y: number } | undefined => {
      const hit = ray.intersectObject(terrain)[0];
      return hit ? { x: hit.point.x, y: -hit.point.z } : undefined;
    };
    const hitItem = (): string | undefined => {
      const hits = ray.intersectObjects([...things.children, ...corals.children], true);
      for (const hit of hits) {
        if (!hit.object.visible || !hit.object.parent?.visible) continue;
        const ids = hit.object.userData.ids as string[] | undefined;
        if (ids && hit.instanceId !== undefined) return ids[hit.instanceId];
        let o: THREE.Object3D | null = hit.object;
        while (o && !o.userData.id) o = o.parent;
        if (o?.userData.id) return o.userData.id as string;
      }
      return undefined;
    };
    const marquee = document.createElement("div");
    marquee.className = "world3d-box";
    el.appendChild(marquee);
    let boxing: { x: number; y: number } | undefined;
    let grabbing: { x: number; y: number } | undefined;
    let downAt: { x: number; y: number } | undefined;
    let holding: number | undefined;
    // The plan's mark under the pointer: a stage, and a handle of the chosen one.
    const hitPlan = (): { stage?: number; handle?: number } | undefined => {
      for (const hit of ray.intersectObjects(planned.children, false)) {
        const data = hit.object.userData as { stage?: number; handle?: number };
        if (data.handle !== undefined) return data;
      }
      const hit = ray.intersectObjects(planned.children, false).find((h) => h.object.userData.stage !== undefined);
      return hit ? hit.object.userData as { stage?: number } : undefined;
    };
    const transforms = () => ["select", "move", "rotate", "scale"].includes(said.current.mode);
    const down = (event: PointerEvent) => {
      if (event.button !== 0) return;
      downAt = { x: event.clientX, y: event.clientY };
      if (gizmo.dragging || gizmo.axis) return;
      cast(event);
      if (said.current.plan?.editing && said.current.onHandle) {
        const handle = hitPlan()?.handle, at = onGround();
        if (handle !== undefined && at) {
          holding = handle;
          controls.enabled = false;
          renderer.domElement.setPointerCapture(event.pointerId);
          said.current.onHandle(handle, at, "start");
          return;
        }
      }
      if (!transforms()) return;
      const id = hitItem();
      if (event.shiftKey && !id) {
        boxing = { x: event.clientX, y: event.clientY };
        controls.enabled = false;
        renderer.domElement.setPointerCapture(event.pointerId);
        return;
      }
      const ground_ = onGround();
      const locked = said.current.items.some((t) => t.id === id && t.locked);
      if (id && ground_ && !locked && !event.shiftKey && said.current.selected.includes(id)
          && (said.current.mode === "select" || said.current.mode === "move")) {
        grabbing = ground_;
        controls.enabled = false;
        renderer.domElement.setPointerCapture(event.pointerId);
        if (scene.current) scene.current.dragging = true;
        said.current.onTransformStart();
      }
    };
    const move = (event: PointerEvent) => {
      cast(event);
      const at = onGround();
      said.current.onHover?.(at);
      if (holding !== undefined) {
        if (at) said.current.onHandle?.(holding, at, "move");
        return;
      }
      if (said.current.plan?.editing) renderer.domElement.style.cursor = hitPlan()?.handle !== undefined ? "grab" : "";
      if (boxing) {
        const r = el.getBoundingClientRect();
        const x0 = Math.min(boxing.x, event.clientX) - r.left, y0 = Math.min(boxing.y, event.clientY) - r.top;
        Object.assign(marquee.style, { display: "block", left: `${x0}px`, top: `${y0}px`,
          width: `${Math.abs(event.clientX - boxing.x)}px`, height: `${Math.abs(event.clientY - boxing.y)}px` });
      }
      if (grabbing && at) said.current.onTransform({ dx: at.x - grabbing.x, dy: at.y - grabbing.y, turnDeg: 0, scale: 1 });
    };
    const up = (event: PointerEvent) => {
      if (event.button !== 0) return;
      const still = downAt && Math.hypot(event.clientX - downAt.x, event.clientY - downAt.y) <= 4;
      downAt = undefined;
      if (holding !== undefined) {
        const k = holding;
        holding = undefined;
        controls.enabled = true;
        cast(event);
        const at = onGround();
        if (at) said.current.onHandle?.(k, at, "end");
        else said.current.onHandle?.(k, { x: NaN, y: NaN }, "end");
        return;
      }
      if (boxing) {
        const r = renderer.domElement.getBoundingClientRect();
        const x0 = Math.min(boxing.x, event.clientX), x1 = Math.max(boxing.x, event.clientX);
        const y0 = Math.min(boxing.y, event.clientY), y1 = Math.max(boxing.y, event.clientY);
        boxing = undefined;
        marquee.style.display = "none";
        controls.enabled = true;
        const inside: string[] = [];
        for (const [id, w] of scene.current?.where ?? []) {
          const p = w.at.clone().project(camera);
          if (p.z > 1) continue;
          const sx = r.left + (p.x + 1) / 2 * r.width, sy = r.top + (1 - p.y) / 2 * r.height;
          if (sx >= x0 && sx <= x1 && sy >= y0 && sy <= y1) inside.push(id);
        }
        said.current.onSelect(inside, "add");
        return;
      }
      if (grabbing) {
        grabbing = undefined;
        controls.enabled = true;
        if (scene.current) scene.current.dragging = false;
        said.current.onTransformEnd();
        if (!still) return;
      }
      if (!still || gizmo.dragging) return;
      if (helper.handleClick(event)) return;
      cast(event);
      if (!transforms()) {
        const at = onGround();
        const stage = said.current.plan ? hitPlan()?.stage : undefined;
        if (at) said.current.onPick(at, { shift: event.shiftKey, ...(stage !== undefined ? { stage } : {}) });
        return;
      }
      const id = hitItem();
      if (id) said.current.onSelect([id], event.shiftKey || event.metaKey || event.ctrlKey ? "toggle" : "replace");
      else if (!event.shiftKey) said.current.onSelect([], "replace");
    };
    const leave = () => said.current.onHover?.(undefined);
    const over = (event: DragEvent) => {
      if (!event.dataTransfer?.types.includes("application/x-iocean")) return;
      event.preventDefault();
      cast(event);
      said.current.onHover?.(onGround());
    };
    const drop = (event: DragEvent) => {
      const key = event.dataTransfer?.getData("application/x-iocean");
      if (!key) return;
      event.preventDefault();
      cast(event);
      const at = onGround();
      if (at) said.current.onDrop?.(key, at);
    };
    // After the gizmo's own, so a press on a handle is the gizmo's; the orbit's
    // is earlier, and stops at once when it is turned off here.
    renderer.domElement.addEventListener("pointerdown", down);
    renderer.domElement.addEventListener("pointermove", move);
    renderer.domElement.addEventListener("pointerup", up);
    renderer.domElement.addEventListener("pointerleave", leave);
    el.addEventListener("dragover", over);
    el.addEventListener("drop", drop);

    let raf = 0;
    const clock = new THREE.Clock();
    const frame = () => {
      const delta = clock.getDelta();
      if (helper.animating) helper.update(delta);
      else controls.update();
      renderer.clear();
      renderer.render(world, camera);
      helper.render(renderer);
      raf = requestAnimationFrame(frame);
    };
    raf = requestAnimationFrame(frame);
    return () => {
      cancelAnimationFrame(raf);
      watching.disconnect();
      el.removeEventListener("dragover", over);
      el.removeEventListener("drop", drop);
      gizmo.detach();
      gizmo.dispose();
      helper.dispose();
      controls.dispose();
      marquee.remove();
      renderer.domElement.remove();
      world.traverse((o) => {
        const mesh = o as THREE.Mesh;
        mesh.geometry?.dispose();
        const material = mesh.material as THREE.Material | THREE.Material[] | undefined;
        (Array.isArray(material) ? material : material ? [material] : []).forEach((m) => {
          (m as THREE.MeshStandardMaterial).map?.dispose();
          m.dispose();
        });
      });
      renderer.dispose();
      scene.current = undefined;
    };
  }, [ground, glass]);

  // What is in it, drawn again whenever it changes.
  useEffect(() => {
    const s = scene.current;
    if (!s) return;
    s.terrain.visible = showing.terrain;
    s.water.visible = showing.water;
    s.corals.visible = showing.reef;
    const chosen = new Set(selected);
    for (const group of [s.things, s.corals, s.marks]) emptied(group);
    s.where.clear();
    const seen = ground.acrossM / 160;
    for (const item of items) {
      if (item.kind === "coral") continue;
      const shape = shapeOf(item, ground, s.lift, chosen.has(item.id));
      if (!shape) continue;
      shape.userData.id = item.id;
      shape.visible = item.kind === "reef" ? showing.reef : showing.structures;
      s.things.add(shape);
      const box = new THREE.Box3().setFromObject(shape);
      s.where.set(item.id, { at: box.getCenter(new THREE.Vector3()), r: Math.max(box.getSize(new THREE.Vector3()).length() / 2, seen / 2) });
    }
    coralsInto(s.corals, items.filter((t) => t.kind === "coral"), ground, s.lift, chosen, s.where);
    // A box round each chosen thing, as a modelling tool marks its selection.
    for (const id of selected) {
      const w = s.where.get(id);
      if (!w) continue;
      const box = new THREE.Box3Helper(new THREE.Box3(w.at.clone().addScalar(-w.r * 0.75), w.at.clone().addScalar(w.r * 0.75)), CHOSEN);
      s.marks.add(box);
    }
  }, [items, showing, selected, ground]);

  // The gizmo, on the selection, in the mode's own form.
  useEffect(() => {
    const s = scene.current;
    if (!s || s.dragging) return;
    const shape = mode === "move" ? "translate" : mode === "rotate" ? "rotate" : mode === "scale" ? "scale" : undefined;
    const held = items.filter((t) => selected.includes(t.id));
    const pts = held.map((t) => s.where.get(t.id)?.at).filter((p): p is THREE.Vector3 => !!p);
    // Only corals grow; equipment and models are their true size.
    const grows = held.length > 0 && held.every((t) => t.kind === "coral");
    if (!shape || !pts.length || held.some((t) => t.locked) || (shape === "scale" && !grows)) {
      s.gizmo.detach();
      return;
    }
    const middle = pts.reduce((a, p) => a.add(p), new THREE.Vector3()).divideScalar(pts.length);
    s.proxy.position.copy(middle);
    s.proxy.quaternion.identity();
    s.proxy.scale.set(1, 1, 1);
    s.gizmo.setMode(shape);
    s.gizmo.showX = shape !== "rotate";
    s.gizmo.showZ = shape !== "rotate";
    s.gizmo.showY = shape !== "translate";
    s.gizmo.setTranslationSnap(snap ? 1 : null);
    s.gizmo.setRotationSnap(snap ? Math.PI / 12 : null);
    s.gizmo.setScaleSnap(snap ? 0.1 : null);
    s.gizmo.attach(s.proxy);
  }, [items, selected, mode, snap, ground]);

  useEffect(() => { if (scene.current) scene.current.grid.visible = grid; }, [grid, ground, glass]);

  // The mission, drawn again whenever it changes.
  useEffect(() => {
    const s = scene.current;
    if (!s) return;
    emptied(s.plan);
    if (plan) stagesInto(s.plan, plan, { floor: (x, y) => floor(ground, x, y, s.lift), lift: s.lift, acrossM: ground.acrossM, resolution: s.resolution });
  }, [plan, ground, glass]);

  // What is in hand, the brush and the tape.
  useEffect(() => {
    const s = scene.current;
    if (!s) return;
    emptied(s.overlay);
    if (ghost) {
      const shape = ghost.kind === "coral" ? coralModel(String(ghost.form ?? "massive")) : shapeOf(ghost, ground, s.lift, false);
      if (shape) {
        if (ghost.kind === "coral") {
          const size = Math.max(0.15, Number(ghost.sizeM ?? 0.5));
          shape.scale.setScalar(size);
          shape.position.set(ghost.x, floor(ground, ghost.x, ghost.y, s.lift), -ghost.y);
        }
        shape.traverse((o) => {
          const m = (o as THREE.Mesh).material as THREE.MeshStandardMaterial | undefined;
          if (m) { m.transparent = true; m.opacity = 0.5; m.depthWrite = false; }
        });
        s.overlay.add(shape);
      }
    }
    if (brush) {
      const ring: THREE.Vector3[] = [];
      for (let k = 0; k <= 64; k++) {
        const a = (k / 64) * Math.PI * 2;
        const x = brush.x + Math.cos(a) * brush.radiusM, y = brush.y + Math.sin(a) * brush.radiusM;
        ring.push(new THREE.Vector3(x, floor(ground, x, y, s.lift) + 0.05, -y));
      }
      s.overlay.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(ring),
        new THREE.LineBasicMaterial({ color: CHOSEN, depthTest: false })));
    }
    if (measure?.length) {
      const pts = measure.map((p) => new THREE.Vector3(p.x, floor(ground, p.x, p.y, s.lift), -p.y));
      const dot = ground.acrossM / 300;
      for (const p of pts) {
        const ball = new THREE.Mesh(new THREE.SphereGeometry(dot, 12, 8), new THREE.MeshBasicMaterial({ color: 0xffe066, depthTest: false }));
        ball.position.copy(p);
        s.overlay.add(ball);
      }
      if (pts.length === 2) {
        s.overlay.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts),
          new THREE.LineBasicMaterial({ color: 0xffe066, depthTest: false })));
      }
    }
  }, [ghost, brush, measure, ground]);

  return <div className="world3d" ref={host} />;
}

function niceStep(v: number): number {
  for (const s of [0.5, 1, 2, 5, 10, 20, 50, 100, 200, 500, 1000]) if (s >= v) return s;
  return 2000;
}

/** A group with what was in it disposed of. */
function emptied(group: THREE.Group): void {
  for (const old of [...group.children]) {
    group.remove(old);
    old.traverse((o) => {
      const mesh = o as THREE.Mesh;
      mesh.geometry?.dispose();
      const m = mesh.material as THREE.Material | THREE.Material[] | undefined;
      (Array.isArray(m) ? m : m ? [m] : []).forEach((x) => x.dispose());
    });
  }
}

/** Inside the glass: the triangles outside it go, and the ground is coloured
 *  as it is, sand on the floor and rock above it, not as a chart. */
function inTheTank(plane: THREE.BufferGeometry, glass: Glass): void {
  const position = plane.attributes.position as THREE.BufferAttribute;
  const inside = (k: number) => {
    const x = position.getX(k), y = -position.getZ(k);
    if (glass.round) {
      const [cx, cy] = glass.round.centre;
      return Math.hypot(x - cx, y - cy) <= glass.round.radiusM;
    }
    return x >= glass.min[0] && x <= glass.max[0] && y >= glass.min[1] && y <= glass.max[1];
  };
  const index = plane.index!;
  const kept: number[] = [];
  for (let t = 0; t < index.count; t += 3) {
    const a = index.getX(t), b = index.getX(t + 1), c = index.getX(t + 2);
    if (inside(a) && inside(b) && inside(c)) kept.push(a, b, c);
  }
  plane.setIndex(kept);
  let lowest = Infinity;
  for (let k = 0; k < position.count; k++) lowest = Math.min(lowest, position.getY(k));
  const colours = new Float32Array(position.count * 3);
  const sand = new THREE.Color(0xd8ccb0), rock = new THREE.Color(0x8a877c), lichen = new THREE.Color(0x667f68);
  const c = new THREE.Color();
  for (let k = 0; k < position.count; k++) {
    const up = position.getY(k) - lowest;
    // A little grain so the rock does not read as plastic.
    const grain = 0.88 + 0.24 * Math.abs(Math.sin(position.getX(k) * 12.9 + position.getZ(k) * 78.2) * 43758.5 % 1);
    if (up < 0.15) c.copy(sand);
    else c.copy(rock).lerp(lichen, Math.min(1, Math.max(0, (Math.sin(up * 1.7) + 1) * 0.3)));
    c.multiplyScalar(grain);
    colours.set([c.r, c.g, c.b], k * 3);
  }
  plane.setAttribute("color", new THREE.BufferAttribute(colours, 3));
}


/** Colonies by form, each form one instanced shape: plates spread flat, mounds
 *  sit round, branches and fans stand up. Coloured as reef coral is in water. */
export const CORAL_SHAPES: Record<string, { make: () => THREE.BufferGeometry; colour: number }> = {
  // A plate spreads well past its foot: drawn twice its listed size across.
  table: { make: () => tableGeometry(), colour: 0x6cc39c },
  massive: { make: () => new THREE.SphereGeometry(0.5, 16, 10, 0, Math.PI * 2, 0, Math.PI / 2), colour: 0xb08a5a },
  brain: { make: () => brainGeometry(), colour: 0xc2a46a },
  branching: { make: () => branchGeometry(5, 0.07, 0.8), colour: 0x8f74b0 },
  finger: { make: () => branchGeometry(7, 0.06, 0.55), colour: 0xd08f6a },
  plume: { make: () => branchGeometry(4, 0.03, 1.1), colour: 0xc8607e },
  fan: { make: () => new THREE.CircleGeometry(0.5, 20, 0, Math.PI).translate(0, 0.08, 0), colour: 0xd9714f },
  sponge: { make: () => new THREE.CylinderGeometry(0.28, 0.22, 0.7, 14, 1, true), colour: 0xe09a3c },
  encrusting: { make: () => new THREE.SphereGeometry(0.5, 14, 6, 0, Math.PI * 2, 0, Math.PI / 4), colour: 0xcf7a8e },
};

function tableGeometry(): THREE.BufferGeometry {
  // A plate on a short stalk.
  const plate = new THREE.CylinderGeometry(1, 0.9, 0.08, 24).translate(0, 0.22, 0);
  const stalk = new THREE.CylinderGeometry(0.08, 0.12, 0.2, 8).translate(0, 0.1, 0);
  return merged([plate, stalk]);
}

function brainGeometry(): THREE.BufferGeometry {
  const g = new THREE.SphereGeometry(0.5, 28, 14, 0, Math.PI * 2, 0, Math.PI / 2);
  const p = g.attributes.position as THREE.BufferAttribute;
  for (let k = 0; k < p.count; k++) {
    const x = p.getX(k), y = p.getY(k), z = p.getZ(k);
    const groove = 1 + 0.05 * Math.sin(x * 22 + Math.sin(z * 9) * 3);
    p.setXYZ(k, x * groove, y * groove, z * groove);
  }
  g.computeVertexNormals();
  return g;
}

/** Arms spread from a foot, each a tapered cylinder leaning out. */
function branchGeometry(arms: number, thick: number, tall: number): THREE.BufferGeometry {
  const parts: THREE.BufferGeometry[] = [new THREE.CylinderGeometry(thick * 1.4, thick * 1.8, tall * 0.25, 6).translate(0, tall * 0.125, 0)];
  for (let i = 0; i < arms; i++) {
    const lean = 0.35 + 0.25 * ((i * 7) % 3) / 2;
    const a = (i / arms) * Math.PI * 2;
    const arm = new THREE.CylinderGeometry(thick * 0.6, thick, tall * (0.75 + 0.1 * (i % 3)), 6).translate(0, tall * 0.4, 0);
    arm.rotateZ(lean);
    arm.rotateY(a);
    arm.translate(0, tall * 0.18, 0);
    parts.push(arm);
  }
  return merged(parts);
}

/** Several geometries as one, positions and normals only. */
function merged(parts: THREE.BufferGeometry[]): THREE.BufferGeometry {
  const flat = parts.map((g) => g.index ? g.toNonIndexed() : g);
  const count = flat.reduce((t, g) => t + g.attributes.position!.count, 0);
  const pos = new Float32Array(count * 3), nor = new Float32Array(count * 3);
  let at = 0;
  for (const g of flat) {
    g.computeVertexNormals();
    pos.set(g.attributes.position!.array as Float32Array, at * 3);
    nor.set(g.attributes.normal!.array as Float32Array, at * 3);
    at += g.attributes.position!.count;
  }
  const out = new THREE.BufferGeometry();
  out.setAttribute("position", new THREE.BufferAttribute(pos, 3));
  out.setAttribute("normal", new THREE.BufferAttribute(nor, 3));
  parts.forEach((g) => g.dispose());
  return out;
}

/** One coral of a form, standing on its foot at the origin, a metre in size. */
export function coralGeometry(form: string): THREE.BufferGeometry {
  const shape = CORAL_SHAPES[form] ?? CORAL_SHAPES.massive!;
  const geometry = shape.make();
  geometry.computeBoundingBox();
  geometry.translate(0, -geometry.boundingBox!.min.y, 0);
  return geometry;
}

export function coralModel(form: string): THREE.Mesh {
  const shape = CORAL_SHAPES[form] ?? CORAL_SHAPES.massive!;
  return new THREE.Mesh(coralGeometry(form), new THREE.MeshStandardMaterial({ color: shape.colour, roughness: 0.75, side: THREE.DoubleSide }));
}

function coralsInto(group: THREE.Group, corals: Shown[], ground: Ground, lift: number, chosen: Set<string>,
                    where: Map<string, { at: THREE.Vector3; r: number }>): void {
  const byForm = new Map<string, Shown[]>();
  for (const c of corals) byForm.set(String(c.form ?? "massive"), [...(byForm.get(String(c.form ?? "massive")) ?? []), c]);
  const m = new THREE.Matrix4(), q = new THREE.Quaternion(), up = new THREE.Vector3(0, 1, 0);
  const colour = new THREE.Color(), picked = new THREE.Color(CHOSEN);
  for (const [form, list] of byForm) {
    const shape = CORAL_SHAPES[form] ?? CORAL_SHAPES.massive!;
    // White, so each colony's own colour (its form's, or chosen) is what shows.
    const mesh = new THREE.InstancedMesh(coralGeometry(form),
      new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.75, side: THREE.DoubleSide }), list.length);
    colour.setHex(shape.colour);
    list.forEach((c, i) => {
      q.setFromAxisAngle(up, -(((c.builtDeg ?? 0) + (c.headingDeg ?? 0)) * Math.PI) / 180);
      const size = Math.max(0.15, Number(c.sizeM ?? 0.5));
      const at = new THREE.Vector3(c.x, floor(ground, c.x, c.y, lift) - 0.02, -c.y);
      m.compose(at, q, new THREE.Vector3(size, size, size));
      mesh.setMatrixAt(i, m);
      mesh.setColorAt(i, chosen.has(c.id) ? picked : colour);
      where.set(c.id, { at: at.clone().setY(at.y + size * 0.3), r: size * (form === "table" ? 1 : 0.6) });
    });
    mesh.userData.ids = list.map((c) => c.id);
    mesh.computeBoundingSphere();
    group.add(mesh);
  }
}

/** A tank's glass and the water in it, and the floor of the hall it stands on. */
function tank(world: THREE.Scene, glass: Glass): THREE.Object3D {
  const [, , floorZ] = glass.min;
  const top = glass.max[2] + 0.4;
  const base = floorZ - 1;
  const tall = top - base;
  const water = new THREE.Group();
  const clear = new THREE.MeshPhysicalMaterial({
    color: 0xcfeeff, transparent: true, opacity: 0.12, roughness: 0.05, metalness: 0,
    side: THREE.DoubleSide, depthWrite: false,
  });
  const body = new THREE.MeshStandardMaterial({ color: 0x2f9fc4, transparent: true, opacity: 0.16, depthWrite: false, side: THREE.DoubleSide });
  const surface = new THREE.MeshStandardMaterial({ color: 0x8fd6ea, transparent: true, opacity: 0.35, depthWrite: false, side: THREE.DoubleSide });
  const collar = new THREE.MeshStandardMaterial({ color: 0xf2f2ee, roughness: 0.4 });
  const steel = new THREE.MeshStandardMaterial({ color: 0x8e979e, metalness: 0.6, roughness: 0.35 });
  const hall = new THREE.MeshStandardMaterial({ color: 0x3a434c, roughness: 0.85 });
  const shell = new THREE.Group();
  if (glass.round) {
    const r = glass.round.radiusM;
    const [cx, cy] = glass.round.centre;
    shell.position.set(cx, 0, -cy);
    const wall = new THREE.Mesh(new THREE.CylinderGeometry(r + 0.3, r + 0.3, tall, 128, 1, true), clear);
    wall.position.y = base + tall / 2;
    const inside = new THREE.Mesh(new THREE.CylinderGeometry(r - 0.02, r - 0.02, glass.max[2] - floorZ, 128, 1, true), body);
    inside.position.y = (glass.max[2] + floorZ) / 2;
    const top_ = new THREE.Mesh(new THREE.CircleGeometry(r - 0.02, 128).rotateX(-Math.PI / 2), surface);
    top_.position.y = glass.max[2];
    const cap = new THREE.Mesh(new THREE.CylinderGeometry(r + 0.55, r + 0.55, 1.2, 128, 1, true), collar);
    cap.position.y = top + 0.6;
    const plinth = new THREE.Mesh(new THREE.CylinderGeometry(r + 0.45, r + 0.55, 1, 128), steel);
    plinth.position.y = base + 0.5;
    const rail = new THREE.Mesh(new THREE.TorusGeometry(r + 1.1, 0.04, 8, 160).rotateX(Math.PI / 2), steel);
    rail.position.y = floorZ - 1 + 1.05;
    shell.add(wall, inside, top_, cap, plinth, rail);
  } else {
    const [x0, y0] = glass.min, [x1, y1] = glass.max;
    const w = x1 - x0, d = y1 - y0;
    const box = new THREE.Mesh(new THREE.BoxGeometry(w + 0.04, tall, d + 0.04), clear);
    box.position.set((x0 + x1) / 2, base + tall / 2, -(y0 + y1) / 2);
    const inside = new THREE.Mesh(new THREE.BoxGeometry(w, glass.max[2] - floorZ, d), body);
    inside.position.set((x0 + x1) / 2, (glass.max[2] + floorZ) / 2, -(y0 + y1) / 2);
    const edges = new THREE.LineSegments(new THREE.EdgesGeometry(box.geometry), new THREE.LineBasicMaterial({ color: 0xbfd4e0 }));
    edges.position.copy(box.position);
    shell.add(box, inside, edges);
  }
  water.add(shell);
  const reach = Math.max(glass.max[0] - glass.min[0], glass.max[1] - glass.min[1]) * 1.6;
  const floor_ = new THREE.Mesh(new THREE.CircleGeometry(reach, 96).rotateX(-Math.PI / 2), hall);
  floor_.position.y = base - 0.01;
  world.add(floor_);
  return water;
}


/** The ground's height in the scene at a world point. */
function floor(ground: Ground, x: number, y: number, lift: number): number {
  return -groundAt(ground, x, y) * lift;
}

function material(kind: string, chosen: boolean, see?: number, colour?: number): THREE.MeshStandardMaterial {
  return new THREE.MeshStandardMaterial({
    color: colour ?? COLOURS[kind] ?? 0x9aa6b2, roughness: 0.6, metalness: 0.1,
    emissive: chosen ? CHOSEN : 0x000000, emissiveIntensity: chosen ? 0.45 : 0,
    transparent: see !== undefined, opacity: see ?? 1,
  });
}

/** A piece of equipment at its true size in metres, standing on the origin
 *  (a vessel floating on it), facing north. */
export function equipmentModel(kind: string, chosen = false): THREE.Group {
  const g = new THREE.Group();
  const add = (geometry: THREE.BufferGeometry, x: number, y: number, z: number, colour?: number) => {
    const mesh = new THREE.Mesh(geometry, material(kind, chosen, undefined, colour));
    mesh.position.set(x, y, z);
    g.add(mesh);
    return mesh;
  };
  switch (kind) {
    case "transponder":
      add(new THREE.CylinderGeometry(0.3, 0.34, 0.08, 16), 0, 0.04, 0, 0x5b6168);
      add(new THREE.CylinderGeometry(0.09, 0.09, 0.7, 12), 0, 0.43, 0);
      add(new THREE.SphereGeometry(0.2, 16, 12), 0, 0.92, 0, 0xf26b1d);
      break;
    case "mooring-block":
      add(new THREE.BoxGeometry(1.2, 0.6, 1.2), 0, 0.3, 0);
      add(new THREE.TorusGeometry(0.16, 0.035, 8, 20), 0, 0.72, 0, 0x5b6168);
      break;
    case "nursery-frame": {
      const leg = () => new THREE.CylinderGeometry(0.025, 0.025, 1, 6);
      for (const [x, z] of [[-1, -0.5], [1, -0.5], [-1, 0.5], [1, 0.5]] as const) add(leg(), x, 0.5, z);
      for (const z of [-0.5, 0.5]) add(new THREE.CylinderGeometry(0.025, 0.025, 2, 6).rotateZ(Math.PI / 2), 0, 1, z);
      for (const y of [0.45, 0.75]) add(new THREE.CylinderGeometry(0.008, 0.008, 2, 4).rotateZ(Math.PI / 2), 0, y, 0, 0xe8e2d0);
      for (const x of [-0.6, 0, 0.6]) add(new THREE.SphereGeometry(0.06, 8, 6), x, 0.75, 0, 0x8f74b0);
      break;
    }
    case "marker-post":
      add(new THREE.CylinderGeometry(0.05, 0.06, 3, 10), 0, 1.5, 0, 0xf2f2ee);
      add(new THREE.CylinderGeometry(0.052, 0.052, 0.4, 10), 0, 2.6, 0);
      add(new THREE.PlaneGeometry(0.6, 0.4), 0.32, 2.75, 0);
      break;
    case "buoy":
      add(new THREE.SphereGeometry(0.8, 20, 14), 0, 0.2, 0);
      add(new THREE.CylinderGeometry(0.05, 0.05, 1.6, 8), 0, 1.6, 0, 0x30353a);
      add(new THREE.SphereGeometry(0.12, 10, 8), 0, 2.45, 0, 0xffe066);
      break;
    case "ship":
    case "dredger": {
      const hull = new THREE.Shape();
      hull.moveTo(-4, -15); hull.lineTo(4, -15); hull.lineTo(4, 10); hull.quadraticCurveTo(4, 15, 0, 15.5);
      hull.quadraticCurveTo(-4, 15, -4, 10); hull.closePath();
      const body = new THREE.ExtrudeGeometry(hull, { depth: 3.2, bevelEnabled: false }).rotateX(Math.PI / 2).translate(0, 2, 0);
      add(body, 0, -1.2, 0, kind === "ship" ? 0x2b3a4a : 0x9a5a22);
      add(new THREE.BoxGeometry(7.6, 0.2, 29), 0, 0.85, 0, 0xc9c6bd);
      add(new THREE.BoxGeometry(6, 4, 6), 0, 3, -9, 0xf2f2ee);
      add(new THREE.CylinderGeometry(0.15, 0.15, 6, 8), 0, 8, -9, 0x30353a);
      if (kind === "dredger") {
        const arm = add(new THREE.BoxGeometry(0.6, 0.6, 18), 2.5, 2, 4, 0xf2c230);
        arm.rotation.x = -0.35;
      }
      break;
    }
    default:
      add(new THREE.CylinderGeometry(0.3, 0.3, 0.6, 16), 0, 0.3, 0);
  }
  return g;
}

/** A thing's shape where it is. Sizes are true; only depths are stretched by
 *  lift. Point things are drawn no smaller than a mark you can find from
 *  across the world. */
function shapeOf(item: Shown, ground: Ground, lift: number, chosen: boolean): THREE.Object3D | undefined {
  const tube = (points: THREE.Vector3[], radius: number) => {
    if (points.length < 2) return undefined;
    const curve = new THREE.CatmullRomCurve3(points, false, "centripetal");
    return new THREE.Mesh(new THREE.TubeGeometry(curve, Math.max(16, points.length * 8), radius, 8, false),
      material(item.kind, chosen));
  };
  // Seen from far off a 0.3 m pipe is nothing: drawn no thinner than a
  // five-hundredth of the world, so it can be found and taken hold of.
  const least = ground.acrossM / 500;
  if (item.route && item.route.length >= 2) {
    const along: THREE.Vector3[] = [];
    for (let i = 1; i < item.route.length; i++) {
      const a = item.route[i - 1]!, b = item.route[i]!;
      const n = Math.max(2, Math.ceil(Math.hypot(b.x - a.x, b.y - a.y) / (ground.acrossM / 200)));
      for (let k = i === 1 ? 0 : 1; k <= n; k++) {
        const x = a.x + (b.x - a.x) * k / n, y = a.y + (b.y - a.y) * k / n;
        along.push(new THREE.Vector3(x, floor(ground, x, y, lift) + least, -y));
      }
    }
    return tube(along, Math.max(item.radiusM ?? 0.4, least));
  }
  if (item.ends && item.ends.length === 2) {
    const [a, b] = item.ends as [{ x: number; y: number; z?: number }, { x: number; y: number; z?: number }];
    const zOf = (p: { x: number; y: number; z?: number }) => p.z === undefined || p.z < 0 && Math.abs(p.z + groundAt(ground, p.x, p.y)) < 0.5
      ? (p.z === 0 ? 0 : floor(ground, p.x, p.y, lift)) : p.z * lift;
    const pa = new THREE.Vector3(a.x, zOf(a), -a.y), pb = new THREE.Vector3(b.x, zOf(b), -b.y);
    // A line hangs: a little sag at its middle.
    const mid = pa.clone().lerp(pb, 0.5);
    mid.x += (pb.x - pa.x) * 0.08;
    return tube([pa, mid, pb], least * 0.6);
  }
  if (item.corners && item.corners.length >= 3) {
    const points = [...item.corners, item.corners[0]!].map((p) => new THREE.Vector3(p.x, floor(ground, p.x, p.y, lift) + least, -p.y));
    const holder = new THREE.Group();
    holder.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(points),
      new THREE.LineBasicMaterial({ color: chosen ? CHOSEN : COLOURS[item.kind] ?? 0x2e9e6e })));
    // Posts at the corners, so a click finds it and it reads as a plot.
    for (const p of points.slice(0, -1)) {
      const post = new THREE.Mesh(new THREE.CylinderGeometry(least * 0.5, least * 0.5, least * 4, 8), material(item.kind, chosen));
      post.position.copy(p).setY(p.y + least * 2);
      holder.add(post);
    }
    return holder;
  }
  const holder = new THREE.Group();
  const base = floor(ground, item.x, item.y, lift);
  holder.position.set(item.x, SURFACE.has(item.kind) ? 0 : item.z !== undefined && item.z > -groundAt(ground, item.x, item.y) + 0.5 ? item.z * lift : base, -item.y);
  holder.rotation.y = -((item.headingDeg ?? 0) * Math.PI) / 180;
  const seen = ground.acrossM / 160;
  if (item.kind === "object" || item.kind === "reef") {
    const [w, l, h] = Array.isArray(item.sizeM) ? item.sizeM : [3, 3, 1];
    const tall = Math.max(h * lift, seen);
    const box = new THREE.Mesh(new THREE.BoxGeometry(Math.max(w, seen), tall, Math.max(l, seen)),
      material(item.kind, chosen, item.kind === "reef" ? 0.55 : undefined));
    box.position.y = tall / 2;
    holder.add(box);
    return holder;
  }
  const model = equipmentModel(item.kind, chosen);
  const size = new THREE.Box3().setFromObject(model).getSize(new THREE.Vector3());
  model.scale.setScalar(Math.max(1, seen / Math.max(size.x, size.y, size.z, 0.01)));
  holder.add(model);
  return holder;
}
