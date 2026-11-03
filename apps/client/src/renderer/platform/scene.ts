// A world as a scene: everything in it is a node of one tree, the way a
// modelling tool's outliner shows it. The water and its volume, the terrain
// and each survey it is fused from, the seabed's classes, the glass of a tank,
// every coral colony, every piece of equipment, every species, every mission.
//
// And what can be put into a world, the catalogue its asset browser shows:
// equipment by where it lands, coral by form, the organisation's own objects.

import type { Asset, Mission } from "@coral-city/api";

import type { IconName } from "../ui/icons.js";
import { TOOLS, type Tool } from "../screens/Layout.js";
import { layerOf, type WorldDocument, type WorldLayer } from "./world.js";

export type Item = NonNullable<WorldLayer["items"]>[number];

/** A coral colony as a place's record lists it. */
export interface Colony { kind: string; sizeM: number; at: [number, number]; prim?: string }

export const CORAL_FORMS: Record<string, { name: string; sizeM: number }> = {
  table: { name: "Table coral", sizeM: 0.8 },
  massive: { name: "Massive coral", sizeM: 0.6 },
  brain: { name: "Brain coral", sizeM: 0.5 },
  branching: { name: "Branching coral", sizeM: 0.5 },
  finger: { name: "Finger coral", sizeM: 0.35 },
  plume: { name: "Sea plume", sizeM: 0.6 },
  fan: { name: "Sea fan", sizeM: 0.6 },
  sponge: { name: "Barrel sponge", sizeM: 0.4 },
  encrusting: { name: "Encrusting coral", sizeM: 0.4 },
};

/** Colonies a place was built with become items of its reef, one each, so
 *  they can be chosen, moved and turned. Past this many they stay one node:
 *  a reef of a hundred thousand is a population, not a list. */
export const MOST_COLONIES = 5000;

/** The world with its built colonies as reef items, when it has none yet. */
export function withColonies(document: WorldDocument, colonies: Colony[] | undefined): WorldDocument {
  if (!colonies?.length || colonies.length > MOST_COLONIES) return document;
  const reef = layerOf(document, "reef");
  if (reef?.items?.some((i) => i.kind === "coral")) return document;
  const counted: Record<string, number> = {};
  const items: Item[] = colonies.map((c, i) => {
    const [x, y] = c.at;
    counted[c.kind] = (counted[c.kind] ?? 0) + 1;
    // The turn the build gave it, from its place, as the runtime does. The
    // runtime reads headingDeg as a turn from how it was built, so a built
    // colony starts at 0 and carries the build's own turn only to be drawn.
    const turn = (((Math.sin(x * 12.9898 + y * 78.233) * 43758.5453) % 1) + 1) % 1;
    return {
      id: `coral-${i + 1}`, kind: "coral", form: c.kind,
      name: `${CORAL_FORMS[c.kind]?.name ?? c.kind} ${counted[c.kind]}`,
      x: Math.round(x * 1000) / 1000, y: Math.round(y * 1000) / 1000,
      sizeM: Math.round(c.sizeM * 1000) / 1000, headingDeg: 0, builtDeg: Math.round(turn * 360),
      built: true, ...(c.prim ? { prim: c.prim } : {}),
    };
  });
  const layers = reef
    ? document.layers.map((l) => l.kind === "reef" ? { ...l, items: [...items, ...(l.items ?? [])] } : l)
    : [...document.layers, { id: "reef", kind: "reef" as const, items }];
  return { ...document, layers };
}

// ---------------------------------------------------------------- catalogue

export type Category = "Seabed" | "Surface" | "Lines" | "Plots" | "Coral" | "Your objects";
export const CATEGORIES: { key: Category; icon: IconName }[] = [
  { key: "Seabed", icon: "transponder" },
  { key: "Surface", icon: "ship" },
  { key: "Lines", icon: "pipeline" },
  { key: "Plots", icon: "restoration-cell" },
  { key: "Coral", icon: "coral" },
  { key: "Your objects", icon: "object" },
];

/** One thing the asset browser offers. */
export interface Placeable {
  key: string;
  name: string;
  category: Category;
  icon: IconName;
  /** What an item of it is: an equipment kind, "coral", "object" or "reef". */
  kind: string;
  form?: string;
  tool?: Tool;
  asset?: Asset;
  /** One line on how it is put down. */
  says: string;
}

const LANDS_IN: Record<Tool["lands"], Category> = { ground: "Seabed", surface: "Surface", span: "Lines", laid: "Lines", region: "Plots" };
const HOW: Record<Tool["lands"], string> = {
  ground: "click the seabed", surface: "click the water", span: "click one end, then the other",
  laid: "click the route, double-click to end", region: "click two corners",
};

