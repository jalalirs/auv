// A new place, started from a terrain.
//
// Every place begins with its ground, and there are four ways to have one: a
// copy of a place from the iOcean Store, your own seabed survey, every public
// source that reaches the spot, or one designed here (flat, at one depth).
// A copy is ready at once; the other three are built on the platform's
// machines. Either way the place then opens in the designer, which is where
// equipment and objects go on it.

import { useEffect, useMemo, useRef, useState } from "react";
import type { Asset, Build, BuildBrief, Platform, StorePlace } from "@coral-city/api";

import type { Held } from "./Deck.js";
import { WorldMap, type LatLon } from "../parts/WorldMap.js";
import { ObjectArt, type ObjectKind } from "../parts/ObjectArt.js";
import { Button, Page, Status } from "../ui/components.js";

type Use = "raster" | "points" | "ortho";
type Own = { file: File; use: Use; errorM: string; stage: string; done: number; objectId?: string };
/** Where the ground comes from. */
type Terrain = "store" | "survey" | "public" | "flat";

const TERRAINS: { key: Terrain; art: ObjectKind; label: string; says: string }[] = [
  { key: "store", art: "store", label: "From the Store", says: "A place iOcean built and checked, copied into yours" },
  { key: "survey", art: "survey", label: "Your survey", says: "A depth map or soundings of your own, over public data" },
  { key: "public", art: "earth", label: "Public data", says: "Every public depth source that reaches the spot" },
  { key: "flat", art: "flat", label: "Design one", says: "A flat seabed at one depth, for a clean test" },
];

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

type Stage =
  | { at: "composing" }
  | { at: "ground"; build: Build }
  | { at: "publishing" };

