// A dive, played back.
//
// Nothing is executed. The recording a run left — poses at five hertz, the
// frames it saw at one, what its sensors said, how its task was going — is
// fetched and scrubbed through: the frame nearest the moment on the left, the
// chart with the track up to that moment on the right, the traces underneath
// with the moment marked on them, and the numbers. What a survey produced,
// looked at — at whatever pace suits, since a recording has no clock of its own.

import { useEffect, useMemo, useRef, useState } from "react";

import type { Artefact, Platform } from "@coral-city/api";

import { Minimap, type Fix, type Geometry, type Site } from "../parts/Minimap.js";
import { Empty, PageHead } from "./parts.js";

interface Pose {
  t: number;
  position: number[];
  headingDeg: number;
  depthM: number;
  altitudeM?: number | null;
  velocity?: number[];
  view?: string;
  frame?: string | null;
}

interface TaskLine {
  t: number;
  kind?: string;
  name?: string;
  score?: number;
  done?: boolean;
  says?: string;
  detail?: Record<string, unknown>;
}

interface Manifest {
  poses: number;
  frames: number;
  seconds: number;
  beganAt?: number[];
  camera?: Record<string, unknown> | null;
  task?: { name?: string; score?: number; done?: boolean; achieved?: Record<string, unknown> } | null;
  site?: Site | null;
  geometry?: Geometry | null;
}

/** One trace under the scrubber: a series over the dive, its name, its unit. */
interface Series { name: string; unit: string; t: number[]; v: number[]; ink: string }

const PACES = [1, 2, 5, 10, 30];

