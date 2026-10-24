// A new place, composed: where, its ground, the assets in it, Resolve, Build.
//
// Plan item 71. A place is put together from things that exist on their own:
// a square of the Earth, a ground (every public source that reaches it, a
// flat seabed, the organisation's own survey files, and soon a place from
// the iOcean map store), and assets made independently (reefs rebuilt from
// dive videos today; pipelines, platforms and foundations as they arrive).
// The ground is built first, then each asset is resolved onto it in turn:
// the candidates shown on its chart, one chosen or nudged, and laid in, each
// lay a new draft version on top of the last. Then it is published.

import { useEffect, useMemo, useRef, useState } from "react";
import type { Asset, Build, BuildBrief, Mapping, Platform, Reconstruction, StorePlace } from "@coral-city/api";

import type { Held } from "./Deck.js";
import { WorldMap, type LatLon } from "../parts/WorldMap.js";
import { FitMap } from "../parts/FitMap.js";
import { ResolveChoice, useVersionGround, type Candidate } from "../parts/ResolveChoice.js";
import { Button, Page, Status } from "../ui/components.js";

type Use = "raster" | "points" | "ortho";
type Own = { file: File; use: Use; errorM: string; stage: string; done: number; objectId?: string };
type GroundKind = "public" | "flat" | "store";

const SIZES = [250, 500, 1000, 2000, 5000];

function guessUse(name: string): Use {
  const ext = name.toLowerCase().split(".").pop() ?? "";
  return ["xyz", "csv", "txt", "pts"].includes(ext) ? "points" : "raster";
}

function slugOf(name: string): string {
  const slug = name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 56);
  return slug.length >= 3 ? slug : `${slug || "place"}-place`;
}

function sizeSaid(m: number): string {
  return m >= 1000 ? `${m / 1000} km` : `${m} m`;
}

/** Where the work is: building the ground, the assets resolved, chosen and laid together, or done. */
type AssetView = { ordinal: number; reconstructionId: string; name?: string; state: string; candidates?: unknown[];
                   start?: [number, number] | null; failure?: string; steps?: { say: string }[] };
const assetsOf = (m: Mapping): AssetView[] => ((m as unknown as { assets?: AssetView[] }).assets ?? []);
type Stage =
  | { at: "composing" }
  | { at: "ground"; build: Build }
  | { at: "assets"; mapping: Mapping }
  | { at: "done"; versionId: string };

