// What flies the vehicle, other than you.
//
// The controllers this institution has deployed, newest first: each an image
// pinned by digest, with what it needs of a machine, and every build it has
// had folded under one row — a dive pins a build, a person thinks in
// controllers. A stack is what a dive
// is defined with on the dive page; deploying one is the SDK's job, from a
// terminal, because a build is a build.

import type { Held } from "./Deck.js";
import { Empty, PageHead, Pill, ago } from "./parts.js";

export function Autonomy({ held }: { held: Held }): React.JSX.Element {
  return (
    <>
      <PageHead title="Autonomy"
        says="Your controllers, in containers, pinned by digest. Each talks ROS 2 to the vehicle exactly as it would to a real one and imports nothing of ours — the same binary should run in a tank and in the sea." />

      <section>
        <h2>Deployed to {held.institution?.name ?? "your institution"}</h2>
        {held.controllers.length === 0 ? (
          <Empty title="Nothing deployed yet">
            Write a controller against the SDK and deploy it with <code>coral-city deploy</code>; it appears here and on the dive page.
          </Empty>
        ) : (
          <div className="ledger">
            {held.controllers.map(({ slug, name, newest, builds }) => {
              const needs = (newest.needs ?? {}) as { gpu?: boolean; gpuMemoryBytes?: number; cpu?: number; memoryBytes?: number };
              const card = needs.gpu || newest.wantsGpu
                ? `${needs.gpuMemoryBytes ? (needs.gpuMemoryBytes / 2 ** 30).toFixed(0) + " GiB of a card" : "a card"}`
                : "no card";
              return (
                <div className="row" key={slug}>
                  <strong>{name}</strong>
                  <span className="when">
                    {slug} · {newest.imageDigest.slice(7, 19)} · {ago(newest.createdAt)}
                    {builds.length > 1 ? ` · ${builds.length} builds` : ""}
                  </span>
                  <Pill kind={needs.gpu || newest.wantsGpu ? "busy" : undefined}>{card}</Pill>
                </div>
              );
            })}
          </div>
        )}
      </section>

      <section>
        <h2>Deploying one</h2>
        <Empty title="From the SDK" soon="one command">
          <code>pip install -e packages/sdk-python</code>, write a class against <code>coral_city.Controller</code>,
          try it in the tank with <code>coral-city tank</code>, then <code>coral-city deploy your.py --slug name</code>.
          A controller that is a model says what it needs with <code>--gpu-memory 8G</code>, and the scheduler places the dive where both it and the simulator fit.
        </Empty>
      </section>
    </>
  );
}
