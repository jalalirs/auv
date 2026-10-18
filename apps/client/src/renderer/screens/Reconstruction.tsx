// One reef rebuilt from a dive video, and putting it on a map.
//
// What it is first: the picture from above with the swim over it, a few of
// the video's frames, how many frames the cameras were found for, how big it
// is and whether that size was measured or assumed, what cover the frames
// show. Then where it goes, which is a choice and two different things:
//
//   a map of its own   a square of flat seabed at a depth somebody chooses,
//                      sand or grown coral round the reef, the reef in the
//                      middle; for a video nobody can say where it was filmed
//   onto a place       the reef's ground fitted to a place's seabed (Resolve),
//                      the candidates shown on the place for somebody to
//                      choose, nudge and accept before it is laid
//
// Either makes a draft version of a place, which is published from here like
// a build.

import { useEffect, useMemo, useState } from "react";
import type { Mapping, Platform, Reconstruction as Rebuilt, ReconstructionObject } from "@coral-city/api";
import type { Held, Packages } from "./Deck.js";
import { stateOf } from "./Reconstructions.js";
import { FitMap, type Spot } from "../parts/FitMap.js";
import { Empty, PageHead, Pill, Row } from "./parts.js";

type Manifest = {
  frames?: number; registered?: number; extentM?: [number, number]; pathLengthM?: number; headingDeg?: number;
  pieces?: { splats: number }[]; scale?: { factor?: number; how?: string; from?: string };
  cover?: { shares?: Record<string, number>; from?: string; kind?: string };
  tape?: { found?: boolean; paintedOut?: boolean; why?: string; how?: string; framesWithTape?: number };
  video?: { durationS?: number; name?: string }; previews?: string[];
};

type Candidate = { at: [number, number]; headingDeg: number; dz: number; startAt?: number[];
                   fit?: { rmsM?: number; placeGroundM?: number } };

const SIZES = [100, 200, 300, 500, 1000];

export function ReconstructionPage({ platform, held, packages, id, onBack, onOpenPlace }: {
  platform: Platform;
  held: Held;
  packages: Packages;
  id: string;
  onBack: () => void;
  onOpenPlace: (id: string) => void;
}): React.JSX.Element {
  const [one, setOne] = useState<Rebuilt | undefined>();
  const [objects, setObjects] = useState<ReconstructionObject[]>([]);
  const [trouble, setTrouble] = useState("");

  useEffect(() => {
    let stale = false;
    const read = () => platform.reconstruction(id).then((r) => { if (!stale) setOne(r); })
      .catch((p) => setTrouble(p instanceof Error ? p.message : "could not read it"));
    void read();
    const again = setInterval(() => void read(), 20_000);
    return () => { stale = true; clearInterval(again); };
  }, [platform, id]);
  useEffect(() => {
    if (one?.state !== "ready") return;
    platform.reconstructionObjects(id).then(setObjects).catch(() => undefined);
  }, [platform, id, one?.state]);

  if (!one) return trouble ? <Empty title="Not found">{trouble}</Empty> : <p className="note">Reading…</p>;
  const m = (one.manifest ?? {}) as Manifest;
  const url = (path: string) => objects.find((o) => o.path === path)?.url;
  const state = stateOf(one);
  const splats = (m.pieces ?? []).reduce((n, p) => n + p.splats, 0);
  const cover = Object.entries(m.cover?.shares ?? {}).filter(([, v]) => v >= 0.01).sort((a, b) => b[1] - a[1]);

  return (
    <>
      <PageHead title={one.name} back="From a dive video" onBack={onBack}
                says={one.brief.video.name ? `Rebuilt from ${one.brief.video.name}.` : undefined}
                aside={<Pill kind={state.kind}>{state.said}</Pill>} />
      {state.doing && one.state !== "failed" ? <p className="note">{state.doing}</p> : null}
      {one.state !== "ready" ? (
        <section>
          <ol className="builder-steps">
            {one.steps.map((s, i) => <li key={i}>{s.say}{s.of ? ` (${s.n} of ${s.of})` : ""}</li>)}
          </ol>
          {one.state === "failed" ? (
            <p className="trouble">{one.failure}{one.said ? <><br /><code>{one.said.slice(-800)}</code></> : null}</p>
          ) : <p className="note">This page reads it again every twenty seconds.</p>}
        </section>
      ) : (
        <>
          <section>
            {url("preview.jpg") ? <img className="recon-preview" src={url("preview.jpg")} alt="the reef from above, the swim over it" /> : null}
            <p className="note">The reef from above, as its splats draw it; the yellow line is the camera's swim, starting at the green dot.</p>
            <div className="recon-frames">
              {(m.previews ?? []).map((p) => url(p) ? <img key={p} src={url(p)} alt="a frame of the video" /> : null)}
            </div>
          </section>
          <div className="two">
            <section>
              <h2>What it is</h2>
              <div className="kvs">
                <Row of="video" is={m.video?.durationS ? `${(m.video.durationS / 60).toFixed(1)} min, ${m.frames} frames taken` : `${m.frames ?? "?"} frames`} />
                <Row of="cameras found" is={`${m.registered ?? "?"} of ${m.frames ?? "?"} frames`} note="COLMAP's global mapper; a frame it could not place is left out" />
                <Row of="size" is={m.extentM ? `${m.extentM[0].toFixed(0)} by ${m.extentM[1].toFixed(0)} m, ${m.pathLengthM ?? "?"} m of swim` : "?"}
                     note={`${m.scale?.how ?? "assumed"}: ${m.scale?.from ?? ""}`} />
                <Row of="splats" is={`${splats.toLocaleString()} in ${m.pieces?.length ?? 0} pieces`} note="each piece drawn when the camera is over its stretch of the swim" />
                <Row of="survey tape" is={m.tape?.paintedOut ? (m.tape.framesWithTape ? `painted out of ${m.tape.framesWithTape} frames` : "painted out") : (m.tape?.why ?? "none found")}
                     note={m.tape?.how} />
              </div>
            </section>
            <section>
              <h2>What the frames show</h2>
              {cover.length === 0 ? <p className="note">No seabed found in the frames.</p> : (
                <div className="kvs">
                  {cover.map(([group, share]) => <Row key={group} of={group.replace(/_/g, " ")} is={`${(share * 100).toFixed(1)}%`} />)}
                </div>
              )}
              <p className="note">{m.cover?.kind ?? "derived"}: {m.cover?.from}</p>
            </section>
          </div>
          <PutOnAMap platform={platform} held={held} packages={packages} rebuilt={one} manifest={m} onOpenPlace={onOpenPlace} />
        </>
      )}
    </>
  );
}

