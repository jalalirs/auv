// A world in three dimensions: its terrain, the water over it, and what is in
// it, to orbit round, choose things in and drag them over the seabed.
//
// Drawn here, in the application, and not by the simulator: it is instant,
// works offline and costs the shared machines nothing. What a camera on a
// vehicle would really see is the simulator's, and a dive.
//
// The world's frame is x east, y north, z up in metres, origin at the middle.
// three.js is y up, so a world point (x, y, z) is drawn at (x, z * lift, -y),
// where lift stretches the depths: a reef three kilometres across and forty
// metres deep is a flat plate at its true shape.

import { useEffect, useRef } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";

import { groundAt, type Ground } from "./SiteChart.js";

/** Something drawn in the world. */
export interface Shown {
  id: string;
  /** A piece of equipment's kind, "object" for a model, "reef" for a reef. */
  kind: string;
  x: number;
  y: number;
  /** Metres up, when it is not on the ground or the surface. */
  z?: number;
  headingDeg?: number;
  /** Across, along and up, metres: a model's or a reef's. */
  sizeM?: [number, number, number];
  route?: { x: number; y: number }[];
  ends?: { x: number; y: number; z?: number }[];
  corners?: { x: number; y: number }[];
  radiusM?: number;
  heightM?: number;
  name?: string;
}

export interface Showing { terrain: boolean; water: boolean; structures: boolean; reef: boolean }

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

/** A coral colony as a place's record lists it: its kind, its size, where. */
export interface Colony { kind: string; sizeM: number; at: [number, number] }

