"use client";

import { useMemo, useState } from "react";
import {
  architecture,
  budget,
  environmentPackage,
  growthAreas,
  missionCatalog,
  modelRegistry,
  principles,
  program,
  reconstructionSteps,
  roadmap,
  scorecards,
  simulationLayers,
  truthClasses,
} from "./plan-data";

const navItems = [
  ["vision", "Vision"],
  ["architecture", "System"],
  ["reconstruction", "3D pipeline"],
  ["lab", "Simulation lab"],
  ["models", "Model engine"],
  ["roadmap", "Roadmap"],
  ["program", "Program"],
];

function Arrow() {
  return <span aria-hidden="true">↗</span>;
}

function StatusMark({ status }: { status: "complete" | "active" | "planned" }) {
  return <span className={`status-mark status-${status}`}>{status}</span>;
}

export default function Home() {
  const [activeArchitecture, setActiveArchitecture] = useState(0);
  const [activePhase, setActivePhase] = useState(1);
  const selectedArchitecture = architecture[activeArchitecture];
  const selectedPhase = roadmap[activePhase];
  const totalBudget = useMemo(() => budget.reduce((sum, [, value]) => sum + value, 0), []);

  return (
    <main>
      <header className="site-header">
        <a className="brand" href="#vision" aria-label="Coral City home">
          <span className="brand-orbit" aria-hidden="true"><i /></span>
          <span><strong>CORAL CITY</strong><small>RED SEA TWIN LAB</small></span>
        </a>
        <nav aria-label="Primary navigation">
          {navItems.map(([href, label]) => <a key={href} href={`#${href}`}>{label}</a>)}
        </nav>
        <a className="header-gate" href="#roadmap"><span>NOW</span>{program.currentGate}</a>
      </header>

      <section className="hero" id="vision">
        <div className="hero-grid" aria-hidden="true" />
        <div className="hero-copy">
          <p className="eyebrow"><span /> {program.version} · {program.updated}</p>
          <h1>A living Red Sea.<br /><em>Before we enter it.</em></h1>
          <p className="hero-lede">{program.northStar}</p>
          <div className="hero-actions">
            <a className="button button-primary" href="#architecture">Enter the system <Arrow /></a>
            <a className="button button-secondary" href="#roadmap">Follow the build plan</a>
          </div>
          <dl className="hero-facts">
            <div><dt>Scope</dt><dd>Reef → coast → Red Sea</dd></div>
            <div><dt>Contract</dt><dd>OpenUSD + ROS 2</dd></div>
            <div><dt>Horizon</dt><dd>{program.horizon}</dd></div>
          </dl>
        </div>

        <div className="twin-window" aria-label="Conceptual reef twin status display">
          <div className="window-bar"><span>REEF CELL 01</span><span>SIMULATION / LIVE TWIN</span></div>
          <div className="reef-radar">
            <div className="radar-ring ring-one" /><div className="radar-ring ring-two" /><div className="radar-ring ring-three" />
            <div className="reef-mass reef-a" /><div className="reef-mass reef-b" /><div className="reef-mass reef-c" />
            <span className="auv auv-one">AUV–01</span><span className="auv auv-two">SPOTTER</span>
            <div className="scan-line" />
          </div>
          <div className="window-readouts">
            <div><span>TRUTH LAYERS</span><strong>6</strong></div>
            <div><span>ACTIVE CELL</span><strong>50 × 50 m</strong></div>
            <div><span>TIME MODE</span><strong>FORECAST +06H</strong></div>
          </div>
        </div>
      </section>

      <section className="truth-strip" aria-label="Digital twin truth classes">
        <p>Every object declares what it is</p>
        <div>{truthClasses.map((item) => <span key={item.id} className={`truth truth-${item.id}`} title={item.detail}>{item.label}</span>)}</div>
      </section>

      <section className="section system-section" id="architecture">
        <div className="section-heading">
          <div><p className="eyebrow">END-TO-END LOOP</p><h2>One system, not disconnected demos.</h2></div>
          <p>Coral City closes the loop from evidence to prediction, simulation, autonomous action, and new evidence. Select a stage to inspect its contract.</p>
        </div>
        <div className="architecture-shell">
          <div className="architecture-flow" role="tablist" aria-label="System stages">
            {architecture.map((item, index) => (
              <button key={item.id} className={index === activeArchitecture ? "active" : ""} onClick={() => setActiveArchitecture(index)} role="tab" aria-selected={index === activeArchitecture}>
                <small>{item.number}</small><strong>{item.label}</strong><span aria-hidden="true">→</span>
              </button>
            ))}
          </div>
          <article className="architecture-detail" role="tabpanel">
            <div><p className="eyebrow">{selectedArchitecture.number} · {selectedArchitecture.label}</p><h3>{selectedArchitecture.title}</h3><p>{selectedArchitecture.summary}</p></div>
            <div className="contract-list"><small>INPUTS / CAPABILITIES</small>{selectedArchitecture.inputs.map((item) => <span key={item}>{item}</span>)}</div>
            <div className="output-card"><small>REQUIRED OUTPUT</small><p>{selectedArchitecture.output}</p></div>
          </article>
        </div>
      </section>

      <section className="section reconstruction-section" id="reconstruction">
        <div className="section-heading light-heading">
          <div><p className="eyebrow">VIDEO → SCIENTIFIC 3D</p><h2>The reef reconstruction factory.</h2></div>
          <p>Photogrammetry is not an import button. A trustworthy model carries calibration, scale, location, time, semantics, uncertainty, and lineage into the twin.</p>
        </div>
        <ol className="pipeline">
          {reconstructionSteps.map(([title, body], index) => (
            <li key={title}><span>{String(index + 1).padStart(2, "0")}</span><div><h3>{title}</h3><p>{body}</p></div></li>
          ))}
        </ol>
        <div className="pipeline-output">
          <span>IMMUTABLE SOURCE</span><i>→</i><span>VERSIONED OBSERVATION</span><i>→</i><span>OPENUSD TILES</span><i>→</i><span>CHANGE THROUGH TIME</span>
        </div>
      </section>

      <section className="section lab-section" id="lab">
        <div className="section-heading">
          <div><p className="eyebrow">THE SIMULATION LAB</p><h2>A federation with one mission contract.</h2></div>
          <p>Isaac is the primary world and robotics experience—not the only scientific model. Specialist engines participate through shared frames, time, fields, assets, and ROS 2 messages.</p>
        </div>
        <div className="layer-stack">
          {simulationLayers.map((layer, index) => (
            <article key={layer.title} style={{ "--layer-index": index } as React.CSSProperties}>
              <span>{String(index + 1).padStart(2, "0")}</span><div><h3>{layer.title}</h3><p>{layer.body}</p></div><small>{layer.tech}</small>
            </article>
          ))}
        </div>
        <div className="missions-block">
          <div><p className="eyebrow">STANDARD MISSIONS</p><h3>The lab becomes real when algorithms can fail fairly.</h3></div>
          <div className="mission-grid">
            {missionCatalog.map(([title, body], index) => <article key={title}><span>{String(index + 1).padStart(2, "0")}</span><h4>{title}</h4><p>{body}</p></article>)}
          </div>
        </div>
      </section>

      <section className="section models-section" id="models">
        <div className="section-heading light-heading">
          <div><p className="eyebrow">CLEAN GROWTH ARCHITECTURE</p><h2>One stable core. Many replaceable engines.</h2></div>
          <p>Coral City owns the contracts, evidence, and experience. Scientific solvers remain independent tools behind small adapters, so adding a serious model never forces a rewrite of the reef, robot, or interface.</p>
        </div>

        <div className="growth-grid">
          {growthAreas.map(([title, body], index) => (
            <article key={title}><span>{String(index + 1).padStart(2, "0")}</span><h3>{title}</h3><p>{body}</p></article>
          ))}
        </div>

        <div className="adapter-story" aria-label="Scientific model adapter flow">
          <div><small>MODEL-NATIVE WORLD</small><strong>SWAN · SCHISM · WRF · OpenDrift · …</strong><p>Each solver keeps its own grids, configuration, binaries, logs, and native results.</p></div>
          <i aria-hidden="true">→</i>
          <div className="adapter-core"><small>SMALL REPLACEABLE ADAPTER</small><strong>prepare · run · collect · normalize · verify</strong><p>The only model-specific code Coral City needs to understand.</p></div>
          <i aria-hidden="true">→</i>
          <div><small>STABLE CORAL CITY CONTRACT</small><strong>Environment Package</strong><ul>{environmentPackage.map((item) => <li key={item}>{item}</li>)}</ul></div>
          <i aria-hidden="true">→</i>
          <div><small>CONSUMERS</small><strong>Living twin · Isaac · ROS 2 · science UI</strong><p>Every consumer sees the same time, frame, units, uncertainty, and provenance.</p></div>
        </div>

        <div className="model-catalog">
          <div className="catalog-heading"><div><p className="eyebrow">CANDIDATE MODEL SHELF</p><h3>Adopt only when a phase needs it.</h3></div><p>These are integration candidates, not ten dependencies we install today. Licence labels are planning notes until independently verified against the selected release and dependencies.</p></div>
          <div className="model-table" role="table" aria-label="Candidate environmental models">
            <div className="model-row model-head" role="row"><span>Model</span><span>Family</span><span>What it gives Coral City</span><span>Licence note</span><span>Build</span><span>When</span></div>
            {modelRegistry.map((model) => (
              <div className="model-row" role="row" key={model.name}><strong>{model.name}</strong><span>{model.family}</span><span>{model.purpose}</span><span>{model.licence}</span><span>{model.build}</span><b>{model.phase}</b></div>
            ))}
          </div>
        </div>
      </section>

      <section className="section roadmap-section" id="roadmap">
        <div className="section-heading">
          <div><p className="eyebrow">THE 24-MONTH WALK</p><h2>Milestones close with evidence.</h2></div>
          <p>No arbitrary completion percentages. A phase is complete only when its acceptance gate passes and its evidence is preserved.</p>
        </div>
        <div className="roadmap-layout">
          <div className="roadmap-index" role="tablist" aria-label="Roadmap phases">
            {roadmap.map((phase, index) => (
              <button key={phase.id} className={index === activePhase ? "active" : ""} onClick={() => setActivePhase(index)} role="tab" aria-selected={index === activePhase}>
                <span>{phase.number}</span><div><strong>{phase.title}</strong><small>{phase.horizon}</small></div><StatusMark status={phase.status} />
              </button>
            ))}
          </div>
          <article className="phase-detail" role="tabpanel">
            <div className="phase-top"><div><p className="eyebrow">{selectedPhase.number} · {selectedPhase.horizon}</p><h3>{selectedPhase.title}</h3></div><StatusMark status={selectedPhase.status} /></div>
            <p className="phase-intent">{selectedPhase.intent}</p>
            <div className="phase-columns">
              <div><small>DELIVERABLES</small><ul>{selectedPhase.deliverables.map((item) => <li key={item}>{item}</li>)}</ul></div>
              <div><small>ACCEPTANCE GATE</small><p>{selectedPhase.gate}</p>{selectedPhase.evidence && <><small>EVIDENCE</small><ul className="evidence-list">{selectedPhase.evidence.map((item) => <li key={item}>{item}</li>)}</ul></>}</div>
            </div>
          </article>
        </div>
      </section>

      <section className="section program-section" id="program">
        <div className="section-heading light-heading">
          <div><p className="eyebrow">$2M-CLASS PILOT</p><h2>Fund the loop, not a showroom.</h2></div>
          <p>An illustrative two-year envelope. Field access, partner scope, vehicle class, and data rights will determine the real program cost.</p>
        </div>
        <div className="program-grid">
          <div className="budget-chart">
            {budget.map(([label, value]) => <div key={label}><span>{label}</span><i><b style={{ width: `${(value / 650) * 100}%` }} /></i><strong>${value}k</strong></div>)}
            <p><span>PILOT ENVELOPE</span><strong>${(totalBudget / 1000).toFixed(1)}M</strong></p>
          </div>
          <div className="scorecards">
            <p className="eyebrow">PROGRAM SCORECARDS</p>
            {scorecards.map(([title, body]) => <article key={title}><h3>{title}</h3><p>{body}</p></article>)}
          </div>
        </div>
      </section>

      <section className="section principles-section">
        <div className="section-heading"><div><p className="eyebrow">NON-NEGOTIABLES</p><h2>How we keep the twin honest.</h2></div></div>
        <div className="principles-grid">{principles.map(([title, body], index) => <article key={title}><span>{String(index + 1).padStart(2, "0")}</span><h3>{title}</h3><p>{body}</p></article>)}</div>
      </section>

      <section className="next-gate">
        <div><p className="eyebrow">CURRENT EXECUTION GATE</p><h2>M2 · Coral District 01</h2><p>Build the first credible 50 × 50 m reef district, establish visual scale and truth classes, and place a controllable robot inside it.</p></div>
        <a className="button button-primary" href="#roadmap">Read the gate <Arrow /></a>
      </section>

      <footer><div><strong>CORAL CITY</strong><span>{program.subtitle}</span></div><p>{program.version} · Updated {program.updated} · The plan advances only with preserved evidence.</p></footer>
    </main>
  );
}
