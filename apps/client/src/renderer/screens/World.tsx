// A world: one place in the sea, in three dimensions, edited as a modelling
// tool edits a scene.
//
// A toolbar along the top (select, move, rotate, scale, scatter, measure,
// snap, undo, views), the scene tree down the left with everything in the
// world in it (the water, each survey under the terrain, every coral colony,
// every piece of equipment, every species, every mission), the view in the
// middle with a gizmo on what is chosen, the assets that can be put in it
// below the view, each with its picture, and the inspector on the right.
//
// One world per place and one design per world: a save is a new version of
// it, the history is what there is to go back to. Objects from the library
// that have a mesh of their own (a platform, a pipe from its route, a reef
// from a video) go into the package's seabed when the world is saved, which
// is the bake a dive runs in; equipment goes to the simulator as things.

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type { Asset, Mapping, Mission, Platform } from "@coral-city/api";
import type { Held, Packages } from "./Deck.js";
import { AssetBrowser } from "../parts/AssetBrowser.js";
import { Outliner } from "../parts/Outliner.js";
import { extentOf, hullOf, launchAt, legsOf, type Drawn, type Plan } from "../catalog/stages.js";
import { groundAt, groundOf, type Ground } from "../parts/SiteChart.js";
import type { PlanIn3D } from "../parts/StagesIn3D.js";
import { World3D, type Delta, type Glass, type Mode, type PopulationShown, type Shown, type View3D, type ViewName } from "../parts/World3D.js";
import { asEdits, colonyItem, Near, readColonies, rowOf, type Population } from "../platform/colonies.js";
import { whereIs } from "../platform/packages.js";
import {
  CORAL_FORMS, catalogue, flat, itemsOf, layerFor, nameOf, pivotOf, transformed, treeOf, withColonies,
  type Colony, type Item, type Node,
} from "../platform/scene.js";
import { layerOf, readWorld, saveWorld, type WorldDocument, type WorldLayer } from "../platform/world.js";
import { Button, Page, Status } from "../ui/components.js";
import { Icon, type IconName } from "../ui/icons.js";
import { ItemInspector, LayerInspector, ManyInspector, NodeInspector, WorldInspector } from "./WorldInspector.js";
import { TOOLS, landed, named, spanBetween, cellBetween } from "./Layout.js";
import { Empty } from "./parts.js";
import "../parts/world.css";

/** Metres in the world to degrees, and back, about its origin. */
function earthOf(origin: { lat: number; lon: number }) {
  const perLon = 111_320 * Math.max(Math.cos(origin.lat * Math.PI / 180), 1e-6);
  return {
    toLatLon: (x: number, y: number) => ({ lat: origin.lat + y / 111_320, lon: origin.lon + x / perLon }),
  };
}

function sizeOf(asset: Asset | undefined): [number, number, number] {
  const s = (asset?.footprint as { sizeM?: number[] } | undefined)?.sizeM;
  return [Math.max(0.2, s?.[0] ?? 3), Math.max(0.2, s?.[1] ?? 3), Math.max(0.1, s?.[2] ?? 1)];
}

const round = (v: number) => Math.round(v * 10) / 10;
const r3 = (v: number) => Math.round(v * 1000) / 1000;
const MOST_STEPS = 100;

/** Every item of a document changed by one rule: kept, changed, or dropped. */
function eachItem(document: WorldDocument, to: (t: Item) => Item | undefined): WorldDocument {
  return {
    ...document,
    layers: document.layers.map((l) => l.kind === "reef" || l.kind === "structures"
      ? { ...l, items: (l.items ?? []).flatMap((t) => { const n = to(t); return n ? [n] : []; }) } : l),
  };
}

/** Items added to the layers they belong in. */
function withItems(document: WorldDocument, added: Item[]): WorldDocument {
  let out = document;
  for (const kind of ["reef", "structures"] as const) {
    const these = added.filter((t) => layerFor(t) === kind);
    if (!these.length) continue;
    out = out.layers.some((l) => l.kind === kind)
      ? { ...out, layers: out.layers.map((l) => l.kind === kind ? { ...l, items: [...(l.items ?? []), ...these] } : l) }
      : { ...out, layers: [...out.layers, { id: kind, kind, items: these }] };
  }
  return out;
}

const TOOLBAR: { mode: Mode; icon: IconName; name: string; key: string }[] = [
  { mode: "select", icon: "select", name: "Select", key: "Q" },
  { mode: "move", icon: "move", name: "Move", key: "W" },
  { mode: "rotate", icon: "rotate", name: "Rotate", key: "E" },
  { mode: "scale", icon: "scale", name: "Scale", key: "R" },
];
const VIEWS: { view: ViewName; icon: IconName; name: string; key: string }[] = [
  { view: "top", icon: "viewTop", name: "Top", key: "7" },
  { view: "front", icon: "viewFront", name: "Front", key: "1" },
  { view: "right", icon: "viewRight", name: "Right", key: "3" },
  { view: "persp", icon: "viewPersp", name: "Perspective", key: "5" },
];