export function Replay({ platform, dive, run, onBack }: {
  platform: Platform;
  dive: string;
  run: string;
  onBack: () => void;
}): React.JSX.Element {
  const [files, setFiles] = useState<Artefact[] | undefined>();
  const [poses, setPoses] = useState<Pose[]>([]);
  const [effort, setEffort] = useState<{ t: number; v: number }[]>([]);
  const [task, setTask] = useState<TaskLine[]>([]);
  const [manifest, setManifest] = useState<Manifest | undefined>();
  const [at, setAt] = useState(0);
  // The frames, downloaded and held in memory rather than fetched as the
  // scrubber moves. Each one was a request to storage over whatever link this
  // machine has, and at five times speed the next was asked for long before
  // the last arrived — so the picture never changed at all. A recording is a
  // few tens of megabytes and downloading it is what a recording is for.
  const [pictures, setPictures] = useState<Map<string, string>>(new Map());
  const [fetched, setFetched] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [pace, setPace] = useState(5);
  const [trouble, setTrouble] = useState<string | undefined>();
  // Simulated seconds into the dive: the clock the playback keeps.
  const clock = useRef(0);

  useEffect(() => {
    let gone = false;
    (async () => {
      try {
        const listed = await platform.artefacts(dive, run);
        if (gone) return;
        setFiles(listed);
        const named = (path: string) => listed.find((f) => f.path === path)?.url;
        const lines = async <T,>(url: string | undefined): Promise<T[]> => {
          if (!url) return [];
          const text = await (await fetch(url)).text();
          return text.split("\n").filter((l) => l.trim() !== "").map((l) => JSON.parse(l) as T);
        };
        const [read, sensors, progress, said] = await Promise.all([
          lines<Pose>(named("poses.jsonl")),
          lines<Record<string, unknown> & { t: number }>(named("sensors.jsonl")),
          lines<TaskLine>(named("task.jsonl")),
          named("manifest.json") ? (await fetch(named("manifest.json")!)).json() as Promise<Manifest> : Promise.resolve(undefined),
        ]);
        if (gone) return;
        setPoses(read);
        setTask(progress);
        setManifest(said);
        // The thrusters' mean absolute command: how hard the vehicle worked.
        setEffort(sensors.map((s) => {
          const cmd = s["/thruster_cmd"] as Record<string, number> | undefined;
          const values = cmd ? Object.values(cmd) : [];
          return { t: s.t, v: values.length === 0 ? 0 : values.reduce((a, b) => a + Math.abs(b), 0) / values.length };
        }));
      } catch (problem) {
        if (!gone) setTrouble(problem instanceof Error ? problem.message : "the recording could not be read");
      }
    })();
    return () => { gone = true; };
  }, [platform, dive, run]);

  // Playback keeps simulated time, so the pace is a fact about the dive rather
  // than about how many poses it happened to record a second.
  useEffect(() => {
    if (!playing || poses.length < 2) return;
    const end = poses[poses.length - 1]!.t;
    let last = performance.now();
    let handle = 0;
    const tick = (now: number) => {
      clock.current = Math.min(end, clock.current + ((now - last) / 1000) * pace);
      last = now;
      setAt(indexAt(poses, clock.current));
      if (clock.current >= end) { setPlaying(false); return; }
      handle = requestAnimationFrame(tick);
    };
    handle = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(handle);
  }, [playing, pace, poses]);

  function seek(seconds: number): void {
    clock.current = Math.max(0, Math.min(poses[poses.length - 1]?.t ?? 0, seconds));
    setAt(indexAt(poses, clock.current));
  }
  function play(): void {
    if (!playing && poses.length > 1 && clock.current >= poses[poses.length - 1]!.t) seek(0);
    setPlaying((p) => !p);
  }

  const frames = useMemo(
    () => new Map((files ?? []).filter((f) => f.path.startsWith("frames/")).map((f) => [f.path, f.url ?? ""])),
    [files]);

  // Downloaded once, a dozen at a time, as soon as the recording is known.
  useEffect(() => {
    if (frames.size === 0) return;
    let gone = false;
    const held = new Map<string, string>();
    void (async () => {
      const paths = [...frames.keys()].sort();
      for (let from = 0; from < paths.length && !gone; from += 12) {
        await Promise.all(paths.slice(from, from + 12).map(async (path) => {
          try {
            const blob = await (await fetch(frames.get(path)!)).blob();
            if (!gone) held.set(path, URL.createObjectURL(blob));
          } catch {
            // A frame that will not come is one the replay does without.
          }
        }));
        if (gone) break;
        setPictures(new Map(held));
        setFetched(held.size);
      }
    })();
    return () => {
      gone = true;
      for (const url of held.values()) URL.revokeObjectURL(url);
    };
  }, [frames]);
  const pose = poses[at];
  const now = pose?.t ?? 0;

  // The chart. A recording made before the manifest carried the site has no
  // bottom to draw; it is charted about where it began, at the scale it covered.
  const site = manifest?.site ?? undefined;
  const origin = useMemo<[number, number]>(() => {
    if (site) return [0, 0];
    const began = manifest?.beganAt;
    return began && began.length >= 2 ? [began[0]!, began[1]!] : [poses[0]?.position[0] ?? 0, poses[0]?.position[1] ?? 0];
  }, [site, manifest, poses]);
  const shift = (x: number, y: number): Fix => ({ x: x - origin[0], y: y - origin[1] });
  const fitted = useMemo<Site | undefined>(() => {
    if (site) return site;
    let reach = 5;
    for (const p of poses) reach = Math.max(reach, Math.abs(p.position[0]! - origin[0]), Math.abs(p.position[1]! - origin[1]));
    return { acrossM: reach * 2.4, rows: 0, columns: 0, heights: [], deepestM: 0, shallowestM: 0 };
  }, [site, poses, origin]);
  const track: Fix[] = useMemo(() => poses.slice(0, at + 1).map((p) => shift(p.position[0]!, p.position[1]!)), [poses, at, origin]);
  const progress = useMemo(() => lastBefore(task, now), [task, now]);
  const geometry = useMemo<Geometry | undefined>(() => {
    const g = manifest?.geometry;
    if (!g) return undefined;
    const moved: Geometry = {};
    if (g.circle) moved.circle = { ...g.circle, ...shift(g.circle.x, g.circle.y) };
    if (g.points) moved.points = g.points.map((p) => ({ ...p, ...shift(p.x, p.y) }));
    if (g.line) moved.line = g.line.map((p) => shift(p.x, p.y));
    if (g.rectangle) moved.rectangle = g.rectangle.map((p) => shift(p.x, p.y));
    moved.reached = typeof progress?.detail?.["reached"] === "number" ? (progress.detail["reached"] as number) : g.reached;
    return moved;
  }, [manifest, origin, progress]);
  const position = pose ? [pose.position[0]! - origin[0], pose.position[1]! - origin[1]] : undefined;
  const beganAt = manifest?.beganAt ? [manifest.beganAt[0]! - origin[0], manifest.beganAt[1]! - origin[1]] : undefined;

  // The frame nearest this moment: the pose says which was taken last.
  const frameUrl = useMemo(() => {
    for (let i = at; i >= 0; i -= 1) {
      const name = poses[i]?.frame;
      if (name) return pictures.get(name) ?? frames.get(name);
    }
    return undefined;
  }, [poses, at, frames, pictures]);

  const traces = useMemo<Series[]>(() => {
    const t = poses.map((p) => p.t);
    const out: Series[] = [
      { name: "depth", unit: "m", t, v: poses.map((p) => p.depthM), ink: "#40c7f4" },
    ];
    if (poses.some((p) => p.altitudeM != null)) {
      out.push({ name: "altitude", unit: "m", t, v: poses.map((p) => p.altitudeM ?? NaN), ink: "#9be564" });
    }
    out.push({ name: "speed", unit: "m/s", t, v: poses.map((p) => p.velocity ? Math.hypot(p.velocity[0]!, p.velocity[1]!, p.velocity[2]!) : NaN), ink: "#f4c542" });
    if (task.length > 1) {
      out.push({ name: "score", unit: "%", t: task.map((l) => l.t), v: task.map((l) => (l.score ?? 0) * 100), ink: "#ff7a5c" });
    } else if (effort.length > 1) {
      out.push({ name: "effort", unit: "", t: effort.map((e) => e.t), v: effort.map((e) => e.v), ink: "#c58cff" });
    }
    return out;
  }, [poses, task, effort]);

  if (trouble !== undefined) {
    return (<><PageHead title="Replay" says={trouble} /><button className="quiet" onClick={onBack}>Back</button></>);
  }
  if (files === undefined) {
    return <PageHead title="Replay" says="Fetching the recording…" />;
  }
  if (files.length === 0) {
    return (
      <>
        <PageHead title="Replay" says="This run left no recording." />
        <Empty title="Nothing to play back">
          A dive records when it is for something. A piloted dive with no task leaves only what it said.
        </Empty>
        <button className="quiet" onClick={onBack}>Back</button>
      </>
    );
  }

  const end = poses[poses.length - 1]?.t ?? 0;
  return (
    <>
      <PageHead title="Replay" back="Dives" onBack={onBack}
                says={`${poses.length} poses, ${frames.size} frames, ${manifest?.seconds?.toFixed(0) ?? "?"} s`
                  + (manifest?.task?.name ? ` · ${manifest.task.name} ${((manifest.task.score ?? 0) * 100).toFixed(0)}%` : "")} />
      <div className="replay">
        <div className="frame">
          {frameUrl ? <img src={frameUrl} alt="what the vehicle saw" /> : <div className="none">no frame yet</div>}
          {frames.size > 0 && fetched < frames.size ? (
            <div className="fetching">
              <span style={{ width: `${(fetched / frames.size) * 100}%` }} />
              <em>downloading the dive — {fetched} of {frames.size} frames</em>
            </div>
          ) : null}
        </div>
        <div className="chart">
          <Minimap site={fitted} track={track} position={position} headingDeg={pose?.headingDeg}
                   beganAt={beganAt} geometry={geometry} large />
        </div>
      </div>
      <div className="scrub">
        <button className="quiet" onClick={play}>{playing ? "Pause" : "Play"}</button>
        <span className="speed">
          {PACES.map((p) => (
            <button key={p} className={p === pace ? "chosen" : undefined} onClick={() => setPace(p)}>{p}×</button>
          ))}
        </span>
        <input type="range" min={0} max={Math.max(0, poses.length - 1)} value={at}
               onChange={(e) => { setPlaying(false); seek(poses[Number(e.target.value)]?.t ?? 0); }} />
        <span className="moment">
          {pose ? `${pose.t.toFixed(1)} / ${end.toFixed(0)} s · ${pose.depthM.toFixed(2)} m down · ${((pose.headingDeg % 360) + 360) % 360 | 0}°`
            + (pose.altitudeM != null ? ` · ${pose.altitudeM.toFixed(2)} m up` : "") : "—"}
        </span>
      </div>
      <div className="replay-task">
        {progress ? (
          <>
            <b>{progress.name ?? progress.kind}</b> · {progress.says || (progress.done ? "done" : "under way")} · <b>{((progress.score ?? 0) * 100).toFixed(0)}%</b>
            {detailWords(progress.detail)}
          </>
        ) : manifest?.task?.name ? `${manifest.task.name} · not yet begun` : "no task on this dive"}
      </div>
      <div className="traces">
        {traces.map((series) => (
          <Trace key={series.name} series={series} now={now} end={end}
                 onSeek={(seconds) => { setPlaying(false); seek(seconds); }} />
        ))}
      </div>
      <details className="files">
        <summary>{files.length} files</summary>
        <ul>
          {files.filter((f) => !f.path.startsWith("frames/")).map((f) => (
            <li key={f.path}><a href={f.url} target="_blank" rel="noreferrer">{f.path}</a> <em>{(f.sizeBytes / 1024).toFixed(1)} KB</em></li>
          ))}
          <li><em>{frames.size} frames under frames/</em></li>
        </ul>
      </details>
      <button className="quiet" onClick={onBack}>Back to dives</button>
    </>
  );
}