export function Compose({ platform, held, base, chosen, onBack, onOpen }: {
  platform: Platform;
  held: Held;
  /** A map store place to build on, from its card's Build on it. */
  base?: string;
  /** An asset already chosen, from its page: a reef or structure to lay, or a survey for the ground. */
  chosen?: string;
  onBack: () => void;
  onOpen: (id: string) => void;
}): React.JSX.Element {
  const institution = held.institution;
  const [view, setView] = useState({ centre: { lat: 22.3, lon: 38.95 } as LatLon, zoom: 9 });
  const [where, setWhere] = useState<LatLon | undefined>();
  const [typed, setTyped] = useState("");
  const [name, setName] = useState("");
  const [acrossM, setAcrossM] = useState(1000);
  const [ground, setGround] = useState<GroundKind>(base ? "store" : "public");
  const [store, setStore] = useState<StorePlace[]>([]);
  const [storeBase, setStoreBase] = useState<string | undefined>(base);
  const [nearby, setNearby] = useState<StorePlace[]>([]);
  const [flatDepth, setFlatDepth] = useState("8");
  const [coral, setCoral] = useState(true);
  const [own, setOwn] = useState<Own[]>([]);
  const [reefs, setReefs] = useState<Reconstruction[]>([]);
  const [picked, setPicked] = useState<string[]>([]);
  // Structures and seabed surveys the institution has made on their own.
  const [others, setOthers] = useState<Asset[]>([]);
  const [surveys, setSurveys] = useState<string[]>([]);
  // Where each standing structure goes: "lat, lon" and a heading.
  const [stands, setStands] = useState<Record<string, { at: string; heading: string }>>({});
  const [catalogue, setCatalogue] = useState<string[]>([]);
  const [place, setPlace] = useState<{ id: string; name: string } | undefined>();
  const [stage, setStage] = useState<Stage>({ at: "composing" });
  const [versionId, setVersionId] = useState<string | undefined>();
  const [trouble, setTrouble] = useState("");
  const [busy, setBusy] = useState(false);
  const [published, setPublished] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    platform.buildSources().then((c) => setCatalogue(Object.keys(c.sources))).catch(() => undefined);
    if (institution) {
      platform.reconstructionsOf(institution.id).then((all) => setReefs(all.filter((r) => r.state === "ready"))).catch(() => undefined);
      platform.listAssets(institution.id).then((all) => setOthers(all.filter((a) => a.kind !== "reef" && a.state === "ready"))).catch(() => undefined);
    }
  }, [platform, institution]);

  useEffect(() => { platform.storePlaces().then(setStore).catch(() => undefined); }, [platform]);
  // The asset somebody came from, chosen once its list has come.
  const took = useRef(false);
  useEffect(() => {
    if (!chosen || took.current) return;
    const survey = others.find((a) => a.id === chosen && a.kind === "bathymetry");
    if (survey) {
      took.current = true;
      setSurveys((was) => was.includes(chosen) ? was : [...was, chosen]);
      // Where the survey is, so the place is put over it.
      const box = (survey.footprint as { bbox?: number[] } | undefined)?.bbox;
      if (box && box.length === 4) {
        const centre = { lat: (box[0]! + box[2]!) / 2, lon: (box[1]! + box[3]!) / 2 };
        setWhere(centre);
        setView({ centre, zoom: 14 });
      }
      return;
    }
    if (others.some((a) => a.id === chosen) || reefs.some((r) => r.id === chosen)) {
      took.current = true;
      setPicked((was) => was.includes(chosen) ? was : [...was, chosen]);
    }
  }, [chosen, others, reefs]);
  const baseOf = (id?: string) => store.find((one) => one.id === id);
  useEffect(() => {
    const one = baseOf(storeBase);
    if (!one?.extent || ground !== "store") return;
    const e = one.extent;
    const at = { lat: (e.north + e.south) / 2, lon: (e.east + e.west) / 2 };
    setWhere(at);
    setView({ centre: at, zoom: 12 });
    setAcrossM(Math.round(Math.max(e.north - e.south, 0) * 111_320));
    if (!name) setName(`${one.name}, ours`);
  }, [storeBase, store, ground]); // eslint-disable-line react-hooks/exhaustive-deps
  // An area that overlaps a store place says so: nobody rebuilds it.
  useEffect(() => {
    if (!where || ground === "store") { setNearby([]); return; }
    let stale = false;
    platform.storePlaces({ lat: where.lat, lon: where.lon, acrossM }).then((found) => { if (!stale) setNearby(found); }).catch(() => undefined);
    return () => { stale = true; };
  }, [platform, where, acrossM, ground]);

  const typedAt = useMemo(() => {
    const found = typed.match(/^\s*(-?\d+(?:\.\d+)?)\s*[, ]\s*(-?\d+(?:\.\d+)?)\s*$/);
    if (!found) return undefined;
    const lat = Number(found[1]), lon = Number(found[2]);
    return Math.abs(lat) <= 85 && Math.abs(lon) <= 180 ? { lat, lon } : undefined;
  }, [typed]);

  // The ground's build, watched until it has made a version.
  useEffect(() => {
    if (stage.at !== "ground" || stage.build.state === "ready" || stage.build.state === "failed") return;
    const again = setInterval(() => {
      platform.build(stage.build.id).then((b) => setStage({ at: "ground", build: b })).catch(() => undefined);
    }, 4000);
    return () => clearInterval(again);
  }, [platform, stage]);
  // Built: every asset resolved onto it at once, or it is done.
  useEffect(() => {
    if (stage.at !== "ground" || stage.build.state !== "ready" || !stage.build.versionId) return;
    setVersionId(stage.build.versionId);
    void resolveAll();
  }, [stage]); // eslint-disable-line react-hooks/exhaustive-deps
  // The mapping, watched while its assets resolve, and while they are laid.
  useEffect(() => {
    if (stage.at !== "assets") return;
    const m = stage.mapping;
    if (m.state === "failed") return;
    if (m.state === "ready") {
      if (m.versionId) setVersionId(m.versionId);
      setStage({ at: "done", versionId: m.versionId ?? versionId ?? "" });
      return;
    }
    const again = setInterval(() => {
      platform.mapping(m.id).then((one) => setStage((s) => s.at === "assets" ? { ...s, mapping: one } : s)).catch(() => undefined);
    }, 4000);
    return () => clearInterval(again);
  }, [platform, stage]); // eslint-disable-line react-hooks/exhaustive-deps

  const resolveAll = async () => {
    if (!place) return;
    if (picked.length === 0) { setStage({ at: "done", versionId: versionId ?? "" }); return; }
    try {
      const mapping = await platform.startPlaceMapping(place.id, {
        assets: picked.map((id) => {
          const structure = others.find((a) => a.id === id);
          if (structure) {
            if (structure.meets !== "stands") return { reconstructionId: id };
            const at = latLonOf(stands[id]?.at ?? "") ?? where!;
            return { reconstructionId: id, placement: { lat: at.lat, lon: at.lon, headingDeg: Number(stands[id]?.heading || 0) } };
          }
          return {
            reconstructionId: id, withinM: Math.max(10, Math.min(5000, acrossM)),
            ...(where ? { start: where } : {}),
            ...(ground === "flat" ? { depthM: Number(flatDepth) } : {}),
          };
        }),
      });
      setStage({ at: "assets", mapping });
    } catch (problem) {
      setTrouble(problem instanceof Error ? problem.message : "Resolve could not start");
    }
  };

  const build = async () => {
    if (!where || !institution) return;
    setBusy(true);
    setTrouble("");
    try {
      const files: NonNullable<BuildBrief["files"]> = [];
      for (let i = 0; i < own.length; i++) {
        const one = own[i]!;
        let objectId = one.objectId;
        if (!objectId) {
          const stored = await platform.upload(institution.id, one.file, {
            onProgress: (stage, done) => setOwn((was) => was.map((o, j) => j === i ? { ...o, stage, done } : o)),
          });
          objectId = stored.id;
          setOwn((was) => was.map((o, j) => j === i ? { ...o, stage: "stored", objectId } : o));
        }
        files.push({ objectId, use: one.use, name: one.file.name, ...(one.errorM ? { errorM: Number(one.errorM) } : {}) });
      }
      const halfLat = acrossM / 2 / 111_320;
      const halfLon = acrossM / 2 / (111_320 * Math.max(Math.cos(where.lat * Math.PI / 180), 1e-6));
      let founded;
      for (let attempt = 0; attempt < 6 && !founded; attempt++) {
        const slug = attempt === 0 ? slugOf(name) : `${slugOf(name)}-${attempt + 1}`;
        try {
          founded = await platform.foundPlace(institution.id, {
            slug, name: name.trim(), verticalDatum: "mean sea level",
            summary: ground === "flat" ? `composed on a flat seabed at ${flatDepth} m`
              : ground === "store" ? `composed on ${baseOf(storeBase)?.name ?? "a map store place"}` : "composed from public data and its own files",
            extent: { west: where.lon - halfLon, south: where.lat - halfLat, east: where.lon + halfLon, north: where.lat + halfLat },
          });
        } catch (refused) {
          if (!(refused instanceof Error) || !/already exists/.test(refused.message)) throw refused;
        }
      }
      if (!founded) throw new Error("a place with that name exists; choose another");
      setPlace({ id: founded.id, name: founded.name });
      const survey = surveys.length ? { survey: surveys } : {};
      const brief: BuildBrief = ground === "store" && storeBase
        ? { base: { kind: "place", cityId: storeBase }, sources: [], ...(files.length ? { files } : {}), ...survey }
        : ground === "flat"
        ? { centre: [where.lat, where.lon], acrossM, sources: [], flatDepthM: Number(flatDepth), coral, ...(files.length ? { files } : {}), ...survey }
        : { centre: [where.lat, where.lon], acrossM, sources: catalogue as BuildBrief["sources"], ...(files.length ? { files } : {}), ...survey };
      setStage({ at: "ground", build: await platform.startBuild(founded.id, brief) });
    } catch (problem) {
      setTrouble(problem instanceof Error ? problem.message : "the place could not be started");
    } finally {
      setBusy(false);
    }
  };

  const publish = async () => {
    if (!versionId) return;
    setBusy(true);
    try {
      await platform.publishVersion(versionId);
      setPublished(true);
    } catch (problem) {
      setTrouble(problem instanceof Error ? problem.message : "could not publish");
    } finally {
      setBusy(false);
    }
  };

  const composing = stage.at === "composing";
  const ready = composing && !!where && name.trim().length > 0 && !!institution && !busy
    && (ground !== "flat" || (Number(flatDepth) >= 0.5 && Number(flatDepth) <= 60))
    && (ground !== "store" || !!storeBase);
  const groundNow = useVersionGround(platform, versionId);
  // The first asset still waiting for its place to be chosen.
  const choosing = stage.at === "assets" && stage.mapping.state === "choosing"
    ? assetsOf(stage.mapping).find((a) => a.state === "choosing") : undefined;
  const extentOf = (r?: Reconstruction): [number, number] => {
    const e = (r?.manifest as { extentM?: number[] } | undefined)?.extentM;
    return e && e.length >= 2 ? [e[0]!, e[1]!] : [50, 10];
  };

  const action = composing ? (
    <Button kind="primary" disabled={!ready} onClick={() => void build()}>{busy ? "Starting…" : "Build"}</Button>
  ) : stage.at === "done" && !published ? (
    <Button kind="primary" disabled={busy || !versionId} onClick={() => void publish()}>Publish</Button>
  ) : published && place ? (
    <Button kind="primary" onClick={() => onOpen(place.id)}>Open the place</Button>
  ) : undefined;

  return (
    <Page title={place?.name ?? "New place"} crumb="Places" onCrumb={onBack} wide actions={action}
          subtitle="Where, its ground, the assets in it; Resolve fits each asset to the ground."
          info="A place is composed from things that exist on their own: a square of the Earth, a ground for it, and assets made independently, such as reefs rebuilt from dive videos. The ground is built first; then each asset is fitted to it in turn, and you choose where it goes before it is laid in.">
      {choosing && stage.at === "assets" ? (
        <section>
          <h2>Where {choosing.name ?? reefs.find((r) => r.id === choosing.reconstructionId)?.name ?? "the asset"} fits
            <span className="note"> · asset {choosing.ordinal + 1} of {assetsOf(stage.mapping).length}</span></h2>
          <ResolveChoice key={choosing.ordinal} candidates={(choosing.candidates ?? []) as Candidate[]} start={choosing.start}
                         ground={groundNow} extentM={extentOf(reefs.find((r) => r.id === choosing.reconstructionId))} busy={busy}
                         onAccept={(choice) => {
                           setBusy(true);
                           platform.acceptMapping(stage.mapping.id, { ...choice, asset: choosing.ordinal })
                             .then((m) => setStage({ at: "assets", mapping: m }))
                             .catch((p) => setTrouble(p instanceof Error ? p.message : "could not choose it"))
                             .finally(() => setBusy(false));
                         }} />
        </section>
      ) : (
        <div className="compose">
          <div className="compose-map">
            {composing || !groundNow ? (
              <>
                <WorldMap view={view} onView={setView} chosen={where} acrossM={acrossM}
                          onChoose={(at) => { if (composing) setWhere(at); }} />
                <div className="builder-where">
                  <input placeholder="latitude, longitude, or click the map" value={typed} disabled={!composing}
                         onChange={(e) => setTyped(e.target.value)}
                         onKeyDown={(e) => {
                           if (e.key === "Enter" && typedAt && composing) {
                             setWhere(typedAt);
                             setView({ centre: typedAt, zoom: Math.max(view.zoom, 13) });
                           }
                         }} />
                  <span className="note">{where ? `${where.lat.toFixed(4)}, ${where.lon.toFixed(4)} · ${sizeSaid(acrossM)} square` : "Zoom in and click the middle of the place."}</span>
                </div>
                {nearby.length > 0 && composing ? (
                  <div className="overlap">
                    <span>This area is in the map store: <strong>{nearby[0]!.name}</strong>{nearby.length > 1 ? ` and ${nearby.length - 1} more` : ""}.</span>
                    <Button onClick={() => { setGround("store"); setStoreBase(nearby[0]!.id); }}>Use it as the ground</Button>
                  </div>
                ) : null}
              </>
            ) : (
              <FitMap heightsUrl={groundNow.heightsUrl} rows={groundNow.rows} columns={groundNow.columns}
                      acrossM={groundNow.acrossM} extentM={[1, 1]} spots={[]} />
            )}
          </div>

          <div className="compose-steps">
            <Step n={1} title="Where" done={!!where && !!name.trim()}>
              <label className="field"><span>Name</span>
                <input value={name} disabled={!composing} onChange={(e) => setName(e.target.value)} placeholder="e.g. Thuwal north reef" />
              </label>
              <div className="field"><span>How wide</span>
                <div className="segmented">
                  {SIZES.map((m) => (
                    <button key={m} type="button" disabled={!composing || ground === "store"} aria-pressed={m === acrossM} onClick={() => setAcrossM(m)}>{sizeSaid(m)}</button>
                  ))}
                </div>
                {ground === "store" ? <span className="note">The store place&rsquo;s own square: {sizeSaid(acrossM)}.</span> : null}
              </div>
            </Step>

            <Step n={2} title="Ground" done={composing ? undefined : true}>
              <div className="choices">
                <Choice on={ground === "public"} disabled={!composing} onPick={() => setGround("public")}
                        title="Every public source here"
                        says="The global depth grid, satellite depths, the laser altimeter where it passed, the learned depth model and the coral atlas; the best wins cell by cell." />
                <Choice on={ground === "flat"} disabled={!composing} onPick={() => setGround("flat")}
                        title="A flat seabed" says="For a place nobody has measured, or a clean test: flat at one depth, said to be assumed.">
                  {ground === "flat" ? (
                    <div className="choice-more">
                      <label className="field"><span>Depth, metres</span>
                        <input value={flatDepth} disabled={!composing} onChange={(e) => setFlatDepth(e.target.value)} />
                      </label>
                      <label className="check"><input type="checkbox" checked={coral} disabled={!composing}
                                                      onChange={(e) => setCoral(e.target.checked)} /> Grow coral on it</label>
                    </div>
                  ) : null}
                </Choice>
                <Choice on={ground === "store"} disabled={!composing || store.length === 0} onPick={() => setGround("store")}
                        title="A place from the iOcean map store"
                        says={store.length ? "Built from public data, checked and published by iOcean; your files and assets go on it." : "The store has no places yet."}>
                  {ground === "store" ? (
                    <div className="choice-more">
                      <label className="field"><span>Which place</span>
                        <select value={storeBase ?? ""} disabled={!composing} onChange={(e) => setStoreBase(e.target.value || undefined)}>
                          <option value="">choose one</option>
                          {store.map((one) => <option key={one.id} value={one.id}>{one.name}{one.deepestM !== undefined ? ` · to ${one.deepestM.toFixed(0)} m` : ""}</option>)}
                        </select>
                      </label>
                    </div>
                  ) : null}
                </Choice>
              </div>
              {others.some((a) => a.kind === "bathymetry") ? (
                <div className="field"><span>Your surveys, laid over the ground</span>
                  <div className="choices">
                    {others.filter((a) => a.kind === "bathymetry").map((a) => {
                      const on = surveys.includes(a.id);
                      return (
                        <Choice key={a.id} on={on} disabled={!composing} multi
                                onPick={() => setSurveys((was) => on ? was.filter((x) => x !== a.id) : [...was, a.id])}
                                title={a.name} says={`seabed survey · ${String(a.stats?.datum ?? "")}`} />
                      );
                    })}
                  </div>
                </div>
              ) : null}
              <div className="field"><span>Your own data, laid over the ground</span>
                {own.map((one, i) => (
                  <div key={i} className="own-file">
                    <span className="own-name">{one.file.name}</span>
                    <select value={one.use} disabled={!composing}
                            onChange={(e) => setOwn((was) => was.map((o, j) => j === i ? { ...o, use: e.target.value as Use } : o))}>
                      <option value="raster">depth map</option>
                      <option value="points">soundings</option>
                      <option value="ortho">photo mosaic</option>
                    </select>
                    <span className="note">{one.stage === "waiting" ? <a onClick={() => setOwn((was) => was.filter((_, j) => j !== i))}>remove</a> : one.stage}</span>
                  </div>
                ))}
                <input ref={fileInput} type="file" multiple hidden
                       onChange={(e) => {
                         const files = e.target.files;
                         if (files) setOwn((was) => [...was, ...Array.from(files).map((file) => ({ file, use: guessUse(file.name), errorM: "", stage: "waiting", done: 0 }))]);
                         e.target.value = "";
                       }} />
                <Button kind="secondary" disabled={!composing} onClick={() => fileInput.current?.click()}>Add a survey, soundings or a mosaic</Button>
              </div>
            </Step>

            <Step n={3} title="Assets" done={composing ? undefined : true}>
              {reefs.length === 0 && !others.some((a) => a.kind === "structure") ? (
                <p className="note">No assets yet. Reefs rebuilt from dive videos appear here (Places, Assets).</p>
              ) : (
                <div className="choices">
                  {reefs.map((r) => {
                    const on = picked.includes(r.id);
                    const e = extentOf(r);
                    return (
                      <Choice key={r.id} on={on} disabled={!composing} multi
                              onPick={() => setPicked((was) => on ? was.filter((x) => x !== r.id) : [...was, r.id])}
                              title={r.name} says={`reef rebuilt from a dive video · ${e[0].toFixed(0)} by ${e[1].toFixed(0)} m`} />
                    );
                  })}
                  {others.filter((a) => a.kind === "structure").map((a) => {
                    const on = picked.includes(a.id);
                    const spot = stands[a.id] ?? { at: "", heading: "0" };
                    return (
                      <Choice key={a.id} on={on} disabled={!composing} multi
                              onPick={() => setPicked((was) => on ? was.filter((x) => x !== a.id) : [...was, a.id])}
                              title={a.name} says={a.meets === "drapes" ? `${a.type ?? "structure"} · follows its own route on the seabed` : `${a.type ?? "structure"} · stands on the seabed`}>
                        {on && a.meets === "stands" ? (
                          <div className="inline-fields">
                            <label>Where (latitude, longitude)
                              <input value={spot.at} disabled={!composing} placeholder="the middle of the place"
                                     onChange={(e) => setStands((was) => ({ ...was, [a.id]: { ...spot, at: e.target.value } }))} />
                            </label>
                            <label>Heading, degrees
                              <input value={spot.heading} disabled={!composing}
                                     onChange={(e) => setStands((was) => ({ ...was, [a.id]: { ...spot, heading: e.target.value } }))} />
                            </label>
                          </div>
                        ) : null}
                      </Choice>
                    );
                  })}
                </div>
              )}
              <p className="note">A reef is fitted to the ground after it is built and you choose where it goes. A structure goes where you say, or along its own route.</p>
            </Step>

            <Step n={4} title="Build and Resolve" done={stage.at === "done" || undefined}>
              {stage.at === "composing" ? <p className="note">Build makes the ground, then fits each asset in turn.</p> : null}
              {stage.at === "ground" ? (
                <div className="progress">
                  <Status tone={stage.build.state === "failed" ? "bad" : "busy"}>ground: {stage.build.state}</Status>
                  <span className="note">{stage.build.steps?.[stage.build.steps.length - 1]?.say}</span>
                  {stage.build.state === "failed" ? <p className="trouble">{stage.build.failure}</p> : null}
                </div>
              ) : null}
              {stage.at === "assets" ? (
                <div className="progress">
                  <Status tone={stage.mapping.state === "failed" ? "bad" : "busy"}>assets: {stage.mapping.state}</Status>
                  {assetsOf(stage.mapping).map((a) => (
                    <span key={a.ordinal} className="note">
                      {a.name ?? reefs.find((r) => r.id === a.reconstructionId)?.name}: {a.state}{a.failure ? `, ${a.failure}` : ""}
                    </span>
                  ))}
                  <span className="note">{stage.mapping.steps?.[stage.mapping.steps.length - 1]?.say}</span>
                  {stage.mapping.state === "failed" ? <p className="trouble">{stage.mapping.failure}</p> : null}
                </div>
              ) : null}
              {stage.at === "done" ? (
                <p className="note">{published ? "Published: dives can fly there." : "Built, with every asset laid in, as a draft. Publish it so dives can use it."}</p>
              ) : null}
            </Step>
            {trouble ? <p className="trouble">{trouble}</p> : null}
          </div>
        </div>
      )}
    </Page>
  );
}