export function catalogue(assets: Asset[]): Placeable[] {
  const out: Placeable[] = Object.entries(TOOLS).map(([key, tool]) => ({
    key, name: tool.name, category: LANDS_IN[tool.lands], icon: key as IconName, kind: key, tool, says: HOW[tool.lands],
  }));
  for (const [form, f] of Object.entries(CORAL_FORMS)) {
    out.push({ key: `coral:${form}`, name: f.name, category: "Coral", icon: `coral-${form}` as IconName, kind: "coral", form,
               says: "click to plant one; Scatter (B) to plant many" });
  }
  for (const a of assets.filter((x) => x.kind === "reef" || x.kind === "structure")) {
    out.push({ key: `asset:${a.id}`, name: a.name, category: "Your objects", icon: a.kind === "reef" ? "video-reef" : "object",
               kind: a.kind === "reef" ? "reef" : "object", asset: a, says: "click the seabed; laid into it on save" });
  }
  return out;
}

// ---------------------------------------------------------------- the tree

export interface Node {
  /** An item's own id, or "@…" for what is not an item. */
  id: string;
  name: string;
  icon: IconName;
  /** What it is, said small after the name. */
  note?: string;
  children?: Node[];
  layer?: WorldLayer["kind"];
  /** A world item: chosen in the view, moved, removed. */
  item?: boolean;
  hidden?: boolean;
  locked?: boolean;
  /** Has an eye and a lock in the outliner. */
  toggles?: boolean;
  mission?: string;
}

export function iconOf(item: Item): IconName {
  if (item.kind === "coral") return `coral-${String(item.form ?? "massive")}` as IconName;
  if (item.kind === "reef") return "video-reef";
  if (item.kind in TOOLS) return item.kind as IconName;
  return "object";
}

export function nameOf(item: Item): string {
  return String(item.name ?? (item.kind === "coral" ? CORAL_FORMS[String(item.form)]?.name : TOOLS[item.kind]?.name) ?? item.kind);
}

export function treeOf(document: WorldDocument, opts: { tank?: { round: boolean; radiusM?: number; depthM: number };
                                                        colonies?: number; missions: Mission[] }): Node[] {
  const layer = (kind: WorldLayer["kind"]) => layerOf(document, kind);
  const hiddenLayer = (kind: WorldLayer["kind"]) => layer(kind)?.visible === false;
  const itemNode = (t: Item): Node => ({ id: t.id, name: nameOf(t), icon: iconOf(t), item: true, toggles: true,
                                         hidden: t.hidden === true, locked: t.locked === true });

  const water: Node = { id: "@water", name: "Water", icon: "water", layer: "water", toggles: true, hidden: hiddenLayer("water"),
    note: String((layer("water")?.params as { waterType?: string } | undefined)?.waterType ?? ""),
    children: [{ id: "@water:volume", name: "Water volume", icon: "water", layer: "water" },
               { id: "@water:surface", name: "Surface", icon: "water", layer: "water" }] };
  const stack = layer("terrain")?.stack ?? [];
  const terrain: Node = { id: "@terrain", name: "Terrain", icon: "terrain", layer: "terrain", toggles: true, hidden: hiddenLayer("terrain"),
    note: `${stack.length} source${stack.length === 1 ? "" : "s"}`,
    children: [...stack].sort((a, b) => (b.priority ?? 0) - (a.priority ?? 0)).map((s) => ({
      id: `@terrain:${stack.indexOf(s)}`, name: s.name ?? s.asset ?? "survey", icon: "source" as IconName, layer: "terrain" as const,
      note: s.role === "check" ? "check" : "depth" })) };
  const classes = Object.entries(layer("seabed")?.classes ?? {});
  const seabed: Node = { id: "@seabed", name: "Seabed", icon: "seabed", layer: "seabed", toggles: true, hidden: hiddenLayer("seabed"),
    note: classes.length ? `${classes.length} classes` : undefined,
    children: classes.map(([k, v]) => ({ id: `@seabed:${k}`, name: v, icon: "swatch" as IconName, layer: "seabed" as const, note: k })) };
  const environment: Node[] = [water, terrain, seabed];
  if (opts.tank) {
    environment.push({ id: "@glass", name: "Glass", icon: "glass", toggles: true, hidden: hiddenLayer("water"),
      note: opts.tank.round ? `round, ${(opts.tank.radiusM! * 2).toFixed(0)} m across` : "box",
      children: [{ id: "@glass:hall", name: "Hall floor", icon: "hall" }] });
  }

  const reefItems = layer("reef")?.items ?? [];
  const corals = reefItems.filter((t) => t.kind === "coral");
  const byForm = new Map<string, Item[]>();
  for (const c of corals) byForm.set(String(c.form ?? "massive"), [...(byForm.get(String(c.form ?? "massive")) ?? []), c]);
  const reefChildren: Node[] = [...byForm].sort((a, b) => b[1].length - a[1].length).map(([form, list]) => ({
    id: `@reef:${form}`, name: CORAL_FORMS[form]?.name ?? form, icon: `coral-${form}` as IconName, layer: "reef" as const,
    note: String(list.length), children: list.map(itemNode) }));
  const others = reefItems.filter((t) => t.kind !== "coral");
  reefChildren.push(...others.map(itemNode));
  const built = Number((layer("reef")?.params as { colonies?: number } | undefined)?.colonies ?? opts.colonies ?? 0);
  if (!corals.length && built > 0) {
    reefChildren.unshift({ id: "@reef:built", name: "Colonies of the build", icon: "colonies", layer: "reef",
                           note: built.toLocaleString() });
  }
  const reef: Node = { id: "@reef", name: "Reef", icon: "reef", layer: "reef", toggles: true, hidden: hiddenLayer("reef"),
    note: String(corals.length + others.length || built || ""), children: reefChildren };

  const structureItems = layer("structures")?.items ?? [];
  const structures: Node = { id: "@structures", name: "Structures", icon: "structures", layer: "structures", toggles: true,
    hidden: hiddenLayer("structures"), note: structureItems.length ? String(structureItems.length) : undefined,
    children: structureItems.map(itemNode) };

  const count = ((layer("life")?.params as { count?: Record<string, number> } | undefined)?.count ?? {});
  const species = Object.entries(count).sort((a, b) => b[1] - a[1]);
  const life: Node = { id: "@life", name: "Life", icon: "life", layer: "life", toggles: true, hidden: hiddenLayer("life"),
    note: species.length ? `${species.reduce((t, [, n]) => t + n, 0)} animals` : undefined,
    children: species.map(([k, n]) => ({ id: `@life:${k}`, name: k.replace(/_/g, " "), icon: /carcharhinus|aetobatus|shark|ray/i.test(k) ? "shark" as IconName : "fish" as IconName,
                                          layer: "life" as const, note: String(n) })) };

  const missions: Node = { id: "@missions", name: "Missions", icon: "missions", note: opts.missions.length ? String(opts.missions.length) : undefined,
    children: opts.missions.map((m) => ({ id: `@mission:${m.id}`, name: m.name, icon: "mission" as IconName, mission: m.id })) };

  return [{ id: "@environment", name: "Environment", icon: "world", children: environment }, reef, structures, life, missions];
}

