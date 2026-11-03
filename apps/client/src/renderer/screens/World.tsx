// A world: one place in the sea, in three dimensions, in layers.
//
// The layers down the side as a modelling tool has them (water, terrain,
// seabed, reef, structures, life, and the world's missions), each one a real
// asset of the library or authored here, each shown or hidden. The world in
// the middle, to orbit, choose in and drag over the seabed. What is chosen
// described beside it. The library of what can be put in it along the bottom
// of the side, opened when wanted.
//
// One world per place and one design per world: a save is a new version of
// it, the history is what there is to go back to. Objects from the library
// that have a mesh of their own (a platform, a pipe from its route, a reef
// from a video) go into the package's seabed when the world is saved, which
// is the bake a dive runs in; equipment goes to the simulator as things.

import React, { useCallback, useEffect, useMemo, useState } from "react";

import type { Asset, Mapping, Mission, Platform } from "@coral-city/api";
import type { Held, Packages } from "./Deck.js";
import { groundAt, groundOf, type Ground } from "../parts/SiteChart.js";
import { drape, restOn } from "../parts/landing.js";
import { World3D, type Colony, type Glass, type Shown } from "../parts/World3D.js";
import { whereIs } from "../platform/packages.js";
import { layerOf, readWorld, saveWorld, type WorldDocument, type WorldLayer, type WorldOf } from "../platform/world.js";
import { GROUPS, TOOLS, landed, named, spanBetween, cellBetween } from "./Layout.js";
import { Button, Page, Status } from "../ui/components.js";
import { Empty } from "./parts.js";
import "../parts/world.css";

type Item = NonNullable<WorldLayer["items"]>[number];

