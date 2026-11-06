// The world editor's inspector: what is chosen, its transform as numbers, and
// what belongs to its kind. One item, several at once, a layer, a survey, a
// species, or the world itself when nothing is chosen.

import React from "react";

import type { Asset } from "@coral-city/api";
import { groundAt, type Ground } from "../parts/SiteChart.js";
import { drape, restOn } from "../parts/landing.js";
import { BUILT_FORMS, CORAL_FORMS, iconOf, nameOf, type Item, type Node } from "../platform/scene.js";
import type { WorldDocument, WorldLayer } from "../platform/world.js";
import { Icon, type IconName } from "../ui/icons.js";
import { TOOLS } from "./Layout.js";

const r1 = (v: number) => Math.round(v * 10) / 10;

/** A number field that says its unit and commits as it is typed. */
function NumberField({ label, value, unit, step = 0.1, onChange, disabled }: {
  label: string; value: number | undefined; unit?: string; step?: number; onChange?: (v: number) => void; disabled?: boolean;
}): React.JSX.Element {
  return (
    <label className="in-num">
      <span>{label}</span>
      <input type="number" step={step} value={value === undefined ? "" : r1(value * 100) / 100 === value ? value : Number(value.toFixed(3))}
             placeholder="—" disabled={disabled || !onChange}
             onChange={(e) => { const v = Number(e.target.value); if (e.target.value !== "" && Number.isFinite(v)) onChange?.(v); }}
             onKeyDown={(e) => e.stopPropagation()} />
      {unit ? <em>{unit}</em> : null}
    </label>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }): React.JSX.Element {
  return <section className="in-sec"><h4>{title}</h4>{children}</section>;
}

function Head({ icon, name, kind, onRename }: { icon: IconName; name: string; kind: string; onRename?: (to: string) => void }): React.JSX.Element {
  return (
    <header className="in-head">
      <span className="in-icon"><Icon name={icon} size={20} /></span>
      <div>
        {onRename ? <input className="in-name" value={name} onChange={(e) => onRename(e.target.value)} onKeyDown={(e) => e.stopPropagation()} />
          : <strong className="in-name">{name}</strong>}
        <small>{kind}</small>
      </div>
    </header>
  );
}

function Actions({ onFrame, onDuplicate, onDelete }: { onFrame: () => void; onDuplicate: () => void; onDelete: () => void }): React.JSX.Element {
  return (
    <div className="in-actions">
      <button onClick={onFrame} title="Frame (F)"><Icon name="frame" /> Frame</button>
      <button onClick={onDuplicate} title="Duplicate (Ctrl+D)"><Icon name="duplicate" /> Duplicate</button>
      <button className="bad" onClick={onDelete} title="Delete (Del)"><Icon name="delete" /> Delete</button>
    </div>
  );
}

