// A new place, built from its data.
//
// Choose a reef on the Earth, say what to build it from — the public sources
// the platform fetches, and the institution's own files — and watch it build.
// The place belongs to the institution: nobody else sees it unless it is
// shared. When the build is done the page says how wrong its depth may be and
// which source made how much of it, shows where it is weak, and offers to
// publish it so dives can fly there.
//
// One page, the map on the left and the work on the right, rather than a
// wizard: everything somebody decides is visible at once, and the map stays
// where the place is.

import { useEffect, useMemo, useState } from "react";
import type { Build, BuildBrief, Platform } from "@coral-city/api";
import type { Held } from "./Deck.js";
import { PageHead, Pill } from "./parts.js";
import { WorldMap, type LatLon } from "../parts/WorldMap.js";

type Use = "raster" | "points" | "ortho";
type Own = {
  file: File;
  use: Use;
  errorM: string;
  stage: "waiting" | "hashing" | "sending" | "stored" | "failed";
  done: number;
  objectId?: string;
  trouble?: string;
};

const DEFAULT_SOURCES = ["gebco", "sentinel2", "allen-coral-atlas"];
const SIZES = [250, 500, 1000, 2000, 5000];

function guessUse(name: string): Use {
  const ext = name.toLowerCase().split(".").pop() ?? "";
  if (["xyz", "csv", "txt", "pts"].includes(ext)) return "points";
  return "raster";
}

function slugOf(name: string): string {
  const slug = name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 56);
  return slug.length >= 3 ? slug : `${slug || "place"}-place`;
}

function megabytes(bytes: number): string {
  return bytes >= 1 << 30 ? `${(bytes / (1 << 30)).toFixed(1)} GB` : `${(bytes / (1 << 20)).toFixed(1)} MB`;
}

