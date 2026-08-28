"use client";

import { useState } from "react";
import {
  architecture,
  deploymentPlanes,
  deploymentProfiles,
  environmentPackage,
  jobLifecycle,
  modelRegistry,
  program,
  reconstructionSteps,
  roadmap,
  truthClasses,
} from "./plan-data";

type View = "architecture" | "product" | "releases" | "models" | "deployment";

const views: { id: View; label: string }[] = [
  { id: "architecture", label: "Architecture" },
  { id: "product", label: "Product" },
  { id: "releases", label: "Releases" },
  { id: "models", label: "Models" },
  { id: "deployment", label: "Deployment" },
];

function Status({ status }: { status: "complete" | "active" | "planned" }) {
  return <span className={`status status-${status}`}>{status}</span>;
}

export default function Home() {
  const [activeView, setActiveView] = useState<View>("architecture");
  const [activePhase, setActivePhase] = useState(0);
  const [activeProfile, setActiveProfile] = useState(0);
  const phase = roadmap[activePhase];
  const profile = deploymentProfiles[activeProfile];

  return (
    <main className="blueprint-app">
      <header className="app-header">
        <button className="brand" onClick={() => setActiveView("architecture")} aria-label="Open Coral City architecture">
          <span className="brand-mark" aria-hidden="true"><i /></span>
          <span><strong>CORAL CITY</strong><small>RED SEA TWIN LAB</small></span>
        </button>
        <nav aria-label="Blueprint views">
          {views.map((view) => (
            <button key={view.id} className={activeView === view.id ? "active" : ""} onClick={() => setActiveView(view.id)} aria-pressed={activeView === view.id}>{view.label}</button>
          ))}
        </nav>
        <div className="active-release"><span>ACTIVE RELEASE</span><strong>{program.currentGate}</strong></div>
      </header>

      <div className="view-bar">
        <div><span>{program.version}</span><i /> <span>{program.updated}</span></div>
        <p>Standalone Coral City architecture · no external project dependency</p>
      </div>

      {activeView === "architecture" && (
        <section className="view architecture-view" aria-labelledby="architecture-title">
          <div className="view-heading">
            <div><p className="kicker">FULL SYSTEM MAP</p><h1 id="architecture-title">How Coral City fits together.</h1></div>
            <p>The applications request outcomes. Our control plane governs them. Data remains durable. Compute is replaceable. Field safety stays local.</p>
          </div>

          <div className="architecture-picture" role="img" aria-label="Coral City architecture from applications through control, data, compute, and field planes">
            {deploymentPlanes.map((plane, index) => (
              <div className="plane-row" key={plane.title}>
                <div className="plane-label"><span>{plane.number}</span><div><small>PLANE</small><strong>{plane.title}</strong></div></div>
                <div className={`plane-components plane-components-${index + 1}`}>
                  {plane.components.map((component) => <div key={component}>{component}</div>)}
                </div>
                <p>{plane.purpose}</p>
              </div>
            ))}
            <div className="architecture-spine" aria-hidden="true"><span>REQUEST</span><i>↓</i><span>GOVERN</span><i>↓</i><span>PRESERVE</span><i>↓</i><span>EXECUTE</span><i>↓</i><span>OBSERVE</span></div>
          </div>

          <div className="architecture-rules">
            <article><span>CONTROL PLANE</span><strong>Decides and records</strong><p>Identity, sites, missions, workflow state, job state, simulator sessions, policy, and provenance.</p></article>
            <article><span>DATA PLANE</span><strong>Preserves scientific truth</strong><p>Videos, reef versions, environmental fields, telemetry, results, metadata, and checksums.</p></article>
            <article><span>COMPUTE + FIELD</span><strong>Acts without owning the product</strong><p>Containers calculate, Isaac simulates, and the edge station controls the real vehicle safely.</p></article>
          </div>
        </section>
      )}

      {activeView === "product" && (
        <section className="view product-view" aria-labelledby="product-title">
          <div className="view-heading">
            <div><p className="kicker">THE PRODUCT</p><h1 id="product-title">A living Red Sea before we enter it.</h1></div>
            <p>{program.northStar}</p>
          </div>
          <div className="product-grid">
            <article className="north-star">
              <div className="reef-orbit" aria-hidden="true"><i /><i /><i /><b>AUV–01</b></div>
              <div><small>ONE CLOSED LOOP</small><h2>Observe → understand → rehearse → deploy → learn</h2><p>A real reef becomes a time-aware scientific twin. Ocean conditions drive simulation. Robots rehearse inside it. Field results return as new evidence.</p></div>
            </article>
            <article className="truth-card"><small>THE TWIN NEVER LIES ABOUT ORIGIN</small><div>{truthClasses.map((item) => <span key={item.id}>{item.label}<small>{item.detail}</small></span>)}</div></article>
          </div>
          <div className="loop-strip">{architecture.map((item) => <article key={item.id}><span>{item.number}</span><strong>{item.label}</strong><p>{item.output}</p></article>)}</div>
          <div className="reconstruction-strip">{reconstructionSteps.map(([title], index) => <span key={title}><i>{String(index + 1).padStart(2, "0")}</i>{title}</span>)}</div>
        </section>
      )}

      {activeView === "releases" && (
        <section className="view releases-view" aria-labelledby="releases-title">
          <div className="view-heading compact-heading">
            <div><p className="kicker">OPERATIONAL RELEASES</p><h1 id="releases-title">Every phase ends in a working system.</h1></div>
            <p>Technical experiments are tasks inside a release. They never count as phases.</p>
          </div>
          <div className="release-workspace">
            <div className="release-list" role="tablist" aria-label="Operational releases">
              {roadmap.map((item, index) => <button key={item.id} className={activePhase === index ? "active" : ""} onClick={() => setActivePhase(index)} role="tab" aria-selected={activePhase === index}><span>{item.number}</span><div><strong>{item.title}</strong><small>{item.horizon}</small></div><Status status={item.status} /></button>)}
            </div>
            <article className="release-detail" role="tabpanel">
              <div className="release-title"><div><p className="kicker">{phase.number} · {phase.horizon}</p><h2>{phase.title}</h2></div><Status status={phase.status} /></div>
              <div className="release-outcome"><small>WORKING SYSTEM AT THE END</small><p>{phase.outcome}</p></div>
              <div className="release-columns">
                <div><small>DELIVERABLES</small><ul>{phase.deliverables.map((item) => <li key={item}>{item}</li>)}</ul></div>
                <div><small>ACCEPTANCE TESTS</small><ul className="test-list">{phase.acceptanceTests.map((item) => <li key={item}>{item}</li>)}</ul><div className="gate"><small>RELEASE GATE</small><p>{phase.gate}</p></div></div>
              </div>
            </article>
          </div>
        </section>
      )}

      {activeView === "models" && (
        <section className="view models-view" aria-labelledby="models-title">
          <div className="view-heading compact-heading">
            <div><p className="kicker">SCIENTIFIC MODEL ENGINE</p><h1 id="models-title">Many solvers. One stable contract.</h1></div>
            <p>Models remain isolated tools. Coral City consumes versioned Environment Packages rather than model-specific internals.</p>
          </div>
          <div className="adapter-picture" role="img" aria-label="Scientific model adapter architecture">
            <article><small>MODEL RUNTIMES</small><strong>SWAN · SCHISM · WRF · OpenDrift · MITgcm · Delft3D</strong><p>Native inputs, grids, binaries, logs, and outputs.</p></article><i>→</i>
            <article className="adapter"><small>REPLACEABLE ADAPTER</small><strong>prepare · run · collect · normalize · verify</strong><p>The only model-specific Coral City code.</p></article><i>→</i>
            <article><small>ENVIRONMENT PACKAGE</small><strong>One scientific contract</strong><ul>{environmentPackage.map((item) => <li key={item}>{item}</li>)}</ul></article><i>→</i>
            <article><small>CONSUMERS</small><strong>Twin · Isaac · ROS 2 · web</strong><p>Stable units, frames, time, uncertainty, and provenance.</p></article>
          </div>
          <div className="table-wrap"><table><thead><tr><th>Model</th><th>Family</th><th>Role</th><th>Build</th><th>Release</th></tr></thead><tbody>{modelRegistry.map((model) => <tr key={model.name}><td>{model.name}</td><td>{model.family}</td><td>{model.purpose}</td><td>{model.build}</td><td>{model.phase}</td></tr>)}</tbody></table></div>
          <p className="model-note">Licence labels remain planning notes until the selected upstream release and its dependencies are independently verified.</p>
        </section>
      )}

      {activeView === "deployment" && (
        <section className="view deployment-view" aria-labelledby="deployment-title">
          <div className="view-heading compact-heading">
            <div><p className="kicker">DEPLOYMENT</p><h1 id="deployment-title">The same system from laptop to Red Sea.</h1></div>
            <p>Only the adapters and scale change. Product contracts remain stable.</p>
          </div>
          <div className="deployment-workspace">
            <div className="profile-picker" role="tablist" aria-label="Deployment profiles">{deploymentProfiles.map((item, index) => <button key={item.title} className={activeProfile === index ? "active" : ""} onClick={() => setActiveProfile(index)} role="tab" aria-selected={activeProfile === index}><small>{item.place}</small><strong>{item.title}</strong></button>)}</div>
            <article className="profile-detail" role="tabpanel"><p className="kicker">SELECTED DEPLOYMENT</p><h2>{profile.title}</h2><ul>{profile.items.map((item) => <li key={item}>{item}</li>)}</ul></article>
            <div className="job-panel"><div><p className="kicker">ONE SCIENTIFIC JOB</p><h2>An image is software. A job is a governed request.</h2><p>A digest-pinned OCI image can execute locally, in Kubernetes, or through Slurm. It writes declared outputs, exits, and never becomes the product.</p></div><ol>{jobLifecycle.map(([title, body], index) => <li key={title}><span>{String(index + 1).padStart(2, "0")}</span><div><strong>{title}</strong><p>{body}</p></div></li>)}</ol></div>
          </div>
        </section>
      )}
    </main>
  );
}
