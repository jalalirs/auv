// A dive, played back.
//
// Nothing is executed. The recording a run left — poses at five hertz, the
// frames it saw at one, how its task was going — is fetched and scrubbed
// through: the frame nearest the moment on the left, the chart with the track
// up to that moment on the right, and the numbers underneath. What a survey
// produced, looked at.

import { useEffect, useMemo, useRef, useState } from "react";

import type { Artefact, Platform } from "@coral-city/api";

import { Minimap, type Fix } from "../parts/Minimap.js";
import { Empty, PageHead } from "./parts.js";

interface Pose {
  t: number;
  position: number[];
  headingDeg: number;
  depthM: number;
  altitudeM?: number | null;
  view?: string;
  frame?: string | null;
}

interface Manifest {
  poses: number;
  frames: number;
  seconds: number;
  beganAt?: number[];
  camera?: Record<string, unknown> | null;
  task?: { name?: string; score?: number; done?: boolean; achieved?: Record<string, unknown> } | null;
}

export function Replay({ platform, dive, run, onBack }: {
  platform: Platform;
  dive: string;
  run: string;
  onBack: () => void;
}): React.JSX.Element {
  const [files, setFiles] = useState<Artefact[] | undefined>();
  const [poses, setPoses] = useState<Pose[]>([]);
  const [manifest, setManifest] = useState<Manifest | undefined>();
  const [at, setAt] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [trouble, setTrouble] = useState<string | undefined>();
  const timer = useRef<ReturnType<typeof setInterval> | undefined>(undefined);

  useEffect(() => {
    let gone = false;
    (async () => {
      try {
        const listed = await platform.artefacts(dive, run);
        if (gone) return;
        setFiles(listed);
        const posesFile = listed.find((f) => f.path === "poses.jsonl");
        const manifestFile = listed.find((f) => f.path === "manifest.json");
        if (manifestFile?.url) {
          setManifest(await (await fetch(manifestFile.url)).json() as Manifest);
        }
        if (posesFile?.url) {
          const text = await (await fetch(posesFile.url)).text();
          const read = text.split("\n").filter((l) => l.trim() !== "").map((l) => JSON.parse(l) as Pose);
          if (!gone) setPoses(read);
        }
      } catch (problem) {
        if (!gone) setTrouble(problem instanceof Error ? problem.message : "the recording could not be read");
      }
    })();
    return () => { gone = true; };
  }, [platform, dive, run]);

  useEffect(() => {
    if (!playing) { if (timer.current) clearInterval(timer.current); return; }
    timer.current = setInterval(() => setAt((i) => (i + 1 >= poses.length ? 0 : i + 1)), 200);
    return () => { if (timer.current) clearInterval(timer.current); };
  }, [playing, poses.length]);

  const frames = useMemo(() => new Map((files ?? []).filter((f) => f.path.startsWith("frames/")).map((f) => [f.path, f.url ?? ""])), [files]);
  const pose = poses[at];
  const track: Fix[] = useMemo(() => poses.slice(0, at + 1).map((p) => ({ x: p.position[0]!, y: p.position[1]! })), [poses, at]);
  // The frame nearest this moment: the pose says which was taken last.
  const frameUrl = useMemo(() => {
    for (let i = at; i >= 0; i -= 1) {
      const name = poses[i]?.frame;
      if (name) return frames.get(name);
    }
    return undefined;
  }, [poses, at, frames]);

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

  return (
    <>
      <PageHead title="Replay" back="Dives" onBack={onBack}
                says={`${poses.length} poses, ${frames.size} frames, ${manifest?.seconds?.toFixed(0) ?? "?"} s`
                  + (manifest?.task?.name ? ` · ${manifest.task.name} ${((manifest.task.score ?? 0) * 100).toFixed(0)}%` : "")} />
      <div className="replay">
        <div className="frame">
          {frameUrl ? <img src={frameUrl} alt="what the vehicle saw" /> : <div className="none">no frame yet</div>}
        </div>
        <div className="chart">
          <Minimap site={undefined} track={track} position={pose?.position} headingDeg={pose?.headingDeg}
                   beganAt={manifest?.beganAt} large />
        </div>
      </div>
      <div className="scrub">
        <button className="quiet" onClick={() => setPlaying((p) => !p)}>{playing ? "Pause" : "Play"}</button>
        <input type="range" min={0} max={Math.max(0, poses.length - 1)} value={at}
               onChange={(e) => { setPlaying(false); setAt(Number(e.target.value)); }} />
        <span className="moment">
          {pose ? `${pose.t.toFixed(1)} s · ${pose.depthM.toFixed(2)} m down · ${pose.headingDeg.toFixed(0)}°`
            + (pose.altitudeM != null ? ` · ${pose.altitudeM.toFixed(2)} m up` : "") : "—"}
        </span>
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