export function BuildPlace({ platform, held, onBack, onOpen }: {
  platform: Platform;
  held: Held;
  onBack: () => void;
  onOpen: (id: string) => void;
}): React.JSX.Element {
  const [view, setView] = useState({ centre: { lat: 22.3, lon: 38.95 } as LatLon, zoom: 9 });
  const [chosen, setChosen] = useState<LatLon | undefined>();
  const [typed, setTyped] = useState("");
  const [name, setName] = useState("");
  const [acrossM, setAcrossM] = useState(1000);
  const [catalogue, setCatalogue] = useState<{ sources: Record<string, string>; fileUses: Record<string, string> }>();
  const [sources, setSources] = useState<string[]>(DEFAULT_SOURCES);
  const [own, setOwn] = useState<Own[]>([]);
  const [build, setBuild] = useState<Build | undefined>();
  const [place, setPlace] = useState<{ id: string; name: string } | undefined>();
  const [weakUrl, setWeakUrl] = useState<string>();
  const [trouble, setTrouble] = useState("");
  const [busy, setBusy] = useState(false);
  const [published, setPublished] = useState(false);

  useEffect(() => {
    platform.buildSources().then(setCatalogue).catch(() => setTrouble("could not read what a place can be built from"));
  }, [platform]);

  // Watched every few seconds until it is done.
  useEffect(() => {
    if (!build || build.state === "ready" || build.state === "failed") return;
    const again = setInterval(() => {
      platform.build(build.id).then(setBuild).catch(() => undefined);
    }, 3000);
    return () => clearInterval(again);
  }, [platform, build]);

  useEffect(() => {
    if (build?.state !== "ready" || !build.versionId) return;
    platform.files(build.versionId)
      .then((files) => setWeakUrl(files.find((f) => f.path === "weak.png")?.url))
      .catch(() => undefined);
  }, [platform, build?.state, build?.versionId]);

  const institution = held.institution;
  const ready = !!chosen && name.trim().length > 0 && !!institution && !busy && !build;

  const typedAt = useMemo(() => {
    const found = typed.match(/^\s*(-?\d+(?:\.\d+)?)\s*[, ]\s*(-?\d+(?:\.\d+)?)\s*$/);
    if (!found) return undefined;
    const lat = Number(found[1]), lon = Number(found[2]);
    return Math.abs(lat) <= 85 && Math.abs(lon) <= 180 ? { lat, lon } : undefined;
  }, [typed]);

  const addFiles = (files: FileList | null) => {
    if (!files) return;
    setOwn((was) => [...was, ...Array.from(files).map((file) => ({
      file, use: guessUse(file.name), errorM: "", stage: "waiting" as const, done: 0 }))]);
  };

  const start = async () => {
    if (!chosen || !institution) return;
    setBusy(true);
    setTrouble("");
    try {
      // The institution's own files first: a build names what it reads.
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
        files.push({ objectId, use: one.use, name: one.file.name,
                     ...(one.errorM ? { errorM: Number(one.errorM) } : {}) });
      }

      const halfLat = acrossM / 2 / 111_320;
      const halfLon = acrossM / 2 / (111_320 * Math.max(Math.cos(chosen.lat * Math.PI / 180), 1e-6));
      let founded;
      for (let attempt = 0; attempt < 6 && !founded; attempt++) {
        const slug = attempt === 0 ? slugOf(name) : `${slugOf(name)}-${attempt + 1}`;
        try {
          founded = await platform.foundPlace(institution.id, {
            slug, name: name.trim(), verticalDatum: "mean sea level",
            summary: `built from ${[...sources, ...own.map((o) => o.file.name)].join(", ")}`,
            extent: { west: chosen.lon - halfLon, south: chosen.lat - halfLat,
                      east: chosen.lon + halfLon, north: chosen.lat + halfLat },
          });
        } catch (refused) {
          if (!(refused instanceof Error) || !/already exists/.test(refused.message)) throw refused;
        }
      }
      if (!founded) throw new Error("a place with that name exists; choose another");
      setPlace({ id: founded.id, name: founded.name });
      setBuild(await platform.startBuild(founded.id, {
        centre: [chosen.lat, chosen.lon], acrossM, sources: sources as BuildBrief["sources"],
        ...(files.length ? { files } : {}),
      }));
    } catch (problem) {
      setTrouble(problem instanceof Error ? problem.message : "the build could not be started");
      setOwn((was) => was.map((o) => o.stage === "hashing" || o.stage === "sending" ? { ...o, stage: "failed" } : o));
    } finally {
      setBusy(false);
    }
  };

  const publish = async () => {
    if (!build?.versionId) return;
    setBusy(true);
    try {
      await platform.publishVersion(build.versionId);
      setPublished(true);
    } catch (problem) {
      setTrouble(problem instanceof Error ? problem.message : "could not publish");
    } finally {
      setBusy(false);
    }
  };

  const steps = build?.steps ?? [];
  const last = steps[steps.length - 1];
  const result = (build?.result ?? {}) as {
    deepestM?: number; depth?: { sources?: { source: string; kind: string; share: number }[];
      weak?: { errorM?: { median?: number; p90?: number; worst?: number } } };
  };
  const leftOut = steps.filter((s) => s.step === "left-out");

  return (
    <>
      <PageHead title="New place" back="Places" onBack={onBack}
        says="Choose a reef, say what to build it from, and the platform builds its seabed and says where it is weak. The place is your institution's: nobody else sees it unless you share it." />
      <div className="builder">
        <div className="builder-map">
          <WorldMap view={view} onView={setView} chosen={chosen} acrossM={acrossM}
                    onChoose={(at) => { if (!build) setChosen(at); }} />
          <div className="builder-where">
            <input placeholder="latitude, longitude — or click the map" value={typed}
                   onChange={(e) => setTyped(e.target.value)}
                   onKeyDown={(e) => {
                     if (e.key === "Enter" && typedAt && !build) {
                       setChosen(typedAt);
                       setView({ centre: typedAt, zoom: Math.max(view.zoom, 13) });
                     }
                   }} />
            {chosen ? <span className="note">{chosen.lat.toFixed(4)}, {chosen.lon.toFixed(4)} · {acrossM >= 1000 ? `${acrossM / 1000} km` : `${acrossM} m`} square</span>
                    : <span className="note">Zoom in on a reef and click its middle.</span>}
          </div>
        </div>

        <div className="builder-side">
          {!build ? (
            <>
              <label>Name
                <input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Thuwal north reef" />
              </label>
              <label>How wide</label>
              <div className="builder-sizes">
                {SIZES.map((m) => (
                  <button key={m} className={m === acrossM ? "" : "quiet"} onClick={() => setAcrossM(m)}>
                    {m >= 1000 ? `${m / 1000} km` : `${m} m`}
                  </button>
                ))}
              </div>

              <h3>Public data</h3>
              <div className="builder-list">
                {Object.entries(catalogue?.sources ?? {}).map(([key, says]) => (
                  <label key={key} className="builder-check">
                    <input type="checkbox" checked={sources.includes(key)}
                           onChange={(e) => setSources((was) => e.target.checked ? [...was, key] : was.filter((s) => s !== key))} />
                    <span><strong>{key}</strong> {says}</span>
                  </label>
                ))}
              </div>
              <p className="note">GEBCO is laid under everything anyway, so every cell has a depth.</p>

              <h3>Your own data</h3>
              <div className="builder-list">
                {own.map((one, i) => (
                  <div key={i} className="builder-file">
                    <span className="builder-file-name">{one.file.name} · {megabytes(one.file.size)}</span>
                    <select value={one.use} disabled={one.stage !== "waiting"}
                            onChange={(e) => setOwn((was) => was.map((o, j) => j === i ? { ...o, use: e.target.value as Use } : o))}>
                      {Object.entries(catalogue?.fileUses ?? { raster: "", points: "", ortho: "" }).map(([key, says]) => (
                        <option key={key} value={key}>{says || key}</option>
                      ))}
                    </select>
                    {one.use !== "ortho" ? (
                      <input className="builder-error" placeholder="± m" value={one.errorM} disabled={one.stage !== "waiting"}
                             onChange={(e) => setOwn((was) => was.map((o, j) => j === i ? { ...o, errorM: e.target.value } : o))} />
                    ) : null}
                    <span className="note">
                      {one.stage === "waiting" ? <a onClick={() => setOwn((was) => was.filter((_, j) => j !== i))}>remove</a>
                        : one.stage === "stored" ? "stored"
                        : one.stage === "failed" ? "failed"
                        : `${one.stage} ${Math.round(100 * one.done / Math.max(one.file.size, 1))}%`}
                    </span>
                  </div>
                ))}
                <label className="builder-add">
                  <input type="file" multiple onChange={(e) => { addFiles(e.target.files); e.target.value = ""; }} />
                  <span>Add a depth map, soundings or a photo mosaic</span>
                </label>
              </div>
              <p className="note">Big files go up in 32 MB parts and resume if the connection drops. Dive videos, to rebuild a reef in 3D, come next.</p>

              {trouble ? <p className="trouble">{trouble}</p> : null}
              <button className="big" disabled={!ready} onClick={() => void start()}>
                {busy ? "Starting…" : "Build"}
              </button>
              {!institution ? <p className="note">You belong to no institution, and a place is built for one.</p> : null}
            </>
          ) : (
            <>
              <h2>{place?.name}</h2>
              <div className="builder-state">
                <Pill kind={build.state === "ready" ? "good" : build.state === "failed" ? "bad" : "busy"}>
                  {build.state}
                </Pill>
                {last && build.state !== "ready" ? <span className="note">{last.say}{last.of ? ` (${last.n} of ${last.of})` : ""}</span> : null}
              </div>
              <ol className="builder-steps">
                {steps.filter((s) => s.step !== "left-out").map((s, i) => (
                  <li key={i}>{s.say}{s.of ? ` (${s.n} of ${s.of})` : ""}</li>
                ))}
              </ol>
              {leftOut.map((s, i) => <p key={i} className="note">Left out: {s.say}</p>)}
              {build.state === "failed" ? (
                <p className="trouble">{build.failure}{build.said ? <><br /><code>{build.said.slice(-600)}</code></> : null}</p>
              ) : null}
              {build.state === "ready" ? (
                <>
                  <h3>Where it is weak</h3>
                  {weakUrl ? <img className="builder-weak" src={weakUrl} alt="how wrong the depth may be, cell by cell" /> : null}
                  <p className="note">Each cell coloured by how wrong its depth may be: under half a metre, to a metre, two, five, more.</p>
                  <div className="builder-facts">
                    <span>median error <strong>{result.depth?.weak?.errorM?.median ?? "?"} m</strong></span>
                    <span>90% within <strong>{result.depth?.weak?.errorM?.p90 ?? "?"} m</strong></span>
                    <span>deepest <strong>{result.deepestM ?? "?"} m</strong></span>
                  </div>
                  <h3>What made it</h3>
                  <ul className="builder-made">
                    {(result.depth?.sources ?? []).map((s) => (
                      <li key={s.source}>{s.source} · {s.kind} · {Math.round(s.share * 100)}%</li>
                    ))}
                  </ul>
                  {trouble ? <p className="trouble">{trouble}</p> : null}
                  {published ? (
                    <button className="big" onClick={() => place && onOpen(place.id)}>Open the place</button>
                  ) : (
                    <button className="big" disabled={busy} onClick={() => void publish()}>Publish, so dives can use it</button>
                  )}
                </>
              ) : null}
            </>
          )}
        </div>
      </div>
    </>
  );
}
