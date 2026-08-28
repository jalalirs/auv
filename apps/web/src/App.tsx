import { useState } from "react";
import { type PlatformState, usePlatform } from "./platform";

const areas = [
  {
    id: "atlas",
    number: "01",
    name: "Reef Atlas",
    eyebrow: "Measured place",
    description:
      "Versioned 3D reef surveys at real scale, joined to source evidence and reconstruction quality.",
    empty: "No reef survey source is connected.",
  },
  {
    id: "environment",
    number: "02",
    name: "Environment",
    eyebrow: "Ocean state",
    description:
      "Observations, analyses, forecasts, and scenarios aligned in space, depth, and time.",
    empty: "No environmental feed is connected.",
  },
  {
    id: "simulation",
    number: "03",
    name: "Simulation",
    eyebrow: "Rehearsal space",
    description:
      "Allocated Isaac Sim sessions where vehicles and sensors operate inside a versioned twin.",
    empty: "No simulator session has been allocated.",
  },
  {
    id: "missions",
    number: "04",
    name: "Missions",
    eyebrow: "Evidence loop",
    description:
      "Design, evaluate, approve, deploy, and recover autonomous missions without losing provenance.",
    empty: "No mission source is connected.",
  },
] as const;

type AreaID = (typeof areas)[number]["id"];

export function App() {
  const platform = usePlatform();
  const [activeArea, setActiveArea] = useState<AreaID>("atlas");
  const selectedArea = areas.find((area) => area.id === activeArea) ?? areas[0];

  return (
    <div className="app-shell">
      <header className="topbar">
        <a className="brand" href="#top" aria-label="Coral City home">
          <span className="brand-mark" aria-hidden="true">
            CC
          </span>
          <span>
            <strong>Coral City</strong>
            <small>Red Sea digital twin</small>
          </span>
        </a>
        <PlatformBadge state={platform} />
      </header>

      <main id="top">
        <section className="hero" aria-labelledby="hero-title">
          <div className="hero-copy">
            <p className="kicker">Observe · understand · rehearse · return</p>
            <h1 id="hero-title">
              One living record of a reef—and every decision made around it.
            </h1>
            <p className="hero-summary">
              Coral City connects measured reef geometry, ocean conditions,
              scientific models, and autonomous marine systems without confusing
              observations, predictions, and simulations.
            </p>
          </div>
          <div className="hero-orbit" aria-hidden="true">
            <div className="orbit orbit-outer" />
            <div className="orbit orbit-inner" />
            <div className="reef-form reef-one" />
            <div className="reef-form reef-two" />
            <span className="coordinate">22.30° N · 38.96° E</span>
          </div>
        </section>

        <section className="workspace" aria-labelledby="workspace-title">
          <div className="section-heading">
            <div>
              <p className="kicker">Platform map</p>
              <h2 id="workspace-title">Four views of the same evidence</h2>
            </div>
            <p>
              Each area has a clear boundary. Nothing shown here is synthetic
              product data.
            </p>
          </div>

          <div className="area-layout">
            <nav className="area-tabs" aria-label="Coral City areas">
              {areas.map((area) => (
                <button
                  className={area.id === activeArea ? "area-tab active" : "area-tab"}
                  key={area.id}
                  onClick={() => setActiveArea(area.id)}
                  type="button"
                  aria-pressed={area.id === activeArea}
                >
                  <span>{area.number}</span>
                  {area.name}
                </button>
              ))}
            </nav>

            <article className="area-panel" aria-live="polite">
              <p className="area-eyebrow">{selectedArea.eyebrow}</p>
              <h3>{selectedArea.name}</h3>
              <p className="area-description">{selectedArea.description}</p>
              <div className="empty-state">
                <span className="empty-pulse" aria-hidden="true" />
                <div>
                  <strong>Awaiting a real source</strong>
                  <p>{selectedArea.empty}</p>
                </div>
              </div>
            </article>
          </div>
        </section>

        <section className="flow" aria-labelledby="flow-title">
          <p className="kicker">The evidence loop</p>
          <h2 id="flow-title">A twin that becomes more truthful after every mission</h2>
          <ol>
            {[
              ["Observe", "Survey and sensor evidence enters unchanged."],
              ["Version", "Every source, transform, and uncertainty is recorded."],
              ["Predict", "Models produce named forecasts and scenarios."],
              ["Rehearse", "Robots are evaluated in the selected twin state."],
              ["Return", "Field observations become the next evidence version."],
            ].map(([title, detail], index) => (
              <li key={title}>
                <span>{String(index + 1).padStart(2, "0")}</span>
                <strong>{title}</strong>
                <p>{detail}</p>
              </li>
            ))}
          </ol>
        </section>
      </main>

      <footer>
        <span>Coral City · engineering foundation R0</span>
        <span>Truth before spectacle</span>
      </footer>
    </div>
  );
}

function PlatformBadge({ state }: { state: PlatformState }) {
  if (state.status === "loading") {
    return (
      <div className="platform-badge loading" role="status">
        <span /> Checking platform
      </div>
    );
  }

  if (state.status === "disconnected") {
    return (
      <div className="platform-badge disconnected" role="status">
        <span /> Control plane unavailable
      </div>
    );
  }

  return (
    <div className="platform-badge connected" role="status">
      <span /> {state.info.service} · {state.info.version}
    </div>
  );
}
