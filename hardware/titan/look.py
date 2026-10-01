"""A page to look at the moulded form: lit like a product shot, orbitable.

    hardware/.venv/bin/python hardware/titan/look.py [titan|mini]   → hardware/out/<which>/look.html

Reads shape.json from shape.py. ?view=iso|front|top|side|rear|under picks
the opening camera, so a still can be taken from any of them.
"""

from __future__ import annotations

import pathlib
import sys

OUT = pathlib.Path(__file__).resolve().parents[1] / "out" / (sys.argv[1] if len(sys.argv) > 1 else "titan")

PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Mini Titan</title>
<style>
:root{--bg:#eef0f2;--ink:#1b1d20}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#eef0f2;--ink:#1b1d20}}
html,body{margin:0;height:100%;background:var(--bg);color:var(--ink);font:13px system-ui,sans-serif;overflow:hidden}
canvas{display:block}
#views{position:fixed;left:16px;bottom:16px;display:flex;gap:6px;flex-wrap:wrap}
#views button{border:1px solid #c9cdd2;background:#fff;border-radius:6px;padding:6px 10px;cursor:pointer}
</style>
<script type="importmap">{"imports":{"three":"https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.module.js","three/addons/":"https://cdn.jsdelivr.net/npm/three@0.160.0/examples/jsm/"}}</script>
</head><body>
<div id="views"></div>
<script type="module">
import * as THREE from 'three';
import {OrbitControls} from 'three/addons/controls/OrbitControls.js';
import {RoomEnvironment} from 'three/addons/environments/RoomEnvironment.js';
const PARTS = __PARTS__;
const r = new THREE.WebGLRenderer({antialias:true, preserveDrawingBuffer:true});
r.setPixelRatio(Math.min(devicePixelRatio, 2));
r.setSize(innerWidth, innerHeight);
r.toneMapping = THREE.ACESFilmicToneMapping; r.toneMappingExposure = 1.0;
r.shadowMap.enabled = true; r.shadowMap.type = THREE.PCFSoftShadowMap;
document.body.appendChild(r.domElement);
const scene = new THREE.Scene();
scene.background = new THREE.Color(0xeef0f2);
const pm = new THREE.PMREMGenerator(r);
scene.environment = pm.fromScene(new RoomEnvironment(r), 0.04).texture;
const cam = new THREE.PerspectiveCamera(30, innerWidth/innerHeight, 1, 5000);
const ctl = new OrbitControls(cam, r.domElement); ctl.enableDamping = true;
const key = new THREE.DirectionalLight(0xffffff, 1.6); key.position.set(150, 200, 400);
key.castShadow = true; key.shadow.mapSize.set(2048, 2048);
Object.assign(key.shadow.camera, {left:-200, right:200, top:200, bottom:-200, near:10, far:1200});
scene.add(key);
const dec = s => Uint8Array.from(atob(s), c => c.charCodeAt(0)).buffer;
const FAST = new URLSearchParams(location.search).has('fast');
const FIN = {
  gloss: c => new THREE.MeshPhysicalMaterial({color:c, roughness:0.32, metalness:0, clearcoat:1, clearcoatRoughness:0.08}),
  satin: c => new THREE.MeshPhysicalMaterial({color:c, roughness:0.55, metalness:0, clearcoat:0.25, clearcoatRoughness:0.35}),
  glass: c => new THREE.MeshPhysicalMaterial({color:c, roughness:0.05, metalness:0.2, clearcoat:1}),
  glow: c => new THREE.MeshStandardMaterial({color:c, emissive:c, emissiveIntensity:1.5}),
  metal: c => new THREE.MeshPhysicalMaterial({color:c, roughness:0.35, metalness:0.85}),
  // Transmission is a second render pass; a software renderer for stills cannot afford it.
  clear: c => FAST ? new THREE.MeshPhysicalMaterial({color:c, roughness:0.05, metalness:0, opacity:0.22, transparent:true, clearcoat:1, depthWrite:false})
                  : new THREE.MeshPhysicalMaterial({color:c, roughness:0.02, metalness:0, transmission:0.96, thickness:3, ior:1.49, transparent:true}),
};
const root = new THREE.Group();
root.rotation.x = -Math.PI/2;          // the model is z up, three is y up
for (const p of PARTS) {
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.BufferAttribute(new Float32Array(dec(p.positions)), 3));
  g.setAttribute('normal', new THREE.BufferAttribute(new Float32Array(dec(p.normals)), 3));
  g.setIndex(new THREE.BufferAttribute(new Uint32Array(dec(p.indices)), 1));
  const m = new THREE.Mesh(g, FIN[p.finish](new THREE.Color(p.colour)));
  m.castShadow = m.receiveShadow = true; root.add(m);
}
scene.add(root);
const box = new THREE.Box3().setFromObject(root);
const floor = new THREE.Mesh(new THREE.PlaneGeometry(4000, 4000), new THREE.ShadowMaterial({opacity:0.18}));
floor.rotation.x = -Math.PI/2; floor.position.y = box.min.y - 0.5; floor.receiveShadow = true; scene.add(floor);
const c = box.getCenter(new THREE.Vector3());
ctl.target.copy(c);
// Three's frame: x forward, y up, z = -port (starboard).
const VIEWS = {iso:[1.0,0.62,-0.95], front:[1,0.12,0], side:[0,0.12,-1], rear:[-1,0.35,-0.5], top:[0.0001,1,0], under:[0.6,-0.5,-0.7], quarter:[-0.7,0.55,-1]};
const R = box.getBoundingSphere(new THREE.Sphere()).radius;
function fit(){ const v = THREE.MathUtils.degToRad(cam.fov)/2; const h = Math.atan(Math.tan(v)*cam.aspect); return R*0.78/Math.sin(Math.min(v,h)); }
function view(n){ const v = new THREE.Vector3(...VIEWS[n]).normalize().multiplyScalar(fit()); cam.position.copy(c).add(v); cam.up.set(n==='top'?1:0, n==='top'?0:1, 0); ctl.update(); }
const bar = document.getElementById('views');
for (const n of Object.keys(VIEWS)) { const b = document.createElement('button'); b.textContent = n; b.onclick = () => view(n); bar.appendChild(b); }
const Q = new URLSearchParams(location.search);
if (Q.get('eye')) {
  // A camera given in the model's own frame (x, y, z up), as a place's fixed view is.
  const [ex, ey, ez] = Q.get('eye').split(',').map(Number), [ax, ay, az] = (Q.get('aim') || '0,0,0').split(',').map(Number);
  cam.fov = Number(Q.get('fov') || 50); cam.updateProjectionMatrix();
  cam.position.set(ex, ez, -ey); ctl.target.set(ax, az, -ay); cam.up.set(0, 1, 0); ctl.update();
} else view(Q.get('view') || 'iso');
addEventListener('resize', () => { cam.aspect = innerWidth/innerHeight; cam.updateProjectionMatrix(); r.setSize(innerWidth, innerHeight); });
(function loop(){ requestAnimationFrame(loop); ctl.update(); r.render(scene, cam); })();
</script></body></html>
"""


def main() -> int:
    parts = (OUT / "shape.json").read_text()
    (OUT / "look.html").write_text(PAGE.replace("__PARTS__", parts))
    print(OUT / "look.html")
    return 0


if __name__ == "__main__":
    sys.exit(main())
