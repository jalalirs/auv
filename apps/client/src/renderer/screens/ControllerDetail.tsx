// One controller: what it is, where it came from, every build it has had, and
// every dive it flew.
//
// The Controllers list answers which one; this page answers what it has done.
// A dive pins a build, so the dives say which build flew them, and a build
// pulled again from its repository shows up as a new row under the same name.

import type { Platform } from "@coral-city/api";
import { ControllerArt } from "../parts/ControllerArt.js";
import { Button, Page, Status, Table } from "../ui/components.js";
import type { Held } from "./Deck.js";
import { headToHead, recordOf, saidAs } from "./flown.js";
import { ago } from "./parts.js";
import { scoreOf, taskOf, toneOf } from "./Runs.js";
import { useState } from "react";

type Source = { kind?: string; repository?: string; ref?: string; commit?: string; path?: string; name?: string };

/** Where a build came from, said in a few words. */
function sourceSaid(source: Source | undefined): string {
  if (!source?.kind) return "deployed from a terminal";
  if (source.kind === "git") {
    const at = source.commit ? source.commit.slice(0, 7) : source.ref ?? "";
    return `${(source.repository ?? "").replace(/^https?:\/\//, "")}${source.path ? `/${source.path}` : ""}${at ? ` at ${at}` : ""}`;
  }
  return source.kind === "zip" ? `a zip${source.name ? `, ${source.name}` : ""}` : source.kind;
}

export function ControllerDetail({ platform, held, slug, onBack, onFly, onReplay, onPulled }: {
  platform?: Platform;
  held: Held;
  slug: string;
  onBack: () => void;
  /** Fly with this build. */
  onFly?: (stackId: string) => void;
  onReplay?: (dive: string, run: string) => void;
  /** A pull from its repository has started; its build is in Controllers, Builds. */
  onPulled?: () => void;
}): React.JSX.Element {
  const [pulling, setPulling] = useState(false);
  const one = held.controllers.find((c) => c.slug === slug);
  if (!one) {
    return (
      <Page title="A controller" crumb="Controllers" onCrumb={onBack}>
        <p className="note">No controller called {slug} is deployed in your institution.</p>
      </Page>
    );
  }
  const flew = recordOf(one.name, held.runs);
  const against = headToHead(one.name, held.controllers.map((c) => c.name), held.runs).map((h) => saidAs(h));
  const dives = held.runs.filter((r) => r.flownBy === one.name);
  const source = one.newest.source as Source | undefined;
  const pull = async () => {
    if (!platform || !held.institution) return;
    setPulling(true);
    try {
      const builds = await platform.controllerBuildsOf(held.institution.id);
      const last = builds.find((b) => (b.report as { slug?: string } | undefined)?.slug === slug || b.slug === slug);
      if (last) { await platform.controllerBuildAgain(last.id); onPulled?.(); }
    } finally {
      setPulling(false);
    }
  };
  return (
    <Page title={one.name} crumb="Controllers" onCrumb={onBack}
          subtitle={`${one.slug} · ${sourceSaid(source)} · ${one.builds.length} version${one.builds.length === 1 ? "" : "s"}`}
          actions={<>
            {source?.kind === "git" ? <Button disabled={pulling || !platform} onClick={() => void pull()}>{pulling ? "Pulling…" : "Pull latest"}</Button> : null}
            <Button kind="primary" onClick={() => onFly?.(one.newest.id)}>Fly with it</Button>
          </>}>
      <div className="controller-facts">
        <ControllerArt digest={one.newest.imageDigest} size={48} />
        <dl className="asset-facts">
          <div><dt>dives</dt><dd>{flew.dives || "never flown"}{flew.neverFlew ? ` (and ${flew.neverFlew} the platform could not start)` : ""}</dd></div>
          <div><dt>scored</dt><dd>{flew.score === undefined ? "—" : `${(flew.score * 100).toFixed(0)}% on average`}</dd></div>
          <div><dt>drift</dt><dd>{flew.driftM === undefined ? "—" : `${flew.driftM.toFixed(1)} m on average`}</dd></div>
          <div><dt>last flown</dt><dd>{flew.lastAt ? ago(flew.lastAt) : "never"}</dd></div>
          {against.length ? <div><dt>against others</dt><dd>{against.join(" · ")}</dd></div> : null}
        </dl>
      </div>
      <section className="controller-section">
        <h2>Dives</h2>
        <Table rows={dives} rowKey={(r) => r.run.id}
               onRow={(r) => onReplay?.(r.dive, r.run.id)}
               search={(r) => `${r.name} ${taskOf(r)} ${r.run.state}`} searchLabel="Search its dives"
               facets={[{ key: "task", label: "Task", value: (r) => taskOf(r) || "no task" },
                        { key: "state", label: "State", value: (r) => r.run.state }]}
               initialSort={{ key: "when", down: true }}
               empty={<>It has not flown yet. <a onClick={() => onFly?.(one.newest.id)}>Fly with it</a>.</>}
               columns={[
                 { key: "dive", label: "Dive", grow: true, sort: (a, b) => a.name.localeCompare(b.name),
                   render: (r) => <><span className="cell-main">{r.name}</span><span className="cell-sub">{taskOf(r) || "no task"}</span></> },
                 { key: "score", label: "Score", align: "right", sort: (a, b) => scoreOf(a) - scoreOf(b),
                   render: (r) => scoreOf(r) >= 0 ? <b>{(scoreOf(r) * 100).toFixed(0)}%</b> : <span className="cell-meta">—</span> },
                 { key: "when", label: "When", sort: (a, b) => a.run.requestedAt.localeCompare(b.run.requestedAt),
                   render: (r) => <span className="cell-meta">{ago(r.run.requestedAt)}</span> },
                 { key: "state", label: "State", render: (r) => <Status tone={toneOf(r.run.state)}>{r.run.state}</Status> },
               ]} />
      </section>
      <section className="controller-section">
        <h2>Versions</h2>
        {/* A version is flown by clicking its row: no button in the row. */}
        <Table rows={one.builds} rowKey={(b) => b.id} onRow={(b) => onFly?.(b.id)}
               initialSort={{ key: "when", down: true }}
               columns={[
                 { key: "digest", label: "Version", grow: true,
                   render: (b) => <><span className="cell-main">{`version ${one.builds.length - one.builds.indexOf(b)}`}{b.id === one.newest.id ? " · newest" : ""}</span><span className="cell-sub">{sourceSaid(b.source as Source | undefined)}</span></> },
                 { key: "when", label: "Built", sort: (a, b) => (a.createdAt ?? "").localeCompare(b.createdAt ?? ""),
                   render: (b) => <span className="cell-meta">{b.createdAt ? ago(b.createdAt) : "—"}</span> },
               ]} />
      </section>
    </Page>
  );
}
