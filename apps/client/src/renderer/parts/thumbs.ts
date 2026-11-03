// Pictures of what can be put in a world, drawn from the same models the
// view draws, once each, by one renderer off the page.

import * as THREE from "three";

import { coralModel, equipmentModel } from "./World3D.js";

const SIZE = 112;
const made = new Map<string, string>();
let renderer: THREE.WebGLRenderer | undefined;

/** A picture of an equipment kind, or of a coral form as "coral:<form>". */
export function thumbOf(key: string): string | undefined {
  const have = made.get(key);
  if (have) return have;
  try {
    renderer ??= new THREE.WebGLRenderer({ antialias: true, alpha: true, preserveDrawingBuffer: true });
    renderer.setSize(SIZE, SIZE);
    renderer.setPixelRatio(2);
    renderer.outputColorSpace = THREE.SRGBColorSpace;
  } catch {
    return undefined;
  }
  const scene = new THREE.Scene();
  scene.add(new THREE.HemisphereLight(0xeaf4ff, 0x2a3640, 1.4));
  const sun = new THREE.DirectionalLight(0xffffff, 1.8);
  sun.position.set(-2, 4, 3);
  scene.add(sun);
  const model = key.startsWith("coral:") ? coralModel(key.slice(6)) : equipmentModel(key);
  scene.add(model);
  const box = new THREE.Box3().setFromObject(model);
  const centre = box.getCenter(new THREE.Vector3());
  const radius = box.getSize(new THREE.Vector3()).length() / 2;
  const camera = new THREE.PerspectiveCamera(30, 1, radius / 100, radius * 100);
  camera.position.copy(centre).add(new THREE.Vector3(1, 0.75, 1.25).normalize().multiplyScalar(radius / Math.sin(Math.PI / 12) * 1.05));
  camera.lookAt(centre);
  renderer.setClearColor(0x000000, 0);
  renderer.clear();
  renderer.render(scene, camera);
  const url = renderer.domElement.toDataURL("image/png");
  scene.traverse((o) => {
    const mesh = o as THREE.Mesh;
    mesh.geometry?.dispose();
    (mesh.material as THREE.Material | undefined)?.dispose?.();
  });
  made.set(key, url);
  return url;
}
