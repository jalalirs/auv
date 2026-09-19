"""The head's design sheet: the model you can orbit, the parts, the open
questions. Generated from head.py's output and README.md.

    hardware/.venv/bin/python hardware/fish/sheet.py   → hardware/out/fish/head.html
"""

from __future__ import annotations

import html
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import params as P  # noqa: E402

OUT = pathlib.Path(__file__).resolve().parents[1] / "out" / "fish"
README = pathlib.Path(__file__).parent / "README.md"


def md_inline(s: str) -> str:
    s = html.escape(s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"`(.+?)`", r"<code>\1</code>", s)
    return s


def open_questions() -> list[str]:
    text = README.read_text()
    m = re.search(r"^## The open questions.*?\n(.*?)(?=^## |\Z)", text, re.S | re.M)
    items, cur = [], None
    for line in m.group(1).splitlines():
        if re.match(r"^\d+\. ", line):
            if cur: items.append(cur)
            cur = re.sub(r"^\d+\. ", "", line)
        elif cur is not None and line.strip():
            cur += " " + line.strip()
    if cur: items.append(cur)
    return items


def main() -> int:
    parts = json.loads((OUT / "parts.json").read_text())
    printed = {k: v for k, v in parts.items() if "print" in v}
    bought = {k: v for k, v in parts.items() if "buy" in v}
    groups = {
        "shell": ["shell", "bezel"], "drive plate": ["drive-plate", "crank"], "tail bay": ["tail-bay"],
        "tray": ["tray"], "motor + seal": ["ref-motor", "ref-seal"], "boards + camera": ["ref-boards", "ref-camera"],
        "window + glands": ["ref-window", "ref-glands"], "cables + ribs": ["ref-cables", "ref-ribs"],
    }
    groups = {g: [n for n in ns if n in parts] for g, ns in groups.items()}
    legend = "".join(
        f"<label><input type='checkbox' data-group='{g}' checked><span class='swatch' "
        f"style='background:{parts[ns[0]]['colour']}'></span>{g}</label>" for g, ns in groups.items() if ns)
    printed_rows = "".join(
        f"<tr><td><span class='swatch' style='background:{v['colour']}'></span> {k}</td><td class='num'>{v['volume_cm3']:.0f}</td>"
        f"<td class='num'>{v['mass_g']}</td><td class='num'>{' × '.join(f'{d:.0f}' for d in v['bbox_mm'])}</td><td class='src'>{html.escape(v['print'])}</td></tr>"
        for k, v in printed.items())
    bought_rows = "".join(
        f"<tr><td><span class='swatch' style='background:{v['colour']}'></span> {k.replace('ref-', '')}</td><td>{html.escape(v['buy'])}</td></tr>"
        for k, v in bought.items())
    questions = "".join(f"<li>{md_inline(q)}</li>" for q in open_questions())
    mass = sum(v["mass_g"] for v in printed.values())

    page = f"""<title>Fish Head</title>
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@500;600;700&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
:root {{
  --ground: #eef3f4; --surface: #ffffff; --ink: #17191b; --muted: #5a6670; --rule: #d3dbde;
  --accent: #f26a1b; --accent-ink: #ffffff; --water: #7fb3d5; --good: #2e7d32;
  --display: "Barlow Condensed", "Arial Narrow", sans-serif; --body: "IBM Plex Sans", "Helvetica Neue", Arial, sans-serif; --mono: "IBM Plex Mono", Menlo, monospace;
  color-scheme: light;
}}
@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{ --ground: #101416; --surface: #171c1f; --ink: #e8ecee; --muted: #98a4ab; --rule: #2a3236; --accent: #f58a45; --accent-ink: #17191b; --water: #6fa3c8; --good: #7bc47f; color-scheme: dark; }} }}
:root[data-theme="dark"] {{ --ground: #101416; --surface: #171c1f; --ink: #e8ecee; --muted: #98a4ab; --rule: #2a3236; --accent: #f58a45; --accent-ink: #17191b; --water: #6fa3c8; --good: #7bc47f; color-scheme: dark; }}
* {{ box-sizing: border-box; }}
body {{ margin: 0; background: var(--ground); color: var(--ink); font-family: var(--body); font-size: 15px; line-height: 1.5; }}
h1, h2, h3 {{ font-family: var(--display); font-weight: 600; margin: 0; text-wrap: balance; }}
h1 {{ font-size: 44px; line-height: 1; }} h2 {{ font-size: 26px; line-height: 1.1; }}
h3 {{ font-size: 18px; text-transform: uppercase; letter-spacing: 0.06em; color: var(--muted); margin: 22px 0 8px; }}
.eyebrow {{ font-family: var(--display); font-weight: 500; text-transform: uppercase; letter-spacing: 0.12em; font-size: 13px; color: var(--accent); }}
header {{ display: flex; align-items: flex-end; justify-content: space-between; gap: 24px; padding: 28px 32px 16px; max-width: 1240px; margin: 0 auto; }}
header p {{ margin: 6px 0 0; color: var(--muted); max-width: 64ch; }}
.stage {{ position: relative; height: 62vh; min-height: 420px; background: linear-gradient(180deg, color-mix(in oklab, var(--water) 18%, var(--ground)), var(--ground)); border-top: 1px solid var(--rule); border-bottom: 1px solid var(--rule); }}
.stage canvas {{ display: block; width: 100%; height: 100%; }}
.legend {{ position: absolute; top: 14px; left: 14px; background: color-mix(in oklab, var(--surface) 88%, transparent); border: 1px solid var(--rule); border-radius: 6px; padding: 10px 12px; display: grid; gap: 6px; font-size: 13px; backdrop-filter: blur(6px); }}
.legend label {{ display: flex; align-items: center; gap: 8px; cursor: pointer; }}
.legend input {{ accent-color: var(--accent); margin: 0; }}
.swatch {{ width: 12px; height: 12px; border-radius: 2px; border: 1px solid var(--rule); display: inline-block; }}
.legend button {{ margin-top: 4px; font: 500 13px var(--body); background: var(--accent); color: var(--accent-ink); border: 0; border-radius: 4px; padding: 6px 10px; cursor: pointer; }}
.legend button:focus-visible, .legend input:focus-visible {{ outline: 2px solid var(--accent); outline-offset: 2px; }}
.hint {{ position: absolute; right: 14px; bottom: 12px; font-size: 12px; color: var(--muted); }}
main {{ max-width: 1240px; margin: 0 auto; padding: 8px 32px 48px; }}
.strip {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 14px; margin: 24px 0 8px; }}
.stat {{ background: var(--surface); border: 1px solid var(--rule); border-radius: 6px; padding: 12px 14px; }}
.stat .v {{ font-family: var(--display); font-size: 34px; font-weight: 700; line-height: 1; font-variant-numeric: tabular-nums; }}
.stat .v small {{ font-size: 16px; font-weight: 500; color: var(--muted); margin-left: 3px; }}
.stat .k {{ font-size: 12px; text-transform: uppercase; letter-spacing: 0.08em; color: var(--muted); margin-top: 6px; }}
.cols {{ display: grid; grid-template-columns: 1fr 1fr; gap: 32px; }}
@media (max-width: 900px) {{ .cols {{ grid-template-columns: 1fr; }} header {{ flex-direction: column; align-items: flex-start; }} }}
.scroll {{ overflow-x: auto; }}
table {{ border-collapse: collapse; width: 100%; font-size: 13.5px; }}
th, td {{ text-align: left; padding: 6px 8px; border-bottom: 1px solid var(--rule); vertical-align: top; }}
th {{ font-family: var(--display); font-weight: 600; text-transform: uppercase; letter-spacing: 0.06em; font-size: 12px; color: var(--muted); }}
td.num, th.num {{ text-align: right; font-family: var(--mono); font-variant-numeric: tabular-nums; white-space: nowrap; }}
td.src {{ color: var(--muted); font-size: 12.5px; }}
ol.q {{ padding-left: 22px; display: grid; gap: 10px; margin: 8px 0 0; }}
ol.q li {{ background: var(--surface); border: 1px solid var(--rule); border-radius: 6px; padding: 10px 12px; }}
.seal {{ border-left: 3px solid var(--accent); padding: 10px 14px; background: var(--surface); margin: 14px 0; }}
footer {{ color: var(--muted); font-size: 13px; border-top: 1px solid var(--rule); padding-top: 14px; margin-top: 36px; }}
code {{ font-family: var(--mono); font-size: 0.92em; }}
</style>

<header>
  <div>
    <div class="eyebrow">Hardware · fish v1 · the head</div>
    <h1>Fish Head</h1>
    <p>One sealed shell from nose to bulkhead. A drive plate closes the rear on an O-ring and carries the motor on its dry side, a lip seal in its thickness, and the crank on its wet side. Behind it a flooded bay guides the two cables into OpenFish's tail. No cable ever crosses a seal; only a 4 mm shaft does.</p>
  </div>
  <div class="eyebrow" style="text-align:right">Drag to orbit · scroll to zoom<br>Generated from the model</div>
</header>

<div class="stage" id="stage">
  <canvas id="view"></canvas>
  <div class="legend">{legend}<button id="lift" type="button">Lift the shell</button></div>
  <div class="hint">x forward · y port · z up · millimetres · origin on the bulkhead plane</div>
</div>

<main>
  <div class="strip">
    <div class="stat"><div class="v">{P.HEAD_LENGTH:.0f}<small>mm</small></div><div class="k">Nose to first rib</div></div>
    <div class="stat"><div class="v">{max(s[1] for s in P.STATIONS):.0f}<small>× {max(s[2] for s in P.STATIONS):.0f} mm</small></div><div class="k">Widest section</div></div>
    <div class="stat"><div class="v">{mass}<small>g</small></div><div class="k">Printed, PETG</div></div>
    <div class="stat"><div class="v">{P.MOTOR_STALL_KGCM:.1f}<small>kg·cm</small></div><div class="k">Motor stall, direct drive</div></div>
    <div class="stat"><div class="v">{'/'.join(f'{r:.0f}' for r in P.CRANK_RADII)}<small>mm</small></div><div class="k">Crank radii to choose from</div></div>
    <div class="stat"><div class="v">{2 * P.CABLE_Y:.1f}<small>mm</small></div><div class="k">Cable spacing, OpenFish's</div></div>
  </div>

  <div class="cols">
    <section>
      <h2>Parts</h2>
      <h3>Printed</h3>
      <div class="scroll"><table><thead><tr><th>Part</th><th class="num">cm³</th><th class="num">g</th><th class="num">Box, mm</th><th>How</th></tr></thead><tbody>{printed_rows}</tbody></table></div>
      <h3>Bought, drawn for the fit</h3>
      <div class="scroll"><table><thead><tr><th>Drawn as</th><th>Part</th></tr></thead><tbody>{bought_rows}</tbody></table></div>
      <div class="seal"><strong>Where water is kept out.</strong> Shell: epoxy coat inside, window on a 26 × 2 O-ring, two PG7 glands on the crown. Plate to shell: a 66 × 2 face O-ring under six M3. Shaft: a 4 × 10 × 4 lip seal, greased, lip to the water. Everything behind the plate floods on purpose.</div>
    </section>
    <section>
      <h2>Open questions, in the order they close</h2>
      <ol class="q">{questions}</ol>
    </section>
  </div>

  <footer>Sources: <code>hardware/fish/params.py</code> (every dimension and its origin), <code>head.py</code> (the parts as code, exporting STEP for Sketchat and JLC3DP), <code>README.md</code>. The tail is OpenFish's (TU Delft, CC BY-SA 4.0); its files are in <code>hardware/reference/openfish</code>.</footer>
</main>

<script src="https://cdn.jsdelivr.net/npm/three@0.128.0/build/three.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/controls/OrbitControls.js"></script>
<script>
(function () {{
  const groups = {json.dumps(groups)};
  const stage = document.getElementById("stage"), canvas = document.getElementById("view");
  const renderer = new THREE.WebGLRenderer({{ canvas, antialias: true, alpha: true }});
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2)); renderer.outputEncoding = THREE.sRGBEncoding;
  const scene = new THREE.Scene(), camera = new THREE.PerspectiveCamera(32, 1, 1, 5000);
  const world = new THREE.Group(); world.rotation.x = -Math.PI / 2; scene.add(world);
  scene.add(new THREE.HemisphereLight(0xffffff, 0x8899aa, 0.9));
  const key = new THREE.DirectionalLight(0xffffff, 0.8); key.position.set(200, -300, 400); scene.add(key);
  const fill = new THREE.DirectionalLight(0xffffff, 0.35); fill.position.set(-300, 200, -100); scene.add(fill);
  const controls = new THREE.OrbitControls(camera, canvas); controls.enableDamping = true; controls.dampingFactor = 0.08;
  const nodes = {{}}; let shell = null, bezel = null, lifted = false, target = 0;
  function size() {{ const w = stage.clientWidth, h = stage.clientHeight; renderer.setSize(w, h, false); camera.aspect = w / h; camera.updateProjectionMatrix(); }}
  window.addEventListener("resize", size); size();
  function decode(b64) {{ const bin = atob(b64), bytes = new Uint8Array(bin.length); for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i); return new Float32Array(bytes.buffer); }}
  fetch("head.json").then((r) => r.json()).then((parts) => {{
    for (const part of parts) {{
      const g = new THREE.BufferGeometry(); g.setAttribute("position", new THREE.BufferAttribute(decode(part.positions), 3)); g.computeVertexNormals();
      const m = new THREE.MeshStandardMaterial({{ color: part.colour, roughness: 0.55, metalness: 0.05, flatShading: true }});
      if (part.alpha < 0.99) {{ m.transparent = true; m.opacity = part.alpha; m.depthWrite = false; }}
      const o = new THREE.Mesh(g, m); o.name = part.name; o.renderOrder = part.alpha < 0.99 ? 2 : 1;
      nodes[part.name] = o; if (part.name === "shell") shell = o; if (part.name === "bezel") bezel = o; world.add(o);
    }}
    const box = new THREE.Box3().setFromObject(world), c = box.getCenter(new THREE.Vector3()), r = box.getSize(new THREE.Vector3()).length() / 2;
    controls.target.copy(c); camera.position.set(c.x + r * 1.4, c.y + r * 1.1, c.z + r * 1.5);
    camera.near = r / 50; camera.far = r * 20; camera.updateProjectionMatrix();
  }});
  document.querySelectorAll(".legend input").forEach((b) => b.addEventListener("change", () => {{ for (const n of groups[b.dataset.group]) if (nodes[n]) nodes[n].visible = b.checked; }}));
  const button = document.getElementById("lift");
  button.addEventListener("click", () => {{ lifted = !lifted; target = lifted ? 110 : 0; button.textContent = lifted ? "Close the shell" : "Lift the shell"; }});
  const still = matchMedia("(prefers-reduced-motion: reduce)").matches;
  function frame() {{
    for (const o of [shell, bezel]) if (o) o.position.z += still ? (target - o.position.z) : (target - o.position.z) * 0.12;
    controls.update(); renderer.render(scene, camera); requestAnimationFrame(frame);
  }}
  frame();
}})();
</script>
"""
    (OUT / "head.html").write_text(page)
    print(OUT / "head.html")
    return 0


if __name__ == "__main__":
    sys.exit(main())