export function Compose({ platform, held, base, chosen, onBack, onOpen, onDesign }: {
  platform: Platform;
  held: Held;
  /** A Store place to start from, from its card. */
  base?: string;
  /** An object somebody came from: a survey starts the place on it. */
  chosen?: string;
  onBack: () => void;
  onOpen: (id: string) => void;
  /** The place, once its ground is ready, in the designer. */
  onDesign: (id: string) => void;
}): React.JSX.Element {
  const institution = held.institution;
  const [terrain, setTerrain] = useState<Terrain | undefined>(base ? "store" : undefined);
  const [view, setView] = useState({ centre: { lat: 22.3, lon: 38.95 } as LatLon, zoom: 9 });
  const [where, setWhere] = useState<LatLon | undefined>();
  const [typed, setTyped] = useState("");
  const [name, setName] = useState("");
  const [acrossM, setAcrossM] = useState(1000);
  const [store, setStore] = useState<StorePlace[]>([]);
  const [storeBase, setStoreBase] = useState<string | undefined>(base);
  const [nearby, setNearby] = useState<StorePlace[]>([]);
  const [flatDepth, setFlatDepth] = useState("8");
  const [coral, setCoral] = useState(true);
  const [own, setOwn] = useState<Own[]>([]);
  const [surveyAssets, setSurveyAssets] = useState<Asset[]>([]);
  const [surveys, setSurveys] = useState<string[]>([]);
  const [catalogue, setCatalogue] = useState<string[]>([]);
  const [place, setPlace] = useState<{ id: string; name: string } | undefined>();
  const [stage, setStage] = useState<Stage>({ at: "composing" });
  const [trouble, setTrouble] = useState("");
  const [busy, setBusy] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    platform.buildSources().then((c) => setCatalogue(Object.keys(c.sources))).catch(() => undefined);
    if (institution) {
      platform.listAssets(institution.id, "bathymetry").then((all) => setSurveyAssets(all.filter((a) => a.state === "ready"))).catch(() => undefined);
    }
  }, [platform, institution]);
  useEffect(() => { platform.storePlaces().then(setStore).catch(() => undefined); }, [platform]);

  // Put the place over a survey: the one somebody came from, or the first chosen.
  const overSurvey = (one: Asset) => {
    const box = (one.footprint as { bbox?: number[] } | undefined)?.bbox;
    if (box && box.length === 4) {
      const centre = { lat: (box[0]! + box[2]!) / 2, lon: (box[1]! + box[3]!) / 2 };
      setWhere(centre);
      setView({ centre, zoom: 14 });
    }
  };
  const took = useRef(false);
  useEffect(() => {
    if (!chosen || took.current) return;
    const survey = surveyAssets.find((a) => a.id === chosen);
    if (!survey) return;
    took.current = true;
    setTerrain("survey");
    setSurveys([chosen]);
    overSurvey(survey);
    if (!name) setName(survey.name.replace(/\s*\([^()]*\)\s*$/, ""));
  }, [chosen, surveyAssets]); // eslint-disable-line react-hooks/exhaustive-deps

  const storeOne = store.find((one) => one.id === storeBase);
  useEffect(() => {
    if (!storeOne?.extent || terrain !== "store") return;
    const e = storeOne.extent;
    const at = { lat: (e.north + e.south) / 2, lon: (e.east + e.west) / 2 };
    setWhere(at);
    setView({ centre: at, zoom: 12 });
  }, [storeOne, terrain]);
  // An area already in the Store says so: nobody rebuilds it.
  useEffect(() => {
    if (!where || terrain === "store" || !terrain) { setNearby([]); return; }
    let stale = false;
    platform.storePlaces({ lat: where.lat, lon: where.lon, acrossM }).then((found) => { if (!stale) setNearby(found); }).catch(() => undefined);
    return () => { stale = true; };
  }, [platform, where, acrossM, terrain]);

  const typedAt = useMemo(() => {
    const found = typed.match(/^\s*(-?\d+(?:\.\d+)?)\s*[, ]\s*(-?\d+(?:\.\d+)?)\s*$/);
    if (!found) return undefined;
    const lat = Number(found[1]), lon = Number(found[2]);
    return Math.abs(lat) <= 85 && Math.abs(lon) <= 180 ? { lat, lon } : undefined;
  }, [typed]);

  // The ground's build, watched until it has made a version; then published
  // (the place is the organisation's own, so publishing is what lets a dive
  // fly it) and opened in the designer.
  useEffect(() => {
    if (stage.at !== "ground" || stage.build.state === "failed") return;
    if (stage.build.state === "ready" && stage.build.versionId && place) {
      setStage({ at: "publishing" });
      platform.publishVersion(stage.build.versionId)
        .then(() => onDesign(place.id))
        .catch((p) => { setTrouble(p instanceof Error ? p.message : "built, but it would not publish"); setStage({ at: "composing" }); });
      return;
    }
    const again = setInterval(() => {
      platform.build(stage.build.id).then((b) => setStage({ at: "ground", build: b })).catch(() => undefined);
    }, 4000);
    return () => clearInterval(again);
  }, [platform, stage]); // eslint-disable-line react-hooks/exhaustive-deps

  const copy = async () => {
    if (!institution || !storeBase) return;
    setBusy(true); setTrouble("");
    try {
      const made = await platform.copyStorePlace(institution.id, storeBase);
      onDesign(made.id);
    } catch (problem) {
      setTrouble(problem instanceof Error ? problem.message : "it could not be copied");
    } finally {
      setBusy(false);
    }
  };

  const build = async () => {
    if (!where || !institution || !terrain || terrain === "store") return;
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
            summary: terrain === "flat" ? `designed: a flat seabed at ${flatDepth} m`
              : terrain === "survey" ? "built on its own survey, over public data" : "built from public data",
            extent: { west: where.lon - halfLon, south: where.lat - halfLat, east: where.lon + halfLon, north: where.lat + halfLat },
          });
        } catch (refused) {
          if (!(refused instanceof Error) || !/already exists/.test(refused.message)) throw refused;
        }
      }
      if (!founded) throw new Error("a place with that name exists; choose another");
      setPlace({ id: founded.id, name: founded.name });
      const survey = surveys.length ? { survey: surveys } : {};
      const brief: BuildBrief = terrain === "flat"
        ? { centre: [where.lat, where.lon], acrossM, sources: [], flatDepthM: Number(flatDepth), coral, ...(files.length ? { files } : {}) }
        : { centre: [where.lat, where.lon], acrossM, sources: catalogue as BuildBrief["sources"], ...(files.length ? { files } : {}), ...survey };
      setStage({ at: "ground", build: await platform.startBuild(founded.id, brief) });
    } catch (problem) {
      setTrouble(problem instanceof Error ? problem.message : "the place could not be started");
    } finally {
      setBusy(false);
    }
  };

  const composing = stage.at === "composing";
  const ready = composing && !!institution && !busy && (terrain === "store" ? !!storeBase
    : !!where && name.trim().length > 0
      && (terrain !== "flat" || (Number(flatDepth) >= 0.5 && Number(flatDepth) <= 60))
      && (terrain !== "survey" || surveys.length > 0 || own.length > 0));

  if (terrain === undefined) {
    return (
      <Page title="New place" crumb="Places" onCrumb={onBack}
            subtitle="Start from a terrain; then put equipment and objects on it in the designer.">
        <div className="object-kinds terrains">
          {TERRAINS.map((t) => (
            <button key={t.key} type="button" className="object-kind" disabled={t.key === "store" && store.length === 0}
                    onClick={() => setTerrain(t.key)}>
              <ObjectArt kind={t.art} size={48} />
              <strong>{t.label}</strong>
              <span>{t.key === "store" && store.length === 0 ? "The Store has no places yet" : t.says}</span>
            </button>
          ))}
        </div>
      </Page>
    );
  }

  const chosenTerrain = TERRAINS.find((t) => t.key === terrain)!;
  const action = terrain === "store" ? (
    <Button kind="primary" disabled={!ready} onClick={() => void copy()}>{busy ? "Copying…" : "Copy and design"}</Button>
  ) : composing ? (
    <Button kind="primary" disabled={!ready} onClick={() => void build()}>{busy ? "Starting…" : "Build and design"}</Button>
  ) : place ? (
    <Button onClick={() => onOpen(place.id)}>Open the place</Button>
  ) : undefined;

  return (
    <Page title={place?.name ?? "New place"} crumb="Places" onCrumb={onBack} wide actions={action}
          subtitle={`${chosenTerrain.label}. ${chosenTerrain.says}.`}
          info="The ground is made first. A copy from the Store is ready at once; a built one takes a few minutes on the platform's machines. Then the place opens in the designer.">
      <div className="compose">
        <div className="compose-map">
          <WorldMap view={view} onView={setView} chosen={where} acrossM={terrain === "store" ? 0 : acrossM}
                    onChoose={(at) => { if (composing && terrain !== "store") setWhere(at); }} />
          {terrain !== "store" ? (
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
          ) : null}
          {nearby.length > 0 && composing ? (
            <div className="overlap">
              <span>This area is in the Store: <strong>{nearby[0]!.name}</strong>{nearby.length > 1 ? ` and ${nearby.length - 1} more` : ""}.</span>
              <Button onClick={() => { setTerrain("store"); setStoreBase(nearby[0]!.id); }}>Copy it instead</Button>
            </div>
          ) : null}
        </div>

        <div className="compose-steps">
          <p className="note"><a onClick={() => { if (composing && !busy) setTerrain(undefined); }}>Start from another terrain</a></p>
          {terrain === "store" ? (
            <Step n={1} title="Which place" done={!!storeBase}>
              <div className="choices">
                {store.map((one) => (
                  <Choice key={one.id} on={storeBase === one.id} disabled={busy} onPick={() => setStoreBase(one.id)}
                          title={one.name} says={[one.summary, one.deepestM !== undefined ? `to ${one.deepestM.toFixed(0)} m` : ""].filter(Boolean).join(" · ")} />
                ))}
              </div>
              <p className="note">The copy is yours: change it as you like, the Store&rsquo;s own stays as it is.</p>
            </Step>
          ) : (<>
            <Step n={1} title="Where" done={!!where && !!name.trim()}>
              <label className="field"><span>Name</span>
                <input value={name} disabled={!composing} onChange={(e) => setName(e.target.value)} placeholder="e.g. Thuwal north reef" />
              </label>
              <div className="field"><span>How wide</span>
                <div className="segmented">
                  {SIZES.map((m) => (
                    <button key={m} type="button" disabled={!composing} aria-pressed={m === acrossM} onClick={() => setAcrossM(m)}>{sizeSaid(m)}</button>
                  ))}
                </div>
              </div>
            </Step>

            <Step n={2} title={terrain === "flat" ? "The seabed" : terrain === "survey" ? "Your survey" : "The sources"} done={composing ? undefined : true}>
              {terrain === "flat" ? (
                <div className="inline-fields">
                  <label className="field"><span>Depth, metres</span>
                    <input value={flatDepth} disabled={!composing} onChange={(e) => setFlatDepth(e.target.value)} />
                  </label>
                  <label className="check"><input type="checkbox" checked={coral} disabled={!composing}
                                                  onChange={(e) => setCoral(e.target.checked)} /> Grow coral on it</label>
                </div>
              ) : null}
              {terrain === "public" ? (
                <p className="note">The global depth grid, satellite depths, the laser altimeter where it passed, the learned depth model and the coral atlas; the best wins cell by cell.</p>
              ) : null}
              {terrain === "survey" ? (<>
                {surveyAssets.length > 0 ? (
                  <div className="choices">
                    {surveyAssets.map((a) => {
                      const on = surveys.includes(a.id);
                      return (
                        <Choice key={a.id} on={on} disabled={!composing} multi
                                onPick={() => { setSurveys((was) => on ? was.filter((x) => x !== a.id) : [...was, a.id]); if (!on && !where) overSurvey(a); }}
                                title={a.name} says={`seabed survey · ${String(a.stats?.datum ?? "")}`} />
                      );
                    })}
                  </div>
                ) : <p className="note">No surveys under Objects yet; add the files here instead.</p>}
                <div className="field"><span>Files</span>
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
                  <Button kind="secondary" disabled={!composing} onClick={() => fileInput.current?.click()}>Add a depth map, soundings or a mosaic</Button>
                </div>
                <p className="note">Public data fills in wherever the survey does not reach.</p>
              </>) : null}
            </Step>

            <Step n={3} title="Build" done={stage.at === "publishing" || undefined}>
              {stage.at === "composing" ? <p className="note">Build makes the ground, then opens the place in the designer.</p> : null}
              {stage.at === "ground" ? (
                <div className="progress">
                  <Status tone={stage.build.state === "failed" ? "bad" : "busy"}>ground: {stage.build.state}</Status>
                  <span className="note">{stage.build.steps?.[stage.build.steps.length - 1]?.say}</span>
                  {stage.build.state === "failed" ? <p className="trouble">{stage.build.failure}</p> : null}
                </div>
              ) : null}
              {stage.at === "publishing" ? <Status tone="busy">publishing, then the designer</Status> : null}
            </Step>
          </>)}
          {trouble ? <p className="trouble">{trouble}</p> : null}
        </div>
      </div>
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
