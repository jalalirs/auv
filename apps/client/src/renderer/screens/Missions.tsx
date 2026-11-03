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
import { Button, Dialog, Menu, Page, Table } from "../ui/components.js";

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
  const [where, setWhere] = useState<string>(() => held.yourPlaces[0]?.id ?? "");
  const [naming, setNaming] = useState("");
  const [planning, setPlanning] = useState(false);
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

  const stagesOf = (row: Row) => ((row.newest?.document as { stages?: unknown[] } | undefined)?.stages ?? []).length;

  const plan = () => {
    const name = naming.trim();
    if (!name || !where) return;
    const slug = name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 62);
    void platform.startMission(where, { slug, name })
      .then((made) => { setNaming(""); setTrouble(""); setPlanning(false); onOpen(made.id, where); })
      .catch((thrown: unknown) => setTrouble(thrown instanceof Error ? thrown.message : "it would not start"));
  };
  const archivingRow = rows?.find((r) => r.mission.id === archiving);

  return (
    <Page title="Missions" subtitle="Plans of work: a place, how it is arranged, and the stages in order."
          info="A mission is drawn on its place's chart, flown by anybody, and compared across both. Archived, never deleted: a dive that flew a version of it still says what it flew."
          actions={<Button kind="primary" onClick={() => setPlanning(true)} disabled={held.yourPlaces.length === 0}>New mission</Button>}>
      {trouble ? <p className="trouble">{trouble}</p> : null}
      {(
        <Table rows={rows ?? []} loading={rows === undefined} rowKey={(r) => r.mission.id} onRow={(r) => onOpen(r.mission.id, r.place)}
               search={(r) => `${r.mission.name} ${r.mission.summary ?? ""} ${placeName(r.place)}`} searchLabel="Search missions"
               facets={[{ key: "place", label: "Place", value: (r) => placeName(r.place) }]}
               initialSort={{ key: "saved", down: true }}
               empty={<>No missions yet. <a onClick={() => setPlanning(true)}>Make one</a> and draw it on its place&rsquo;s chart.</>}
               columns={[
                 { key: "plan", label: "Mission", sort: (a, b) => a.mission.name.localeCompare(b.mission.name),
                   render: (r) => <><span className="cell-main">{r.mission.name}</span>{r.mission.summary ? <span className="cell-sub">{r.mission.summary}</span> : null}</> },
                 { key: "place", label: "Place", priority: 2, sort: (a, b) => placeName(a.place).localeCompare(placeName(b.place)),
                   render: (r) => <span className="cell-meta">{placeName(r.place)}</span> },
                 { key: "stages", label: "Stages", align: "right", priority: 3, sort: (a, b) => stagesOf(a) - stagesOf(b),
                   render: (r) => stagesOf(r) || "—" },
                 { key: "saved", label: "Saved", priority: 2,
                   sort: (a, b) => (a.newest?.createdAt ?? "").localeCompare(b.newest?.createdAt ?? ""),
                   render: (r) => <span className="cell-meta">{r.newest ? `v${r.newest.ordinal} · ${when(r.newest.createdAt)}` : "not yet"}</span> },
                 { key: "flown", label: "Flown", align: "right", sort: (a, b) => (a.cost?.runs ?? 0) - (b.cost?.runs ?? 0),
                   render: (r) => <span className="cell-meta">{r.cost?.runs ? `${r.cost.runs} ${r.cost.runs === 1 ? "dive" : "dives"}` : "never"}</span> },
               ]}
               actions={(r) => (
                 <Menu items={[
                     { label: "Fly", disabled: !r.newest, onSelect: () => onFly(r.mission.id) },
                     { label: "Duplicate", onSelect: () => void duplicate(r) },
                     { label: "Archive…", danger: true, onSelect: () => setArchiving(r.mission.id) },
                   ]} />
               )} />
      )}
      {planning ? (
        <Dialog title="New mission" onClose={() => setPlanning(false)}
                actions={<><Button kind="ghost" onClick={() => setPlanning(false)}>Cancel</Button>
                  <Button kind="primary" disabled={!naming.trim() || !where} onClick={plan}>Create and open</Button></>}>
          <label className="field"><span>Place</span>
            <select value={where} onChange={(e) => setWhere(e.target.value)}>
              {held.yourPlaces.map((one) => <option key={one.id} value={one.id}>{one.name}</option>)}
            </select>
          </label>
          <label className="field"><span>Name</span>
            <input autoFocus value={naming} onChange={(e) => setNaming(e.target.value)}
                   onKeyDown={(e) => { if (e.key === "Enter") plan(); }} placeholder="e.g. Survey the north plot" />
          </label>
        </Dialog>
      ) : null}
      {archivingRow ? (
        <Dialog title={`Archive ${archivingRow.mission.name}?`} onClose={() => setArchiving(undefined)}
                actions={<><Button kind="ghost" onClick={() => setArchiving(undefined)}>Keep it</Button>
                  <Button kind="danger" onClick={() => void archive(archivingRow)}>Archive</Button></>}>
          <p className="note">It leaves this list. Every dive that flew it stays in the record and still says what it flew.</p>
        </Dialog>
      ) : null}
    </Page>
  );
}