/** The index of the last pose at or before this moment. */
function indexAt(poses: Pose[], seconds: number): number {
  let low = 0;
  let high = poses.length - 1;
  while (low < high) {
    const mid = (low + high + 1) >> 1;
    if (poses[mid]!.t <= seconds) low = mid; else high = mid - 1;
  }
  return low;
}

function lastBefore(lines: TaskLine[], seconds: number): TaskLine | undefined {
  let found: TaskLine | undefined;
  for (const line of lines) {
    if (line.t > seconds) break;
    found = line;
  }
  return found;
}

/** A task's detail as words: the numbers a person would want beside the score. */
function detailWords(detail: Record<string, unknown> | undefined): string {
  if (!detail) return "";
  const parts: string[] = [];
  for (const [key, value] of Object.entries(detail)) {
    if (typeof value === "number") {
      const name = key.replace(/([A-Z])/g, " $1").toLowerCase().replace(/ m$/, " m");
      parts.push(`${name} ${Number.isInteger(value) ? value : value.toFixed(2)}`);
    } else if (typeof value === "boolean") {
      parts.push(`${key.replace(/([A-Z])/g, " $1").toLowerCase()}${value ? "" : ": no"}`);
    }
  }
  return parts.length === 0 ? "" : ` · ${parts.slice(0, 4).join(" · ")}`;
}