export function ItemInspector({ item, ground, onChange, onFrame, onDuplicate, onDelete }: {
  item: Item; ground: Ground | undefined;
  /** A change to the item, kept as one step of the history. */
  onChange: (to: Partial<Item>) => void;
  onFrame: () => void; onDuplicate: () => void; onDelete: () => void;
}): React.JSX.Element {
  const x = Number(item.x ?? 0), y = Number(item.y ?? 0);
  const point = typeof item.x === "number" && !item.route && !item.ends && !item.corners;
  const size = item.sizeM as [number, number, number] | undefined;
  const fit = ground && Array.isArray(size) && item.kind === "object" && item.meets !== "drapes"
    ? restOn(ground, x, y, size[0], size[1], Number(item.headingDeg ?? 0)) : undefined;
  const laid = ground && Array.isArray(item.route) ? drape(ground, item.route as { x: number; y: number }[]) : undefined;
  const depth = ground && point ? groundAt(ground, x, y) : undefined;
  const tool = TOOLS[item.kind];
  const kind = item.kind === "coral" ? `coral colony${item.built ? ", from the build" : ", planted here"}`
    : item.kind === "object" ? "object from the library" : item.kind === "reef" ? "reef from video" : tool?.name ?? item.kind;
  const turns = item.kind === "coral" || item.kind === "object" || (!!tool && point && tool.lands !== "region");
  return (
    <div className="in">
      <Head icon={iconOf(item)} name={nameOf(item)} kind={kind} onRename={(to) => onChange({ name: to })} />
      <Section title="Transform">
        <div className="in-grid">
          {point ? <>
            <NumberField label="X" unit="m E" value={x} disabled={item.locked === true} onChange={(v) => onChange({ x: v })} />
            <NumberField label="Y" unit="m N" value={y} disabled={item.locked === true} onChange={(v) => onChange({ y: v })} />
          </> : null}
          {depth !== undefined ? <NumberField label="Depth" unit="m" value={r1(depth)} /> : null}
          {turns ? <NumberField label="Heading" unit="°" step={5} value={Number(item.headingDeg ?? 0)} disabled={item.locked === true}
                                onChange={(v) => onChange({ headingDeg: ((v % 360) + 360) % 360 })} /> : null}
          {item.kind === "coral" ? <NumberField label="Size" unit="m" step={0.05} value={Number(item.sizeM ?? 0.5)} disabled={item.locked === true}
                                                onChange={(v) => onChange({ sizeM: Math.max(0.05, v) })} /> : null}
        </div>
      </Section>
      {item.kind === "coral" ? (
        <Section title="Coral">
          <label className="in-row"><span>Form</span>
            <select value={String(item.form ?? "massive")} onChange={(e) => onChange({ form: e.target.value })} onKeyDown={(e) => e.stopPropagation()}>
              {formsWith([item]).map(([k, name]) => <option key={k} value={k}>{name}</option>)}
            </select>
          </label>
          {item.prim ? <p className="in-note">In the build as {String(item.prim)}</p> : null}
        </Section>
      ) : null}
      {tool || fit || laid || item.kind === "object" || item.kind === "reef" ? (
        <Section title="On the seabed">
          <dl>
            {tool && depth !== undefined ? <><dt>Lands</dt><dd>{tool.says(depth)}</dd></> : null}
            {fit ? <><dt>Fit</dt><dd>{fit.tiltDeg >= 0.5 ? `leans ${fit.tiltDeg.toFixed(0)}°` : "level"}{fit.clearM >= 0.05 ? `, ${fit.clearM.toFixed(1)} m clear under one side` : ""}</dd></> : null}
            {laid ? <><dt>Length</dt><dd>{laid.lengthM.toFixed(0)} m, {laid.spans.length} free span{laid.spans.length === 1 ? "" : "s"}</dd></> : null}
            {item.kind === "object" || item.kind === "reef" ? <><dt>In the seabed</dt><dd>{item.laid ? "yes" : "on save"}</dd></> : null}
          </dl>
        </Section>
      ) : null}
      <Section title="Display">
        <label className="in-check"><input type="checkbox" checked={item.hidden !== true} onChange={(e) => onChange({ hidden: !e.target.checked })} /> Visible</label>
        <label className="in-check"><input type="checkbox" checked={item.locked === true} onChange={(e) => onChange({ locked: e.target.checked })} /> Locked</label>
      </Section>
      <Actions onFrame={onFrame} onDuplicate={onDuplicate} onDelete={onDelete} />
    </div>
  );
}