/** Every node of a tree, depth first. */
export function flat(nodes: Node[]): Node[] {
  return nodes.flatMap((n) => [n, ...flat(n.children ?? [])]);
}

/** Items by id, across the reef and the structures. */
export function itemsOf(document: WorldDocument | undefined): Map<string, Item> {
  const out = new Map<string, Item>();
  if (!document) return out;
  for (const kind of ["reef", "structures"] as const) for (const t of layerOf(document, kind)?.items ?? []) out.set(t.id, t);
  return out;
}

/** The layer an item belongs in. */
export function layerFor(item: Item): "reef" | "structures" {
  return item.kind === "coral" || item.kind === "reef" ? "reef" : "structures";
}

// ---------------------------------------------------------------- transforms

export interface Delta { dx: number; dy: number; turnDeg: number; scale: number }

const r3 = (v: number) => Math.round(v * 1000) / 1000;

/** An item moved, turned about a pivot, and grown, from where it started.
 *  Points that land by a rule (on the ground, at the surface) are landed by
 *  the caller. */
export function transformed(item: Item, d: Delta, pivot: { x: number; y: number }): Item {
  const turn = (d.turnDeg * Math.PI) / 180;
  const c = Math.cos(turn), s = Math.sin(turn);
  // Heading is clockwise from north; a turn by the gizmo is the same sense.
  const about = (p: { x: number; y: number }) => {
    const ox = p.x - pivot.x, oy = p.y - pivot.y;
    return { x: r3(pivot.x + ox * c + oy * s + d.dx), y: r3(pivot.y - ox * s + oy * c + d.dy) };
  };
  const out: Item = { ...item };
  if (typeof item.x === "number" && typeof item.y === "number") Object.assign(out, about({ x: item.x, y: item.y }));
  for (const key of ["route", "corners", "ends"] as const) {
    const list = item[key] as { x: number; y: number }[] | undefined;
    if (Array.isArray(list)) out[key] = list.map((p) => ({ ...p, ...about(p) }));
  }
  if (d.turnDeg && (typeof item.headingDeg === "number" || item.kind === "coral" || item.kind === "object" || item.kind in TOOLS)) {
    out.headingDeg = Math.round(((((Number(item.headingDeg ?? 0) + d.turnDeg) % 360) + 360) % 360) * 10) / 10;
  }
  if (d.scale !== 1 && item.kind === "coral") out.sizeM = r3(Math.max(0.05, Number(item.sizeM ?? 0.5) * d.scale));
  if (item.kind === "object" || item.kind === "reef") out.laid = false;
  return out;
}

/** The middle of a set of items, where the gizmo sits. */
export function pivotOf(items: Item[]): { x: number; y: number } | undefined {
  const at = items.flatMap((t) => typeof t.x === "number" && typeof t.y === "number" ? [{ x: t.x, y: t.y }]
    : ((t.route ?? t.corners ?? t.ends) as { x: number; y: number }[] | undefined) ?? []);
  if (!at.length) return undefined;
  return { x: at.reduce((s, p) => s + p.x, 0) / at.length, y: at.reduce((s, p) => s + p.y, 0) / at.length };
}