/** One series over the whole dive, with the moment marked on it. */
function Trace({ series, now, end, onSeek }: {
  series: Series;
  now: number;
  end: number;
  onSeek: (seconds: number) => void;
}): React.JSX.Element {
  const canvas = useRef<HTMLCanvasElement>(null);
  const value = useMemo(() => {
    let v = NaN;
    for (let i = 0; i < series.t.length; i += 1) {
      if (series.t[i]! > now) break;
      v = series.v[i]!;
    }
    return v;
  }, [series, now]);

  useEffect(() => {
    const surface = canvas.current;
    if (surface === null) return;
    const width = Math.max(1, Math.floor(surface.clientWidth * devicePixelRatio));
    const height = Math.max(1, Math.floor(surface.clientHeight * devicePixelRatio));
    if (surface.width !== width) surface.width = width;
    if (surface.height !== height) surface.height = height;
    const ink = surface.getContext("2d");
    if (ink === null) return;
    ink.fillStyle = "#050a12";
    ink.fillRect(0, 0, width, height);
    if (series.t.length < 2 || end <= 0) return;

    let low = Infinity;
    let high = -Infinity;
    for (const v of series.v) {
      if (!Number.isFinite(v)) continue;
      if (v < low) low = v;
      if (v > high) high = v;
    }
    if (!Number.isFinite(low)) return;
    if (high - low < 1e-6) { low -= 0.5; high += 0.5; }
    const pad = (high - low) * 0.1;
    low -= pad; high += pad;
    const headroom = 20 * devicePixelRatio;   // the label sits above the line
    const x = (t: number) => (t / end) * width;
    const y = (v: number) => headroom + (1 - (v - low) / (high - low)) * (height - headroom - 4 * devicePixelRatio);

    ink.strokeStyle = "#13233a";
    ink.lineWidth = devicePixelRatio;
    for (const share of [0.5]) {
      ink.beginPath(); ink.moveTo(0, headroom + (height - headroom) * share); ink.lineTo(width, headroom + (height - headroom) * share); ink.stroke();
    }

    ink.beginPath();
    let started = false;
    for (let i = 0; i < series.t.length; i += 1) {
      const v = series.v[i]!;
      if (!Number.isFinite(v)) { started = false; continue; }
      if (!started) { ink.moveTo(x(series.t[i]!), y(v)); started = true; } else ink.lineTo(x(series.t[i]!), y(v));
    }
    ink.strokeStyle = series.ink;
    ink.lineWidth = 1.5 * devicePixelRatio;
    ink.lineJoin = "round";
    ink.stroke();

    // The moment.
    const nx = x(now);
    ink.strokeStyle = "rgba(255, 255, 255, 0.45)";
    ink.lineWidth = devicePixelRatio;
    ink.beginPath(); ink.moveTo(nx, headroom - 4 * devicePixelRatio); ink.lineTo(nx, height); ink.stroke();
    if (Number.isFinite(value)) {
      ink.fillStyle = series.ink;
      ink.beginPath(); ink.arc(nx, y(value), 3 * devicePixelRatio, 0, Math.PI * 2); ink.fill();
    }

    ink.fillStyle = "#4d6485";
    ink.font = `${10 * devicePixelRatio}px system-ui, sans-serif`;
    ink.textBaseline = "bottom";
    ink.fillText(short(low + pad), 6 * devicePixelRatio, height - 3 * devicePixelRatio);
    ink.textAlign = "right";
    ink.fillText(short(high - pad), width - 6 * devicePixelRatio, height - 3 * devicePixelRatio);
    ink.textAlign = "left";
  }, [series, now, end, value]);

  return (
    <div className="trace" onClick={(e) => {
      const box = e.currentTarget.getBoundingClientRect();
      onSeek(((e.clientX - box.left) / Math.max(1, box.width)) * end);
    }}>
      <canvas ref={canvas} />
      <span className="label">{series.name}<b>{Number.isFinite(value) ? short(value) : "—"}</b><i>{series.unit}</i></span>
    </div>
  );
}

function short(v: number): string {
  const magnitude = Math.abs(v);
  if (magnitude >= 100) return v.toFixed(0);
  if (magnitude >= 10) return v.toFixed(1);
  return v.toFixed(2);
}
