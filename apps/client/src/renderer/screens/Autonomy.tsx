// What flies the vehicle, other than you — and what each one has done.
//
// The controllers this institution has deployed, newest first: each an image
// pinned by digest, with what it needs of a machine, and every build it has
// had folded under one row — a dive pins a build, a person thinks in
// controllers. A stack is what a dive
// is defined with on the dive page; deploying one is the SDK's job, from a
// terminal, because a build is a build.
//
// And beside each, what it flew. The page used to answer "what have I
// uploaded", which is the smallest question anybody has about a controller.
// The one they have is which of these should fly my mission, and the answer
// was already in the record: every dive the institution defined, which stack
// flew it, and what became of it. A controller that has never flown says so
// in those words — it is the most useful row here, because it is the
// difference between a controller somebody deployed and one somebody trusts.

import { ControllerArt } from "../parts/ControllerArt.js";
import type { Held } from "./Deck.js";
import { headToHead, recordOf, saidAs } from "./flown.js";
import { ago } from "./parts.js";
import { useState } from "react";
import { Button, Dialog, Menu, Page, Status, Table } from "../ui/components.js";

export function Autonomy({ held, onFly, onRuns, onCompare }: {
  held: Held;
  /** Fly a single task with this controller (its newest build). */
  onFly?: (stackId: string) => void;
  /** Its dives, in Runs. */
  onRuns?: (flownBy: string) => void;
  onCompare?: () => void;
}): React.JSX.Element {
  const [deploying, setDeploying] = useState(false);
  type Row = Held["controllers"][number] & { flew: ReturnType<typeof recordOf>; against: string[] };
  const rows: Row[] = held.controllers.map((one) => ({
    ...one,
    flew: recordOf(one.name, held.runs),
    against: headToHead(one.name, held.controllers.map((c) => c.name), held.runs).map((h) => saidAs(h)),
  }));
  const cardOf = (r: Row) => {
    const needs = (r.newest.needs ?? {}) as { gpu?: boolean; gpuMemoryBytes?: number };
    return needs.gpu || r.newest.wantsGpu
      ? (needs.gpuMemoryBytes ? `${(needs.gpuMemoryBytes / 2 ** 30).toFixed(0)} GiB of a card` : "a card") : "no card";
  };
  return (
    <Page title="Controllers" subtitle="What flies the vehicle other than you: each one's dives, scores, and builds."
          info="Your controllers, in containers, pinned by digest. Each talks ROS 2 to the vehicle exactly as it would to a real one and imports nothing of ours: the same binary should run in a tank and in the sea. A dive pins a build; a person thinks in controllers, so every build folds under one row."
          actions={<Button onClick={() => setDeploying(true)}>Deploy one</Button>}>
      <Table rows={rows} rowKey={(r) => r.slug}
             search={(r) => `${r.name} ${r.slug}`} searchLabel="Search controllers"
             facets={[{ key: "flown", label: "Flown", value: (r) => r.flew.dives === 0 ? "never flown" : "flown" },
                      { key: "card", label: "Needs", value: (r) => cardOf(r) === "no card" ? "no card" : "a card" }]}
             initialSort={{ key: "last", down: true }}
             empty={<>Nothing deployed yet. <a onClick={() => setDeploying(true)}>Deploy one</a> from the SDK; it appears here and on the dive page.</>}
             columns={[
               { key: "name", label: "Controller", sort: (a, b) => a.name.localeCompare(b.name),
                 render: (r) => (
                   <div className="controller-cell">
                     <ControllerArt digest={r.newest.imageDigest} size={28} />
                     <div title={r.against.length ? r.against.join(" · ") : undefined}>
                       <span className="cell-main">{r.name}</span>
                       <span className="cell-sub">{r.slug} · {r.newest.imageDigest.slice(7, 19)}{r.builds.length > 1 ? ` · ${r.builds.length} builds` : ""}</span>
                     </div>
                   </div>
                 ) },
               { key: "dives", label: "Dives", align: "right", sort: (a, b) => a.flew.dives - b.flew.dives,
                 render: (r) => r.flew.dives || <span className="cell-meta">never</span> },
               { key: "score", label: "Scored", align: "right", sort: (a, b) => (a.flew.score ?? -1) - (b.flew.score ?? -1),
                 render: (r) => r.flew.score === undefined ? <span className="cell-meta">—</span> : <b>{(r.flew.score * 100).toFixed(0)}%</b> },
               { key: "drift", label: "Drift", align: "right", priority: 3,
                 render: (r) => <span className="cell-meta">{r.flew.driftM === undefined ? "—" : `${r.flew.driftM.toFixed(1)} m`}</span> },
               { key: "energy", label: "Energy", align: "right", priority: 3,
                 render: (r) => <span className="cell-meta">{r.flew.energyWh === undefined ? "—" : `${r.flew.energyWh.toFixed(1)} Wh`}</span> },
               { key: "last", label: "Last flown", priority: 2, sort: (a, b) => (a.flew.lastAt ?? "").localeCompare(b.flew.lastAt ?? ""),
                 render: (r) => <span className="cell-meta" title={r.flew.neverFlew ? `${r.flew.neverFlew} of its dives could not be started by the platform` : undefined}>{r.flew.lastAt ? ago(r.flew.lastAt) : "never"}{r.flew.neverFlew ? ` · ${r.flew.neverFlew} unstarted` : ""}</span> },
               { key: "card", label: "Needs", priority: 2, render: (r) => <Status tone={cardOf(r) === "no card" ? "quiet" : "busy"}>{cardOf(r)}</Status> },
             ]}
             actions={(r) => (
               <>
                 <Button onClick={() => onFly?.(r.newest.id)}>Fly with it</Button>
                 <Menu items={[
                   { label: "Its dives", disabled: r.flew.dives === 0, onSelect: () => onRuns?.(r.name) },
                   { label: "Compare controllers", onSelect: () => onCompare?.() },
                 ]} />
               </>
             )} />
      {deploying ? (
        <Dialog title="Deploying a controller" onClose={() => setDeploying(false)}
                actions={<Button kind="primary" onClick={() => setDeploying(false)}>Done</Button>}>
          <ol className="steps">
            <li><code>pip install -e packages/sdk-python</code></li>
            <li>Write a class against <code>iocean.Controller</code>.</li>
            <li>Try it in the tank: <code>iocean tank</code></li>
            <li>Deploy it: <code>iocean deploy your.py --slug name</code></li>
          </ol>
          <p className="note">A controller that is a model says what it needs with <code>--gpu-memory 8G</code>, and the scheduler places the dive where both it and the simulator fit.</p>
        </Dialog>
      ) : null}
    </Page>
  );
}