export function ManyInspector({ items, onEach, onFrame, onDuplicate, onDelete }: {
  items: Item[];
  /** The same change to every one, as one step of the history. */
  onEach: (to: (was: Item) => Partial<Item>) => void;
  onFrame: () => void; onDuplicate: () => void; onDelete: () => void;
}): React.JSX.Element {
  const kinds = new Map<string, number>();
  for (const t of items) kinds.set(nameOfKind(t), (kinds.get(nameOfKind(t)) ?? 0) + 1);
  const corals = items.every((t) => t.kind === "coral");
  const same = <T,>(f: (t: Item) => T): T | undefined => items.every((t) => f(t) === f(items[0]!)) ? f(items[0]!) : undefined;
  return (
    <div className="in">
      <Head icon={corals ? "colonies" : "structures"} name={`${items.length} selected`} kind={[...kinds].map(([k, n]) => `${n} ${k}`).join(", ")} />
      <Section title="Transform">
        <div className="in-grid">
          <NumberField label="Heading" unit="°" step={5} value={same((t) => Number(t.headingDeg ?? 0))}
                       onChange={(v) => onEach(() => ({ headingDeg: ((v % 360) + 360) % 360 }))} />
          {corals ? <NumberField label="Size" unit="m" step={0.05} value={same((t) => Number(t.sizeM ?? 0.5))}
                                 onChange={(v) => onEach(() => ({ sizeM: Math.max(0.05, v) }))} /> : null}
        </div>
        <p className="in-note">Move, turn and grow them together with W, E and R.</p>
      </Section>
      {corals ? (
        <Section title="Coral">
          <label className="in-row"><span>Form</span>
            <select value={same((t) => String(t.form)) ?? ""} onChange={(e) => onEach(() => ({ form: e.target.value }))} onKeyDown={(e) => e.stopPropagation()}>
              <option value="" disabled>mixed</option>
              {formsWith(items).map(([k, name]) => <option key={k} value={k}>{name}</option>)}
            </select>
          </label>
        </Section>
      ) : null}
      <Section title="Display">
        <label className="in-check"><input type="checkbox" checked={items.every((t) => t.hidden !== true)} onChange={(e) => onEach(() => ({ hidden: !e.target.checked }))} /> Visible</label>
        <label className="in-check"><input type="checkbox" checked={items.every((t) => t.locked === true)} onChange={(e) => onEach(() => ({ locked: e.target.checked }))} /> Locked</label>
      </Section>
      <Actions onFrame={onFrame} onDuplicate={onDuplicate} onDelete={onDelete} />
    </div>
  );
}

/** The forms a coral can be given, and any a big reef built them as besides
 *  (rock, rubble), so a rock chosen reads as a rock. */
function formsWith(items: Item[]): [string, string][] {
  const out: [string, string][] = Object.entries(CORAL_FORMS).map(([k, f]) => [k, f.name]);
  for (const form of new Set(items.map((t) => String(t.form ?? "")))) {
    if (BUILT_FORMS[form] && !CORAL_FORMS[form]) out.push([form, BUILT_FORMS[form]]);
  }
  return out;
}

function nameOfKind(t: Item): string {
  if (t.kind === "coral") return (CORAL_FORMS[String(t.form)]?.name ?? BUILT_FORMS[String(t.form)] ?? "coral").toLowerCase();
  return (TOOLS[t.kind]?.name ?? (t.kind === "object" ? "object" : t.kind)).toLowerCase();
}

/** Nothing chosen: the world itself. */
export function WorldInspector({ document, name, version, counts, glass }: {
  document: WorldDocument; name: string; version?: number;
  counts: { corals: number; structures: number; species: number; animals: number; missions: number };
  glass?: string;
}): React.JSX.Element {
  const [w, l] = document.frame.extentM;
  return (
    <div className="in">
      <Head icon="world" name={name} kind={version ? `world, version ${version}` : "world, not saved yet"} />
      <Section title="Frame">
        <dl>
          <dt>Extent</dt><dd>{w.toLocaleString()} × {l.toLocaleString()} m</dd>
          <dt>On Earth</dt><dd>{document.georef ? `${document.georef.origin.lat.toFixed(5)}, ${document.georef.origin.lon.toFixed(5)}` : "nowhere: a tank or a made-up place"}</dd>
          {glass ? <><dt>Glass</dt><dd>{glass}</dd></> : null}
          <dt>Baked into</dt><dd>{document.bake?.version ?? "not baked yet"}</dd>
        </dl>
      </Section>
      <Section title="In it">
        <dl>
          <dt>Coral colonies</dt><dd>{counts.corals.toLocaleString()}</dd>
          <dt>Structures</dt><dd>{counts.structures}</dd>
          <dt>Species</dt><dd>{counts.species}{counts.animals ? `, ${counts.animals.toLocaleString()} animals` : ""}</dd>
          <dt>Missions</dt><dd>{counts.missions}</dd>
        </dl>
      </Section>
      <Section title="Keys">
        <dl className="in-keys">
          <dt>Q W E R</dt><dd>select, move, rotate, scale</dd>
          <dt>B, M</dt><dd>scatter coral, measure</dd>
          <dt>F</dt><dd>frame the selection</dd>
          <dt>7 1 3 5</dt><dd>top, front, right, perspective</dd>
          <dt>Shift-drag</dt><dd>box select</dd>
          <dt>Ctrl Z, Ctrl ⇧ Z</dt><dd>undo, redo</dd>
          <dt>Ctrl D, Del, H</dt><dd>duplicate, delete, hide</dd>
        </dl>
      </Section>
    </div>
  );
}

