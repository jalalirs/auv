// What work is planned, and where.
//
// A mission is the thing a reef programme actually owns: this place, arranged
// this way, these stages in this order. Until it existed here, a plan of work
// lived inside one dive's objective and died with that dive — which meant two
// people could not fly the same round, and nothing could be compared.
//
// This is the library: every plan, where it is, how far it has got and how
// often it has flown, and what can be done with it — open it on its chart,
// fly it, copy it, or archive it. Archived, not deleted: a run that flew a
// version of it still says what it flew. Writing one is the designer
// (Designer.tsx).

import { useCallback, useEffect, useState } from "react";

import type { AssetVersion, Cost, Mission, Platform } from "@coral-city/api";

import type { Held } from "./Deck.js";
import { PageHead, Pill } from "./parts.js";

interface Row {
  mission: Mission;
  place: string;
  newest: AssetVersion | undefined;
  cost: Cost | undefined;
}

function when(iso: string | undefined): string {
  if (!iso) return "";
  const days = (Date.now() - new Date(iso).getTime()) / 86_400_000;
  return days < 1 ? "today" : days < 2 ? "yesterday" : `${Math.round(days)} d ago`;
}

export function Missions({ platform, held, onOpen, onFly }: {
  platform: Platform;
  held: Held;
  onOpen: (mission: string, place: string) => void;
  onFly: (mission: string) => void;
}): React.JSX.Element {
  const [rows, setRows] = useState<Row[] | undefined>();
  const [where, setWhere] = useState<string>(() => held.places[0]?.id ?? "");
  const [naming, setNaming] = useState("");
  const [archiving, setArchiving] = useState<string | undefined>();
  const [trouble, setTrouble] = useState("");

  const read = useCallback(() => {
    let stale = false;
    void (async () => {
      const found = await Promise.all(held.places.map(async (place) =>
        (await platform.missionsOf(place.id).catch((): Mission[] => []))
          .map((mission) => ({ mission, place: place.id }))));
      const all = found.flat();
      const filled = await Promise.all(all.map(async (one) => ({
        ...one,
        newest: (await platform.versionsOfMission(one.mission.id).catch((): AssetVersion[] => []))[0],
        cost: await platform.missionCost(one.mission.id).catch((): Cost | undefined => undefined),
      })));
      if (!stale) setRows(filled);
    })();
    return () => { stale = true; };
  }, [platform, held.places]);
  useEffect(read, [read]);

  const duplicate = useCallback(async (row: Row) => {
    setTrouble("");
    try {
      const slug = `${row.mission.slug}`.slice(0, 50) + "-" + Date.now().toString(36).slice(-5);
      const made = await platform.startMission(row.place, { slug, name: `${row.mission.name} (copy)` });
      if (row.newest?.document) {
        await platform.saveMission(made.id, row.newest.document as never, `copied from ${row.mission.name}`);
      }
      onOpen(made.id, row.place);
    } catch (thrown) {
      setTrouble(thrown instanceof Error ? thrown.message : "it would not copy");
    }
  }, [platform, onOpen]);

  const archive = useCallback(async (row: Row) => {
    setTrouble("");
    try {
      await platform.archiveMission(row.mission.id);
      setArchiving(undefined);
      read();
    } catch (thrown) {
      setTrouble(thrown instanceof Error ? thrown.message : "it would not archive");
    }
  }, [platform, read]);

  const placeName = (id: string) => held.places.find((p) => p.id === id)?.name ?? "somewhere";

  return (
    <>
      <PageHead title="Missions" says="A place, the arrangement it was planned over, and the work in order — drawn on its chart, flown by anybody, and comparable across both."
                aside={<Pill>{rows?.length ?? 0} {rows?.length === 1 ? "plan" : "plans"}</Pill>} />

      <section className="library">
        {rows === undefined ? <p className="quiet">Reading the plans…</p>
          : rows.length === 0 ? <p className="quiet">Nothing is planned yet. Name one below and draw it on its place&rsquo;s chart.</p>
          : (
          <table>
            <thead>
              <tr><th>Plan</th><th>Place</th><th>Stages</th><th>Saved</th><th>Flown</th><th /></tr>
            </thead>
            <tbody>
              {rows.map((row) => {
                const stages = ((row.newest?.document as { stages?: unknown[] } | undefined)?.stages ?? []).length;
                return (
                  <tr key={row.mission.id}>
                    <td className="what" onClick={() => onOpen(row.mission.id, row.place)}>
                      <strong>{row.mission.name}</strong>
                      {row.mission.summary ? <small>{row.mission.summary}</small> : null}
                    </td>
                    <td>{placeName(row.place)}</td>
                    <td>{stages || "—"}</td>
                    <td>{row.newest ? `v${row.newest.ordinal} · ${when(row.newest.createdAt)}` : "not yet"}</td>
                    <td>{row.cost?.runs ? `${row.cost.runs} ${row.cost.runs === 1 ? "run" : "runs"}` : "never"}</td>
                    <td className="row-acts">
                      {archiving === row.mission.id ? (
                        <>
                          <span className="quiet">Archive it? Its runs stay in the record.</span>
                          <button type="button" className="quiet" onClick={() => setArchiving(undefined)}>Keep</button>
                          <button type="button" onClick={() => void archive(row)}>Archive</button>
                        </>
                      ) : (
                        <>
                          <button type="button" className="quiet" onClick={() => onOpen(row.mission.id, row.place)}>Open</button>
                          <button type="button" disabled={!row.newest} onClick={() => onFly(row.mission.id)}>Fly</button>
                          <button type="button" className="quiet" onClick={() => void duplicate(row)}>Duplicate</button>
                          <button type="button" className="quiet" onClick={() => setArchiving(row.mission.id)}>Archive</button>
                        </>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}

        <form className="naming" onSubmit={(event) => {
          event.preventDefault();
          const name = naming.trim();
          if (!name || !where) return;
          const slug = name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 62);
          void platform.startMission(where, { slug, name })
            .then((made) => { setNaming(""); setTrouble(""); onOpen(made.id, where); })
            .catch((thrown: unknown) => setTrouble(thrown instanceof Error ? thrown.message : "it would not start"));
        }}>
          <select value={where} onChange={(e) => setWhere(e.target.value)}>
            {held.places.map((one) => <option key={one.id} value={one.id}>{one.name}</option>)}
          </select>
          <input value={naming} onChange={(e) => setNaming(e.target.value)} placeholder="name a new plan of work" />
          <button type="submit" disabled={!naming.trim() || !where}>Plan one</button>
        </form>
        {trouble ? <p className="trouble">{trouble}</p> : null}
      </section>
    </>
  );
}