function PutOnAMap({ platform, held, packages, rebuilt, manifest, onOpenPlace }: {
  platform: Platform;
  held: Held;
  packages: Packages;
  rebuilt: Rebuilt;
  manifest: Manifest;
  onOpenPlace: (id: string) => void;
}): React.JSX.Element {
  const [mode, setMode] = useState<"own" | "onto">("own");
  const [mapping, setMapping] = useState<Mapping | undefined>();
  const [busy, setBusy] = useState(false);
  const [trouble, setTrouble] = useState("");
  const [published, setPublished] = useState(false);
  // A map of its own.
  const [name, setName] = useState(`${rebuilt.name} reef`);
  const [acrossM, setAcrossM] = useState(300);
  const [depthM, setDepthM] = useState("8");
  const [pad, setPad] = useState<"sand" | "coral">("sand");
  const [heading, setHeading] = useState("0");
  const [where, setWhere] = useState(rebuilt.brief.start ? `${rebuilt.brief.start.lat}, ${rebuilt.brief.start.lon}` : "");
  // Onto a place.
  const [placeId, setPlaceId] = useState(held.places[0]?.id ?? "");
  const [withinM, setWithinM] = useState("400");
  const [saidDepth, setSaidDepth] = useState("");
  const [chosen, setChosen] = useState(0);
  const [nudge, setNudge] = useState({ dx: 0, dy: 0, turn: 0 });

  useEffect(() => {
    platform.mappingsOf(rebuilt.id).then((found) => { if (found[0]) setMapping(found[0]); }).catch(() => undefined);
  }, [platform, rebuilt.id]);
  useEffect(() => {
    if (!mapping || mapping.state === "ready" || mapping.state === "failed" || mapping.state === "choosing") return;
    const again = setInterval(() => { platform.mapping(mapping.id).then(setMapping).catch(() => undefined); }, 5000);
    return () => clearInterval(again);
  }, [platform, mapping]);

  const at = useMemo(() => {
    const found = where.match(/^\s*(-?\d+(?:\.\d+)?)\s*[, ]\s*(-?\d+(?:\.\d+)?)\s*$/);
    return found ? { lat: Number(found[1]), lon: Number(found[2]) } : undefined;
  }, [where]);

  const start = async (body: Parameters<Platform["startMapping"]>[1]) => {
    setBusy(true);
    setTrouble("");
    try {
      setMapping(await platform.startMapping(rebuilt.id, body));
    } catch (problem) {
      setTrouble(problem instanceof Error ? problem.message : "could not start");
    } finally {
      setBusy(false);
    }
  };

  const candidates = ((mapping?.candidates ?? []) as Candidate[]);
  const pick = candidates[chosen];
  const nudged: Candidate | undefined = pick && {
    ...pick, at: [pick.at[0] + nudge.dx, pick.at[1] + nudge.dy], headingDeg: (pick.headingDeg + nudge.turn + 360) % 360,
    ...(nudge.dx || nudge.dy || nudge.turn ? { startAt: undefined } : {}),
  };
  const moved = nudge.dx !== 0 || nudge.dy !== 0 || nudge.turn !== 0;
  const pkg = mapping?.cityId ? packages.places.get(mapping.cityId) : packages.places.get(placeId);
  const hf = pkg?.site?.mesh?.heightfield;
  const spots: Spot[] = candidates.map((c, i) => (i === chosen && nudged ? nudged : c));

  const accept = async () => {
    if (!mapping || !nudged) return;
    setBusy(true);
    try {
      setMapping(await platform.acceptMapping(mapping.id, moved
        ? { placement: { at: nudged.at, headingDeg: nudged.headingDeg, dz: nudged.dz } }
        : { candidate: chosen }));
    } catch (problem) {
      setTrouble(problem instanceof Error ? problem.message : "could not lay it");
    } finally {
      setBusy(false);
    }
  };

  const publish = async () => {
    if (!mapping?.versionId) return;
    setBusy(true);
    try {
      await platform.publishVersion(mapping.versionId);
      setPublished(true);
    } catch (problem) {
      setTrouble(problem instanceof Error ? problem.message : "could not publish");
    } finally {
      setBusy(false);
    }
  };

  return (
    <section>
      <h2>Put it on a map</h2>
      {!mapping || mapping.state === "failed" ? (
        <>
          {mapping?.state === "failed" ? <p className="trouble">The last try failed: {mapping.failure}</p> : null}
          <div className="builder-sizes">
            <button className={mode === "own" ? "" : "quiet"} onClick={() => setMode("own")}>A map of its own</button>
            <button className={mode === "onto" ? "" : "quiet"} onClick={() => setMode("onto")}>Onto a place</button>
          </div>
          {mode === "own" ? (
            <div className="builder-side">
              <p className="note">A square of flat seabed with the reef in its middle. For a video nobody can place: the ground round it is assumed, and the place says so.</p>
              <label>Name <input value={name} onChange={(e) => setName(e.target.value)} /></label>
              <label>Where the video starts
                <input value={where} onChange={(e) => setWhere(e.target.value)} placeholder="latitude, longitude; a nominal Red Sea spot if empty" />
              </label>
              <label>How wide</label>
              <div className="builder-sizes">
                {SIZES.map((s) => (
                  <button key={s} className={s === acrossM ? "" : "quiet"} onClick={() => setAcrossM(s)}>{s >= 1000 ? `${s / 1000} km` : `${s} m`}</button>
                ))}
              </div>
              <label>Depth of the reef, metres <input value={depthM} onChange={(e) => setDepthM(e.target.value)} /></label>
              <label>Around it</label>
              <div className="builder-sizes">
                <button className={pad === "sand" ? "" : "quiet"} onClick={() => setPad("sand")}>Flat sand</button>
                <button className={pad === "coral" ? "" : "quiet"} onClick={() => setPad("coral")}>Grown coral</button>
              </div>
              <label>Turned, degrees <input value={heading} onChange={(e) => setHeading(e.target.value)} placeholder="0 keeps the reef's long axis east" /></label>
              {manifest.extentM && manifest.extentM[0] > acrossM * 0.9
                ? <p className="trouble">The reef is {manifest.extentM[0].toFixed(0)} m long; choose a wider square.</p> : null}
              {trouble ? <p className="trouble">{trouble}</p> : null}
              <button className="big" disabled={busy || !name.trim() || (where.trim() !== "" && !at) || !Number.isFinite(Number(depthM))}
                      onClick={() => void start({ mode: "own", name: name.trim(), acrossM, depthM: Number(depthM), pad,
                                                  headingDeg: Number(heading) || 0, ...(at ? { start: at } : {}) })}>
                Build the map
              </button>
            </div>
          ) : (
            <div className="builder-side">
              <p className="note">The reef's own ground is fitted to the place's seabed: every spot and heading tried, the ones where the ground agrees best kept, for you to choose from before anything is laid.</p>
              <label>Place
                <select value={placeId} onChange={(e) => setPlaceId(e.target.value)}>
                  {held.places.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                </select>
              </label>
              <label>Search within, metres of where the video starts
                <input value={withinM} onChange={(e) => setWithinM(e.target.value)} />
              </label>
              {!rebuilt.brief.start ? <p className="note">No start was given with the video, so the whole place is searched.</p> : null}
              <label>Depth of the reef, if known <input value={saidDepth} onChange={(e) => setSaidDepth(e.target.value)} placeholder="metres" /></label>
              {trouble ? <p className="trouble">{trouble}</p> : null}
              <button className="big" disabled={busy || !placeId}
                      onClick={() => void start({ mode: "onto", cityId: placeId, withinM: Number(withinM) || 400,
                                                  ...(saidDepth.trim() ? { depthM: Number(saidDepth) } : {}) })}>
                Resolve
              </button>
            </div>
          )}
        </>
      ) : mapping.state === "choosing" ? (
        <div className="builder">
          <div className="builder-map">
            {hf && pkg?.site?.from?.acrossMetres ? (
              <FitMap heightsUrl={pkg.files.find((f) => f.path === hf.file)?.url} rows={hf.rows} columns={hf.columns}
                      acrossM={pkg.site.from.acrossMetres} extentM={manifest.extentM ?? [50, 10]} spots={spots}
                      chosen={chosen} start={mapping.start as [number, number] | null | undefined}
                      onChoose={(i) => { setChosen(i); setNudge({ dx: 0, dy: 0, turn: 0 }); }} />
            ) : <p className="note">Reading the place's seabed…</p>}
          </div>
          <div className="builder-side">
            <h3>Where it fits</h3>
            <div className="rows">
              {candidates.map((c, i) => (
                <button key={i} type="button" className={`row open${i === chosen ? " chosen" : ""}`}
                        onClick={() => { setChosen(i); setNudge({ dx: 0, dy: 0, turn: 0 }); }}>
                  <span className="what">{i + 1}. ({c.at[0].toFixed(0)}, {c.at[1].toFixed(0)}) m, {c.headingDeg} degrees</span>
                  <span className="quiet">{c.fit?.rmsM?.toFixed(2)} m rms · ground {c.fit?.placeGroundM?.toFixed(1)} m</span>
                </button>
              ))}
            </div>
            <p className="note">rms is how far the place's seabed and the reef's own ground still disagree once the reef is raised or lowered to fit.</p>
            <h3>Nudge</h3>
            <div className="builder-sizes">
              <button className="quiet" onClick={() => setNudge((n) => ({ ...n, dy: n.dy + 5 }))}>5 m north</button>
              <button className="quiet" onClick={() => setNudge((n) => ({ ...n, dy: n.dy - 5 }))}>5 m south</button>
              <button className="quiet" onClick={() => setNudge((n) => ({ ...n, dx: n.dx + 5 }))}>5 m east</button>
              <button className="quiet" onClick={() => setNudge((n) => ({ ...n, dx: n.dx - 5 }))}>5 m west</button>
              <button className="quiet" onClick={() => setNudge((n) => ({ ...n, turn: n.turn + 10 }))}>turn 10 left</button>
              <button className="quiet" onClick={() => setNudge((n) => ({ ...n, turn: n.turn - 10 }))}>turn 10 right</button>
            </div>
            {moved ? <p className="note">Moved by hand from candidate {chosen + 1}: its fit no longer applies, and its height is kept.</p> : null}
            {trouble ? <p className="trouble">{trouble}</p> : null}
            <button className="big" disabled={busy || !nudged} onClick={() => void accept()}>Lay it here</button>
          </div>
        </div>
      ) : (
        <>
          <div className="builder-state">
            <Pill kind={mapping.state === "ready" ? "good" : "busy"}>{mapping.state}</Pill>
          </div>
          <ol className="builder-steps">
            {(mapping.steps ?? []).map((s, i) => <li key={i}>{s.say}{s.of ? ` (${s.n} of ${s.of})` : ""}</li>)}
          </ol>
          {mapping.state === "ready" && mapping.cityId ? (
            published ? (
              <button className="big" onClick={() => onOpenPlace(mapping.cityId!)}>Open the place</button>
            ) : (
              <>
                {trouble ? <p className="trouble">{trouble}</p> : null}
                <p className="note">A draft version of the place, with the reef in it. Publish it so dives can fly there.</p>
                <button className="big" disabled={busy} onClick={() => void publish()}>Publish, so dives can use it</button>
              </>
            )
          ) : null}
        </>
      )}
    </section>
  );
}