/** A node that is not an item: a survey of the terrain, a species, a class. */
export function NodeInspector({ node, layer, glass, onChange, onOpenMission }: {
  node: Node; layer: WorldLayer | undefined; glass?: string; onChange: (to: WorldLayer) => void; onOpenMission: (id: string) => void;
}): React.JSX.Element | null {
  if (node.id.startsWith("@glass")) {
    return (
      <div className="in">
        <Head icon={node.icon} name={node.name} kind={node.id === "@glass" ? "the tank's wall" : "what the tank stands on"} />
        {glass ? <Section title="Tank"><dl><dt>Shape</dt><dd>{glass}</dd><dt>Stops</dt><dd>a vehicle stops at the glass</dd></dl></Section> : null}
      </div>
    );
  }
  if (node.mission) {
    return (
      <div className="in">
        <Head icon="mission" name={node.name} kind="mission in this world" />
        <div className="in-actions"><button onClick={() => onOpenMission(node.mission!)}><Icon name="mission" /> Open the mission</button></div>
      </div>
    );
  }
  if (node.id.startsWith("@life:") && layer) {
    const key = node.id.slice(6);
    const params = (layer.params ?? {}) as Record<string, unknown>;
    const count = (params.count ?? {}) as Record<string, number>;
    return (
      <div className="in">
        <Head icon={node.icon} name={node.name} kind="species in this world" />
        <Section title="Population">
          <div className="in-grid">
            <NumberField label="Count" step={1} value={count[key] ?? 0}
                         onChange={(v) => onChange({ ...layer, params: { ...params, count: { ...count, [key]: Math.max(0, Math.round(v)) } } })} />
          </div>
        </Section>
      </div>
    );
  }
  if (node.id.startsWith("@terrain:") && layer) {
    const s = layer.stack?.[Number(node.id.slice(9))];
    if (!s) return null;
    return (
      <div className="in">
        <Head icon="source" name={s.name ?? s.asset ?? "survey"} kind={s.role === "check" ? "checks the depths" : "gives depths"} />
        <Section title="Source">
          <dl>
            <dt>Priority</dt><dd>{s.priority ?? 0}</dd>
            {s.origin ? <><dt>Origin</dt><dd>{s.origin}</dd></> : null}
            {s.asset ? <><dt>Asset</dt><dd>{s.asset}</dd></> : <><dt>Asset</dt><dd>from the build, not in the library</dd></>}
            {s.citation ? <><dt>Cite</dt><dd>{s.citation}</dd></> : null}
          </dl>
        </Section>
      </div>
    );
  }
  if (node.id.startsWith("@seabed:")) {
    return <div className="in"><Head icon="swatch" name={node.name} kind={`seabed class ${node.note ?? ""}`} /></div>;
  }
  return null;
}