function Step({ n, title, done, children }: { n: number; title: string; done?: boolean; children: React.ReactNode }): React.JSX.Element {
  return (
    <section className="step">
      <h3><span className={`step-n${done ? " done" : ""}`}>{done ? "✓" : n}</span>{title}</h3>
      <div className="step-body">{children}</div>
    </section>
  );
}

function Choice({ on, disabled, multi, onPick, title, says, children }: {
  on: boolean; disabled?: boolean; multi?: boolean; onPick?: () => void; title: string; says: string; children?: React.ReactNode;
}): React.JSX.Element {
  return (
    <div className={`choice${on ? " on" : ""}${disabled ? " off" : ""}`}>
      <button type="button" className="choice-head" disabled={disabled} aria-pressed={on} onClick={onPick}>
        <span className={`choice-mark${multi ? " multi" : ""}`} aria-hidden>{on ? (multi ? "✓" : "●") : ""}</span>
        <span><strong>{title}</strong><span className="choice-says">{says}</span></span>
      </button>
      {children}
    </div>
  );
}

/** "lat, lon" typed in, when it is two numbers on the Earth. */
function latLonOf(typed: string): LatLon | undefined {
  const found = typed.match(/^\s*(-?\d+(?:\.\d+)?)\s*[, ]\s*(-?\d+(?:\.\d+)?)\s*$/);
  if (!found) return undefined;
  const lat = Number(found[1]), lon = Number(found[2]);
  return Math.abs(lat) <= 90 && Math.abs(lon) <= 180 ? { lat, lon } : undefined;
}