const LAYER_NAMES: Record<WorldLayer["kind"], string> = {
  water: "Water", terrain: "Terrain", seabed: "Seabed", reef: "Reef", structures: "Structures", life: "Life",
};
const ORDER: WorldLayer["kind"][] = ["water", "terrain", "seabed", "reef", "structures", "life"];

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
  const [of, setOf] = useState<WorldOf | undefined>();
  const [document, setDocument] = useState<WorldDocument | undefined>();
  const [assets, setAssets] = useState<Asset[]>([]);
  const [missions, setMissions] = useState<Mission[]>([]);
  const [chosen, setChosen] = useState<string | undefined>();
  const [layer, setLayer] = useState<WorldLayer["kind"]>("structures");
  const [tool, setTool] = useState<string | undefined>();
  const [first, setFirst] = useState<{ x: number; y: number } | undefined>();
  const [route, setRoute] = useState<{ x: number; y: number }[]>([]);
  const [hover, setHover] = useState<{ x: number; y: number } | undefined>();
  const [library, setLibrary] = useState(false);
  // The inspector floats over the world only while something is open in it.
  const [inspecting, setInspecting] = useState(false);
  const [changed, setChanged] = useState(false);
  const [busy, setBusy] = useState(false);
  const [said, setSaid] = useState("");
  // The place was built again since the world was saved.
  const [rebuilt, setRebuilt] = useState(false);
  const [trouble, setTrouble] = useState("");
  const [mapping, setMapping] = useState<Mapping | undefined>();

  useEffect(() => { void groundOf(pkg).then(setGround); }, [pkg]);
  // A tank is drawn as its glass and the water in it.
  // The colonies a place was built with, when its record lists them.
  const colonies = useMemo(() => {
    const listed = (pkg?.site as unknown as { reef?: { colonies_at?: Colony[] } } | undefined)?.reef?.colonies_at;
    return Array.isArray(listed) ? listed.filter((c) => Array.isArray(c.at)) : undefined;
  }, [pkg]);
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
      setDocument(newer ? { ...read.document, bake: { version: pkg.version.id, at: pkg.version.createdAt } } : read.document);
      setChanged(read.version === undefined || !!newer);
      setRebuilt(!!newer);
    }).catch((p) => setTrouble(p instanceof Error ? p.message : "the world could not be read"));
    return () => { stale = true; };
  }, [platform, city?.id, pkg?.version.id]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!org) return;
    platform.listAssets(org).then((all) => setAssets(all.filter((a) => a.state === "ready"))).catch(() => undefined);
  }, [platform, org]);
  useEffect(() => {
    void platform.missionsOf(place).then(setMissions).catch(() => undefined);
  }, [platform, place]);

  const items = useCallback((kind: WorldLayer["kind"]): Item[] =>
    (document && layerOf(document, kind)?.items) ?? [], [document]);
  const visible = (kind: WorldLayer["kind"]) => (document && layerOf(document, kind)?.visible) !== false;

  /** Changes one layer, and marks the world as not saved. */
  const change = (kind: WorldLayer["kind"], to: (was: WorldLayer) => WorldLayer) => {
    setDocument((was) => was && {
      ...was,
      layers: was.layers.some((l) => l.kind === kind)
        ? was.layers.map((l) => l.kind === kind ? to(l) : l)
        : [...was.layers, to({ id: kind, kind })],
    });
    setChanged(true);
    setSaid("");
  };
  const setItems = (kind: "structures" | "reef", to: (was: Item[]) => Item[]) =>
    change(kind, (l) => ({ ...l, items: to(l.items ?? []) }));

  const assetOf = tool?.startsWith("asset:") ? assets.find((a) => `asset:${a.id}` === tool) : undefined;
  const toolOf = tool && !tool.startsWith("asset:") ? TOOLS[tool] : undefined;

  const pick = useCallback((at: { x: number; y: number }) => {
    if (!ground) return;
    if (assetOf) {
      const reef = assetOf.kind === "reef";
      const one: Item = { id: named(reef ? "reef" : "object"), kind: reef ? "reef" : "object", asset: assetOf.id,
        name: assetOf.name, meets: reef ? "reef" : assetOf.meets ?? "stands",
        x: round(at.x), y: round(at.y), headingDeg: 0, sizeM: sizeOf(assetOf) };
      setItems(reef ? "reef" : "structures", (was) => [...was, one]);
      setChosen(one.id);
      setTool(undefined);
      return;
    }
    if (!tool || !toolOf) { setChosen(undefined); return; }
    if (toolOf.lands === "laid") { setRoute((was) => [...was, { x: round(at.x), y: round(at.y) }]); return; }
    if (toolOf.lands === "span" || toolOf.lands === "region") {
      if (!first) { setFirst(at); return; }
      const made = toolOf.lands === "span" ? spanBetween(tool, toolOf, ground, first, at) : cellBetween(tool, ground, first, at);
      setFirst(undefined);
      if (made) { setItems("structures", (was) => [...was, made as unknown as Item]); setChosen(made.id); }
      return;
    }
    const made = { id: named(tool), kind: tool, ...landed(toolOf.lands, ground, at.x, at.y) };
    setItems("structures", (was) => [...was, made as unknown as Item]);
    setChosen(made.id);
  }, [ground, tool, toolOf, assetOf, first]); // eslint-disable-line react-hooks/exhaustive-deps

  const finishRoute = () => {
    if (!tool || toolOf?.lands !== "laid") return;
    setRoute([]);
    if (route.length < 2) return;
    const middle = route[Math.floor(route.length / 2)]!;
    const made = { id: named(tool), kind: tool, x: middle.x, y: middle.y, route, radiusM: 0.16, bendRadiusM: 150 };
    setItems("structures", (was) => [...was, made as unknown as Item]);
    setChosen(made.id);
  };

  const move = useCallback((id: string, at: { x: number; y: number }) => {
    if (!ground) return;
    const shift = (was: Item[]) => was.map((t) => {
      if (t.id !== id || t.route || t.ends || t.corners || t.laid) return t;
      if (t.kind === "object" || t.kind === "reef") return { ...t, x: round(at.x), y: round(at.y) };
      return { ...t, ...landed(TOOLS[t.kind]?.lands ?? "ground", ground, at.x, at.y) };
    });
    setItems("structures", shift);
    setItems("reef", shift);
  }, [ground]); // eslint-disable-line react-hooks/exhaustive-deps

  const remove = () => {
    if (!chosen) return;
    setItems("structures", (was) => was.filter((t) => t.id !== chosen));
    setItems("reef", (was) => was.filter((t) => t.id !== chosen));
    setChosen(undefined);
  };

  // What is drawn: every structure and reef that has a place in the frame.
  const shown = useMemo((): Shown[] => {
    const all: Shown[] = [];
    for (const t of [...items("structures"), ...items("reef")]) {
      if (typeof t.x !== "number" && !t.route && !t.ends && !t.corners) continue;
      all.push({ ...(t as unknown as Shown), x: Number(t.x ?? 0), y: Number(t.y ?? 0) });
    }
    if (route.length && hover && toolOf?.lands === "laid") all.push({ id: "drawing", kind: "pipeline", x: 0, y: 0, route: [...route, hover] });
    return all;
  }, [items, route, hover, toolOf]);

  const chosenItem = [...items("structures"), ...items("reef")].find((t) => t.id === chosen);
  const unlaid = [...items("structures").filter((t) => t.kind === "object"), ...items("reef")]
    .filter((t) => !t.laid && typeof t.asset === "string" && t.asset);

  // Saving: the document, then whatever objects are not in the seabed yet
  // laid into a new version of the package, then the document again, baked
  // into that version.
  const save = async () => {
    if (!city || !of || !document) return;
    setBusy(true); setTrouble("");
    try {
      const next = await saveWorld(platform, city, of, document,
        `${items("structures").length} structures, ${items("reef").length} reefs`);
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
    const made = await platform.startPlaceMapping(place, {
      assets: unlaid.map((o) => {
        const at = earth.toLatLon(Number(o.x), Number(o.y));
        if (o.kind === "reef") return { reconstructionId: String(o.asset), start: at, withinM: 50 };
        if (o.meets === "drapes") return { reconstructionId: String(o.asset) };
        return { reconstructionId: String(o.asset), placement: { lat: at.lat, lon: at.lon, headingDeg: Number(o.headingDeg ?? 0) } };
      }),
    });
    setMapping(made);
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
          const laid = (was: Item[]) => was.map((t) => ids.has(t.id) ? { ...t, laid: true, laidBy: mapping.id } : t);
          const baked: WorldDocument = {
            ...document,
            layers: document.layers.map((l) => l.kind === "structures" || l.kind === "reef" ? { ...l, items: laid(l.items ?? []) } : l),
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
  const libraryAssets = assets.filter((a) => a.kind === "reef" || a.kind === "structure");

  return (
    <Page fill crumb="Worlds" onCrumb={onBack} title={city.name}
          status={<Status tone={trouble ? "bad" : changed || mapping ? "busy" : "good"}>{trouble || status}</Status>}
          actions={<>
            <Button kind={library ? "primary" : undefined} onClick={() => setLibrary(!library)}>Add</Button>
            <Button onClick={() => onDive(of?.version?.id)} disabled={changed || !of?.version}>Dive</Button>
            <Button kind="primary" disabled={busy || !!mapping || !changed} onClick={() => void save()}>Save</Button>
          </>}>
      <div className="wed">
        <section className="wed-view" onDoubleClick={finishRoute}>
          {ground && document ? (
            <World3D ground={ground} glass={glass} colonies={colonies} items={shown} chosen={chosen} placing={!!tool}
                     showing={{ terrain: visible("terrain"), water: visible("water"), structures: visible("structures"), reef: visible("reef") }}
                     onPick={pick} onChoose={(id) => { setChosen(id); if (id) setLayer(items("reef").some((t) => t.id === id) ? "reef" : "structures"); }}
                     onMove={move} onHover={setHover} />
          ) : <div className="wed-wait">Reading the terrain…</div>}
          <div className="wed-hint">
            {tool ? (first ? "click the other end" : toolOf?.lands === "laid" ? "click the route, double-click to finish" : "click the seabed to put it down")
              : chosen ? "drag it over the seabed; orbit with the mouse" : "click a thing to choose it; drag to orbit, scroll to zoom"}
          </div>
        </section>

        <aside className="wed-panel wed-layers">
          <h3>Layers</h3>
          {ORDER.map((kind) => {
            const here = document ? layerOf(document, kind) : undefined;
            const list = kind === "structures" || kind === "reef" ? here?.items ?? [] : [];
            return (
              <div key={kind} className={`wed-layer${layer === kind ? " on" : ""}`}>
                <div className="wed-layer-row" onClick={() => { setLayer(kind); setChosen(undefined); setInspecting(true); }}>
                  <button className={`eye${visible(kind) ? "" : " off"}`} title={visible(kind) ? "Hide" : "Show"}
                          onClick={(e) => { e.stopPropagation(); change(kind, (l) => ({ ...l, visible: !visible(kind) })); }}>
                    <svg viewBox="0 0 16 16" width="14" height="14"><path d="M1 8s2.6-5 7-5 7 5 7 5-2.6 5-7 5-7-5-7-5z" fill="none" stroke="currentColor" strokeWidth="1.3"/>{visible(kind) ? <circle cx="8" cy="8" r="2.2" fill="currentColor"/> : <path d="M2 14 14 2" stroke="currentColor" strokeWidth="1.3"/>}</svg>
                  </button>
                  <span>{LAYER_NAMES[kind]}</span>
                  <small>{kind === "terrain" ? `${here?.stack?.length ?? 0} sources` : list.length ? list.length : ""}</small>
                </div>
                {list.length > 0 && layer === kind ? (
                  <ul>
                    {list.map((t) => (
                      <li key={t.id} className={t.id === chosen ? "on" : ""} onClick={() => setChosen(t.id)}>
                        {String(t.name ?? TOOLS[t.kind]?.name ?? t.kind)}
                      </li>
                    ))}
                  </ul>
                ) : null}
              </div>
            );
          })}
          <div className={`wed-layer${layer === ("missions" as never) ? " on" : ""}`}>
            <div className="wed-layer-row"><span className="eye-gap" /><span>Missions</span><small>{missions.length || ""}</small></div>
            <ul>
              {missions.map((m) => <li key={m.id} onClick={() => onMission(m.id)}>{m.name}</li>)}
              <li className="add" onClick={onNewMission}>+ New mission</li>
            </ul>
          </div>
        </aside>

        {library ? (
          <aside className="wed-panel wed-library">
            <header><strong>Add to the world</strong>
              <button className="wed-close" title="Close" onClick={() => { setLibrary(false); setTool(undefined); }}>×</button></header>
              {GROUPS.map((group) => (
                <div key={group.lands}>
                  <h4>{group.title}</h4>
                  <div className="wed-tiles">
                    {Object.entries(TOOLS).filter(([, t]) => t.lands === group.lands).map(([key, t]) => (
                      <button key={key} className={tool === key ? "on" : ""}
                              onClick={() => { setFirst(undefined); setRoute([]); setTool(tool === key ? undefined : key); }}>{t.name}</button>
                    ))}
                  </div>
                </div>
              ))}
              <h4>Your objects</h4>
              <div className="wed-tiles">
                {libraryAssets.length === 0 ? <em>none ready</em> : libraryAssets.map((a) => (
                  <button key={a.id} className={tool === `asset:${a.id}` ? "on" : ""}
                          onClick={() => setTool(tool === `asset:${a.id}` ? undefined : `asset:${a.id}`)}>{a.name}</button>
                ))}
              </div>
          </aside>
        ) : null}

        {chosenItem || inspecting ? (
          <aside className="wed-panel wed-inspector">
            <button className="wed-close" title="Close" onClick={() => { setChosen(undefined); setInspecting(false); }}>×</button>
          {chosenItem ? (
            <ItemInspector item={chosenItem} ground={ground} onDelete={remove}
                           onTurn={(deg) => setItems(chosenItem.kind === "reef" ? "reef" : "structures",
                             (was) => was.map((t) => t.id === chosenItem.id ? { ...t, headingDeg: deg, laid: false } : t))} />
          ) : document ? (
            <LayerInspector layer={layerOf(document, layer) ?? { id: layer, kind: layer }} document={document} assets={assets}
                            onChange={(to) => change(layer, () => to)} />
          ) : null}
          </aside>
        ) : null}

        <footer className="wed-status">
          <span>{hover ? `${hover.x.toFixed(0)} m E, ${hover.y.toFixed(0)} m N` : ""}</span>
          <span>{depthHere !== undefined ? `${depthHere.toFixed(1)} m deep` : ""}</span>
          <span>{document?.georef ? `${document.georef.origin.lat.toFixed(4)}, ${document.georef.origin.lon.toFixed(4)}` : "no place on Earth"}</span>
          <span>{unlaid.length ? `${unlaid.length} to lay into the seabed on save` : ""}</span>
        </footer>
      </div>
    </Page>
  );
}

function ItemInspector({ item, ground, onDelete, onTurn }: {
  item: Item; ground: Ground | undefined; onDelete: () => void; onTurn: (deg: number) => void;
}): React.JSX.Element {
  const x = Number(item.x ?? 0), y = Number(item.y ?? 0);
  const size = item.sizeM as [number, number, number] | undefined;
  const fit = ground && size && item.kind === "object" && item.meets !== "drapes"
    ? restOn(ground, x, y, size[0], size[1], Number(item.headingDeg ?? 0)) : undefined;
  const laid = ground && Array.isArray(item.route) ? drape(ground, item.route as { x: number; y: number }[]) : undefined;
  return (
    <div className="wed-props">
      <h3>{String(item.name ?? TOOLS[item.kind]?.name ?? item.kind)}</h3>
      <dl>
        <dt>Kind</dt><dd>{item.kind === "object" ? "object from the library" : item.kind === "reef" ? "reef" : TOOLS[item.kind]?.name ?? item.kind}</dd>
        {item.route ? null : <><dt>Where</dt><dd>{x.toFixed(1)} m E, {y.toFixed(1)} m N</dd></>}
        {ground && !item.route ? <><dt>Depth</dt><dd>{groundAt(ground, x, y).toFixed(1)} m</dd></> : null}
        {fit ? <><dt>Fit</dt><dd>{fit.tiltDeg >= 0.5 ? `leans ${fit.tiltDeg.toFixed(0)}°` : "level"}{fit.clearM >= 0.05 ? `, ${fit.clearM.toFixed(1)} m clear under one side` : ""}</dd></> : null}
        {laid ? <><dt>Length</dt><dd>{laid.lengthM.toFixed(0)} m, {laid.spans.length} free span{laid.spans.length === 1 ? "" : "s"}</dd></> : null}
        {item.kind === "object" || item.kind === "reef" ? <><dt>In the seabed</dt><dd>{item.laid ? "yes" : "on save"}</dd></> : null}
      </dl>
      {(item.kind === "object" && item.meets !== "drapes") ? (
        <label className="wed-field">Heading
          <input type="number" value={Number(item.headingDeg ?? 0)} step={5}
                 onChange={(e) => onTurn(((Number(e.target.value) % 360) + 360) % 360)} /> °
        </label>
      ) : null}
      <Button kind="danger" onClick={onDelete}>Remove</Button>
    </div>
  );
}

function LayerInspector({ layer, document, assets, onChange }: {
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
          <p className="wed-note">Open the library to put equipment or your objects in the world.</p>
        </div>
      );
  }
}
