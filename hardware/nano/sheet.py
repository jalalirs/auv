"""The design sheet: one page, generated from the model's own numbers.

    hardware/.venv/bin/python hardware/nano/sheet.py   → hardware/out/sheet.html

The page carries the coloured model (nano.glb beside it), the envelope, the
mass budget, the bill of materials and the open items. Nothing on it is
typed twice: parts.json, params.py and budget.py are the sources.
"""

from __future__ import annotations

import html
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import budget  # noqa: E402
import params as P  # noqa: E402

OUT = pathlib.Path(__file__).resolve().parents[1] / "out"
README = pathlib.Path(__file__).resolve().parents[1] / "README.md"
BOM = pathlib.Path(__file__).parent / "bom.md"


def md_table_rows(section: str) -> list[list[str]]:
    """The rows of the first table under a heading in bom.md."""
    text = BOM.read_text()
    m = re.search(rf"^## {re.escape(section)}\n(.*?)(?=^## |\Z)", text, re.S | re.M)
    rows = []
    for line in m.group(1).splitlines():
        if line.startswith("|") and not set(line) <= set("|- "):
            cells = [c.strip() for c in line.strip("|").split("|")]
            rows.append(cells)
    return rows[1:]  # drop the header


def md_inline(s: str) -> str:
    s = html.escape(s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"\[(.+?)\]\((.+?)\)", r'<a href="\2">\1</a>', s)
    return s


def open_items() -> list[tuple[bool, str]]:
    items = []
    for line in README.read_text().splitlines():
        m = re.match(r"^- \[( |x)\] (.*)$", line)
        if m:
            items.append((m.group(1) == "x", m.group(2)))
        elif items and line.startswith("      "):
            done, text = items[-1]
            items[-1] = (done, text + " " + line.strip())
    return items


def geometry(parts: dict) -> None:
    """nano.json: every part as flat triangles, float32 in base64, with its
    colour. The artifact host serves JSON and not GLB, and three.js builds a
    mesh from this in a dozen lines without a loader."""
    import base64

    import numpy as np
    import trimesh

    out = []
    for name, meta in parts.items():
        mesh = trimesh.load(OUT / f"{name}.stl", force="mesh")
        tris = mesh.vertices[mesh.faces].astype(np.float32).reshape(-1)
        out.append({"name": name, "colour": meta["colour"], "alpha": meta.get("alpha", 1.0),
                    "triangles": int(len(mesh.faces)),
                    "positions": base64.b64encode(tris.tobytes()).decode("ascii")})
    (OUT / "nano.json").write_text(json.dumps(out))
    print(OUT / "nano.json", sum(p["triangles"] for p in out), "triangles")


