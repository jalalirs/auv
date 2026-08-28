"use client";

import { useState } from "react";
import {
  architecture,
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

type SvgNodeProps = {
  x: number;
  y: number;
  width: number;
  height: number;
  title: string;
  detail: string;
  tone?: "control" | "data" | "compute" | "field" | "app";
};

function SvgNode({ x, y, width, height, title, detail, tone = "data" }: SvgNodeProps) {
  return (
    <g className={`diagram-node diagram-node-${tone}`}>
      <rect x={x} y={y} width={width} height={height} rx="8" />
      <text x={x + 16} y={y + 24} className="diagram-node-title">{title}</text>
      <text x={x + 16} y={y + 43} className="diagram-node-detail">{detail}</text>
    </g>
  );
}

function CoralCityArchitecture() {
  return (
    <div className="system-map-shell">
      <div className="system-map-toolbar">
        <div><span className="legend-line legend-control" />Command + governance</div>
        <div><span className="legend-line legend-data" />Scientific data</div>
        <div><span className="legend-line legend-runtime" />Jobs + simulation</div>
        <div><span className="legend-line legend-telemetry" />Telemetry + observations</div>
      </div>
      <div className="system-map-scroll">
        <svg className="system-map" viewBox="0 0 1440 850" role="img" aria-labelledby="system-map-title system-map-description">
          <title id="system-map-title">Complete Coral City system architecture</title>
          <desc id="system-map-description">Applications connect to the Coral City control plane. The control plane governs scientific data, reconstruction, ocean-model jobs, Isaac simulation, ROS 2 autonomy, and field missions. Field observations return to the durable digital twin.</desc>
          <defs>
            <marker id="arrow-control" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" /></marker>
            <marker id="arrow-data" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" /></marker>
            <marker id="arrow-runtime" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" /></marker>
            <marker id="arrow-telemetry" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" /></marker>
            <linearGradient id="twin-core" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#183f43" /><stop offset="1" stopColor="#10292f" /></linearGradient>
          </defs>

          <g className="diagram-zone zone-apps">
            <rect x="24" y="24" width="1392" height="116" rx="12" />
            <text x="46" y="50" className="zone-index">01 · EXPERIENCE PLANE</text>
            <SvgNode x={46} y={66} width={245} height={56} title="Coral City Web" detail="Sites · maps · forecasts · missions" tone="app" />
            <SvgNode x={310} y={66} width={245} height={56} title="Scientific Workspace" detail="Reconstruction · change · evidence" tone="app" />
            <SvgNode x={574} y={66} width={245} height={56} title="Isaac Streaming Client" detail="3D world · rehearsal · inspection" tone="app" />
            <SvgNode x={838} y={66} width={245} height={56} title="Field Operator Station" detail="Mission safety · vehicle status" tone="app" />
            <SvgNode x={1102} y={66} width={292} height={56} title="External Science APIs" detail="Forecasts · observations · catalogues" tone="app" />
          </g>

          <g className="diagram-zone zone-control">
            <rect x="24" y="170" width="1392" height="208" rx="12" />
            <text x="46" y="198" className="zone-index">02 · CORAL CITY CONTROL PLANE — THE PRODUCT BRAIN</text>
            <SvgNode x={46} y={218} width={212} height={62} title="Identity + API Gateway" detail="Auth · policy · stable APIs" tone="control" />
            <SvgNode x={278} y={218} width={212} height={62} title="Site + Twin Registry" detail="Sites · versions · truth classes" tone="control" />
            <SvgNode x={510} y={218} width={212} height={62} title="Mission Service" detail="Plans · constraints · approvals" tone="control" />
            <SvgNode x={742} y={218} width={212} height={62} title="Workflow Controller" detail="Pipelines · retries · state" tone="control" />
            <SvgNode x={974} y={218} width={212} height={62} title="Job + Session Manager" detail="OCI jobs · HPC · Isaac sessions" tone="control" />
            <SvgNode x={1206} y={218} width={188} height={62} title="Provenance Ledger" detail="Inputs · code · checksums" tone="control" />
            <rect x="278" y="307" width="1108" height="48" rx="8" className="twin-core" />
            <text x="298" y="328" className="diagram-node-title">DIGITAL TWIN CONTRACT</text>
            <text x="298" y="346" className="diagram-node-detail">common site ID · UTC time · EPSG frame · units · uncertainty · lineage · immutable artifact references</text>
          </g>

          <g className="diagram-zone zone-data">
            <rect x="24" y="410" width="430" height="362" rx="12" />
            <text x="46" y="438" className="zone-index">03 · SCIENTIFIC DATA PLANE</text>
            <SvgNode x={46} y={460} width={184} height={64} title="PostgreSQL + PostGIS" detail="Sites · missions · spatial metadata" tone="data" />
            <SvgNode x={248} y={460} width={184} height={64} title="Object Store" detail="Video · USD · Zarr · NetCDF · bags" tone="data" />
            <SvgNode x={46} y={544} width={184} height={64} title="Time-series Store" detail="Telemetry · Spotter · CTD · ADCP" tone="data" />
            <SvgNode x={248} y={544} width={184} height={64} title="Artifact Catalogue" detail="Versions · lineage · quality · access" tone="data" />
            <rect x="46" y="632" width="386" height="114" rx="8" className="truth-store" />
            <text x="64" y="656" className="diagram-node-title">DURABLE SCIENTIFIC TRUTH</text>
            <text x="64" y="680" className="diagram-copy">Measured reef geometry + imagery</text>
            <text x="64" y="699" className="diagram-copy">Environmental fields + forecasts</text>
            <text x="64" y="718" className="diagram-copy">Mission telemetry + derived products</text>
          </g>

          <g className="diagram-zone zone-compute">
            <rect x="484" y="410" width="606" height="362" rx="12" />
            <text x="506" y="438" className="zone-index">04 · REPLACEABLE COMPUTE + SIMULATION PLANE</text>
            <SvgNode x={506} y={460} width={176} height={66} title="3D Reconstruction" detail="COLMAP · NeRF · semantic QA" tone="compute" />
            <SvgNode x={700} y={460} width={176} height={66} title="Model Adapter SDK" detail="Prepare · run · normalize · verify" tone="compute" />
            <SvgNode x={894} y={460} width={174} height={66} title="Isaac Sim" detail="USD world · RTX sensors · PhysX" tone="compute" />
            <rect x="506" y="552" width="370" height="106" rx="8" className="runtime-cluster" />
            <text x="524" y="576" className="diagram-node-title">OCI / KUBERNETES / SLURM / HPC</text>
            <text x="524" y="600" className="diagram-copy">WRF · SWAN · WAVEWATCH III · SCHISM</text>
            <text x="524" y="619" className="diagram-copy">OpenDrift · GOTM/FABM/ERSEM · MITgcm</text>
            <text x="524" y="638" className="diagram-copy">ADCIRC · HYSPLIT · Delft3D</text>
            <SvgNode x={894} y={552} width={174} height={106} title="ROS 2 Autonomy Lab" detail="Perception · SLAM · planning · control · swarm" tone="compute" />
            <rect x="506" y="683" width="562" height="63" rx="8" className="environment-package" />
            <text x="524" y="707" className="diagram-node-title">VERSIONED ENVIRONMENT PACKAGE</text>
            <text x="524" y="727" className="diagram-node-detail">currents · waves · wind · temperature · visibility · uncertainty → Isaac + ROS 2 + web</text>
          </g>

          <g className="diagram-zone zone-field">
            <rect x="1120" y="410" width="296" height="362" rx="12" />
            <text x="1142" y="438" className="zone-index">05 · FIELD + EDGE PLANE</text>
            <SvgNode x={1142} y={460} width={252} height={66} title="Edge Mission Station" detail="Offline-first · safety authority · sync" tone="field" />
            <SvgNode x={1142} y={548} width={252} height={66} title="AUV / ROV / Surface Robot" detail="Cameras · sonar · DVL · IMU · CTD" tone="field" />
            <SvgNode x={1142} y={636} width={120} height={84} title="Fixed Sensors" detail="ADCP · reef stations" tone="field" />
            <SvgNode x={1274} y={636} width={120} height={84} title="Metocean" detail="Spotter · wind · satellite" tone="field" />
          </g>

          <g className="diagram-flows">
            <path className="flow-control" d="M 169 122 V 218" />
            <path className="flow-control" d="M 432 122 V 202 H 152 V 218" />
            <path className="flow-control" d="M 696 122 V 202 H 152" />
            <path className="flow-control" d="M 960 122 V 202 H 152" />
            <path className="flow-data" d="M 1248 122 V 154 H 384 V 218" />
            <path className="flow-control" d="M 258 249 H 278" />
            <path className="flow-control" d="M 490 249 H 510" />
            <path className="flow-control" d="M 722 249 H 742" />
            <path className="flow-control" d="M 954 249 H 974" />
            <path className="flow-control" d="M 1186 249 H 1206" />
            <path className="flow-data" d="M 384 355 V 392 H 239 V 460" />
            <path className="flow-runtime" d="M 848 355 V 392 H 788 V 460" />
            <path className="flow-runtime" d="M 1080 355 V 392 H 981 V 460" />
            <path className="flow-control" d="M 1080 280 V 390 H 1268 V 460" />
            <path className="flow-data" d="M 454 690 H 484" />
            <path className="flow-data" d="M 484 714 H 454" />
            <path className="flow-runtime" d="M 876 605 H 894" />
            <path className="flow-telemetry" d="M 1120 680 H 1090 V 714 H 1068" />
            <path className="flow-runtime" d="M 1090 714 H 1120 V 493 H 1142" />
            <path className="flow-control" d="M 1268 526 V 548" />
            <path className="flow-telemetry" d="M 1268 614 V 628 H 1202 V 636" />
            <path className="flow-telemetry" d="M 1268 628 H 1334 V 636" />
            <path className="flow-telemetry" d="M 1142 590 H 1106 V 790 H 238 V 746" />
          </g>

          <g className="loop-caption">
            <rect x="24" y="800" width="1392" height="34" rx="8" />
            <text x="44" y="822">OBSERVE → RECONSTRUCT → ASSIMILATE → PREDICT → SIMULATE → PLAN → DEPLOY → OBSERVE AGAIN</text>
          </g>
        </svg>
      </div>
    </div>
  );
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

          <CoralCityArchitecture />
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