export function LayerInspector({ layer, document, assets, onChange }: {
  layer: WorldLayer; document: WorldDocument; assets: Asset[]; onChange: (to: WorldLayer) => void;
}): React.JSX.Element {
  const params = (layer.params ?? {}) as Record<string, unknown>;
  const set = (key: string, value: unknown) => onChange({ ...layer, params: { ...params, [key]: value } });
  switch (layer.kind) {
    case "water":
      return (
        <div className="wed-props">
          <h3>Water</h3>
          <p className="wed-note">What belongs to the place. Current, wind and waves are each dive's.</p>
          <label className="wed-field">Water type
            <select value={String(params.waterType ?? "Jerlov IB")} onChange={(e) => set("waterType", e.target.value)}>
              {["Jerlov I", "Jerlov IA", "Jerlov IB", "Jerlov II", "Jerlov III", "Jerlov 1C", "Jerlov 3C", "Jerlov 5C"].map((w) => <option key={w}>{w}</option>)}
            </select>
          </label>
          {([["visibilityM", "Visibility", "m"], ["temperatureC", "Temperature", "°C"], ["salinityPsu", "Salinity", "PSU"]] as const).map(([key, name, unit]) => (
            <label key={key} className="wed-field">{name}
              <input type="number" value={Number(params[key] ?? 0)} onChange={(e) => set(key, Number(e.target.value))} /> {unit}
            </label>
          ))}
        </div>
      );
    case "terrain": {
      const surveys = assets.filter((a) => a.kind === "bathymetry");
      const stack = layer.stack ?? [];
      return (
        <div className="wed-props">
          <h3>Terrain</h3>
          <p className="wed-note">Fused from these, highest priority on top. {document.georef ? "" : "This world has no place on Earth, so surveys tied to one cannot go in."}</p>
          <ol className="wed-stack">
            {[...stack].sort((a, b) => (b.priority ?? 0) - (a.priority ?? 0)).map((s, i) => (
              <li key={`${s.asset}-${s.name}-${i}`}>
                <strong>{s.name ?? s.asset}</strong>
                <span>{s.role === "check" ? "checks the depths" : "gives depths"}{s.origin ? `, ${s.origin}` : ""}</span>
                {s.citation ? <em>{s.citation}</em> : null}
                {s.asset ? <button onClick={() => onChange({ ...layer, stack: stack.filter((x) => x !== s) })}>Remove</button> : null}
              </li>
            ))}
          </ol>
          {layer.result ? <p className="wed-note">Built: {layer.result.name ?? layer.result.asset}{layer.result.version ? `, version ${layer.result.version}` : ""}</p> : null}
          {document.georef && surveys.length ? (
            <label className="wed-field">Add
              <select value="" onChange={(e) => {
                const a = surveys.find((x) => x.id === e.target.value);
                if (a) onChange({ ...layer, stack: [...stack, { asset: a.id, name: a.name, role: "depth", priority: 100, origin: a.madeFrom }] });
              }}>
                <option value="">a bathymetry from the library…</option>
                {surveys.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
              </select>
            </label>
          ) : null}
        </div>
      );
    }
    case "seabed":
      return (
        <div className="wed-props">
          <h3>Seabed</h3>
          <dl>{Object.entries(layer.classes ?? {}).map(([k, v]) => <React.Fragment key={k}><dt>{k}</dt><dd>{v}</dd></React.Fragment>)}</dl>
        </div>
      );
    case "reef":
      return (
        <div className="wed-props">
          <h3>Reef</h3>
          <dl>
            <dt>Colonies</dt><dd>{Number(params.colonies ?? 0).toLocaleString()}</dd>
            {params.from ? <><dt>From</dt><dd>{String(params.from)}</dd></> : null}
            <dt>Reefs from video</dt><dd>{(layer.items ?? []).length}</dd>
          </dl>
        </div>
      );
    case "life": {
      const count = (params.count ?? {}) as Record<string, number>;
      const rows = Object.entries(count).sort((a, b) => b[1] - a[1]);
      return (
        <div className="wed-props">
          <h3>Life</h3>
          {rows.length === 0 && !layer.from ? <p className="wed-note">No species list yet.</p> : null}
          {layer.from ? <p className="wed-note">From {layer.from.name ?? layer.from.asset}</p> : null}
          <dl>{rows.map(([k, v]) => <React.Fragment key={k}><dt>{k.replace(/_/g, " ")}</dt><dd>{v}</dd></React.Fragment>)}</dl>
        </div>
      );
    }
    default:
      return (
        <div className="wed-props">
          <h3>Structures</h3>
          <p className="wed-note">Take equipment, coral or your objects from the assets below and put them in the world.</p>
        </div>
      );
  }
}