def main() -> int:
    parts = json.loads((OUT / "parts.json").read_text())
    geometry(parts)
    b = budget.compute()
    printed = {k: v for k, v in parts.items() if "print" in v}
    bought = {k: v for k, v in parts.items() if "buy" in v}

    budget_rows = "".join(
        f"<tr><td>{html.escape(n)}</td><td class='num'>{m:.0f}</td>"
        f"<td class='num'>{'' if v is None else f'{v:.0f}'}</td><td class='num'>{z:+.0f}</td>"
        f"<td class='src'>{html.escape(s)}</td></tr>"
        for n, m, v, z, s in b["rows"])

    def bom_section(title: str):
        rows = md_table_rows(title)
        body = "".join("<tr>" + "".join(
            f"<td class='{'num' if i in (1, 2) else ''}'>{md_inline(c)}</td>" for i, c in enumerate(r)) + "</tr>"
            for r in rows)
        return (f"<h3>{html.escape(title)}</h3><div class='scroll'><table class='bom'>"
                f"<thead><tr><th>Part</th><th class='num'>Qty</th><th class='num'>USD</th><th>Source</th></tr></thead>"
                f"<tbody>{body}</tbody></table></div>")

    bom_html = "".join(bom_section(t) for t in
                       ("The dry hull (Blue Robotics, 3\" locking series)", "Propulsion", "Inside the tube", "Outside"))

    items_html = "".join(
        f"<li class='{'done' if d else ''}'><span class='tick'>{'✓' if d else ''}</span><span>{md_inline(t)}</span></li>"
        for d, t in open_items())

    thrusters = [(n, at, "z") for n, at in P.VERTICAL] + [(n, at, "x") for n, at in P.HORIZONTAL]
    thruster_rows = "".join(
        f"<tr><td>{n}</td><td class='num'>{x:+.0f}</td><td class='num'>{y:+.0f}</td><td class='num'>{z:+.0f}</td>"
        f"<td class='num'>{'+' + a}</td></tr>" for n, (x, y, z), a in thrusters)

    groups = {
        "cover": ["cover"], "chassis": ["chassis", "bezel"], "hull": ["ref-tube", "ref-front-cap", "ref-rear-cap"],
        "thrusters": ["ref-thrusters"], "inside": ["ref-camera", "ref-computer", "ref-battery", "ref-escs"],
        "lights": ["ref-lights"],
    }
    legend = "".join(
        f"<label><input type='checkbox' data-group='{g}' checked><span class='swatch' "
        f"style='background:{parts[names[0]]['colour']}'></span>{g}</label>" for g, names in groups.items())

    page = f"""<title>Nano Titan</title>
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@500;600;700&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
:root {{
  --ground: #eef3f4; --surface: #ffffff; --ink: #17191b; --muted: #5a6670; --rule: #d3dbde;
  --accent: #f26a1b; --accent-ink: #ffffff; --acrylic: #7fb3d5; --good: #2e7d32;
  --display: "Barlow Condensed", "Arial Narrow", sans-serif;
  --body: "IBM Plex Sans", "Helvetica Neue", Arial, sans-serif;
  --mono: "IBM Plex Mono", "SFMono-Regular", Menlo, monospace;
  color-scheme: light;
}}
@media (prefers-color-scheme: dark) {{
  :root:not([data-theme="light"]) {{
    --ground: #101416; --surface: #171c1f; --ink: #e8ecee; --muted: #98a4ab; --rule: #2a3236;
    --accent: #f58a45; --accent-ink: #17191b; --acrylic: #6fa3c8; --good: #7bc47f; color-scheme: dark;
  }}
}}
:root[data-theme="dark"] {{
  --ground: #101416; --surface: #171c1f; --ink: #e8ecee; --muted: #98a4ab; --rule: #2a3236;
  --accent: #f58a45; --accent-ink: #17191b; --acrylic: #6fa3c8; --good: #7bc47f; color-scheme: dark;
}}
* {{ box-sizing: border-box; }}
body {{ margin: 0; background: var(--ground); color: var(--ink); font-family: var(--body); font-size: 15px; line-height: 1.5; }}
a {{ color: inherit; text-decoration-color: var(--accent); }}
h1, h2, h3 {{ font-family: var(--display); font-weight: 600; letter-spacing: 0.01em; text-wrap: balance; margin: 0; }}
h1 {{ font-size: 44px; line-height: 1; }}
h2 {{ font-size: 26px; line-height: 1.1; }}
h3 {{ font-size: 18px; text-transform: uppercase; letter-spacing: 0.06em; color: var(--muted); margin: 22px 0 8px; }}
.eyebrow {{ font-family: var(--display); font-weight: 500; text-transform: uppercase; letter-spacing: 0.12em; font-size: 13px; color: var(--accent); }}
header {{ display: flex; align-items: flex-end; justify-content: space-between; gap: 24px; padding: 28px 32px 16px; max-width: 1240px; margin: 0 auto; }}
header p {{ margin: 6px 0 0; color: var(--muted); max-width: 62ch; }}
.stage {{ position: relative; height: 64vh; min-height: 420px; background: linear-gradient(180deg, color-mix(in oklab, var(--acrylic) 18%, var(--ground)), var(--ground)); border-top: 1px solid var(--rule); border-bottom: 1px solid var(--rule); }}
.stage canvas {{ display: block; width: 100%; height: 100%; }}
.legend {{ position: absolute; top: 14px; left: 14px; background: color-mix(in oklab, var(--surface) 88%, transparent); border: 1px solid var(--rule); border-radius: 6px; padding: 10px 12px; display: grid; gap: 6px; font-size: 13px; backdrop-filter: blur(6px); }}
.legend label {{ display: flex; align-items: center; gap: 8px; cursor: pointer; text-transform: capitalize; }}
.legend input {{ accent-color: var(--accent); margin: 0; }}
.swatch {{ width: 12px; height: 12px; border-radius: 2px; border: 1px solid var(--rule); display: inline-block; }}
.legend button {{ margin-top: 4px; font: 500 13px var(--body); background: var(--accent); color: var(--accent-ink); border: 0; border-radius: 4px; padding: 6px 10px; cursor: pointer; }}
.legend button:focus-visible, .legend input:focus-visible {{ outline: 2px solid var(--accent); outline-offset: 2px; }}
.hint {{ position: absolute; right: 14px; bottom: 12px; font-size: 12px; color: var(--muted); }}
main {{ max-width: 1240px; margin: 0 auto; padding: 8px 32px 48px; }}
.strip {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 14px; margin: 24px 0 8px; }}
.stat {{ background: var(--surface); border: 1px solid var(--rule); border-radius: 6px; padding: 12px 14px; }}
.stat .v {{ font-family: var(--display); font-size: 34px; font-weight: 700; line-height: 1; font-variant-numeric: tabular-nums; }}
.stat .v small {{ font-size: 16px; font-weight: 500; color: var(--muted); margin-left: 3px; }}
.stat .k {{ font-size: 12px; text-transform: uppercase; letter-spacing: 0.08em; color: var(--muted); margin-top: 6px; }}
.stat.net .v {{ color: var(--good); }}
.cols {{ display: grid; grid-template-columns: 1fr 1fr; gap: 32px; }}
@media (max-width: 900px) {{ .cols {{ grid-template-columns: 1fr; }} header {{ flex-direction: column; align-items: flex-start; }} }}
.scroll {{ overflow-x: auto; }}
table {{ border-collapse: collapse; width: 100%; font-size: 13.5px; }}
th, td {{ text-align: left; padding: 6px 8px; border-bottom: 1px solid var(--rule); vertical-align: top; }}
th {{ font-family: var(--display); font-weight: 600; text-transform: uppercase; letter-spacing: 0.06em; font-size: 12px; color: var(--muted); }}
td.num, th.num {{ text-align: right; font-family: var(--mono); font-variant-numeric: tabular-nums; white-space: nowrap; }}
td.src {{ color: var(--muted); font-size: 12.5px; }}
tr.total td {{ font-weight: 600; border-top: 2px solid var(--ink); }}
.note {{ background: var(--surface); border-left: 3px solid var(--accent); padding: 10px 14px; margin: 14px 0; color: var(--ink); }}
ul.items {{ list-style: none; padding: 0; margin: 0; display: grid; gap: 8px; }}
ul.items li {{ display: grid; grid-template-columns: 22px 1fr; gap: 8px; padding: 8px 10px; background: var(--surface); border: 1px solid var(--rule); border-radius: 6px; }}
ul.items li.done {{ color: var(--muted); }}
.tick {{ font-family: var(--mono); color: var(--good); text-align: center; }}
ul.items li:not(.done) .tick::before {{ content: ""; display: block; width: 10px; height: 10px; border: 1.5px solid var(--accent); border-radius: 2px; margin: 5px auto; }}
footer {{ color: var(--muted); font-size: 13px; border-top: 1px solid var(--rule); padding-top: 14px; margin-top: 36px; }}
code {{ font-family: var(--mono); font-size: 0.92em; }}
@media (prefers-reduced-motion: reduce) {{ .legend button {{ transition: none; }} }}
</style>

<header>
  <div>
    <div class="eyebrow">Hardware &middot; first vehicle &middot; design sheet</div>
    <h1>Nano Titan</h1>
    <p>A Geneinno Titan at 0.55 scale, built the way hobby ROVs are built: a bought acrylic tube is the dry hull and the seal, printed nylon around it is the shape, the structure and the thruster pods. Battery inside, tether removable. It flies over the same ROS 2 topics the simulator's vehicles do.</p>
  </div>
  <div class="eyebrow" style="text-align:right">Drag to orbit &middot; scroll to zoom<br>Generated from the model, 18 Sep 2026</div>
</header>

<div class="stage" id="stage">
  <canvas id="view"></canvas>
  <div class="legend">{legend}<button id="lift" type="button">Lift the cover</button></div>
  <div class="hint">x forward &middot; y port &middot; z up &middot; millimetres</div>
</div>

<main>
  <div class="strip">
    <div class="stat"><div class="v">{P.OVERALL_L:.0f}<small>× {P.OVERALL_W:.0f} × {P.OVERALL_H:.0f} mm</small></div><div class="k">Envelope with the stern pods</div></div>
    <div class="stat"><div class="v">{b['mass_g']:.0f}<small>g</small></div><div class="k">Mass, all parts</div></div>
    <div class="stat"><div class="v">{b['displaced_cm3']:.0f}<small>cm³</small></div><div class="k">Displacement</div></div>
    <div class="stat net"><div class="v">{b['net_g']:+.0f}<small>g</small></div><div class="k">Net in fresh water &middot; floats</div></div>
    <div class="stat"><div class="v">{b['righting_mm']:.1f}<small>mm</small></div><div class="k">Righting arm, CB above CG</div></div>
    <div class="stat"><div class="v">{b['heave_n']:.1f}<small>N</small></div><div class="k">Heave, 4 verticals</div></div>
    <div class="stat"><div class="v">{b['surge_n']:.1f}<small>N</small></div><div class="k">Surge, 2 stern pods</div></div>
  </div>

  <div class="cols">
    <section>
      <h2>What it is made of</h2>
      <h3>Printed, MJF PA12 at JLC3DP</h3>
      <div class="scroll"><table>
        <thead><tr><th>Part</th><th class="num">cm³</th><th class="num">g</th><th class="num">Box, mm</th><th>Finish</th></tr></thead>
        <tbody>{''.join(f"<tr><td>{k}</td><td class='num'>{v['volume_cm3']:.0f}</td><td class='num'>{v['mass_g']}</td><td class='num'>{' × '.join(f'{d:.0f}' for d in v['bbox_mm'])}</td><td class='src'>{html.escape(v['print'])}</td></tr>" for k, v in printed.items())}</tbody>
      </table></div>
      <h3>Bought</h3>
      <div class="scroll"><table>
        <thead><tr><th>Drawn as</th><th>Part</th></tr></thead>
        <tbody>{''.join(f"<tr><td><span class='swatch' style='background:{v['colour']}'></span> {k.replace('ref-', '')}</td><td>{html.escape(v['buy'])}</td></tr>" for k, v in bought.items())}</tbody>
      </table></div>

      <h3>Thrusters, body frame</h3>
      <div class="scroll"><table>
        <thead><tr><th>Unit</th><th class="num">x</th><th class="num">y</th><th class="num">z</th><th class="num">Pushes</th></tr></thead>
        <tbody>{thruster_rows}</tbody>
      </table></div>
      <p class="note">Six ApisQueen UG500, {P.THRUSTER_THRUST_N:.1f} N each. CW and CCW diagonally on the verticals, one of each at the stern, so reaction torques cancel. The duct is {P.DUCT_D:.0f} mm over a {P.THRUSTER_PROP_D:.0f} mm propeller; the motor's own diameter and mount pattern are unpublished, so the hub carries slots for 12 to 19 mm and the first unit to arrive is measured.</p>

      <h2 style="margin-top:28px">Mass against buoyancy</h2>
      <div class="scroll"><table>
        <thead><tr><th>Part</th><th class="num">g</th><th class="num">cm³</th><th class="num">z</th><th>Source</th></tr></thead>
        <tbody>{budget_rows}<tr class="total"><td>Total</td><td class="num">{b['mass_g']:.0f}</td><td class="num">{b['displaced_cm3']:.0f}</td><td></td><td class="src">buoyancy {b['buoyancy_g']:.0f} g in fresh water</td></tr></tbody>
      </table></div>
      <p class="note">Aim for +20 to +40 g so a dead vehicle rises. Shorten the steel bars to get there; lead shot in the rails for the last few grams. The righting arm of {b['righting_mm']:.1f} mm is under half the catalogue BlueROV2's 20; the cover is the mass that hurts, and the ballast bars are the mass that helps.</p>
    </section>

    <section>
      <h2>Bill of materials</h2>
      {bom_html}
      <p class="note">Roughly 850 to 1,000 USD before shipping and customs. The hull is a third of it and the thrusters a sixth. Order the tube, flanges, caps and one thruster first: everything printed is designed around their real dimensions.</p>

      <h2 style="margin-top:28px">Where it stands</h2>
      <ul class="items">{items_html}</ul>
    </section>
  </div>

  <footer>Sources in the repository: <code>hardware/nano/params.py</code> (every dimension and where it came from), <code>model.py</code> (the parts as code, exporting STEP for JLC3DP), <code>budget.py</code>, <code>bom.md</code>. Frame: x forward, y port, z up, right-handed, the same body frame as the simulator, so these thruster positions copy into a <code>dynamics.json</code> without a sign flip.</footer>
</main>

<script src="https://cdn.jsdelivr.net/npm/three@0.128.0/build/three.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/controls/OrbitControls.js"></script>
<script>
(function () {{
  const groups = {json.dumps(groups)};
  const alphas = {{ "ref-tube": 0.42, "ref-front-cap": 0.5 }};
  const stage = document.getElementById("stage");
  const canvas = document.getElementById("view");
  const renderer = new THREE.WebGLRenderer({{ canvas, antialias: true, alpha: true }});
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.outputEncoding = THREE.sRGBEncoding;
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(32, 1, 1, 5000);
  // The model is x forward, z up. three.js is y up: tip the world so z is up.
  const world = new THREE.Group();
  world.rotation.x = -Math.PI / 2;
  scene.add(world);
  scene.add(new THREE.HemisphereLight(0xffffff, 0x8899aa, 0.9));
  const key = new THREE.DirectionalLight(0xffffff, 0.8); key.position.set(200, -300, 400); scene.add(key);
  const fill = new THREE.DirectionalLight(0xffffff, 0.35); fill.position.set(-300, 200, -100); scene.add(fill);
  const controls = new THREE.OrbitControls(camera, canvas);
  controls.enableDamping = true; controls.dampingFactor = 0.08;
  const nodes = {{}};
  let cover = null, lifted = false, target = 0;

  function size() {{
    const w = stage.clientWidth, h = stage.clientHeight;
    renderer.setSize(w, h, false);
    camera.aspect = w / h; camera.updateProjectionMatrix();
  }}
  window.addEventListener("resize", size); size();

  function decode(b64) {{
    const bin = atob(b64), bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    return new Float32Array(bytes.buffer);
  }}
  fetch("nano.json").then((r) => r.json()).then((parts) => {{
    for (const part of parts) {{
      const g = new THREE.BufferGeometry();
      g.setAttribute("position", new THREE.BufferAttribute(decode(part.positions), 3));
      g.computeVertexNormals();
      const m = new THREE.MeshStandardMaterial({{ color: part.colour, roughness: 0.55, metalness: 0.05, flatShading: true }});
      m.color.convertSRGBToLinear();
      const a = alphas[part.name] !== undefined ? alphas[part.name] : part.alpha;
      if (a < 0.99) {{ m.transparent = true; m.opacity = a; m.depthWrite = false; }}
      const o = new THREE.Mesh(g, m);
      o.name = part.name; o.renderOrder = a < 0.99 ? 2 : 1;
      nodes[part.name] = o;
      if (part.name === "cover") cover = o;
      world.add(o);
    }}
    const box = new THREE.Box3().setFromObject(world);
    const c = box.getCenter(new THREE.Vector3());
    const r = box.getSize(new THREE.Vector3()).length() / 2;
    controls.target.copy(c);
    camera.position.set(c.x + r * 1.5, c.y + r * 1.0, c.z + r * 1.7);
    camera.near = r / 50; camera.far = r * 20; camera.updateProjectionMatrix();
  }});

  document.querySelectorAll(".legend input").forEach((box) => box.addEventListener("change", () => {{
    for (const name of groups[box.dataset.group]) if (nodes[name]) nodes[name].visible = box.checked;
  }}));
  const button = document.getElementById("lift");
  button.addEventListener("click", () => {{
    lifted = !lifted; target = lifted ? 90 : 0;
    button.textContent = lifted ? "Close the cover" : "Lift the cover";
  }});
  const still = matchMedia("(prefers-reduced-motion: reduce)").matches;
  function frame() {{
    if (cover) cover.position.z += still ? (target - cover.position.z) : (target - cover.position.z) * 0.12;
    controls.update();
    renderer.render(scene, camera);
    requestAnimationFrame(frame);
  }}
  frame();
}})();
</script>
"""
    (OUT / "sheet.html").write_text(page)
    print(OUT / "sheet.html", len(page), "bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