export function World3D({ ground, glass, colonies, items, showing, chosen, placing, onPick, onChoose, onMove, onHover }: {
  ground: Ground;
  /** A tank: drawn as its glass and the water in it, the ground cut to it. */
  glass?: Glass;
  /** The colonies a place was built with, drawn as simple shapes by kind. */
  colonies?: Colony[];
  items: Shown[];
  showing: Showing;
  chosen?: string;
  /** Something is in hand: a click on the seabed puts it down. */
  placing?: boolean;
  onPick: (at: { x: number; y: number }) => void;
  onChoose: (id: string | undefined) => void;
  onMove: (id: string, at: { x: number; y: number }) => void;
  onHover?: (at: { x: number; y: number } | undefined) => void;
}): React.JSX.Element {
  const host = useRef<HTMLDivElement>(null);
  const scene = useRef<{
    renderer: THREE.WebGLRenderer; scene: THREE.Scene; camera: THREE.PerspectiveCamera;
    controls: OrbitControls; terrain: THREE.Mesh; water: THREE.Object3D; things: THREE.Group; corals: THREE.Group;
    lift: number;
  } | undefined>(undefined);
  const said = useRef({ onPick, onChoose, onMove, onHover, chosen, placing });
  said.current = { onPick, onChoose, onMove, onHover, chosen, placing };

  // The scene, once per ground.
  useEffect(() => {
    const el = host.current;
    if (!el) return;
    const lift = glass ? 1 : liftOf(ground);
    const across = ground.acrossM;
    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    el.appendChild(renderer.domElement);
    const world = new THREE.Scene();
    world.background = new THREE.Color(0x0d2236);
    world.fog = new THREE.Fog(0x0d2236, across * 1.2, across * 4);
    const camera = new THREE.PerspectiveCamera(45, 1, across / 2000, across * 20);
    camera.position.set(across * 0.45, across * 0.55, across * 0.75);
    const controls = new OrbitControls(camera, renderer.domElement);
    // Look at the middle of the seabed, wherever it is: 10 m down off a reef,
    // half a metre in a tank.
    const depths = Array.from(ground.depth).filter(Number.isFinite);
    const middle = depths.length ? depths.reduce((t, d) => t + Math.max(0, d), 0) / depths.length : 0;
    controls.target.set(0, -middle * lift, 0);
    controls.maxPolarAngle = Math.PI * 0.495;
    controls.enableDamping = true;
    controls.update();

    world.add(new THREE.HemisphereLight(0xdfefff, 0x1b2a38, 1.1));
    const sun = new THREE.DirectionalLight(0xffffff, 1.6);
    sun.position.set(-across, across * 1.5, -across * 0.6);
    world.add(sun);
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

    const things = new THREE.Group();
    world.add(things);
    const corals = coralsOf(colonies ?? [], ground, lift);
    world.add(corals);
    scene.current = { renderer, scene: world, camera, controls, terrain, water, things, corals, lift };

    const fit = () => {
      const w = el.clientWidth || 1, h = el.clientHeight || 1;
      renderer.setSize(w, h);
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
    };
    fit();
    const watching = new ResizeObserver(fit);
    watching.observe(el);

    // Choosing, putting down and dragging.
    const ray = new THREE.Raycaster();
    const pointer = new THREE.Vector2();
    const cast = (event: PointerEvent) => {
      const box = renderer.domElement.getBoundingClientRect();
      pointer.set(((event.clientX - box.left) / box.width) * 2 - 1, -((event.clientY - box.top) / box.height) * 2 + 1);
      ray.setFromCamera(pointer, camera);
    };
    const onGround = (): { x: number; y: number } | undefined => {
      const hit = ray.intersectObject(terrain)[0];
      return hit ? { x: hit.point.x, y: -hit.point.z } : undefined;
    };
    const thingHit = (): string | undefined => {
      for (const hit of ray.intersectObjects(things.children, true)) {
        let o: THREE.Object3D | null = hit.object;
        while (o && !o.userData.id) o = o.parent;
        if (o?.userData.id && o.visible) return o.userData.id as string;
      }
      return undefined;
    };
    let dragging: string | undefined;
    let downAt: { x: number; y: number } | undefined;
    const down = (event: PointerEvent) => {
      if (event.button !== 0) return;
      cast(event);
      downAt = { x: event.clientX, y: event.clientY };
      const id = thingHit();
      if (id && id === said.current.chosen && !said.current.placing) {
        dragging = id;
        controls.enabled = false;
        renderer.domElement.setPointerCapture(event.pointerId);
      }
    };
    const move = (event: PointerEvent) => {
      cast(event);
      const at = onGround();
      said.current.onHover?.(at);
      if (dragging && at) said.current.onMove(dragging, at);
    };
    const up = (event: PointerEvent) => {
      if (dragging) {
        dragging = undefined;
        controls.enabled = true;
        return;
      }
      if (!downAt || Math.hypot(event.clientX - downAt.x, event.clientY - downAt.y) > 4) return;
      cast(event);
      const id = said.current.placing ? undefined : thingHit();
      if (id) { said.current.onChoose(id); return; }
      const at = onGround();
      if (at) said.current.onPick(at);
    };
    const leave = () => said.current.onHover?.(undefined);
    renderer.domElement.addEventListener("pointerdown", down);
    renderer.domElement.addEventListener("pointermove", move);
    renderer.domElement.addEventListener("pointerup", up);
    renderer.domElement.addEventListener("pointerleave", leave);

    let raf = 0;
    const frame = () => {
      controls.update();
      renderer.render(world, camera);
      raf = requestAnimationFrame(frame);
    };
    raf = requestAnimationFrame(frame);
    return () => {
      cancelAnimationFrame(raf);
      watching.disconnect();
      controls.dispose();
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
  }, [ground, glass, colonies]);

  // What is in it, drawn again whenever it changes.
  useEffect(() => {
    const s = scene.current;
    if (!s) return;
    s.terrain.visible = showing.terrain;
    s.water.visible = showing.water;
    s.corals.visible = showing.reef;
    for (const old of [...s.things.children]) {
      s.things.remove(old);
      old.traverse((o) => {
        const mesh = o as THREE.Mesh;
        mesh.geometry?.dispose();
        (mesh.material as THREE.Material | undefined)?.dispose?.();
      });
    }
    for (const item of items) {
      const shape = shapeOf(item, ground, s.lift, item.id === chosen);
      if (!shape) continue;
      shape.userData.id = item.id;
      shape.visible = item.kind === "reef" ? showing.reef : showing.structures;
      s.things.add(shape);
    }
  }, [items, showing, chosen, ground]);

  return <div className="world3d" ref={host} />;
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

/** Colonies by kind, each kind one instanced shape: plates spread flat, mounds
 *  sit round, branches and fans stand up. Coloured as reef coral is in water. */
const CORAL_SHAPES: Record<string, { make: () => THREE.BufferGeometry; colour: number }> = {
  // A plate spreads well past its foot: drawn twice its listed size across.
  table: { make: () => new THREE.CylinderGeometry(1, 0.85, 0.08, 20), colour: 0x6cc39c },
  massive: { make: () => new THREE.SphereGeometry(0.5, 14, 10, 0, Math.PI * 2, 0, Math.PI / 2), colour: 0xb08a5a },
  brain: { make: () => new THREE.SphereGeometry(0.5, 14, 10, 0, Math.PI * 2, 0, Math.PI / 2), colour: 0xc2a46a },
  branching: { make: () => new THREE.ConeGeometry(0.42, 0.9, 7), colour: 0x8f74b0 },
  finger: { make: () => new THREE.ConeGeometry(0.3, 0.8, 6), colour: 0xd08f6a },
  plume: { make: () => new THREE.ConeGeometry(0.22, 1.1, 6), colour: 0xc8607e },
  fan: { make: () => new THREE.BoxGeometry(0.9, 0.9, 0.06), colour: 0xd9714f },
  sponge: { make: () => new THREE.CylinderGeometry(0.25, 0.32, 0.7, 10), colour: 0xe09a3c },
  encrusting: { make: () => new THREE.SphereGeometry(0.5, 12, 6, 0, Math.PI * 2, 0, Math.PI / 3), colour: 0xcf7a8e },
};

function coralsOf(colonies: Colony[], ground: Ground, lift: number): THREE.Group {
  const group = new THREE.Group();
  const byKind = new Map<string, Colony[]>();
  for (const c of colonies) byKind.set(c.kind, [...(byKind.get(c.kind) ?? []), c]);
  const m = new THREE.Matrix4(), q = new THREE.Quaternion(), up = new THREE.Vector3(0, 1, 0);
  for (const [kind, list] of byKind) {
    const shape = CORAL_SHAPES[kind] ?? CORAL_SHAPES.massive!;
    const geometry = shape.make();
    // Standing on its foot; a plate held a little off the rock, as tables grow.
    geometry.computeBoundingBox();
    geometry.translate(0, -geometry.boundingBox!.min.y + (kind === "table" ? 0.2 : 0), 0);
    const mesh = new THREE.InstancedMesh(geometry, new THREE.MeshStandardMaterial({ color: shape.colour, roughness: 0.75 }), list.length);
    list.forEach((c, i) => {
      const [x, y] = c.at;
      const turn = (Math.sin(x * 12.9898 + y * 78.233) * 43758.5453) % 1;
      q.setFromAxisAngle(up, turn * Math.PI * 2);
      const size = Math.max(0.15, c.sizeM);
      m.compose(new THREE.Vector3(x, floor(ground, x, y, lift) - 0.02, -y), q, new THREE.Vector3(size, size, size));
      mesh.setMatrixAt(i, m);
    });
    group.add(mesh);
  }
  return group;
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

function material(kind: string, chosen: boolean, see?: number): THREE.MeshStandardMaterial {
  return new THREE.MeshStandardMaterial({
    color: COLOURS[kind] ?? 0x9aa6b2, roughness: 0.6, metalness: 0.1,
    emissive: chosen ? 0xff7a1a : 0x000000, emissiveIntensity: chosen ? 0.55 : 0,
    transparent: see !== undefined, opacity: see ?? 1,
  });
}

/** A thing's shape. Sizes are true; only depths are stretched by lift. */
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
    return tube([new THREE.Vector3(a.x, zOf(a), -a.y), new THREE.Vector3(b.x, zOf(b), -b.y)], least * 0.6);
  }
  if (item.corners && item.corners.length >= 3) {
    const points = [...item.corners, item.corners[0]!].map((p) => new THREE.Vector3(p.x, floor(ground, p.x, p.y, lift) + least, -p.y));
    const loop = new THREE.Line(new THREE.BufferGeometry().setFromPoints(points),
      new THREE.LineBasicMaterial({ color: chosen ? 0xff7a1a : COLOURS[item.kind] ?? 0x2e9e6e }));
    // A thin flat strip so a click on the edge finds it.
    const holder = new THREE.Group();
    holder.add(loop);
    const centre = item.corners.reduce((s, p) => ({ x: s.x + p.x / item.corners!.length, y: s.y + p.y / item.corners!.length }), { x: 0, y: 0 });
    const pad = new THREE.Mesh(new THREE.SphereGeometry(least * 2), material(item.kind, chosen));
    pad.position.set(centre.x, floor(ground, centre.x, centre.y, lift) + least * 2, -centre.y);
    holder.add(pad);
    return holder;
  }
  const holder = new THREE.Group();
  const base = floor(ground, item.x, item.y, lift);
  const surface = item.kind === "ship" || item.kind === "buoy" || item.kind === "dredger";
  holder.position.set(item.x, surface ? 0 : item.z !== undefined && item.z > -groundAt(ground, item.x, item.y) + 0.5 ? item.z * lift : base, -item.y);
  holder.rotation.y = -((item.headingDeg ?? 0) * Math.PI) / 180;
  // A thing on its own is a mark to find from across the world: no smaller
  // than a hundred-and-sixtieth of it.
  const seen = ground.acrossM / 160;
  const grow = (true_: number) => Math.max(true_, seen);
  switch (item.kind) {
    case "ship":
    case "dredger": {
      const hull = new THREE.Mesh(new THREE.BoxGeometry(grow(8), grow(3), grow(30)), material(item.kind, chosen));
      hull.position.y = -grow(3) / 2 + grow(1);
      holder.add(hull);
      break;
    }
    case "buoy": {
      const ball = new THREE.Mesh(new THREE.SphereGeometry(grow(0.8)), material(item.kind, chosen));
      holder.add(ball);
      break;
    }
    case "object":
    case "reef": {
      const [w, l, h] = item.sizeM ?? [3, 3, 1];
      const box = new THREE.Mesh(new THREE.BoxGeometry(grow(w), Math.max(h * lift, seen), grow(l)),
        material(item.kind, chosen, item.kind === "reef" ? 0.55 : undefined));
      box.position.y = Math.max(h * lift, seen) / 2;
      holder.add(box);
      break;
    }
    default: {
      const radius = grow(item.radiusM ?? (item.kind === "mooring-block" ? 0.6 : item.kind === "nursery-frame" ? 1 : 0.3));
      const height = Math.max((item.heightM ?? (item.kind === "marker-post" ? 3 : item.kind === "nursery-frame" ? 1 : 0.6)) * lift, seen * 2);
      const body = new THREE.Mesh(item.kind === "mooring-block" || item.kind === "nursery-frame"
        ? new THREE.BoxGeometry(radius * 2, height, radius * 2) : new THREE.CylinderGeometry(radius, radius, height, 16),
        material(item.kind, chosen));
      body.position.y = height / 2;
      holder.add(body);
    }
  }
  return holder;
}