export function World({ platform, held, packages, place, onBack, onChanged, onDive, onMission, onNewMission }: {
  platform: Platform;
  held: Held;
  packages: Packages;
  place: string;
  onBack: () => void;
  onChanged: () => void;
  /** A new dive in this world, at this version of it. */
  onDive: (worldVersion: string | undefined) => void;
  onMission: (id: string) => void;
  onNewMission: () => void;
}): React.JSX.Element {
  const city = held.places.find((p) => p.id === place);
  const pkg = packages.places.get(place) ?? undefined;
  const org = held.institution?.id;
  const [ground, setGround] = useState<Ground | undefined>();
  const [of, setOf] = useState<Awaited<ReturnType<typeof readWorld>> | undefined>();
  const [document, setDocument] = useState<WorldDocument | undefined>();
  const [assets, setAssets] = useState<Asset[]>([]);
  const [missions, setMissions] = useState<Mission[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [mode, setMode] = useState<Mode>("select");
  const [hand, setHand] = useState<string | undefined>();
  const [first, setFirst] = useState<{ x: number; y: number } | undefined>();
  const [route, setRoute] = useState<{ x: number; y: number }[]>([]);
  const [hover, setHover] = useState<{ x: number; y: number } | undefined>();
  const [measure, setMeasure] = useState<{ x: number; y: number }[]>([]);
  const [scatter, setScatter] = useState({ radiusM: 1, count: 6 });
  const [snap, setSnap] = useState(false);
  const [grid, setGrid] = useState(true);
  const [panels, setPanels] = useState({ left: true, right: true, bottom: true });
  const [open, setOpen] = useState<Set<string>>(() => new Set(["@environment", "@reef", "@structures", "@life", "@missions"]));
  const [menu, setMenu] = useState<{ node: Node; x: number; y: number } | undefined>();
  const [renaming, setRenaming] = useState<string | undefined>();
  const [changed, setChanged] = useState(false);
  const [busy, setBusy] = useState(false);
  const [said, setSaid] = useState("");
  // The place was built again since the world was saved.
  const [rebuilt, setRebuilt] = useState(false);
  const [trouble, setTrouble] = useState("");
  const [mapping, setMapping] = useState<Mapping | undefined>();
  const [, setSteps] = useState(0);
  const view = useRef<View3D>(null);
  const history = useRef<{ past: WorldDocument[]; future: WorldDocument[] }>({ past: [], future: [] });
  const current = useRef<WorldDocument | undefined>(undefined);
  current.current = document;
  // What the selection was when the gizmo or a drag took hold of it.
  const holding = useRef<{ items: Item[]; pivot: { x: number; y: number } } | undefined>(undefined);

  useEffect(() => { void groundOf(pkg).then(setGround); }, [pkg]);
  const colonies = useMemo(() => {
    const listed = (pkg?.site as unknown as { reef?: { colonies_at?: Colony[] } } | undefined)?.reef?.colonies_at;
    return Array.isArray(listed) ? listed.filter((c) => Array.isArray(c.at)) : undefined;
  }, [pkg]);
  // A big reef's colonies, from the file its build wrote: drawn whole, and
  // only those changed are the world's.
  const [population, setPopulation] = useState<{ p: Population; near: Near } | undefined>();
  useEffect(() => {
    setPopulation(undefined);
    const name = (pkg?.site as unknown as { reef?: { coloniesFile?: string } } | undefined)?.reef?.coloniesFile;
    const file = name ? pkg?.files.find((f) => f.path === name) : undefined;
    if (!file) return;
    let stale = false;
    void fetch(file.url).then((r) => r.arrayBuffer()).then((bytes) => {
      const p = readColonies(bytes);
      if (!stale) setPopulation({ p, near: new Near(p) });
    }).catch(() => undefined);
    return () => { stale = true; };
  }, [pkg?.version.id]); // eslint-disable-line react-hooks/exhaustive-deps
  // A tank is drawn as its glass and the water in it.
  const glass = useMemo(() => {
    const site = pkg?.site as unknown as { enclosed?: boolean; interior?: Glass } | undefined;
    return site?.enclosed && site.interior ? site.interior : undefined;
  }, [pkg]);
  useEffect(() => {
    if (!city) return;
    let stale = false;
    void readWorld(platform, city, pkg).then((read) => {
      if (stale) return;
      setOf(read);
      // The place built again since this world was saved: its new build is
      // what a dive should fly, once the world is saved with it.
      const bake = read.document.bake;
      const newer = pkg && read.version && bake?.version !== pkg.version.id
        && (!bake?.at || pkg.version.createdAt > String(bake.at));
      const doc = newer ? { ...read.document, bake: { version: pkg.version.id, at: pkg.version.createdAt } } : read.document;
      // The colonies the place was built with, each an item of the reef.
      setDocument(withColonies(doc, colonies));
      history.current = { past: [], future: [] };
      setChanged(read.version === undefined || !!newer);
      setRebuilt(!!newer);
    }).catch((p) => setTrouble(p instanceof Error ? p.message : "the world could not be read"));
    return () => { stale = true; };
  }, [platform, city?.id, pkg?.version.id, colonies]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!org) return;
    platform.listAssets(org).then((all) => setAssets(all.filter((a) => a.state === "ready"))).catch(() => undefined);
  }, [platform, org]);
  useEffect(() => {
    void platform.missionsOf(place).then(setMissions).catch(() => undefined);
  }, [platform, place]);

  // ------------------------------------------------------------ history

  const apply = (next: WorldDocument) => {
    current.current = next;
    setDocument(next);
    setChanged(true);
    setSaid("");
  };
  const record = () => {
    if (!current.current) return;
    history.current.past.push(current.current);
    if (history.current.past.length > MOST_STEPS) history.current.past.shift();
    history.current.future = [];
    setSteps((n) => n + 1);
  };
  /** One step of the history. */
  const edit = (to: (was: WorldDocument) => WorldDocument) => {
    if (!current.current) return;
    record();
    apply(to(current.current));
  };
  const undo = () => {
    const prev = history.current.past.pop();
    if (!prev || !current.current) return;
    history.current.future.push(current.current);
    apply(prev);
    setSteps((n) => n + 1);
  };
  const redo = () => {
    const next = history.current.future.pop();
    if (!next || !current.current) return;
    history.current.past.push(current.current);
    apply(next);
    setSteps((n) => n + 1);
  };

  const changeLayer = (kind: WorldLayer["kind"], to: (was: WorldLayer) => WorldLayer) => edit((was) => ({
    ...was,
    layers: was.layers.some((l) => l.kind === kind)
      ? was.layers.map((l) => l.kind === kind ? to(l) : l)
      : [...was.layers, to({ id: kind, kind })],
  }));

  // ------------------------------------------------------------ the scene

  const all = useMemo(() => itemsOf(document), [document]);
  const visible = (kind: WorldLayer["kind"]) => (document && layerOf(document, kind)?.visible) !== false;
  const tree = useMemo(() => document ? treeOf(document, {
    tank: glass ? { round: !!glass.round, radiusM: glass.round?.radiusM, depthM: -glass.min[2] } : undefined,
    colonies: colonies?.length, missions,
  }) : [], [document, glass, colonies, missions]);
  const nodes = useMemo(() => new Map(flat(tree).map((n) => [n.id, n])), [tree]);
  const placeables = useMemo(() => catalogue(assets), [assets]);
  const inHand = hand ? placeables.find((p) => p.key === hand) : undefined;
  const chosenItems = selected.map((id) => all.get(id)).filter((t): t is Item => !!t);
  const viewMode: Mode = inHand ? (inHand.kind === "coral" && mode === "scatter" ? "scatter" : "place") : mode === "scatter" ? "select" : mode;

  const select = useCallback((ids: string[], how: "replace" | "add" | "toggle") => {
    setMenu(undefined);
    // A built colony of a big reef chosen in the view becomes an item, as
    // it was built; it is kept only if it is then changed.
    const rows = population && current.current
      ? ids.filter((id) => !itemsOf(current.current).has(id)).map((id) => rowOf(id, population.p.count)).filter((r): r is number => r !== undefined)
      : [];
    if (rows.length && current.current) {
      const p = population!.p;
      // Not a change: choosing it is not editing it.
      const next = withItems(current.current, rows.map((row) => colonyItem(p, row, `${CORAL_FORMS[p.forms[p.form[row]!] ?? ""]?.name ?? "Coral"} ${row + 1}`)));
      current.current = next;
      setDocument(next);
    }
    setSelected((was) => how === "replace" ? ids
      : how === "add" ? [...was, ...ids.filter((i) => !was.includes(i))]
      : ids.reduce((s, i) => s.includes(i) ? s.filter((x) => x !== i) : [...s, i], was));
  }, [population]); // eslint-disable-line react-hooks/exhaustive-deps

  // ------------------------------------------------------------ putting things in

  const newCoral = (form: string, at: { x: number; y: number }, sizeM?: number, headingDeg?: number): Item => {
    const n = [...all.values()].filter((t) => t.kind === "coral" && t.form === form).length + 1;
    return { id: named("coral"), kind: "coral", form, name: `${CORAL_FORMS[form]?.name ?? form} ${n}`,
             x: r3(at.x), y: r3(at.y), sizeM: r3(sizeM ?? CORAL_FORMS[form]?.sizeM ?? 0.5), headingDeg: Math.round(headingDeg ?? 0) };
  };

  /** What is in hand, put down here; undefined when it needs another click. */
  const made = (key: string, at: { x: number; y: number }): Item[] | undefined => {
    const p = placeables.find((x) => x.key === key);
    if (!p || !ground) return undefined;
    if (p.kind === "coral") return [newCoral(p.form!, at, undefined, Math.random() * 360)];
    if (p.asset) {
      const reef = p.kind === "reef";
      return [{ id: named(reef ? "reef" : "object"), kind: p.kind, asset: p.asset.id, name: p.asset.name,
                meets: reef ? "reef" : p.asset.meets ?? "stands", x: round(at.x), y: round(at.y), headingDeg: 0, sizeM: sizeOf(p.asset) }];
    }
    const tool = p.tool!;
    if (tool.lands === "laid" || tool.lands === "span" || tool.lands === "region") return undefined;
    return [{ id: named(key), kind: key, ...landed(tool.lands, ground, at.x, at.y) } as unknown as Item];
  };

  const put = (list: Item[], keep: boolean) => {
    edit((was) => withItems(was, list));
    setSelected(list.map((t) => t.id));
    if (!keep) { setHand(undefined); setMode("move"); }
  };

  const pick = (at: { x: number; y: number }, how: { shift: boolean }) => {
    if (!ground) return;
    if (viewMode === "measure") { setMeasure((was) => was.length >= 2 ? [at] : [...was, at]); return; }
    if (!inHand || !hand) return;
    if (viewMode === "scatter" && inHand.form) {
      const list: Item[] = [];
      for (let k = 0; k < scatter.count; k++) {
        const r = scatter.radiusM * Math.sqrt(Math.random()), a = Math.random() * Math.PI * 2;
        const base = CORAL_FORMS[inHand.form]?.sizeM ?? 0.5;
        list.push(newCoral(inHand.form, { x: at.x + Math.cos(a) * r, y: at.y + Math.sin(a) * r }, base * (0.7 + Math.random() * 0.6), Math.random() * 360));
        list[list.length - 1]!.name = `${CORAL_FORMS[inHand.form]?.name} ${[...all.values()].filter((t) => t.form === inHand.form).length + k + 1}`;
      }
      put(list, true);
      return;
    }
    const tool = inHand.tool;
    if (tool?.lands === "laid") { setRoute((was) => [...was, { x: round(at.x), y: round(at.y) }]); return; }
    if (tool && (tool.lands === "span" || tool.lands === "region")) {
      if (!first) { setFirst(at); return; }
      const one = tool.lands === "span" ? spanBetween(hand, tool, ground, first, at) : cellBetween(hand, ground, first, at);
      setFirst(undefined);
      if (one) put([one as unknown as Item], how.shift);
      return;
    }
    const list = made(hand, at);
    if (list) put(list, how.shift);
  };

  const finishRoute = () => {
    if (!hand || inHand?.tool?.lands !== "laid") return;
    setRoute([]);
    if (route.length < 2) return;
    const middle = route[Math.floor(route.length / 2)]!;
    put([{ id: named(hand), kind: hand, x: middle.x, y: middle.y, route, radiusM: 0.16, bendRadiusM: 150 } as unknown as Item], false);
  };

  const drop = (key: string, at: { x: number; y: number }) => {
    const list = made(key, at);
    if (list) put(list, false);
    else { setHand(key); pick(at, { shift: false }); }
  };

  // ------------------------------------------------------------ transforms

  const land = (t: Item): Item => {
    if (!ground) return t;
    const tool = TOOLS[t.kind];
    if (!tool || t.route || t.corners) return t;
    if (t.ends) {
      const [a, b] = tool.endsOn ?? ["ground", "ground"];
      return { ...t, ends: (t.ends as { x: number; y: number }[]).map((e, i) => landed(i === 0 ? a : b, ground, e.x, e.y)) };
    }
    return { ...t, ...landed(tool.lands, ground, Number(t.x), Number(t.y)), x: t.x, y: t.y };
  };

  const transformStart = () => {
    const these = chosenItems.filter((t) => !t.locked);
    const pivot = pivotOf(these);
    if (!pivot) return;
    record();
    holding.current = { items: these, pivot };
  };
  const transform = (d: Delta) => {
    const h = holding.current;
    if (!h || !current.current) return;
    const step = snap ? { ...d, dx: Math.round(d.dx), dy: Math.round(d.dy) } : d;
    const moved = new Map(h.items.map((t) => [t.id, land(transformed(t, step, h.pivot))]));
    apply(eachItem(current.current, (t) => moved.get(t.id) ?? t));
  };
  const transformEnd = () => { holding.current = undefined; };

  /** The same change to every chosen item, as one step. */
  const changeEach = (to: (was: Item) => Partial<Item>) => {
    const ids = new Set(chosenItems.map((t) => t.id));
    edit((was) => eachItem(was, (t) => ids.has(t.id) ? land({ ...t, ...to(t), ...(t.kind === "object" || t.kind === "reef" ? { laid: false } : {}) }) : t));
  };

  const remove = () => {
    const ids = new Set(chosenItems.filter((t) => !t.locked).map((t) => t.id));
    if (!ids.size) return;
    // A big reef's built colony is not in the world to drop: it is hidden,
    // which takes it out of the dive.
    const built = (t: Item) => population !== undefined && rowOf(t.id, population.p.count) !== undefined;
    edit((was) => eachItem(was, (t) => !ids.has(t.id) ? t : built(t) ? { ...t, hidden: true } : undefined));
    setSelected([]);
  };

  const duplicate = () => {
    if (!chosenItems.length || !ground) return;
    const step = Math.max(0.5, ground.acrossM / 200);
    const copies = chosenItems.map((t) => {
      // A copy of a big reef's built colony names the colony it copies, so
      // a dive draws it as that one is drawn.
      const row = population ? rowOf(t.id, population.p.count) : undefined;
      return land({ ...transformed(t, { dx: step, dy: -step, turnDeg: 0, scale: 1 }, { x: 0, y: 0 }),
        id: row !== undefined ? named("coral-new") : named(t.kind), name: `${nameOf(t)} copy`, built: false, laid: false, locked: false,
        ...(row !== undefined ? { copyOf: t.id } : {}) });
    });
    edit((was) => withItems(was, copies));
    setSelected(copies.map((t) => t.id));
  };

  const toggle = (node: Node, what: "hidden" | "locked") => {
    if (node.item) {
      const t = all.get(node.id);
      if (!t) return;
      const on = !(t[what] === true);
      const ids = new Set(selected.includes(node.id) ? chosenItems.map((x) => x.id) : [node.id]);
      edit((was) => eachItem(was, (x) => ids.has(x.id) ? { ...x, [what]: on } : x));
      return;
    }
    const layer = node.layer ?? (node.id === "@glass" ? "water" : undefined);
    if (layer && what === "hidden" && (node.id === `@${layer}` || node.id === "@glass")) {
      changeLayer(layer, (l) => ({ ...l, visible: l.visible === false }));
      return;
    }
    // A group: all its items.
    const ids = new Set(flat(node.children ?? []).filter((c) => c.item).map((c) => c.id));
    if (!ids.size) return;
    const on = ![...ids].every((id) => all.get(id)?.[what] === true);
    edit((was) => eachItem(was, (x) => ids.has(x.id) ? { ...x, [what]: on } : x));
  };

  const frame = (ids = selected) => view.current?.frame(ids.flatMap((id) => {
    const n = nodes.get(id);
    return n?.item ? [id] : n ? flat(n.children ?? []).filter((c) => c.item).map((c) => c.id) : [];
  }));

  const rename = (id: string, name: string | undefined) => {
    setRenaming(undefined);
    if (name === undefined || !all.has(id) || !name.trim()) return;
    edit((was) => eachItem(was, (t) => t.id === id ? { ...t, name: name.trim() } : t));
  };

  // ------------------------------------------------------------ keys

  const keys = useRef<(e: KeyboardEvent) => void>(() => undefined);
  keys.current = (e: KeyboardEvent) => {
    const target = e.target as HTMLElement | null;
    if (target && (target.tagName === "INPUT" || target.tagName === "SELECT" || target.tagName === "TEXTAREA" || target.isContentEditable)) return;
    const mod = e.metaKey || e.ctrlKey;
    const k = e.key.toLowerCase();
    if (mod && k === "z") { e.preventDefault(); if (e.shiftKey) redo(); else undo(); return; }
    if (mod && k === "y") { e.preventDefault(); redo(); return; }
    if (mod && k === "d") { e.preventDefault(); duplicate(); return; }
    if (mod && k === "a") { e.preventDefault(); setSelected([...all.values()].filter((t) => !t.hidden).map((t) => t.id)); return; }
    if (mod && k === "s") { e.preventDefault(); void save(); return; }
    if (mod) return;
    if (k === "escape") { if (hand || first || route.length) { setHand(undefined); setFirst(undefined); setRoute([]); } else { setSelected([]); setMeasure([]); } setMenu(undefined); return; }
    if (k === "delete" || k === "backspace") { e.preventDefault(); remove(); return; }
    if (k === "f2" && selected.length === 1) { setRenaming(selected[0]); return; }
    if (k === "h") {
      if (e.altKey) edit((was) => eachItem(was, (t) => t.hidden ? { ...t, hidden: false } : t));
      else if (chosenItems.length) changeEach((t) => ({ hidden: !t.hidden }));
      return;
    }
    if (k === "f") { frame(); return; }
    const tool = TOOLBAR.find((t) => t.key.toLowerCase() === k);
    if (tool) { setHand(undefined); setMode(tool.mode); return; }
    if (k === "b") { setMode("scatter"); if (!inHand?.form) setHand("coral:table"); return; }
    if (k === "m") { setHand(undefined); setMode("measure"); setMeasure([]); return; }
    const v = VIEWS.find((x) => x.key === e.key);
    if (v) { view.current?.view(v.view); return; }
  };
  useEffect(() => {
    const on = (e: KeyboardEvent) => keys.current(e);
    window.addEventListener("keydown", on);
    return () => window.removeEventListener("keydown", on);
  }, []);

  // ------------------------------------------------------------ what is drawn

  const shown = useMemo((): Shown[] => {
    const out: Shown[] = [];
    for (const t of all.values()) {
      if (t.hidden) continue;
      if (typeof t.x !== "number" && !t.route && !t.ends && !t.corners) continue;
      out.push({ ...(t as unknown as Shown), x: Number(t.x ?? 0), y: Number(t.y ?? 0) });
    }
    if (route.length && hover && inHand?.tool?.lands === "laid") out.push({ id: "drawing", kind: "pipeline", x: 0, y: 0, route: [...route, hover] });
    return out;
  }, [all, route, hover, inHand]);
  const ghost = useMemo((): Shown | undefined => {
    if (!inHand || !hover || viewMode === "scatter" || !ground) return undefined;
    if (inHand.kind === "coral") return { id: "ghost", kind: "coral", form: inHand.form, x: hover.x, y: hover.y, sizeM: CORAL_FORMS[inHand.form!]?.sizeM };
    if (inHand.tool && (inHand.tool.lands === "ground" || inHand.tool.lands === "surface")) return { id: "ghost", kind: inHand.kind, x: hover.x, y: hover.y };
    if (inHand.asset) return { id: "ghost", kind: inHand.kind, x: hover.x, y: hover.y, sizeM: sizeOf(inHand.asset) };
    return undefined;
  }, [inHand, hover, viewMode, ground]);

  // The rows changed are drawn as the world's items, and left out of the rest.
  const populationShown = useMemo((): PopulationShown | undefined => {
    if (!population) return undefined;
    const taken = new Set<number>();
    for (const t of all.values()) { const row = t.kind === "coral" ? rowOf(t.id, population.p.count) : undefined; if (row !== undefined) taken.add(row); }
    return { ...population, taken };
  }, [population, all]);

  // A mission chosen in the scene: its work drawn in the world, as last saved.
  const missionChosen = selected.length === 1 && selected[0]!.startsWith("@mission:") ? selected[0]!.slice("@mission:".length) : undefined;
  const [missionPlan, setMissionPlan] = useState<Plan | undefined>();
  useEffect(() => {
    setMissionPlan(undefined);
    if (!missionChosen) return;
    let stale = false;
    void platform.versionsOfMission(missionChosen).then((versions) => {
      const said = versions[0]?.document as Plan | undefined;
      if (!stale && said) setMissionPlan({ ...said, stages: said.stages ?? [] });
    }).catch(() => undefined);
    return () => { stale = true; };
  }, [platform, missionChosen]);
  const planShown = useMemo((): PlanIn3D | undefined => {
    if (!missionPlan || !document) return undefined;
    const drawn = ((layerOf(document, "structures")?.items ?? []).filter((t) => t.kind !== "object")) as unknown as Drawn[];
    const begin = pkg?.site?.beginAt;
    const launch = launchAt(missionPlan, drawn, { x: Number(begin?.[0] ?? 0), y: Number(begin?.[1] ?? 0) });
    return { stages: missionPlan.stages, legs: legsOf(missionPlan.stages, drawn, launch, hullOf(undefined)), drawn, launch };
  }, [missionPlan, document, pkg]);
  // Chosen, it is looked at.
  useEffect(() => {
    if (planShown?.stages.length) view.current?.frameOn([planShown.launch, ...extentOf(planShown.stages, planShown.drawn, planShown.legs)]);
  }, [missionPlan]); // eslint-disable-line react-hooks/exhaustive-deps

  // ------------------------------------------------------------ saving

  const unlaid = [...all.values()].filter((t) => (t.kind === "object" || t.kind === "reef") && !t.laid && typeof t.asset === "string" && t.asset);

  // Saving: the document, then whatever objects are not in the seabed yet
  // laid into a new version of the package, then the document again, baked
  // into that version.
  const save = async () => {
    if (!city || !of || !document || busy || mapping || !changed) return;
    setBusy(true); setTrouble("");
    try {
      const corals = [...all.values()].filter((t) => t.kind === "coral").length;
      const next = await saveWorld(platform, city, of, population ? asEdits(document, population.p) : document,
        `${corals} corals, ${(layerOf(document, "structures")?.items ?? []).length} structures`);
      setOf(next);
      setChanged(false);
      setRebuilt(false);
      setSaid(`Saved, version ${next.version?.ordinal}.`);
      if (unlaid.length > 0) await layIn();
      onChanged();
    } catch (problem) {
      setTrouble(problem instanceof Error ? problem.message : "it would not save");
    } finally {
      setBusy(false);
    }
  };

  const layIn = async () => {
    const origin = document?.georef?.origin
      ?? (() => { const c = whereIs(city?.extent, pkg?.site); return c ? { lat: c.latitude, lon: c.longitude } : undefined; })();
    if (!origin) { setTrouble("objects are laid in by where they are on Earth, and this world has no place on Earth"); return; }
    const earth = earthOf(origin);
    const started = await platform.startPlaceMapping(place, {
      assets: unlaid.map((o) => {
        const at = earth.toLatLon(Number(o.x), Number(o.y));
        if (o.kind === "reef") return { reconstructionId: String(o.asset), start: at, withinM: 50 };
        if (o.meets === "drapes") return { reconstructionId: String(o.asset) };
        return { reconstructionId: String(o.asset), placement: { lat: at.lat, lon: at.lon, headingDeg: Number(o.headingDeg ?? 0) } };
      }),
    });
    setMapping(started);
  };
  useEffect(() => {
    if (!mapping || mapping.state === "failed") return;
    if (mapping.state === "ready") {
      const versionId = mapping.versionId;
      const ids = new Set(unlaid.map((o) => o.id));
      setMapping(undefined);
      if (!versionId || !city || !of || !document) return;
      void (async () => {
        try {
          await platform.publishVersion(versionId);
          const baked: WorldDocument = {
            ...eachItem(document, (t) => ids.has(t.id) ? { ...t, laid: true, laidBy: mapping.id } : t),
            bake: { version: versionId, at: new Date().toISOString() },
          };
          const next = await saveWorld(platform, city, of, baked, "laid in and baked");
          setOf(next);
          setDocument(baked);
          setSaid("Laid into the seabed and baked: dives fly with them now.");
          onChanged();
        } catch (problem) {
          setTrouble(problem instanceof Error ? problem.message : "laid, but it would not bake");
        }
      })();
      return;
    }
    const again = setInterval(() => { platform.mapping(mapping.id).then(setMapping).catch(() => undefined); }, 3000);
    return () => clearInterval(again);
  }, [platform, mapping]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!city) return <Empty title="Not a world you have">It may have been withdrawn.</Empty>;
  if (pkg === undefined) return <Empty title="No ground yet">This world has no terrain baked yet.</Empty>;

  const depthHere = ground && hover ? groundAt(ground, hover.x, hover.y) : undefined;
  const status = mapping ? `laying objects into the seabed: ${mapping.state}` : busy ? "saving…"
    : changed ? (rebuilt ? "new build of the place: Save to dive in it" : "not saved") : said || (of?.version ? `version ${of.version.ordinal}` : "");
  const hint = viewMode === "measure" ? (measure.length === 1 ? "click the second point" : "click two points on the ground")
    : viewMode === "scatter" ? `click to plant ${scatter.count} ${inHand?.name.toLowerCase()} within ${scatter.radiusM} m`
    : inHand ? (first ? "click the other end" : inHand.tool?.lands === "laid" ? (route.length ? "click on, double-click to finish" : "click the route's first point") : `${inHand.says}; Shift keeps it in hand; Esc puts it back`)
    : selected.length ? "drag a handle, or the thing itself; Shift-drag to box select" : "click to choose, Shift-drag to box select; orbit with the mouse";
  const tape = measure.length === 2 && ground ? (() => {
    const [a, b] = measure as [{ x: number; y: number }, { x: number; y: number }];
    const across = Math.hypot(b.x - a.x, b.y - a.y), rise = groundAt(ground, a.x, a.y) - groundAt(ground, b.x, b.y);
    return `${across.toFixed(across < 10 ? 2 : 0)} m across, ${Math.abs(rise).toFixed(1)} m ${rise > 0 ? "up" : "down"}`;
  })() : undefined;
  const only = chosenItems.length === 1 ? chosenItems[0] : undefined;
  const node = selected.length ? nodes.get(selected[0]!) : undefined;
  const life = document ? layerOf(document, "life") : undefined;
  const animals = Object.values(((life?.params as { count?: Record<string, number> } | undefined)?.count) ?? {});
  const tankSays = glass?.round ? `round, ${(glass.round.radiusM * 2).toFixed(0)} m across, ${(-glass.min[2]).toFixed(1)} m deep`
    : glass ? `a box, ${(-glass.min[2]).toFixed(1)} m deep` : undefined;
  const past = history.current.past.length, future = history.current.future.length;

  const button = (icon: IconName, name: string, on: boolean, onClick: () => void, disabled = false) => (
    <button key={name} className={`tb${on ? " on" : ""}`} title={name} aria-label={name} onClick={onClick} disabled={disabled}><Icon name={icon} size={17} /></button>
  );

  return (
    <Page fill crumb="Worlds" onCrumb={onBack} title={city.name}
          status={<Status tone={trouble ? "bad" : changed || mapping ? "busy" : "good"}>{trouble || status}</Status>}
          actions={<>
            <Button onClick={() => onDive(of?.version?.id)} disabled={changed || !of?.version}><Icon name="dive" size={14} /> Dive</Button>
            <Button kind="primary" disabled={busy || !!mapping || !changed} onClick={() => void save()}><Icon name="save" size={14} /> Save</Button>
          </>}>
      <div className={`wed${panels.left ? "" : " no-left"}${panels.right ? "" : " no-right"}${panels.bottom ? "" : " no-bottom"}`}
           onClick={() => setMenu(undefined)}>
        <div className="wed-tools" role="toolbar">
          <div className="tb-group">
            {TOOLBAR.map((t) => button(t.icon, `${t.name} (${t.key})`, !inHand && mode === t.mode, () => { setHand(undefined); setMode(t.mode); }))}
          </div>
          <div className="tb-group">
            {button("scatter", "Scatter coral (B)", viewMode === "scatter", () => { setMode("scatter"); if (!inHand?.form) setHand("coral:table"); })}
            {button("measure", "Measure (M)", viewMode === "measure", () => { setHand(undefined); setMode("measure"); setMeasure([]); })}
          </div>
          {viewMode === "scatter" ? (
            <div className="tb-group tb-options">
              <label>Radius <input type="number" min={0.2} step={0.5} value={scatter.radiusM}
                                   onChange={(e) => setScatter({ ...scatter, radiusM: Math.max(0.2, Number(e.target.value) || 1) })} /> m</label>
              <label>Count <input type="number" min={1} max={100} value={scatter.count}
                                  onChange={(e) => setScatter({ ...scatter, count: Math.min(100, Math.max(1, Math.round(Number(e.target.value) || 1))) })} /></label>
            </div>
          ) : null}
          {viewMode === "measure" && tape ? <div className="tb-group tb-options"><span>{tape}</span></div> : null}
          <div className="tb-group">
            {button("snap", "Snap: whole metres, 15°", snap, () => setSnap(!snap))}
            {button("grid", "Grid", grid, () => setGrid(!grid))}
          </div>
          <div className="tb-group">
            {button("undo", `Undo (Ctrl Z)${past ? `, ${past} step${past === 1 ? "" : "s"}` : ""}`, false, undo, !past)}
            {button("redo", "Redo (Ctrl Shift Z)", false, redo, !future)}
          </div>
          <div className="tb-group">
            {button("duplicate", "Duplicate (Ctrl D)", false, duplicate, !chosenItems.length)}
            {button("delete", "Delete (Del)", false, remove, !chosenItems.length)}
            {button("frame", "Frame selection (F)", false, () => frame())}
          </div>
          <div className="tb-group">
            {VIEWS.map((v) => button(v.icon, `${v.name} view (${v.key})`, false, () => view.current?.view(v.view)))}
          </div>
          <span className="tb-gap" />
          <div className="tb-group">
            {button("panelLeft", "Scene", panels.left, () => setPanels({ ...panels, left: !panels.left }))}
            {button("panelBottom", "Assets", panels.bottom, () => setPanels({ ...panels, bottom: !panels.bottom }))}
            {button("panelRight", "Inspector", panels.right, () => setPanels({ ...panels, right: !panels.right }))}
          </div>
        </div>

        <aside className="wed-dock wed-scene">
          <header><Icon name="world" size={14} /> Scene <small>{all.size.toLocaleString()} items</small></header>
          <Outliner nodes={tree} selected={selected} open={open}
                    onOpen={(id, on) => setOpen((was) => { const s = new Set(was); if (on) s.add(id); else s.delete(id); return s; })}
                    onSelect={(ids, how) => {
                      const mission = ids.length === 1 ? nodes.get(ids[0]!)?.mission : undefined;
                      if (mission) { select(ids, "replace"); return; }
                      select(ids, how);
                    }}
                    onToggle={toggle} onFrame={(n) => n.mission ? onMission(n.mission) : frame([n.id])}
                    onMenu={(n, at) => setMenu({ node: n, ...at })} renaming={renaming} onRename={rename} />
          <button className="wed-new" onClick={onNewMission}><Icon name="plus" size={14} /> New mission</button>
        </aside>

        <section className="wed-centre">
          <div className="wed-view" onDoubleClick={finishRoute}>
            {ground && document ? (
              <World3D ground={ground} glass={glass} items={shown} selected={selected} mode={viewMode} snap={snap} grid={grid}
                       ghost={ghost} measure={viewMode === "measure" ? measure : undefined} plan={planShown} population={populationShown}
                       brush={viewMode === "scatter" && hover ? { ...hover, radiusM: scatter.radiusM } : undefined}
                       showing={{ terrain: visible("terrain"), water: visible("water"), structures: visible("structures"), reef: visible("reef") }}
                       api={view} onPick={pick} onSelect={select} onHover={setHover} onDrop={drop}
                       onTransformStart={transformStart} onTransform={transform} onTransformEnd={transformEnd} />
            ) : <div className="wed-wait">Reading the terrain…</div>}
            <div className="wed-hint">{hint}</div>
          </div>
          <div className="wed-dock wed-assets">
            <AssetBrowser items={placeables} hand={hand}
                          onHand={(key) => { setHand(key); setFirst(undefined); setRoute([]); if (key && !key.startsWith("coral:") && mode === "scatter") setMode("select"); }} />
          </div>
        </section>

        <aside className="wed-dock wed-inspector">
          {only ? (
            <ItemInspector item={only} ground={ground} onChange={(to) => changeEach(() => to)}
                           onFrame={() => frame()} onDuplicate={duplicate} onDelete={remove} />
          ) : chosenItems.length > 1 ? (
            <ManyInspector items={chosenItems} onEach={changeEach} onFrame={() => frame()} onDuplicate={duplicate} onDelete={remove} />
          ) : node && document && (node.id === `@${node.layer}` || node.id.startsWith("@water")) ? (
            <LayerInspector layer={layerOf(document, node.layer!) ?? { id: node.layer!, kind: node.layer! }} document={document} assets={assets}
                            onChange={(to) => changeLayer(node.layer!, () => to)} />
          ) : node && document && /^@(life|terrain|seabed):|^@mission:|^@glass/.test(node.id) ? (
            <NodeInspector node={node} layer={node.layer ? layerOf(document, node.layer) : undefined} onOpenMission={onMission}
                           glass={tankSays} onChange={(to) => changeLayer(to.kind, () => to)} />
          ) : document ? (
            <WorldInspector document={document} name={city.name} version={of?.version?.ordinal}
                            glass={tankSays}
                            counts={{ corals: [...all.values()].filter((t) => t.kind === "coral").length
                                        || Number((layerOf(document, "reef")?.params as { colonies?: number } | undefined)?.colonies ?? 0),
                                      structures: (layerOf(document, "structures")?.items ?? []).length,
                                      species: animals.length, animals: animals.reduce((a, b) => a + b, 0), missions: missions.length }} />
          ) : null}
        </aside>

        <footer className="wed-status">
          <span className="st-mode"><Icon name={viewMode === "place" ? (inHand?.icon ?? "plus") : viewMode === "scatter" ? "scatter" : TOOLBAR.find((t) => t.mode === viewMode)?.icon ?? "measure"} size={12} /> {viewMode}{inHand ? `: ${inHand.name}` : ""}</span>
          <span>{hover ? `${hover.x.toFixed(1)} E  ${hover.y.toFixed(1)} N` : "—"}</span>
          <span>{depthHere !== undefined ? `${depthHere.toFixed(1)} m deep` : ""}</span>
          <span>{selected.length ? `${chosenItems.length || selected.length} selected` : ""}</span>
          <span>{unlaid.length ? `${unlaid.length} to lay into the seabed on save` : ""}</span>
          <span className="st-end">{document?.georef ? `${document.georef.origin.lat.toFixed(4)}, ${document.georef.origin.lon.toFixed(4)}` : "no place on Earth"}</span>
        </footer>

        {menu ? (
          <div className="wed-menu" style={{ left: menu.x, top: menu.y }} onClick={(e) => e.stopPropagation()}>
            {menu.node.mission ? <button onClick={() => { setMenu(undefined); onMission(menu.node.mission!); }}><Icon name="mission" size={14} /> Open</button> : null}
            <button onClick={() => { setMenu(undefined); frame(); }}><Icon name="frame" size={14} /> Frame <kbd>F</kbd></button>
            {menu.node.item ? <>
              <button onClick={() => { setMenu(undefined); setRenaming(menu.node.id); }}><Icon name="rename" size={14} /> Rename <kbd>F2</kbd></button>
              <button onClick={() => { setMenu(undefined); duplicate(); }}><Icon name="duplicate" size={14} /> Duplicate <kbd>Ctrl D</kbd></button>
            </> : null}
            {menu.node.toggles ? <>
              <button onClick={() => { setMenu(undefined); toggle(menu.node, "hidden"); }}><Icon name={menu.node.hidden ? "eye" : "eyeOff"} size={14} /> {menu.node.hidden ? "Show" : "Hide"} <kbd>H</kbd></button>
              {menu.node.item || menu.node.children?.some((c) => c.item) ? (
                <button onClick={() => { setMenu(undefined); toggle(menu.node, "locked"); }}><Icon name={menu.node.locked ? "unlock" : "lock"} size={14} /> {menu.node.locked ? "Unlock" : "Lock"}</button>
              ) : null}
            </> : null}
            {chosenItems.length ? <button className="bad" onClick={() => { setMenu(undefined); remove(); }}><Icon name="delete" size={14} /> Delete <kbd>Del</kbd></button> : null}
          </div>
        ) : null}
      </div>
    </Page>
  );
}
