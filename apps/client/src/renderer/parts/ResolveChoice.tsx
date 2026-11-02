// Where Resolve says an asset fits a place's ground, for somebody to choose.
//
// The candidates on the place's chart, best first beside it, the chosen one
// nudged by hand if wanted, and Lay it here. Used by a place being composed
// (Compose.tsx) and by a reconstruction's own page.

import { useEffect, useState } from "react";
import type { MappingChoice, Platform } from "@coral-city/api";

import { FitMap, type Spot } from "./FitMap.js";
import { Button, Skeleton } from "../ui/components.js";

export type Candidate = { at: [number, number]; headingDeg: number; dz: number; startAt?: number[];
                          fit?: { rmsM?: number; placeGroundM?: number } };

/** A version's seabed: its site record and where its heightfield is. */
export type Ground = { acrossM: number; rows: number; columns: number; heightsUrl?: string };

/** A version's ground, read from its files. */
export function useVersionGround(platform: Platform, versionId: string | undefined): Ground | undefined {
  const [ground, setGround] = useState<Ground | undefined>();
  useEffect(() => {
    setGround(undefined);
    if (!versionId) return;
    let stale = false;
    void (async () => {
      const files = await platform.files(versionId);
      const siteUrl = files.find((f) => f.path === "site.json")?.url;
      if (!siteUrl) return;
      const site = await (await fetch(siteUrl)).json() as {
        from?: { acrossMetres?: number }; mesh?: { heightfield?: { rows: number; columns: number; file: string } } };
      const hf = site.mesh?.heightfield;
      if (!hf || !site.from?.acrossMetres) return;
      if (!stale) {
        setGround({ acrossM: site.from.acrossMetres, rows: hf.rows, columns: hf.columns,
                    heightsUrl: files.find((f) => f.path === hf.file)?.url });
      }
    })().catch(() => undefined);
    return () => { stale = true; };
  }, [platform, versionId]);
  return ground;
}

export function ResolveChoice({ candidates, start, ground, extentM, busy, onAccept }: {
  candidates: Candidate[];
  start?: [number, number] | null;
  ground: Ground | undefined;
  /** The asset's length and width, in its own frame. */
  extentM: [number, number];
  busy?: boolean;
  onAccept: (choice: MappingChoice) => void;
}): React.JSX.Element {
  const [chosen, setChosen] = useState(0);
  const [nudge, setNudge] = useState({ dx: 0, dy: 0, turn: 0 });
  const pick = candidates[chosen];
  const moved = nudge.dx !== 0 || nudge.dy !== 0 || nudge.turn !== 0;
  const nudged: Candidate | undefined = pick && {
    ...pick, at: [pick.at[0] + nudge.dx, pick.at[1] + nudge.dy], headingDeg: (pick.headingDeg + nudge.turn + 360) % 360,
    ...(moved ? { startAt: undefined } : {}),
  };
  const spots: Spot[] = candidates.map((c, i) => (i === chosen && nudged ? nudged : c));
  const choose = (i: number) => { setChosen(i); setNudge({ dx: 0, dy: 0, turn: 0 }); };

  return (
    <div className="resolve">
      <div className="resolve-map">
        {ground ? (
          <FitMap heightsUrl={ground.heightsUrl} rows={ground.rows} columns={ground.columns} acrossM={ground.acrossM}
                  extentM={extentM} spots={spots} chosen={chosen} start={start} onChoose={choose} />
        ) : <Skeleton height={320} />}
      </div>
      <div className="resolve-side">
        <div className="rows">
          {candidates.map((c, i) => (
            <button key={i} type="button" className={`row open${i === chosen ? " chosen" : ""}`} onClick={() => choose(i)}>
              <span className="what">{i + 1}. ({c.at[0].toFixed(0)}, {c.at[1].toFixed(0)}) m, {c.headingDeg}°</span>
              <span className="quiet">{c.fit?.rmsM?.toFixed(2)} m rms · ground {c.fit?.placeGroundM?.toFixed(1)} m</span>
            </button>
          ))}
        </div>
        <p className="note">rms is how far the place&rsquo;s seabed and the asset&rsquo;s own ground still disagree once it is raised or lowered to fit.</p>
        <div className="nudges">
          <Button kind="ghost" onClick={() => setNudge((n) => ({ ...n, dy: n.dy + 5 }))}>↑ 5 m</Button>
          <Button kind="ghost" onClick={() => setNudge((n) => ({ ...n, dy: n.dy - 5 }))}>↓ 5 m</Button>
          <Button kind="ghost" onClick={() => setNudge((n) => ({ ...n, dx: n.dx - 5 }))}>← 5 m</Button>
          <Button kind="ghost" onClick={() => setNudge((n) => ({ ...n, dx: n.dx + 5 }))}>→ 5 m</Button>
          <Button kind="ghost" onClick={() => setNudge((n) => ({ ...n, turn: n.turn + 10 }))}>Turn left 10°</Button>
          <Button kind="ghost" onClick={() => setNudge((n) => ({ ...n, turn: n.turn - 10 }))}>Turn right 10°</Button>
        </div>
        {moved ? <p className="note">Moved by hand from candidate {chosen + 1}: its fit no longer applies; its height is kept.</p> : null}
        <Button kind="primary" disabled={busy || !nudged} onClick={() => nudged && onAccept(moved
          ? { placement: { at: nudged.at, headingDeg: nudged.headingDeg, dz: nudged.dz } }
          : { candidate: chosen })}>Lay it here</Button>
      </div>
    </div>
  );
}
